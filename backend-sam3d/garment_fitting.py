import io
import os

import cv2
import numpy as np
import trimesh
from PIL import Image
from scipy.spatial import cKDTree


GARMENT_TEMPLATES = {
    "shirt": ("base_shirt.glb",),
    "pants": ("jeans.glb", "base_jeans.glb", "base_pants.glb"),
}
BODY_HEIGHT_RANGES = {
    "shirt": (0.50, 0.85),
    "pants": (0.03, 0.55),
}


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


def classify_garment(garment_mask: np.ndarray) -> str:
    mask_y, mask_x = np.nonzero(garment_mask)
    if len(mask_x) == 0:
        raise ValueError("No se detectó una prenda en la imagen.")

    left, right = int(mask_x.min()), int(mask_x.max())
    top, bottom = int(mask_y.min()), int(mask_y.max())
    width = right - left + 1
    height = bottom - top + 1
    center_start = int(left + width * 0.46)
    center_end = max(center_start + 1, int(left + width * 0.54))
    lower_start = int(top + height * 0.45)
    lower_center = garment_mask[lower_start:bottom + 1, center_start:center_end]
    center_gap_ratio = float(np.mean(~np.any(lower_center, axis=1)))

    if width / height < 0.82 or center_gap_ratio > 0.25:
        return "pants"
    return "shirt"


def _load_mesh(mesh_bytes: bytes, *, file_type: str, label: str) -> trimesh.Trimesh:
    try:
        mesh = trimesh.load(io.BytesIO(mesh_bytes), file_type=file_type, force="mesh")
    except Exception as error:
        raise ValueError(f"No se pudo cargar la malla de {label}.") from error

    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"El archivo de {label} no contiene una malla 3D válida.")

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if (
        vertices.ndim != 2
        or vertices.shape[1] != 3
        or len(vertices) == 0
        or faces.ndim != 2
        or faces.shape[1] != 3
        or len(faces) == 0
        or not np.isfinite(vertices).all()
    ):
        raise ValueError(f"La malla de {label} no contiene geometría válida.")
    return mesh


def _find_template(garment_type: str, templates_dir: str) -> str:
    names = GARMENT_TEMPLATES[garment_type]
    for name in names:
        path = os.path.join(templates_dir, name)
        if os.path.isfile(path):
            return path

    expected_names = ", ".join(names)
    raise FileNotFoundError(
        f"No se encontró la plantilla de {garment_type} en '{templates_dir}'. "
        f"Nombres admitidos: {expected_names}."
    )


def _remove_duplicate_inner_layers(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    parts = mesh.split(only_watertight=False)
    duplicate_parts: set[int] = set()
    for first_index, first in enumerate(parts):
        for second_index in range(first_index + 1, len(parts)):
            second = parts[second_index]
            if (
                first_index in duplicate_parts
                or second_index in duplicate_parts
                or len(first.vertices) != len(second.vertices)
                or len(first.faces) != len(second.faces)
                or first.volume * second.volume >= 0
            ):
                continue

            extent = float(np.ptp(first.vertices, axis=0).max())
            if extent <= 1e-8:
                continue
            if float(np.max(np.abs(first.bounds - second.bounds))) > extent * 0.002:
                continue

            distances = cKDTree(first.vertices).query(
                second.vertices,
                workers=-1,
            )[0]
            if float(distances.max()) <= extent * 0.002:
                duplicate_parts.add(
                    first_index if first.volume < 0 else second_index
                )

    if not duplicate_parts:
        return mesh
    return trimesh.util.concatenate(
        [part for index, part in enumerate(parts) if index not in duplicate_parts]
    )


def _fit_template_to_body(
    template_mesh: trimesh.Trimesh,
    body_vertices: np.ndarray,
    garment_type: str,
) -> None:
    body_vertical_axis = int(np.argmax(np.ptp(body_vertices, axis=0)))
    body_height = float(np.ptp(body_vertices[:, body_vertical_axis]))
    if body_height <= 1e-8:
        raise ValueError("No se pudo determinar la altura del cuerpo.")

    body_min_height = float(body_vertices[:, body_vertical_axis].min())
    low, high = BODY_HEIGHT_RANGES[garment_type]
    region_mask = (
        (body_vertices[:, body_vertical_axis] >= body_min_height + body_height * low)
        & (body_vertices[:, body_vertical_axis] <= body_min_height + body_height * high)
    )
    region_vertices = body_vertices[region_mask]
    if len(region_vertices) < 3:
        raise ValueError(
            f"No se encontraron suficientes vértices en la zona de {garment_type}."
        )

    body_lower = np.empty(3, dtype=np.float64)
    body_upper = np.empty(3, dtype=np.float64)
    for axis in range(3):
        if axis == body_vertical_axis:
            body_lower[axis] = body_min_height + body_height * low
            body_upper[axis] = body_min_height + body_height * high
        else:
            body_lower[axis], body_upper[axis] = np.percentile(
                region_vertices[:, axis],
                [5, 95],
            )

    body_extents = body_upper - body_lower
    other_body_axes = [axis for axis in range(3) if axis != body_vertical_axis]
    body_lateral_axis = max(other_body_axes, key=lambda axis: body_extents[axis])
    body_depth_axis = next(
        axis for axis in other_body_axes if axis != body_lateral_axis
    )
    if np.any(body_extents <= 1e-8):
        raise ValueError("No se pudo calcular el volumen de ajuste del cuerpo.")

    template_vertices = np.asarray(template_mesh.vertices, dtype=np.float64)
    template_extents = np.ptp(template_vertices, axis=0)
    template_vertical_axis = int(np.argmax(template_extents))
    other_template_axes = [
        axis for axis in range(3) if axis != template_vertical_axis
    ]
    template_lateral_axis = max(
        other_template_axes,
        key=lambda axis: template_extents[axis],
    )
    template_depth_axis = next(
        axis for axis in other_template_axes if axis != template_lateral_axis
    )
    if np.any(template_extents <= 1e-8):
        raise ValueError("La plantilla tiene dimensiones inválidas.")

    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = 0.0
    template_lower = template_vertices.min(axis=0)
    axis_mapping = (
        (template_vertical_axis, body_vertical_axis),
        (template_lateral_axis, body_lateral_axis),
        (template_depth_axis, body_depth_axis),
    )
    for template_axis, body_axis in axis_mapping:
        scale = body_extents[body_axis] / template_extents[template_axis]
        transform[body_axis, template_axis] = scale
        transform[body_axis, 3] = (
            body_lower[body_axis] - template_lower[template_axis] * scale
        )
    template_mesh.apply_transform(transform)


def _make_garment_texture(
    garment_pixels: np.ndarray,
    garment_mask: np.ndarray,
) -> Image.Image:
    mask_y, mask_x = np.nonzero(garment_mask)
    padding = max(1, int(round(max(garment_pixels.shape[:2]) * 0.02)))
    left = max(0, int(mask_x.min()) - padding)
    top = max(0, int(mask_y.min()) - padding)
    right = min(garment_pixels.shape[1], int(mask_x.max()) + padding + 1)
    bottom = min(garment_pixels.shape[0], int(mask_y.max()) + padding + 1)

    texture = garment_pixels[top:bottom, left:right].copy()
    mask = garment_mask[top:bottom, left:right]
    if not np.any(mask):
        raise ValueError("No se detectó una prenda en la imagen.")

    garment_color = np.median(texture[mask, :3], axis=0).astype(np.uint8)
    texture[~mask, :3] = garment_color
    texture[:, :, 3] = np.where(mask, texture[:, :, 3], 0)
    return Image.fromarray(texture)


def build_fitted_garment(
    body_bytes: bytes,
    garment_pixels: np.ndarray,
    garment_mask: np.ndarray,
    templates_dir: str,
) -> tuple[trimesh.Scene, str]:
    if not body_bytes.startswith(b"glTF"):
        raise ValueError("El cuerpo seleccionado no es un archivo GLB válido.")
    if (
        garment_pixels.ndim != 3
        or garment_pixels.shape[2] != 4
        or garment_mask.shape != garment_pixels.shape[:2]
    ):
        raise ValueError("La imagen y la máscara de la prenda no son compatibles.")

    body_mesh = _load_mesh(body_bytes, file_type="glb", label="cuerpo")
    garment_type = classify_garment(garment_mask)
    template_path = _find_template(garment_type, templates_dir)
    with open(template_path, "rb") as template_file:
        template_bytes = template_file.read()
    template_mesh = _load_mesh(
        template_bytes,
        file_type="glb",
        label=f"plantilla '{template_path}'",
    )
    template_mesh = _remove_duplicate_inner_layers(template_mesh)
    _fit_template_to_body(
        template_mesh,
        np.asarray(body_mesh.vertices, dtype=np.float64),
        garment_type,
    )
    garment = template_mesh
    uv = getattr(garment.visual, "uv", None)
    if uv is None or uv.shape != (len(garment.vertices), 2):
        raise ValueError(
            f"La plantilla '{template_path}' no tiene coordenadas UV válidas."
        )

    material = trimesh.visual.material.PBRMaterial(
        baseColorTexture=_make_garment_texture(garment_pixels, garment_mask),
        baseColorFactor=[255, 255, 255, 255],
        alphaMode="BLEND",
        doubleSided=True,
    )
    garment.visual = trimesh.visual.TextureVisuals(uv=uv, material=material)

    scene = trimesh.Scene()
    scene.add_geometry(
        garment,
        node_name="fitted_garment",
        geom_name="fitted_garment",
    )
    return scene, garment_type
