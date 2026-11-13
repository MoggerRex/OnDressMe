import io
import logging
import os
import shutil
import sys
import tempfile
import threading
import uuid
from collections import OrderedDict
import torch
import trimesh
import numpy as np
import cv2
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image
from starlette.concurrency import run_in_threadpool
from starlette.background import BackgroundTask

# Agregar el repositorio clonado al PATH de Python
repo_path = os.path.join(os.path.dirname(__file__), "sam-3d-body")
sys.path.append(repo_path)

from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body_hf
from sam_3d_body.metadata.mhr70 import mhr_names
from services.blender_simulator import GarmentSimulationError
from services.garment_pipeline import (
    GarmentPipelineError,
    MAX_GARMENT_MESH_BYTES,
    SUPPORTED_GARMENT_TYPES,
)
from services.garment_library import (
    GarmentLibraryError,
    body_fingerprint,
    get_garment,
    list_garments,
    process_or_reuse_garment,
)

app = FastAPI(title="OnDressMe 3D Generation Server")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://[::1]:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Avatar-Id",
        "X-Pipeline-Info",
        "X-Garment-Id",
        "X-Garment-Cached",
    ],
)

_MAX_CACHED_AVATARS = 3
_avatar_cache: OrderedDict[
    str, tuple[trimesh.Trimesh, dict[str, np.ndarray]]
] = OrderedDict()
_avatar_cache_lock = threading.Lock()


def _remember_avatar(
    vertices: np.ndarray,
    faces: np.ndarray,
    landmarks: dict[str, np.ndarray],
) -> str:
    avatar_id = uuid.uuid4().hex
    body_mesh = trimesh.Trimesh(
        vertices=vertices.copy(),
        faces=faces.copy(),
        process=False,
    )
    body_landmarks = {
        name: np.asarray(point, dtype=np.float64).copy()
        for name, point in landmarks.items()
    }
    with _avatar_cache_lock:
        _avatar_cache[avatar_id] = (body_mesh, body_landmarks)
        while len(_avatar_cache) > _MAX_CACHED_AVATARS:
            _avatar_cache.popitem(last=False)
    return avatar_id


def _cached_avatar(avatar_id: str):
    with _avatar_cache_lock:
        cached_avatar = _avatar_cache.get(avatar_id)
        if cached_avatar is None:
            return None, None
        body_mesh = cached_avatar[0].copy()
        body_landmarks = {
            name: point.copy()
            for name, point in cached_avatar[1].items()
        }
    return body_mesh, body_landmarks


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


def orient_body_keypoints(
    keypoints: np.ndarray,
    raw_body_vertices: np.ndarray,
) -> np.ndarray:
    oriented_keypoints = np.asarray(keypoints, dtype=np.float64).copy()
    raw_vertices = np.asarray(raw_body_vertices, dtype=np.float64)
    if (
        oriented_keypoints.ndim != 2
        or oriented_keypoints.shape[1] != 3
        or not np.isfinite(oriented_keypoints).all()
    ):
        raise ValueError("SAM 3D Body devolvió puntos articulares inválidos.")

    raw_vertices = raw_vertices.copy()
    raw_vertices[:, 1:] *= -1
    bounds = np.vstack((raw_vertices.min(axis=0), raw_vertices.max(axis=0)))
    center = bounds.mean(axis=0)
    oriented_keypoints[:, 1:] *= -1
    oriented_keypoints[:, 0] -= center[0]
    oriented_keypoints[:, 1] -= bounds[0, 1]
    oriented_keypoints[:, 2] -= center[2]
    return oriented_keypoints


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
        keypoints = orient_body_keypoints(
            outputs[0]["pred_keypoints_3d"],
            outputs[0]["pred_vertices"],
        )
        landmark_names = (
            "left-hip",
            "right-hip",
            "left-knee",
            "right-knee",
            "left-ankle",
            "right-ankle",
            "nose",
            "neck",
        )
        body_landmarks = {
            name: keypoints[mhr_names.index(name)]
            for name in landmark_names
        }

        img_array = np.array(img)
        skin_color = estimate_skin_color(img_array)
        vertex_colors = np.empty((len(vertices), 4), dtype=np.uint8)
        vertex_colors[:, :3] = skin_color
        vertex_colors[:, 3] = 255

        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        mesh.visual.vertex_colors = vertex_colors
        avatar_id = _remember_avatar(vertices, faces, body_landmarks)

        output_dir = tempfile.mkdtemp(prefix="sam3d-body-")
        output_path = os.path.join(output_dir, "avatar_output.glb")
        mesh.export(output_path, include_normals=True)

        return FileResponse(
            output_path,
            media_type="model/gltf-binary",
            filename="avatar_output.glb",
            headers={"X-Avatar-Id": avatar_id},
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


@app.post("/generate-garment")
async def generate_garment(
    garment_mesh: UploadFile | None = File(default=None),
    avatar_id: str = Form(...),
    garment_type: str = Form(default="tshirt"),
    image: UploadFile | None = File(default=None),
):
    try:
        if image is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Una foto no proporciona la geometría necesaria para simular tela. "
                    "Sube una malla GLB/OBJ ya reconstruida; Garment3DGen requiere "
                    "una malla base y una malla objetivo, normalmente generada con InstantMesh."
                ),
            )
        if garment_mesh is None:
            raise HTTPException(
                status_code=422,
                detail="Falta la malla 3D de la prenda (archivo GLB u OBJ).",
            )

        garment_type = garment_type.strip().lower()
        if garment_type not in SUPPORTED_GARMENT_TYPES:
            raise HTTPException(
                status_code=422,
                detail="Tipo de prenda no admitido. Usa 'tshirt' o 'pants'.",
            )

        body_mesh, body_landmarks = _cached_avatar(avatar_id)
        if body_mesh is None or body_landmarks is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No se encontró ese cuerpo SAM 3D. Genera el maniquí de nuevo "
                    "si reiniciaste el backend o creaste otro cuerpo."
                ),
            )

        mesh_bytes = await garment_mesh.read(MAX_GARMENT_MESH_BYTES + 1)
        if len(mesh_bytes) > MAX_GARMENT_MESH_BYTES:
            raise HTTPException(
                status_code=413,
                detail="La malla de prenda supera el límite de 64 MB.",
            )

        result = await run_in_threadpool(
            process_or_reuse_garment,
            body_mesh,
            body_landmarks,
            mesh_bytes,
            garment_mesh.filename or "",
            garment_type,
        )

        return FileResponse(
            result.file_path,
            media_type="model/gltf-binary",
            filename=result.item["download_filename"],
            headers={
                "X-Pipeline-Info": result.pipeline_info,
                "X-Garment-Id": result.item["id"],
                "X-Garment-Cached": str(result.cached).lower(),
            },
        )
    except HTTPException:
        raise
    except GarmentPipelineError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except GarmentSimulationError as error:
        logger.exception("No se pudo completar la simulación de la prenda.")
        raise HTTPException(status_code=503, detail=str(error)) from error
    except GarmentLibraryError as error:
        logger.exception("No se pudo guardar o reutilizar la prenda.")
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        logger.exception("Error procesando la prenda.")
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/wardrobe/{avatar_id}")
async def get_wardrobe(avatar_id: str):
    body_mesh, body_landmarks = _cached_avatar(avatar_id)
    if body_mesh is None or body_landmarks is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No se encontró ese cuerpo SAM 3D. Genera el maniquí de nuevo "
                "si reiniciaste el backend o creaste otro cuerpo."
            ),
        )
    try:
        body_id = await run_in_threadpool(
            body_fingerprint,
            body_mesh,
            body_landmarks,
        )
        items = await run_in_threadpool(list_garments, body_id)
        return {"items": items}
    except GarmentLibraryError as error:
        logger.exception("No se pudo consultar la biblioteca local de prendas.")
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.get("/wardrobe/{avatar_id}/{item_id}/model")
async def get_wardrobe_model(avatar_id: str, item_id: str):
    body_mesh, body_landmarks = _cached_avatar(avatar_id)
    if body_mesh is None or body_landmarks is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No se encontró ese cuerpo SAM 3D. Genera el maniquí de nuevo "
                "si reiniciaste el backend o creaste otro cuerpo."
            ),
        )
    try:
        body_id = await run_in_threadpool(
            body_fingerprint,
            body_mesh,
            body_landmarks,
        )
        garment = await run_in_threadpool(get_garment, body_id, item_id)
        if garment is None:
            raise HTTPException(
                status_code=404,
                detail="La prenda no pertenece a la biblioteca de este maniquí.",
            )
        item, file_path = garment
        return FileResponse(
            file_path,
            media_type="model/gltf-binary",
            filename=item["download_filename"],
        )
    except HTTPException:
        raise
    except GarmentLibraryError as error:
        logger.exception("No se pudo cargar la prenda de la biblioteca.")
        raise HTTPException(status_code=500, detail=str(error)) from error