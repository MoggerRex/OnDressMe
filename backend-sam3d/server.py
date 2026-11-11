import io
import logging
import os
import shutil
import sys
import tempfile
import torch
import trimesh
import numpy as np
import cv2
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

# Agregar el repositorio clonado al PATH de Python
repo_path = os.path.join(os.path.dirname(__file__), "sam-3d-body")
sys.path.append(repo_path)

from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body_hf

app = FastAPI(title="OnDressMe 3D Generation Server")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if not torch.cuda.is_available():
    raise RuntimeError("SAM 3D Body requiere una GPU CUDA disponible.")

print("Cargando el modelo SAM 3D Body desde Hugging Face...")
try:
    network, model_cfg = load_sam_3d_body_hf(
        "facebook/sam-3d-body-vith",
        device="cuda",
    )
    estimator = SAM3DBodyEstimator(
        sam_3d_body_model=network,
        model_cfg=model_cfg,
    )
    print("¡Modelo SAM 3D Body cargado exitosamente en VRAM!")
except Exception as e:
    logger.exception("Error al cargar el modelo SAM 3D Body.")
    raise RuntimeError("No se pudo inicializar SAM 3D Body.") from e


def estimate_skin_color(image: np.ndarray) -> np.ndarray:
    height, width, _ = image.shape
    face_region = image[
        int(height * 0.18):int(height * 0.30),
        int(width * 0.40):int(width * 0.60),
    ]

    hsv = cv2.cvtColor(face_region, cv2.COLOR_RGB2HSV)
    ycrcb = cv2.cvtColor(face_region, cv2.COLOR_RGB2YCrCb)
    hue, saturation, value = cv2.split(hsv)
    _, cr, cb = cv2.split(ycrcb)
    skin_mask = (
        ((hue <= 25) | (hue >= 170))
        & (saturation >= 30)
        & (value >= 40)
        & (cr >= 133)
        & (cr <= 173)
        & (cb >= 77)
        & (cb <= 127)
    )
    skin_pixels = face_region[skin_mask]

    if len(skin_pixels) == 0:
        logger.warning("No se pudo estimar el tono de piel; se usará un tono neutro.")
        return np.array([180, 130, 110], dtype=np.uint8)

    return np.median(skin_pixels, axis=0).astype(np.uint8)


def extract_garment_mask(garment_pixels: np.ndarray) -> np.ndarray:
    if garment_pixels.ndim != 3 or garment_pixels.shape[2] != 4:
        raise ValueError("La imagen de la prenda debe contener píxeles RGBA.")

    alpha = garment_pixels[:, :, 3]
    if np.any(alpha < 255):
        garment_mask = alpha > 16
    else:
        image_height, image_width = alpha.shape
        if image_height < 5 or image_width < 5:
            raise ValueError("La imagen de la prenda es demasiado pequeña.")

        grabcut_mask = np.zeros((image_height, image_width), dtype=np.uint8)
        background_model = np.zeros((1, 65), dtype=np.float64)
        foreground_model = np.zeros((1, 65), dtype=np.float64)
        rectangle = (
            int(image_width * 0.05),
            int(image_height * 0.05),
            int(image_width * 0.90),
            int(image_height * 0.90),
        )
        try:
            cv2.grabCut(
                cv2.cvtColor(garment_pixels[:, :, :3], cv2.COLOR_RGB2BGR),
                grabcut_mask,
                rectangle,
                background_model,
                foreground_model,
                8,
                cv2.GC_INIT_WITH_RECT,
            )
        except cv2.error as error:
            raise ValueError(
                "No se pudo separar la prenda del fondo; usa una imagen con "
                "fondo transparente o con más contraste."
            ) from error

        garment_mask = np.isin(
            grabcut_mask,
            (cv2.GC_FGD, cv2.GC_PR_FGD),
        )

    component_count, labels, component_stats, _ = cv2.connectedComponentsWithStats(
        garment_mask.astype(np.uint8),
        connectivity=8,
    )
    if component_count <= 1:
        raise ValueError("No se detectó una prenda en la imagen.")

    largest_component = 1 + int(np.argmax(component_stats[1:, cv2.CC_STAT_AREA]))
    garment_mask = labels == largest_component
    garment_mask = cv2.morphologyEx(
        garment_mask.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
    ).astype(bool)
    foreground_ratio = float(np.mean(garment_mask))
    if foreground_ratio < 0.02 or foreground_ratio > 0.90:
        raise ValueError(
            "No se pudo identificar la silueta de la prenda. "
            "Prueba con fondo transparente o con más contraste."
        )

    return garment_mask


def orient_body_vertices(vertices: np.ndarray) -> np.ndarray:
    oriented_vertices = np.asarray(vertices, dtype=np.float64).copy()
    if (
        oriented_vertices.ndim != 2
        or oriented_vertices.shape[1] != 3
        or len(oriented_vertices) == 0
        or not np.isfinite(oriented_vertices).all()
    ):
        raise ValueError("SAM 3D Body devolvió vértices inválidos.")

    oriented_vertices[:, 1:] *= -1
    bounds = np.vstack(
        (oriented_vertices.min(axis=0), oriented_vertices.max(axis=0))
    )
    center = bounds.mean(axis=0)
    oriented_vertices[:, 0] -= center[0]
    oriented_vertices[:, 1] -= bounds[0, 1]
    oriented_vertices[:, 2] -= center[2]
    return oriented_vertices


def build_garment_shell(
    body_bytes: bytes,
    garment_pixels: np.ndarray,
    garment_mask: np.ndarray,
) -> tuple[trimesh.Scene, str]:
    if not body_bytes.startswith(b"glTF"):
        raise ValueError("El cuerpo seleccionado no es un archivo GLB válido.")

    try:
        body_mesh = trimesh.load(
            io.BytesIO(body_bytes),
            file_type="glb",
            force="mesh",
        )
    except Exception as error:
        raise ValueError(
            "No se pudo cargar la malla GLB del cuerpo seleccionado."
        ) from error

    if not isinstance(body_mesh, trimesh.Trimesh):
        raise ValueError("El archivo del cuerpo no contiene una malla 3D válida.")

    vertices = np.asarray(body_mesh.vertices, dtype=np.float64)
    faces = np.asarray(body_mesh.faces, dtype=np.int64)
    if (
        vertices.ndim != 2
        or vertices.shape[1] != 3
        or len(vertices) == 0
        or faces.ndim != 2
        or faces.shape[1] != 3
        or len(faces) == 0
        or not np.isfinite(vertices).all()
    ):
        raise ValueError("La malla del cuerpo no contiene vértices y caras válidos.")

    # La dimensión más larga identifica la altura en un cuerpo de pie.
    vertical_axis = int(np.argmax(np.ptp(vertices, axis=0)))
    body_height = np.ptp(vertices[:, vertical_axis])
    if body_height <= 0:
        raise ValueError("No se pudo determinar la altura del cuerpo.")

    image_height, image_width = garment_pixels.shape[:2]
    if (
        image_height == 0
        or image_width == 0
        or garment_mask.shape != (image_height, image_width)
    ):
        raise ValueError("La máscara de la prenda no coincide con su imagen.")

    mask_y, mask_x = np.nonzero(garment_mask)
    if len(mask_x) == 0:
        raise ValueError("No se detectó una prenda en la imagen.")
    mask_left, mask_right = mask_x.min(), mask_x.max()
    mask_top, mask_bottom = mask_y.min(), mask_y.max()
    mask_width = mask_right - mask_left + 1
    mask_height = mask_bottom - mask_top + 1

    center_strip_start = int(mask_left + mask_width * 0.46)
    center_strip_end = max(
        center_strip_start + 1,
        int(mask_left + mask_width * 0.54),
    )
    lower_region_start = int(mask_top + mask_height * 0.45)
    lower_center_strip = garment_mask[
        lower_region_start:mask_bottom + 1,
        center_strip_start:center_strip_end,
    ]
    center_gap_ratio = float(
        np.mean(~np.any(lower_center_strip, axis=1))
    )
    aspect_ratio = mask_width / mask_height
    garment_type = (
        "pants"
        if aspect_ratio < 0.82 or center_gap_ratio > 0.25
        else "shirt"
    )
    template_names = {
        "shirt": ("camisa.glb", "base_camisa.glb", "base_shirt.glb"),
        "pants": ("jeans.glb", "base_jeans.glb", "base_pants.glb"),
    }
    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    template_path = next(
        (
            os.path.join(templates_dir, name)
            for name in template_names[garment_type]
            if os.path.isfile(os.path.join(templates_dir, name))
        ),
        None,
    )
    if template_path is None:
        expected_names = ", ".join(template_names[garment_type])
        raise FileNotFoundError(
            f"No se encontró la plantilla de {garment_type} en "
            f"'{templates_dir}'. Nombres admitidos: {expected_names}."
        )

    try:
        garment_mesh = trimesh.load(template_path, force="mesh")
    except Exception as error:
        raise ValueError(
            f"No se pudo cargar la plantilla 3D '{template_path}'."
        ) from error

    if not isinstance(garment_mesh, trimesh.Trimesh):
        raise ValueError(
            f"La plantilla '{template_path}' no contiene una malla 3D válida."
        )

    template_vertices = np.asarray(garment_mesh.vertices, dtype=np.float64)
    template_faces = np.asarray(garment_mesh.faces, dtype=np.int64)
    if (
        template_vertices.ndim != 2
        or template_vertices.shape[1] != 3
        or len(template_vertices) == 0
        or template_faces.ndim != 2
        or template_faces.shape[1] != 3
        or len(template_faces) == 0
        or not np.isfinite(template_vertices).all()
    ):
        raise ValueError(
            f"La plantilla '{template_path}' no contiene geometría válida."
        )

    body_height_min = vertices[:, vertical_axis].min()
    if garment_type == "shirt":
        template_height = float(np.ptp(template_vertices[:, vertical_axis]))
        shirt_height_ratio = float(
            np.clip(template_height / body_height, 0.30, 0.45)
        )
        shirt_center_from_top = 0.34
        band_top_fraction = shirt_center_from_top - shirt_height_ratio / 2
        band_bottom_fraction = shirt_center_from_top + shirt_height_ratio / 2
        height_range = (
            1.0 - band_bottom_fraction,
            1.0 - band_top_fraction,
        )
    else:
        height_range = (0.03, 0.55)

    body_band_vertex_mask = (
        (
            vertices[:, vertical_axis]
            >= body_height_min + body_height * height_range[0]
        )
        & (
            vertices[:, vertical_axis]
            <= body_height_min + body_height * height_range[1]
        )
    )
    body_band_faces = faces[np.all(body_band_vertex_mask[faces], axis=1)]
    if len(body_band_faces) == 0:
        raise ValueError(
            f"No se encontraron caras del cuerpo en la zona de {garment_type}."
        )

    band_vertex_indices = np.unique(body_band_faces)
    body_region_vertices = vertices[band_vertex_indices]
    body_bounds = np.vstack(
        (body_region_vertices.min(axis=0), body_region_vertices.max(axis=0))
    )
    body_extents = np.ptp(body_bounds, axis=0)
    remaining_axes = [axis for axis in range(3) if axis != vertical_axis]
    clearance_distance = 0.03 * float(np.mean(body_extents[remaining_axes]))
    if clearance_distance <= 0:
        raise ValueError("No se pudo calcular la holgura de la prenda.")

    normals = np.asarray(body_mesh.vertex_normals, dtype=np.float64)[
        band_vertex_indices
    ]
    normal_lengths = np.linalg.norm(normals, axis=1)
    if not np.isfinite(normals).all() or np.any(normal_lengths <= 1e-8):
        raise ValueError("La malla del cuerpo tiene normales inválidas en el torso.")

    garment_vertices = body_region_vertices + (
        normals / normal_lengths[:, np.newaxis]
    ) * clearance_distance
    vertex_remap = np.full(len(vertices), -1, dtype=np.int64)
    vertex_remap[band_vertex_indices] = np.arange(len(band_vertex_indices))
    garment_faces = vertex_remap[body_band_faces]
    lateral_axis = max(remaining_axes, key=lambda axis: body_extents[axis])
    image_u = (
        body_region_vertices[:, lateral_axis] - body_bounds[0, lateral_axis]
    ) / body_extents[lateral_axis]
    image_v = (
        body_region_vertices[:, vertical_axis] - body_bounds[0, vertical_axis]
    ) / body_extents[vertical_axis]
    garment_uv = np.column_stack((image_u, image_v))

    body_center = body_bounds.mean(axis=0)

    texture_padding = max(1, int(round(max(mask_width, mask_height) * 0.02)))
    texture_left = max(0, mask_left - texture_padding)
    texture_top = max(0, mask_top - texture_padding)
    texture_right = min(image_width, mask_right + texture_padding + 1)
    texture_bottom = min(image_height, mask_bottom + texture_padding + 1)
    texture_pixels = garment_pixels[
        texture_top:texture_bottom,
        texture_left:texture_right,
    ].copy()
    texture_mask = garment_mask[
        texture_top:texture_bottom,
        texture_left:texture_right,
    ]
    _, nearest_foreground = cv2.distanceTransformWithLabels(
        (~texture_mask).astype(np.uint8),
        cv2.DIST_L2,
        5,
        labelType=cv2.DIST_LABEL_PIXEL,
    )
    foreground_y, foreground_x = np.nonzero(texture_mask)
    foreground_labels = nearest_foreground[foreground_y, foreground_x]
    color_by_label = np.zeros(
        (int(nearest_foreground.max()) + 1, 3),
        dtype=np.uint8,
    )
    color_by_label[foreground_labels] = texture_pixels[
        foreground_y,
        foreground_x,
        :3,
    ]
    texture_pixels[:, :, :3] = color_by_label[nearest_foreground]
    texture_pixels[:, :, 3] = 255
    texture_image = Image.fromarray(texture_pixels)
    material = trimesh.visual.material.PBRMaterial(
        baseColorTexture=texture_image,
        baseColorFactor=[255, 255, 255, 255],
        alphaMode="OPAQUE",
    )
    garment_result = trimesh.Trimesh(
        vertices=garment_vertices - body_center,
        faces=garment_faces,
        process=False,
    )
    garment_result.visual = trimesh.visual.TextureVisuals(
        uv=garment_uv,
        material=material,
    )
    garment_result.vertex_normals

    garment_scene = trimesh.Scene()
    garment_scene.add_geometry(
        garment_result,
        node_name="fitted_garment",
        geom_name="fitted_garment",
        transform=trimesh.transformations.translation_matrix(body_center),
    )
    return garment_scene, garment_type


@app.post("/generate-3d")
async def generate_3d(image: UploadFile = File(...)):
    output_dir = None
    try:
        img_bytes = await image.read()
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        with torch.inference_mode():
            outputs = estimator.process_one_image(np.asarray(img))

        if not outputs:
            raise HTTPException(
                status_code=422,
                detail="SAM 3D Body no encontró una persona en la imagen.",
            )

        vertices = orient_body_vertices(outputs[0]["pred_vertices"])
        faces = estimator.faces

        img_array = np.array(img)
        skin_color = estimate_skin_color(img_array)
        vertex_colors = np.empty((len(vertices), 4), dtype=np.uint8)
        vertex_colors[:, :3] = skin_color
        vertex_colors[:, 3] = 255

        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        mesh.visual.vertex_colors = vertex_colors

        output_dir = tempfile.mkdtemp(prefix="sam3d-body-")
        output_path = os.path.join(output_dir, "avatar_output.glb")
        mesh.export(output_path, include_normals=True)

        return FileResponse(
            output_path,
            media_type="model/gltf-binary",
            filename="avatar_output.glb",
            background=BackgroundTask(shutil.rmtree, output_dir),
        )
    except HTTPException:
        if output_dir and os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        raise
    except Exception as e:
        if output_dir and os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        logger.exception("Error procesando la imagen.")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate-cloth")
async def generate_cloth(
    garment_image: UploadFile = File(...),
    body_glb: UploadFile = File(...),
):
    output_dir = None
    try:
        image_bytes = await garment_image.read()
        try:
            garment = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        except (OSError, ValueError) as e:
            raise HTTPException(
                status_code=422,
                detail="El archivo no es una imagen válida.",
            ) from e

        body_bytes = await body_glb.read()
        garment_pixels = np.asarray(garment, dtype=np.uint8)
        garment_mask = await run_in_threadpool(
            extract_garment_mask,
            garment_pixels,
        )
        garment_scene, garment_type = await run_in_threadpool(
            build_garment_shell,
            body_bytes,
            garment_pixels,
            garment_mask,
        )
        logger.info("Prenda detectada como %s.", garment_type)

        output_dir = tempfile.mkdtemp(prefix="sam3d-cloth-")
        output_path = os.path.join(output_dir, "prenda_fit.glb")
        garment_scene.export(output_path, include_normals=True)
        return FileResponse(
            output_path,
            media_type="model/gltf-binary",
            filename="prenda_fit.glb",
            background=BackgroundTask(shutil.rmtree, output_dir),
        )
    except HTTPException:
        raise
    except ValueError as e:
        if output_dir and os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        if output_dir and os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        logger.exception("Error generando la prenda sobre el cuerpo seleccionado.")
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo generar la prenda ajustada al cuerpo: {e}",
        ) from e