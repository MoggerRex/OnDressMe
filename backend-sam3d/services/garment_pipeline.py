from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import trimesh


MAX_GARMENT_MESH_BYTES = 64 * 1024 * 1024
MAX_GARMENT_VERTICES = 500_000
SUPPORTED_GARMENT_TYPES = {"tshirt", "pants"}


class GarmentPipelineError(ValueError):
    """Raised when an input garment or body mesh cannot be processed safely."""


@dataclass(frozen=True)
class GarmentBuildResult:
    scene: trimesh.Scene
    metrics: dict[str, int | float | str]
    warnings: tuple[str, ...]


def _smooth_section_values(values: np.ndarray) -> np.ndarray:
    smoothing_weights = np.array([1.0, 2.0, 3.0, 2.0, 1.0]) / 9.0
    return np.convolve(
        np.pad(values, (2, 2), mode="edge"),
        smoothing_weights,
        mode="valid",
    )


def _body_section_centers(
    vertices: np.ndarray,
    fractions: np.ndarray,
    body_min_y: float,
    body_height: float,
    center_x: float | None = None,
    central_radius: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    normalized_y = (vertices[:, 1] - body_min_y) / body_height
    centerline_x = []
    centerline_z = []
    for fraction in fractions:
        band = np.abs(normalized_y - fraction) <= 0.04
        samples = vertices[band]
        if center_x is not None and central_radius is not None:
            central = samples[np.abs(samples[:, 0] - center_x) <= central_radius]
            if len(central) >= 8:
                samples = central
        if len(samples) < 8:
            raise GarmentPipelineError(
                "La resolución de la malla no permite seguir el eje corporal."
            )
        x_low, x_high = np.quantile(samples[:, 0], [0.1, 0.9])
        z_low, z_high = np.quantile(samples[:, 2], [0.1, 0.9])
        centerline_x.append(float((x_low + x_high) * 0.5))
        centerline_z.append(float((z_low + z_high) * 0.5))

    centerline_x = np.asarray(centerline_x, dtype=np.float64)
    centerline_z = np.asarray(centerline_z, dtype=np.float64)
    if not np.isfinite(centerline_x).all() or not np.isfinite(centerline_z).all():
        raise GarmentPipelineError(
            "No se pudo determinar el eje corporal en la malla SAM 3D."
        )
    centerline_x = _smooth_section_values(centerline_x)
    centerline_z = _smooth_section_values(centerline_z)
    return centerline_x, centerline_z


def _bilateral_section_centers(
    vertices: np.ndarray,
    normalized_y: np.ndarray,
    fractions: np.ndarray,
    center_x: float,
) -> np.ndarray | None:
    sample_fractions = fractions[(fractions >= 0.08) & (fractions <= 0.48)]
    centers = np.empty((len(fractions), 2, 2), dtype=np.float64)

    side_masks = (vertices[:, 0] < center_x, vertices[:, 0] >= center_x)
    for side_index, side_mask in enumerate(side_masks):
        valid_fractions = []
        side_centers = []
        for fraction in sample_fractions:
            band = np.abs(normalized_y - fraction) <= 0.04
            samples = vertices[band & side_mask]
            if len(samples) < 8:
                continue
            x_low, x_high = np.quantile(samples[:, 0], [0.1, 0.9])
            z_low, z_high = np.quantile(samples[:, 2], [0.1, 0.9])
            valid_fractions.append(float(fraction))
            side_centers.append(
                [float((x_low + x_high) * 0.5), float((z_low + z_high) * 0.5)]
            )

        if len(valid_fractions) < 2:
            return None

        side_centers_array = np.asarray(side_centers, dtype=np.float64)
        smoothed_x = _smooth_section_values(side_centers_array[:, 0])
        smoothed_z = _smooth_section_values(side_centers_array[:, 1])
        centers[:, side_index, 0] = np.interp(
            fractions, valid_fractions, smoothed_x
        )
        centers[:, side_index, 1] = np.interp(
            fractions, valid_fractions, smoothed_z
        )

    return centers


def _validate_body_mesh(body_mesh: trimesh.Trimesh) -> np.ndarray:
    if isinstance(body_mesh, trimesh.Scene):
        body_mesh = body_mesh.dump(concatenate=True)
    if not isinstance(body_mesh, trimesh.Trimesh):
        raise GarmentPipelineError("SAM 3D no proporcionó una malla corporal.")

    vertices = np.asarray(body_mesh.vertices, dtype=np.float64)
    faces = np.asarray(body_mesh.faces, dtype=np.int64)
    if (
        vertices.ndim != 2
        or vertices.shape[1] != 3
        or len(vertices) < 30
        or not np.isfinite(vertices).all()
    ):
        raise GarmentPipelineError("La malla corporal contiene vértices inválidos.")
    if (
        faces.ndim != 2
        or faces.shape[1] != 3
        or len(faces) == 0
        or faces.min() < 0
        or faces.max() >= len(vertices)
    ):
        raise GarmentPipelineError("La malla corporal contiene caras inválidas.")

    return vertices


def _body_torso_profile(
    vertices: np.ndarray,
) -> tuple[
    float,
    float,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    float,
    float,
    float,
    float,
    float,
    float,
]:
    bounds = np.vstack((vertices.min(axis=0), vertices.max(axis=0)))
    body_height = float(bounds[1, 1] - bounds[0, 1])
    if body_height <= 0 or body_height < 0.55 * max(
        bounds[1, 0] - bounds[0, 0],
        bounds[1, 2] - bounds[0, 2],
    ):
        raise GarmentPipelineError(
            "La malla corporal debe estar erguida y usar el eje Y como vertical."
        )

    center_x = float(np.median(vertices[:, 0]))
    normalized_y = (vertices[:, 1] - bounds[0, 1]) / body_height
    body_width = float(bounds[1, 0] - bounds[0, 0])
    central = np.abs(vertices[:, 0] - center_x) <= max(
        body_width * 0.20, body_height * 0.14
    )
    section_widths = []
    section_depths = []
    for fraction in (0.58, 0.64, 0.70, 0.76, 0.82):
        band = np.abs(normalized_y - fraction) <= 0.025
        samples = vertices[band & central]
        if len(samples) < 8:
            samples = vertices[band]
        if len(samples) >= 8:
            x_low, x_high = np.quantile(samples[:, 0], [0.05, 0.95])
            z_low, z_high = np.quantile(samples[:, 2], [0.05, 0.95])
            section_widths.append(float(x_high - x_low))
            section_depths.append(float(z_high - z_low))

    if not section_widths or max(section_widths) <= 0:
        raise GarmentPipelineError(
            "No se pudieron medir secciones fiables del torso SAM 3D."
        )

    target_width = max(section_widths) * 1.20
    target_height = body_height * 0.35
    centerline_fractions = np.linspace(0.50, 0.85, 18)
    centerline_x, centerline_z = _body_section_centers(
        vertices,
        centerline_fractions,
        float(bounds[0, 1]),
        body_height,
        center_x,
        max(body_width * 0.20, body_height * 0.14),
    )

    target_center_fraction = 0.675
    target_center_y = float(bounds[0, 1] + body_height * target_center_fraction)
    target_center_x = float(
        np.interp(target_center_fraction, centerline_fractions, centerline_x)
    )
    target_center_z = float(
        np.interp(target_center_fraction, centerline_fractions, centerline_z)
    )
    target_depth = (
        float(np.median(section_depths)) + body_height * 0.05
        if section_depths
        else 0.0
    )
    return (
        target_width,
        target_height,
        centerline_fractions,
        centerline_x,
        centerline_z,
        target_center_x,
        target_center_y,
        target_center_z,
        float(bounds[0, 1]),
        body_height,
        target_depth,
    )


def _body_pants_profile(
    vertices: np.ndarray,
) -> tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray | None,
]:
    bounds = np.vstack((vertices.min(axis=0), vertices.max(axis=0)))
    body_height = float(bounds[1, 1] - bounds[0, 1])
    if body_height <= 0 or body_height < 0.55 * max(
        bounds[1, 0] - bounds[0, 0],
        bounds[1, 2] - bounds[0, 2],
    ):
        raise GarmentPipelineError(
            "La malla corporal debe estar erguida y usar el eje Y como vertical."
        )

    center_x = float(np.median(vertices[:, 0]))
    body_width = float(bounds[1, 0] - bounds[0, 0])
    normalized_y = (vertices[:, 1] - bounds[0, 1]) / body_height
    central_limit = max(body_width * 0.20, body_height * 0.14)
    hip_widths = []
    hip_depths = []
    hip_centers_x = []
    hip_centers_z = []
    for fraction in (0.52, 0.54, 0.56):
        band = np.abs(normalized_y - fraction) <= 0.02
        samples = vertices[band & (np.abs(vertices[:, 0] - center_x) <= central_limit)]
        if len(samples) < 8:
            samples = vertices[band]
        if len(samples) < 8:
            continue
        x_low, x_high = np.quantile(samples[:, 0], [0.05, 0.95])
        z_low, z_high = np.quantile(samples[:, 2], [0.05, 0.95])
        hip_widths.append(float(x_high - x_low))
        hip_depths.append(float(z_high - z_low))
        hip_centers_x.append(float((x_low + x_high) * 0.5))
        hip_centers_z.append(float((z_low + z_high) * 0.5))

    if not hip_widths or max(hip_widths) <= 0 or max(hip_depths) <= 0:
        raise GarmentPipelineError(
            "No se pudieron medir secciones fiables de la cadera para el pantalón."
        )

    low_fraction = 0.02
    high_fraction = 0.57
    centerline_fractions = np.linspace(low_fraction, high_fraction, 18)
    centerline_x, centerline_z = _body_section_centers(
        vertices,
        centerline_fractions,
        float(bounds[0, 1]),
        body_height,
    )
    leg_centers = _bilateral_section_centers(
        vertices,
        normalized_y,
        centerline_fractions,
        center_x,
    )
    return (
        max(hip_widths) * 1.22,
        body_height * (high_fraction - low_fraction),
        float(np.median(hip_centers_x)),
        float(bounds[0, 1] + body_height * (low_fraction + high_fraction) * 0.5),
        float(np.median(hip_centers_z)),
        float(bounds[0, 1]),
        body_height,
        max(hip_depths) * 1.35,
        low_fraction,
        high_fraction,
        centerline_fractions,
        centerline_x,
        centerline_z,
        leg_centers,
    )


def load_garment_mesh(
    contents: bytes,
    filename: str,
    body_mesh: trimesh.Trimesh,
    garment_type: str = "tshirt",
) -> GarmentBuildResult:
    garment_type = garment_type.strip().lower()
    if garment_type not in SUPPORTED_GARMENT_TYPES:
        raise GarmentPipelineError(
            "Tipo de prenda no admitido. Usa 'tshirt' o 'pants'."
        )

    if not contents:
        raise GarmentPipelineError("El archivo de malla de prenda está vacío.")
    if len(contents) > MAX_GARMENT_MESH_BYTES:
        raise GarmentPipelineError("La malla de prenda supera el límite de 64 MB.")

    mesh_format = Path(filename).suffix.lower().lstrip(".")
    if mesh_format not in {"glb", "obj"}:
        raise GarmentPipelineError(
            "Usa un archivo GLB o OBJ generado por una herramienta de reconstrucción 3D."
        )
    if mesh_format == "glb" and contents[:4] != b"glTF":
        raise GarmentPipelineError("El archivo GLB no tiene una cabecera válida.")

    try:
        scene = trimesh.load(
            BytesIO(contents),
            file_type=mesh_format,
            force="scene",
        )
    except Exception as error:
        raise GarmentPipelineError(
            "No se pudo leer la malla de prenda. Comprueba que el archivo esté completo."
        ) from error

    if not isinstance(scene, trimesh.Scene) or not scene.geometry:
        raise GarmentPipelineError("El archivo no contiene geometría de prenda.")

    vertex_count = 0
    face_count = 0
    for geometry in scene.geometry.values():
        if not isinstance(geometry, trimesh.Trimesh):
            raise GarmentPipelineError(
                "La malla debe contener geometría triangular."
            )
        vertices = np.asarray(geometry.vertices, dtype=np.float64)
        faces = np.asarray(geometry.faces, dtype=np.int64)
        if (
            vertices.ndim != 2
            or vertices.shape[1] != 3
            or len(vertices) < 3
            or not np.isfinite(vertices).all()
        ):
            raise GarmentPipelineError(
                "La malla de prenda contiene vértices inválidos."
            )
        if (
            faces.ndim != 2
            or faces.shape[1] != 3
            or len(faces) == 0
            or faces.min() < 0
            or faces.max() >= len(vertices)
        ):
            raise GarmentPipelineError("La malla de prenda contiene caras inválidas.")
        vertex_count += len(vertices)
        face_count += len(faces)

    if vertex_count > MAX_GARMENT_VERTICES:
        raise GarmentPipelineError(
            "La malla supera el límite de 500 000 vértices para la simulación local."
        )

    garment_bounds = np.asarray(scene.bounds, dtype=np.float64)
    if garment_bounds.shape != (2, 3) or not np.isfinite(garment_bounds).all():
        raise GarmentPipelineError("No se pudieron calcular los límites de la malla.")
    garment_extents = garment_bounds[1] - garment_bounds[0]
    if (
        garment_extents[1] <= 0
        or garment_extents[0] <= 0
        or garment_extents[1] < max(garment_extents[0], garment_extents[2]) * 0.35
    ):
        raise GarmentPipelineError(
            "La malla debe estar aproximadamente erguida, con el eje Y vertical."
        )

    body_vertices = _validate_body_mesh(body_mesh)
    leg_centers = None
    if garment_type == "pants":
        (
            target_width,
            target_height,
            center_x,
            center_y,
            center_z,
            body_min_y,
            body_height,
            target_depth,
            target_fraction_low,
            target_fraction_high,
            centerline_fractions,
            centerline_x,
            centerline_z,
            leg_centers,
        ) = _body_pants_profile(body_vertices)
    else:
        (
            target_width,
            target_height,
            centerline_fractions,
            centerline_x,
            centerline_z,
            center_x,
            center_y,
            center_z,
            body_min_y,
            body_height,
            target_depth,
        ) = _body_torso_profile(body_vertices)
        target_fraction_low = float(centerline_fractions[0])
        target_fraction_high = float(centerline_fractions[-1])
    if target_width <= 0 or target_height <= 0 or target_depth <= 0:
        raise GarmentPipelineError(
            "Las secciones del torso no tienen dimensiones válidas."
        )

    scale_x = target_width / float(garment_extents[0])
    scale_y = target_height / float(garment_extents[1])
    scale_z = target_depth / float(garment_extents[2])
    if not np.isfinite([scale_x, scale_y, scale_z]).all() or min(
        scale_x, scale_y, scale_z
    ) <= 0:
        raise GarmentPipelineError("No se pudo ajustar la escala de la prenda.")

    source_center = garment_bounds.mean(axis=0)
    target_center = np.array([center_x, center_y, center_z], dtype=np.float64)
    transform = np.eye(4, dtype=np.float64)
    transform[:3, :3] = np.diag([scale_x, scale_y, scale_z])
    transform[:3, 3] = target_center - transform[:3, :3] @ source_center
    scene.apply_transform(transform)

    target_y_low = body_min_y + body_height * target_fraction_low
    target_y_high = body_min_y + body_height * target_fraction_high
    centerline_y = body_min_y + centerline_fractions * body_height
    reference_x = float(np.interp(center_y, centerline_y, centerline_x))
    reference_z = float(np.interp(center_y, centerline_y, centerline_z))
    garment_leg_centers = None
    if leg_centers is not None:
        garment_world_vertices = []
        for node in scene.graph.nodes_geometry:
            node_transform, geometry_name = scene.graph[node]
            geometry = scene.geometry[geometry_name]
            garment_world_vertices.append(
                trimesh.transform_points(
                    np.asarray(geometry.vertices, dtype=np.float64),
                    node_transform,
                )
            )
        all_garment_vertices = np.concatenate(garment_world_vertices, axis=0)
        garment_height_fraction = np.clip(
            (all_garment_vertices[:, 1] - target_y_low) / target_height,
            0.0,
            1.0,
        )
        garment_body_fractions = (
            target_fraction_low
            + garment_height_fraction
            * (target_fraction_high - target_fraction_low)
        )
        garment_leg_centers = _bilateral_section_centers(
            all_garment_vertices,
            garment_body_fractions,
            centerline_fractions,
            center_x,
        )

    for node in scene.graph.nodes_geometry:
        node_transform, geometry_name = scene.graph[node]
        inverse_transform = np.linalg.inv(node_transform)
        geometry = scene.geometry[geometry_name]
        world_vertices = trimesh.transform_points(
            np.asarray(geometry.vertices, dtype=np.float64),
            node_transform,
        )
        garment_height_fraction = np.clip(
            (world_vertices[:, 1] - target_y_low) / target_height,
            0.0,
            1.0,
        )
        body_fractions = (
            target_fraction_low
            + garment_height_fraction
            * (target_fraction_high - target_fraction_low)
        )
        target_x = np.interp(body_fractions, centerline_fractions, centerline_x)
        target_z = np.interp(body_fractions, centerline_fractions, centerline_z)
        world_vertices[:, 0] += target_x - reference_x
        world_vertices[:, 2] += target_z - reference_z
        if leg_centers is not None and garment_leg_centers is not None:
            left_x = np.interp(
                body_fractions, centerline_fractions, leg_centers[:, 0, 0]
            )
            right_x = np.interp(
                body_fractions, centerline_fractions, leg_centers[:, 1, 0]
            )
            left_z = np.interp(
                body_fractions, centerline_fractions, leg_centers[:, 0, 1]
            )
            right_z = np.interp(
                body_fractions, centerline_fractions, leg_centers[:, 1, 1]
            )
            garment_left_x = np.interp(
                body_fractions,
                centerline_fractions,
                garment_leg_centers[:, 0, 0],
            )
            garment_right_x = np.interp(
                body_fractions,
                centerline_fractions,
                garment_leg_centers[:, 1, 0],
            )
            garment_left_z = np.interp(
                body_fractions,
                centerline_fractions,
                garment_leg_centers[:, 0, 1],
            )
            garment_right_z = np.interp(
                body_fractions,
                centerline_fractions,
                garment_leg_centers[:, 1, 1],
            )
            side_weight = np.clip(
                (world_vertices[:, 0] - center_x) / (target_width * 0.12) + 0.5,
                0.0,
                1.0,
            )
            leg_blend = np.clip((0.52 - body_fractions) / 0.12, 0.0, 1.0)
            leg_blend = leg_blend * leg_blend * (3.0 - 2.0 * leg_blend)
            leg_offset_x = (
                (left_x - garment_left_x - (target_x - reference_x))
                * (1.0 - side_weight)
                + (right_x - garment_right_x - (target_x - reference_x))
                * side_weight
            )
            leg_offset_z = (
                (left_z - garment_left_z - (target_z - reference_z))
                * (1.0 - side_weight)
                + (right_z - garment_right_z - (target_z - reference_z))
                * side_weight
            )
            world_vertices[:, 0] += leg_blend * leg_offset_x
            world_vertices[:, 2] += leg_blend * leg_offset_z
        geometry.vertices = trimesh.transform_points(
            world_vertices,
            inverse_transform,
        )

    fit_region = "cadera y piernas" if garment_type == "pants" else "torso"
    warnings = [
        f"La geometría recibida se ajustó por secciones de {fit_region} SAM 3D y luego se simuló; no se reconstruyó desde una foto.",
        "Antes de simular, Blender proyecta fuera del cuerpo los vértices de la prenda que empiezan en penetración.",
    ]
    if garment_type == "pants" and (
        leg_centers is None or garment_leg_centers is None
    ):
        warnings.append(
            "La malla corporal no permitió separar ambas piernas; se aplicó un centrado general por altura."
        )
    if mesh_format == "obj":
        warnings.append(
            "Un OBJ cargado sin sus archivos MTL/texturas conserva la geometría, pero puede quedar sin textura; usa GLB para materiales embebidos."
        )

    return GarmentBuildResult(
        scene=scene,
        metrics={
            "geometry_source": "uploaded_garment_mesh",
            "garment_type": garment_type,
            "source_format": mesh_format,
            "image_use": (
                "embedded_or_mesh_materials" if mesh_format == "glb" else "none_or_external_obj"
            ),
            "body_height_units": round(body_height, 5),
            "garment_vertex_count": vertex_count,
            "garment_face_count": face_count,
            "fit_scale_x": round(float(scale_x), 6),
            "fit_scale_y": round(float(scale_y), 6),
            "fit_scale_z": round(float(scale_z), 6),
            "fit_torso_y_min": round(float(target_y_low), 5),
            "fit_torso_y_max": round(float(target_y_high), 5),
            "simulation": "pending",
        },
        warnings=tuple(warnings),
    )
