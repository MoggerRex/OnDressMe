from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import trimesh

from services.body_skeleton import arm_vertex_mask, has_arm_bones, without_arms
from services.patterns.analyzer import from_scene
from services.patterns.editor import apply_edits
from services.patterns.segmenter import SegmentationError, segment
from services.patterns.validation import validate
from services.body_volume import BodyVolume, resolve_overlaps
from services.leg_fit import body_crotch_y, fit_leg_sections, garment_crotch_y
from services.torso_fit import fit_torso_sections
from services.sleeve_fit import keep_off_arms, retarget_sleeves
from services.garment_rig import (
    lookup_vertex_weights,
    read_garment_rig,
    retarget_offsets,
)


MAX_GARMENT_MESH_BYTES = 64 * 1024 * 1024
MAX_GARMENT_VERTICES = 500_000
UPPER_GARMENT_TYPES = {"tshirt", "tank", "longsleeve"}
LOWER_GARMENT_TYPES = {"pants", "shorts"}
SUPPORTED_GARMENT_TYPES = UPPER_GARMENT_TYPES | LOWER_GARMENT_TYPES | {"shoes"}
FIT_MULTIPLIERS = {"tight": 0.2, "regular": 1.0, "loose": 2.0}
# Ease added over the body, per garment type, at the "regular" fit.
TORSO_EASE = {"tshirt": 0.20, "longsleeve": 0.20, "tank": 0.06}
# Ease of the level-by-level torso fit (share of the avatar's section, times looseness).
SECTION_EASE = {"tshirt": 0.12, "longsleeve": 0.12, "tank": 0.10}
HIP_EASE = 0.12
LEG_EASE = {"pants": 0.06, "shorts": 0.14}
SHORTS_HEM_ABOVE_KNEE = 0.12  # hem height as a share of the knee-to-hip distance
PANTS_WAIST_CLEARANCE_FACTOR = 1.02


class GarmentPipelineError(ValueError):
    """Raised when an input garment or body mesh cannot be processed safely."""


@dataclass(frozen=True)
class GarmentBuildResult:
    scene: trimesh.Scene
    metrics: dict[str, int | float | str]
    warnings: tuple[str, ...]
    # (GarmentMesh as uploaded, Segmentation) when pieces were requested.
    pattern: tuple | None = None


@dataclass(frozen=True)
class PantsBodyProfile:
    target_width: float
    target_height: float
    center_x: float
    center_y: float
    center_z: float
    body_min_y: float
    body_height: float
    target_depth: float
    low_fraction: float
    waist_fraction: float
    centerline_fractions: np.ndarray
    centerline_x: np.ndarray
    centerline_z: np.ndarray
    section_widths: np.ndarray
    section_depths: np.ndarray
    leg_centers: np.ndarray | None
    waist_width: float
    waist_depth: float
    landmark_anchored: bool
    front_direction: np.ndarray | None
    waist_center_xz: np.ndarray
    waist_contour_radii: np.ndarray
    waist_contour_clearance: float
    anterior_surface_distance: float
    posterior_rise: float
    posterior_anchor_center_xz: np.ndarray | None
    posterior_anchor_xz: np.ndarray | None
    posterior_surface_distance: float
    posterior_clearance: float
    posterior_anchor_y: float


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


def _landmark_leg_centers(
    landmarks: dict[str, np.ndarray],
    fractions: np.ndarray,
    body_min_y: float,
    body_height: float,
) -> np.ndarray:
    centers = np.empty((len(fractions), 2, 2), dtype=np.float64)
    sides = (
        ("left-hip", "left-knee", "left-ankle"),
        ("right-hip", "right-knee", "right-ankle"),
    )
    if landmarks[sides[0][0]][0] > landmarks[sides[1][0]][0]:
        sides = (sides[1], sides[0])

    sample_y = body_min_y + fractions * body_height
    for side_index, (hip_name, knee_name, ankle_name) in enumerate(sides):
        points = np.asarray(
            [landmarks[ankle_name], landmarks[knee_name], landmarks[hip_name]],
            dtype=np.float64,
        )
        order = np.argsort(points[:, 1])
        points = points[order]
        unique_y, inverse = np.unique(points[:, 1], return_inverse=True)
        if len(unique_y) < 2:
            raise GarmentPipelineError(
                "Las anclas MHR no permiten seguir una pierna en la malla corporal."
            )
        x_values = np.bincount(inverse, weights=points[:, 0]) / np.bincount(inverse)
        z_values = np.bincount(inverse, weights=points[:, 2]) / np.bincount(inverse)
        centers[:, side_index, 0] = np.interp(sample_y, unique_y, x_values)
        centers[:, side_index, 1] = np.interp(sample_y, unique_y, z_values)

    return centers


def _apply_posterior_waist_anchor(
    vertices: np.ndarray,
    front_direction: np.ndarray,
    anchor_center_xz: np.ndarray,
    posterior_surface_distance: float,
    clearance: float,
    anchor_y: float,
    body_depth: float,
    target_y_low: float,
    target_height: float,
) -> np.ndarray:
    if target_height <= 0:
        return vertices

    rear_direction = -front_direction
    relative_xz = vertices[:, [0, 2]] - anchor_center_xz
    posterior_distance = relative_xz @ rear_direction
    posterior_weight = np.clip(
        (posterior_distance - body_depth * 0.05) / max(body_depth * 0.20, 1e-6),
        0.0,
        1.0,
    )
    posterior_weight = posterior_weight**2 * (3.0 - 2.0 * posterior_weight)

    height_fraction = np.clip(
        (vertices[:, 1] - target_y_low) / target_height,
        0.0,
        1.0,
    )
    waistband_weight = np.clip((height_fraction - 0.65) / 0.35, 0.0, 1.0)
    waistband_weight = waistband_weight**2 * (3.0 - 2.0 * waistband_weight)
    required_distance = posterior_surface_distance + clearance
    posterior_offset = np.maximum(required_distance - posterior_distance, 0.0)
    posterior_offset = (
        np.minimum(posterior_offset, body_depth * 0.5)
        * posterior_weight
        * waistband_weight
    )
    vertices[:, 0] += rear_direction[0] * posterior_offset
    vertices[:, 2] += rear_direction[1] * posterior_offset
    vertical_offset = np.maximum(anchor_y - vertices[:, 1], 0.0)
    vertices[:, 1] += vertical_offset * posterior_weight * waistband_weight
    return vertices


def _apply_anterior_waist_clamp(
    vertices: np.ndarray,
    front_direction: np.ndarray,
    waist_center_xz: np.ndarray,
    anterior_surface_distance: float,
    clearance: float,
    target_y_low: float,
    target_height: float,
) -> np.ndarray:
    if target_height <= 0:
        return vertices

    relative_xz = vertices[:, [0, 2]] - waist_center_xz
    anterior_distance = relative_xz @ front_direction
    height_fraction = np.clip(
        (vertices[:, 1] - target_y_low) / target_height,
        0.0,
        1.0,
    )
    waistband_weight = np.clip((height_fraction - 0.72) / 0.28, 0.0, 1.0)
    waistband_weight = waistband_weight**2 * (3.0 - 2.0 * waistband_weight)
    excess = np.maximum(
        anterior_distance - (anterior_surface_distance + clearance),
        0.0,
    )
    inward_offset = excess * waistband_weight
    vertices[:, 0] -= front_direction[0] * inward_offset
    vertices[:, 2] -= front_direction[1] * inward_offset
    return vertices


def _body_radial_profile(
    samples: np.ndarray,
    center_xz: np.ndarray,
    bin_count: int = 48,
) -> np.ndarray:
    offsets = samples[:, [0, 2]] - center_xz
    radii = np.linalg.norm(offsets, axis=1)
    angles = np.arctan2(offsets[:, 1], offsets[:, 0])
    bins = np.floor((angles + np.pi) * bin_count / (2.0 * np.pi)).astype(int)
    bins %= bin_count

    profile = np.full(bin_count, np.nan, dtype=np.float64)
    for bin_index in range(bin_count):
        bin_radii = radii[bins == bin_index]
        if len(bin_radii):
            profile[bin_index] = float(np.quantile(bin_radii, 0.95))

    populated = np.flatnonzero(np.isfinite(profile))
    if len(populated) < 6:
        raise GarmentPipelineError(
            "La malla corporal no tiene suficiente resolución para ajustar toda la cintura."
        )
    extended_indices = np.concatenate(
        (populated[-1:] - bin_count, populated, populated[:1] + bin_count)
    )
    extended_radii = profile[np.concatenate((populated[-1:], populated, populated[:1]))]
    profile = np.interp(np.arange(bin_count), extended_indices, extended_radii)
    return (
        np.roll(profile, 2)
        + 2.0 * np.roll(profile, 1)
        + 3.0 * profile
        + 2.0 * np.roll(profile, -1)
        + np.roll(profile, -2)
    ) / 9.0


def _sample_radial_profile(angles: np.ndarray, profile: np.ndarray) -> np.ndarray:
    bin_count = len(profile)
    angle_step = 2.0 * np.pi / bin_count
    profile_angles = -np.pi + (np.arange(bin_count) + 0.5) * angle_step
    sample_angles = (angles + np.pi) % (2.0 * np.pi) - np.pi
    extended_angles = np.concatenate(
        ([profile_angles[-1] - 2.0 * np.pi], profile_angles, [profile_angles[0] + 2.0 * np.pi])
    )
    extended_profile = np.concatenate(([profile[-1]], profile, [profile[0]]))
    return np.interp(sample_angles, extended_angles, extended_profile)


def _apply_waist_contour_clamp(
    vertices: np.ndarray,
    waist_center_xz: np.ndarray,
    waist_contour_radii: np.ndarray,
    clearance: float,
    target_y_low: float,
    target_height: float,
) -> np.ndarray:
    if target_height <= 0:
        return vertices

    relative_xz = vertices[:, [0, 2]] - waist_center_xz
    radii = np.linalg.norm(relative_xz, axis=1)
    angles = np.arctan2(relative_xz[:, 1], relative_xz[:, 0])
    body_radii = _sample_radial_profile(angles, waist_contour_radii)
    max_radii = body_radii + clearance
    height_fraction = np.clip(
        (vertices[:, 1] - target_y_low) / target_height,
        0.0,
        1.0,
    )
    waistband_weight = np.clip((height_fraction - 0.72) / 0.28, 0.0, 1.0)
    waistband_weight = waistband_weight**2 * (3.0 - 2.0 * waistband_weight)
    adjusted_radii = radii - np.maximum(radii - max_radii, 0.0) * waistband_weight
    radial_scale = np.divide(
        adjusted_radii,
        radii,
        out=np.ones_like(adjusted_radii),
        where=radii > 1e-8,
    )
    vertices[:, 0] = waist_center_xz[0] + relative_xz[:, 0] * radial_scale
    vertices[:, 2] = waist_center_xz[1] + relative_xz[:, 1] * radial_scale
    return vertices


def _body_section_dimensions(
    vertices: np.ndarray,
    normalized_y: np.ndarray,
    fractions: np.ndarray,
    center_x: float,
    central_radius: float,
) -> tuple[np.ndarray, np.ndarray]:
    widths = []
    depths = []
    for fraction in fractions:
        band = np.abs(normalized_y - fraction) <= 0.035
        samples = vertices[
            band & (np.abs(vertices[:, 0] - center_x) <= central_radius)
        ]
        if len(samples) < 8:
            samples = vertices[band]
        if len(samples) < 8:
            raise GarmentPipelineError(
                "La resolución de la malla no permite medir la cintura y las piernas."
            )
        x_low, x_high = np.quantile(samples[:, 0], [0.05, 0.95])
        z_low, z_high = np.quantile(samples[:, 2], [0.05, 0.95])
        widths.append(float(x_high - x_low))
        depths.append(float(z_high - z_low))

    return (
        _smooth_section_values(np.asarray(widths, dtype=np.float64)),
        _smooth_section_values(np.asarray(depths, dtype=np.float64)),
    )


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
    landmarks: dict[str, np.ndarray] | None = None,
    ease: float = 0.20,
    armpit: bool = False,
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

    body_width = float(bounds[1, 0] - bounds[0, 0])
    # Los huesos de brazos y manos se excluyen de las secciones del torso.
    vertices, _ = without_arms(vertices, landmarks, body_height)
    center_x = float(np.median(vertices[:, 0]))
    normalized_y = (vertices[:, 1] - bounds[0, 1]) / body_height
    central = np.abs(vertices[:, 0] - center_x) <= max(
        body_width * 0.20, body_height * 0.14
    )
    section_widths = []
    section_depths = []
    fractions = (0.58, 0.64, 0.70, 0.76, 0.82)
    if armpit and landmarks is not None and "left-shoulder" in landmarks:
        # Sleeveless: the armhole edge must stop where the arm starts, so the
        # width is the torso at the armpit (shoulder joint minus ~6% of height).
        shoulder_y = float(
            np.mean([landmarks["left-shoulder"][1], landmarks["right-shoulder"][1]])
        )
        armpit_fraction = (shoulder_y - 0.06 * body_height - bounds[0, 1]) / body_height
        fractions = (armpit_fraction - 0.03, armpit_fraction, armpit_fraction + 0.02)
    for fraction in fractions:
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

    target_width = max(section_widths) * (1.0 + ease)
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
    landmarks: dict[str, np.ndarray] | None = None,
    hem: str = "ankle",
    ease: float = HIP_EASE,
) -> PantsBodyProfile:
    bounds = np.vstack((vertices.min(axis=0), vertices.max(axis=0)))
    body_height = float(bounds[1, 1] - bounds[0, 1])
    if body_height <= 0 or body_height < 0.55 * max(
        bounds[1, 0] - bounds[0, 0],
        bounds[1, 2] - bounds[0, 2],
    ):
        raise GarmentPipelineError(
            "La malla corporal debe estar erguida y usar el eje Y como vertical."
        )

    body_width = float(bounds[1, 0] - bounds[0, 0])
    # Las manos cerca de la cadera no deben medirse como cadera: se descartan
    # los vértices asignados a los huesos de brazos y manos.
    vertices, _ = without_arms(vertices, landmarks, body_height)
    center_x = float(np.median(vertices[:, 0]))
    normalized_y = (vertices[:, 1] - bounds[0, 1]) / body_height
    central_limit = max(body_width * 0.20, body_height * 0.14)
    landmark_anchored = landmarks is not None
    front_direction = None
    posterior_rise = 0.0
    hip_fraction = 0.54
    if landmarks is not None:
        required_landmarks = (
            "left-hip",
            "right-hip",
            "left-knee",
            "right-knee",
            "left-ankle",
            "right-ankle",
            "nose",
            "neck",
        )
        for name in required_landmarks:
            landmark = landmarks.get(name)
            if landmark is None:
                raise GarmentPipelineError(
                    f"Falta el ancla MHR '{name}' para ajustar el pantalón."
                )
            point = np.asarray(landmark, dtype=np.float64)
            if point.shape != (3,) or not np.isfinite(point).all():
                raise GarmentPipelineError(
                    f"La ancla MHR '{name}' no contiene coordenadas 3D válidas."
                )
        hips = np.asarray(
            [landmarks["left-hip"], landmarks["right-hip"]],
            dtype=np.float64,
        )
        hip_fraction = float(
            (np.mean(hips[:, 1]) - bounds[0, 1]) / body_height
        )
        center_x = float(np.mean(hips[:, 0]))
        front_direction = (
            np.asarray(landmarks["nose"], dtype=np.float64)[[0, 2]]
            - np.asarray(landmarks["neck"], dtype=np.float64)[[0, 2]]
        )
        front_length = float(np.linalg.norm(front_direction))
        if front_length <= body_height * 1e-4:
            raise GarmentPipelineError(
                "Las anclas MHR no permiten determinar la orientación frontal del cuerpo."
            )
        front_direction /= front_length
        posterior_rise = body_height * 0.02

    hip_widths = []
    hip_depths = []
    hip_centers_x = []
    hip_centers_z = []
    hip_sample_fractions = (
        np.clip(hip_fraction + np.array([-0.02, 0.0, 0.02]), 0.02, 0.64)
        if landmarks is not None
        else (0.52, 0.54, 0.56)
    )
    for fraction in hip_sample_fractions:
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
    if hem == "knee":
        # Shorts end a little above the knee (MHR knees when available).
        knee_fraction = 0.285
        if landmarks is not None:
            knee_fraction = float(
                (np.mean([landmarks["left-knee"][1], landmarks["right-knee"][1]]) - bounds[0, 1])
                / body_height
            )
        low_fraction = knee_fraction + SHORTS_HEM_ABOVE_KNEE * (hip_fraction - knee_fraction)
    profile_fractions = np.linspace(low_fraction, 0.60, 30)
    if landmarks is not None:
        profile_fractions = np.linspace(low_fraction, 0.64, 32)
    section_widths, section_depths = _body_section_dimensions(
        vertices,
        normalized_y,
        profile_fractions,
        center_x,
        central_limit,
    )
    waist_candidates = np.flatnonzero(
        (profile_fractions >= 0.48)
        & (profile_fractions <= (0.64 if landmarks is not None else 0.60))
    )
    if landmarks is None:
        waist_index = int(
            waist_candidates[
                np.argmin(
                    section_widths[waist_candidates]
                    * section_depths[waist_candidates]
                )
            ]
        )
    else:
        target_waist_fraction = float(np.clip(hip_fraction + 0.075, 0.48, 0.64))
        waist_index = int(
            waist_candidates[
                np.argmin(
                    np.abs(profile_fractions[waist_candidates] - target_waist_fraction)
                )
            ]
        )
    waist_fraction = float(profile_fractions[waist_index])
    waist_width = float(section_widths[waist_index])
    waist_depth = float(section_depths[waist_index])
    centerline_fractions = np.linspace(low_fraction, waist_fraction, 24)
    centerline_x, centerline_z = _body_section_centers(
        vertices,
        centerline_fractions,
        float(bounds[0, 1]),
        body_height,
        center_x,
        central_limit,
    )
    waist_band = (
        (np.abs(normalized_y - waist_fraction) <= 0.035)
        & (np.abs(vertices[:, 0] - center_x) <= central_limit)
    )
    waist_samples = vertices[waist_band]
    if len(waist_samples) < 8:
        waist_samples = vertices[np.abs(normalized_y - waist_fraction) <= 0.035]
    if len(waist_samples) < 8:
        raise GarmentPipelineError(
            "La malla corporal no tiene suficientes puntos en la cintura para ajustar el pantalón."
        )
    waist_center_xz = np.array(
        [
            float(np.mean(np.quantile(waist_samples[:, 0], [0.1, 0.9]))),
            float(np.mean(np.quantile(waist_samples[:, 2], [0.1, 0.9]))),
        ],
        dtype=np.float64,
    )
    waist_contour_radii = _body_radial_profile(waist_samples, waist_center_xz)
    waist_contour_clearance = max(body_height * 0.006, 0.004)
    anterior_surface_distance = 0.0
    if front_direction is not None:
        anterior_distances = (
            waist_samples[:, [0, 2]] - waist_center_xz
        ) @ front_direction
        anterior_surface_distance = float(np.quantile(anterior_distances, 0.95))

    posterior_anchor_center_xz = None
    posterior_anchor_xz = None
    posterior_surface_distance = 0.0
    posterior_clearance = max(body_height * 0.012, 0.006)
    posterior_anchor_y = 0.0
    if front_direction is not None:
        posterior_anchor_fraction = min(
            waist_fraction + posterior_rise / body_height,
            0.70,
        )
        anchor_band = (
            (np.abs(normalized_y - posterior_anchor_fraction) <= 0.035)
            & (np.abs(vertices[:, 0] - center_x) <= central_limit)
        )
        anchor_samples = vertices[anchor_band]
        if len(anchor_samples) < 8:
            anchor_samples = vertices[
                np.abs(normalized_y - posterior_anchor_fraction) <= 0.035
            ]
        if len(anchor_samples) < 8:
            raise GarmentPipelineError(
                "La malla corporal no tiene suficientes puntos en la cintura posterior para crear un anclaje seguro."
            )

        anchor_center_x = float(
            np.mean(np.quantile(anchor_samples[:, 0], [0.1, 0.9]))
        )
        anchor_center_z = float(
            np.mean(np.quantile(anchor_samples[:, 2], [0.1, 0.9]))
        )
        posterior_anchor_center_xz = np.array(
            [anchor_center_x, anchor_center_z], dtype=np.float64
        )
        rear_direction = -front_direction
        posterior_distances = (
            anchor_samples[:, [0, 2]] - posterior_anchor_center_xz
        ) @ rear_direction
        posterior_surface_distance = float(np.quantile(posterior_distances, 0.95))
        posterior_anchor_xz = posterior_anchor_center_xz + rear_direction * (
            posterior_surface_distance + posterior_clearance
        )
        posterior_anchor_y = float(
            bounds[0, 1] + body_height * posterior_anchor_fraction
        )
        waist_y = float(bounds[0, 1] + body_height * waist_fraction)
        posterior_rise = max(posterior_anchor_y - waist_y, 0.0)

    if landmarks is not None:
        hip_centers_x = [float(np.mean(hips[:, 0]))]
        leg_centers = _landmark_leg_centers(
            landmarks,
            centerline_fractions,
            float(bounds[0, 1]),
            body_height,
        )
        surface_leg_centers = _bilateral_section_centers(
            vertices,
            normalized_y,
            centerline_fractions,
            center_x,
        )
        if surface_leg_centers is not None:
            leg_centers[:, :, 1] = surface_leg_centers[:, :, 1]
        else:
            leg_centers[:, :, 1] = centerline_z[:, np.newaxis]
    else:
        leg_centers = _bilateral_section_centers(
            vertices,
            normalized_y,
            centerline_fractions,
            center_x,
        )
    return PantsBodyProfile(
        target_width=max(hip_widths) * (1.0 + ease),
        target_height=body_height * (waist_fraction - low_fraction),
        center_x=float(np.median(hip_centers_x)),
        center_y=float(
            bounds[0, 1]
            + body_height * (low_fraction + waist_fraction) * 0.5
        ),
        center_z=float(np.median(hip_centers_z)),
        body_min_y=float(bounds[0, 1]),
        body_height=body_height,
        target_depth=max(hip_depths) * (1.0 + ease),
        low_fraction=low_fraction,
        waist_fraction=waist_fraction,
        centerline_fractions=centerline_fractions,
        centerline_x=centerline_x,
        centerline_z=centerline_z,
        section_widths=section_widths,
        section_depths=section_depths,
        leg_centers=leg_centers,
        waist_width=waist_width,
        waist_depth=waist_depth,
        landmark_anchored=landmark_anchored,
        front_direction=front_direction,
        waist_center_xz=waist_center_xz,
        waist_contour_radii=waist_contour_radii,
        waist_contour_clearance=waist_contour_clearance,
        anterior_surface_distance=anterior_surface_distance,
        posterior_rise=posterior_rise,
        posterior_anchor_center_xz=posterior_anchor_center_xz,
        posterior_anchor_xz=posterior_anchor_xz,
        posterior_surface_distance=posterior_surface_distance,
        posterior_clearance=posterior_clearance,
        posterior_anchor_y=posterior_anchor_y,
    )


def read_garment_scene(contents: bytes, filename: str, require_upright: bool = True):
    """Load and validate an uploaded GLB/OBJ garment.

    Returns (scene, mesh_format, vertex_count, face_count, bounds, extents).
    """
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
    if require_upright and (
        garment_extents[1] <= 0
        or garment_extents[0] <= 0
        or garment_extents[1] < max(garment_extents[0], garment_extents[2]) * 0.35
    ):
        raise GarmentPipelineError(
            "La malla debe estar aproximadamente erguida, con el eje Y vertical."
        )
    return scene, mesh_format, vertex_count, face_count, garment_bounds, garment_extents


def _densify_scene(scene: trimesh.Scene, edge_fraction: float = 0.014) -> int:
    """Subdivide coarse garment meshes so sleeves can bend smoothly.

    Low-poly garments (a few hundred triangles) tear when their sleeves are
    bent onto the arm. Each pass splits every triangle in four and carries the
    UV coordinates along. Returns the number of vertices added.
    """
    added = 0
    for geometry in scene.geometry.values():
        if not isinstance(geometry, trimesh.Trimesh):
            continue
        size = float(np.ptp(geometry.vertices, axis=0).max())
        for _ in range(2):
            edges = geometry.vertices[geometry.edges_unique]
            median = float(np.median(np.linalg.norm(edges[:, 0] - edges[:, 1], axis=1)))
            if median <= edge_fraction * size or len(geometry.faces) > 60000:
                break
            visual = geometry.visual
            uv = getattr(visual, "uv", None)
            attributes = {"uv": np.asarray(uv)} if uv is not None else None
            before = len(geometry.vertices)
            result = trimesh.remesh.subdivide(
                np.asarray(geometry.vertices), np.asarray(geometry.faces), vertex_attributes=attributes
            )
            vertices, faces = result[0], result[1]
            if attributes is not None and isinstance(visual, trimesh.visual.TextureVisuals):
                geometry.vertices, geometry.faces = vertices, faces
                geometry.visual = trimesh.visual.TextureVisuals(
                    uv=result[2]["uv"], material=visual.material
                )
            else:
                geometry.vertices, geometry.faces = vertices, faces
                geometry.visual = trimesh.visual.ColorVisuals(geometry)
            added += len(vertices) - before
    return added


def _garment_torso_core(scene: trimesh.Scene):
    """Bounds of a long-sleeve shirt without its sleeves, from the hem width.

    The hem is the narrowest lower band, so sleeves (T/A pose) do not count.
    Returns (bounds (2, 3), hem centre x, hem width).
    """
    points = np.concatenate(
        [
            trimesh.transform_points(np.asarray(scene.geometry[name].vertices, dtype=np.float64), scene.graph[node][0])
            for node in scene.graph.nodes_geometry
            for name in [scene.graph[node][1]]
        ]
    )
    y_low, y_range = points[:, 1].min(), float(np.ptp(points[:, 1]))
    best = None
    for start in np.linspace(0.03, 0.30, 10):
        band = points[np.abs((points[:, 1] - y_low) / y_range - start) <= 0.03]
        if len(band) < 20:
            continue
        # Sleeves that hang down reach the hem band: keep only the cluster of
        # fabric around the middle (a gap between clusters = space between the
        # torso and a hanging sleeve).
        xs = np.sort(band[:, 0])
        cuts = np.flatnonzero(np.diff(xs) > 0.10 * y_range)
        groups = np.split(xs, cuts + 1)
        median = float(np.median(xs))
        group = next((g for g in groups if g[0] <= median <= g[-1]), max(groups, key=len))
        width = float(group[-1] - group[0])
        if len(group) >= 20 and width > 0 and (best is None or width < best[0]):
            best = (width, float((group[0] + group[-1]) / 2))
    if best is None or best[0] <= 0:
        raise GarmentPipelineError("No se pudo medir el ancho del torso de la camisa.")
    width, center = best
    core = points[np.abs(points[:, 0] - center) <= width / 2 * 1.08]
    bounds = np.array(
        [
            [center - width / 2, core[:, 1].min(), core[:, 2].min()],
            [center + width / 2, core[:, 1].max(), core[:, 2].max()],
        ]
    )
    return bounds, center, width


def _garment_armpit_y(vertices: np.ndarray) -> float | None:
    """Height of a sleeveless garment's armpit: its widest level in the upper part."""
    y_low, y_high = float(vertices[:, 1].min()), float(vertices[:, 1].max())
    if y_high - y_low <= 0:
        return None
    best = None
    edges = np.linspace(y_low, y_high, 25)
    for low, high in zip(edges[:-1], edges[1:]):
        if (low + high) / 2 < y_low + 0.45 * (y_high - y_low):
            continue
        slab = vertices[(vertices[:, 1] >= low) & (vertices[:, 1] < high)]
        if len(slab) >= 8:
            width = float(np.ptp(slab[:, 0]))
            if best is None or width > best[0]:
                best = (width, (low + high) / 2)
    return None if best is None else best[1]


def load_garment_mesh(
    contents: bytes,
    filename: str,
    body_mesh: trimesh.Trimesh,
    garment_type: str = "tshirt",
    body_landmarks: dict[str, np.ndarray] | None = None,
    fit: str = "regular",
    edits: dict[str, dict[str, float]] | None = None,
) -> GarmentBuildResult:
    fit = fit.strip().lower()
    if fit not in FIT_MULTIPLIERS:
        raise GarmentPipelineError("Ajuste no admitido. Usa 'tight', 'regular' o 'loose'.")
    looseness = FIT_MULTIPLIERS[fit]
    garment_type = garment_type.strip().lower()
    if garment_type not in SUPPORTED_GARMENT_TYPES:
        raise GarmentPipelineError(
            "Tipo de prenda no admitido. Usa 'tshirt', 'tank', 'longsleeve', 'pants', 'shorts' o 'shoes'."
        )

    if garment_type == "shoes":
        from services.shoe_fit import fit_shoes

        return fit_shoes(contents, filename, body_mesh, body_landmarks)

    (
        scene,
        mesh_format,
        vertex_count,
        face_count,
        garment_bounds,
        garment_extents,
    ) = read_garment_scene(contents, filename)

    bend_sleeves = garment_type in ("longsleeve", "tshirt") and has_arm_bones(body_landmarks)
    if garment_type == "longsleeve":
        if not has_arm_bones(body_landmarks):
            raise GarmentPipelineError(
                "La camisa de manga larga necesita los huesos de los brazos (hombro, codo y muñeca) del avatar."
            )
    if bend_sleeves:
        _densify_scene(scene)
        # Scale by the torso only; the sleeves are bent onto the arm bones later.
        garment_bounds, _, _ = _garment_torso_core(scene)
        garment_extents = garment_bounds[1] - garment_bounds[0]

    pattern = None
    if edits is not None:
        if garment_type not in UPPER_GARMENT_TYPES:
            raise GarmentPipelineError("La modificación por piezas solo está disponible para camisas.")
        # Pieces are found on the uploaded shape; the fitting below keeps the
        # vertex order, so the labels stay valid.
        garment_data = from_scene(scene)
        try:
            pattern = (garment_data, segment(garment_data))
        except SegmentationError as error:
            raise GarmentPipelineError(str(error)) from error

    body_vertices = _validate_body_mesh(body_mesh)
    arm_mask = arm_vertex_mask(body_vertices, body_landmarks)
    arm_excluded = int(arm_mask.sum()) if arm_mask is not None else 0
    leg_centers = None
    pants_profile = None
    is_lower = garment_type in LOWER_GARMENT_TYPES
    if is_lower:
        pants_profile = _body_pants_profile(
            body_vertices,
            body_landmarks,
            hem="knee" if garment_type == "shorts" else "ankle",
            ease=HIP_EASE * looseness,
        )
        target_width = pants_profile.target_width
        target_height = pants_profile.target_height
        center_x = pants_profile.center_x
        center_y = pants_profile.center_y
        center_z = pants_profile.center_z
        body_min_y = pants_profile.body_min_y
        body_height = pants_profile.body_height
        target_depth = pants_profile.target_depth
        target_fraction_low = pants_profile.low_fraction
        target_fraction_high = pants_profile.waist_fraction
        centerline_fractions = pants_profile.centerline_fractions
        centerline_x = pants_profile.centerline_x
        centerline_z = pants_profile.centerline_z
        leg_centers = pants_profile.leg_centers
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
        ) = _body_torso_profile(
            body_vertices,
            body_landmarks,
            ease=TORSO_EASE[garment_type] * looseness,
            armpit=garment_type == "tank",
        )
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
    garment_rotation = np.eye(3, dtype=np.float64)
    if pants_profile is not None and pants_profile.front_direction is not None:
        front_x, front_z = pants_profile.front_direction
        garment_rotation = np.array(
            [
                [front_z, 0.0, front_x],
                [0.0, 1.0, 0.0],
                [-front_x, 0.0, front_z],
            ],
            dtype=np.float64,
        )
    transform[:3, :3] = garment_rotation @ np.diag(
        [scale_x, scale_y, scale_z]
    )
    transform[:3, 3] = target_center - transform[:3, :3] @ source_center

    # Huesos propios de la prenda (skin del GLB): permiten mapear cada pierna
    # de la prenda sobre el hueso correspondiente del cuerpo SAM 3D.
    rig_offsets = None
    rig_joint_count = 0
    if is_lower and mesh_format == "glb" and body_landmarks:
        garment_rig = read_garment_rig(contents)
        if garment_rig is not None:
            source_vertices = np.concatenate(
                [
                    trimesh.transform_points(
                        np.asarray(scene.geometry[geometry_name].vertices, dtype=np.float64),
                        scene.graph[node][0],
                    )
                    for node in scene.graph.nodes_geometry
                    for geometry_name in [scene.graph[node][1]]
                ],
                axis=0,
            )
            rig_weights = lookup_vertex_weights(
                garment_rig,
                source_vertices,
                tolerance=float(np.max(garment_extents)) * 1e-3,
            )
            if rig_weights is not None:
                rig_joints = trimesh.transform_points(
                    garment_rig.joint_positions, transform
                )
                retargeted = retarget_offsets(
                    garment_rig, rig_weights, body_landmarks, rig_joints
                )
                if retargeted is not None:
                    rig_offsets, rig_joint_count = retargeted
    scene.apply_transform(transform)

    target_y_low = body_min_y + body_height * target_fraction_low
    target_y_high = body_min_y + body_height * target_fraction_high
    centerline_y = body_min_y + centerline_fractions * body_height
    reference_x = float(np.interp(center_y, centerline_y, centerline_x))
    reference_z = float(np.interp(center_y, centerline_y, centerline_z))
    garment_leg_centers = None
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
    all_garment_height_fraction = np.clip(
        (all_garment_vertices[:, 1] - target_y_low) / target_height,
        0.0,
        1.0,
    )
    garment_body_fractions = (
        target_fraction_low
        + all_garment_height_fraction
        * (target_fraction_high - target_fraction_low)
    )
    if leg_centers is not None:
        garment_leg_centers = _bilateral_section_centers(
            all_garment_vertices,
            garment_body_fractions,
            centerline_fractions,
            center_x,
        )

    fitted_world_vertices = []
    scene_nodes = list(scene.graph.nodes_geometry)
    rig_cursor = 0
    for node in scene_nodes:
        node_transform, geometry_name = scene.graph[node]
        geometry = scene.geometry[geometry_name]
        world_vertices = trimesh.transform_points(
            np.asarray(geometry.vertices, dtype=np.float64),
            node_transform,
        )
        node_rig_offsets = None
        if rig_offsets is not None:
            node_rig_offsets = rig_offsets[rig_cursor : rig_cursor + len(world_vertices)]
            rig_cursor += len(world_vertices)
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
        if leg_centers is not None and (
            garment_leg_centers is not None or node_rig_offsets is not None
        ):
            geometric_legs = garment_leg_centers is not None
            leg_reference = (
                garment_leg_centers if geometric_legs else leg_centers
            )
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
                leg_reference[:, 0, 0],
            )
            garment_right_x = np.interp(
                body_fractions,
                centerline_fractions,
                leg_reference[:, 1, 0],
            )
            garment_left_z = np.interp(
                body_fractions,
                centerline_fractions,
                leg_reference[:, 0, 1],
            )
            garment_right_z = np.interp(
                body_fractions,
                centerline_fractions,
                leg_reference[:, 1, 1],
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
            if node_rig_offsets is not None:
                # Con huesos, cada vértice sigue a los huesos de su pierna
                # según sus pesos de skin, no una división por mitades en X.
                leg_offset_x = node_rig_offsets[:, 0] - (target_x - reference_x)
                if not geometric_legs:
                    leg_offset_z = np.zeros_like(leg_offset_z)
            world_vertices[:, 0] += leg_blend * leg_offset_x
            world_vertices[:, 2] += leg_blend * leg_offset_z
        fitted_world_vertices.append(world_vertices)

    waist_scale_limited = False
    if pants_profile is not None:
        fitted_vertices = np.concatenate(fitted_world_vertices, axis=0)
        fitted_height_fraction = np.clip(
            (fitted_vertices[:, 1] - target_y_low) / target_height,
            0.0,
            1.0,
        )
        pants_fit_fractions = np.linspace(0.56, 1.0, 18)
        pants_fit_scale_x = []
        pants_fit_scale_z = []
        body_profile_fractions = np.linspace(
            pants_profile.low_fraction,
            pants_profile.waist_fraction,
            len(pants_profile.section_widths),
        )
        for fit_fraction in pants_fit_fractions:
            section_vertices = np.empty((0, 3), dtype=np.float64)
            for half_width in (0.04, 0.08, 0.12, 0.18, 0.25):
                section = np.abs(fitted_height_fraction - fit_fraction) <= half_width
                section_vertices = fitted_vertices[section]
                if len(section_vertices) >= 8:
                    break
            if len(section_vertices) < 8:
                nearest = np.argsort(
                    np.abs(fitted_height_fraction - fit_fraction)
                )[:8]
                section_vertices = fitted_vertices[nearest]
            if len(section_vertices) < 8:
                raise GarmentPipelineError(
                    "La malla del pantalón no permite medir la cintura."
                )
            x_low, x_high = np.quantile(section_vertices[:, 0], [0.05, 0.95])
            z_low, z_high = np.quantile(section_vertices[:, 2], [0.05, 0.95])
            source_width = float(x_high - x_low)
            source_depth = float(z_high - z_low)
            body_fraction = (
                target_fraction_low
                + fit_fraction * (target_fraction_high - target_fraction_low)
            )
            target_section_width = float(
                np.interp(
                    body_fraction,
                    body_profile_fractions,
                    pants_profile.section_widths,
                )
                * PANTS_WAIST_CLEARANCE_FACTOR
            )
            target_section_depth = float(
                np.interp(
                    body_fraction,
                    body_profile_fractions,
                    pants_profile.section_depths,
                )
                * PANTS_WAIST_CLEARANCE_FACTOR
            )
            if source_width <= 0 or source_depth <= 0:
                raise GarmentPipelineError(
                    "La malla del pantalón contiene secciones sin ancho o profundidad."
                )
            raw_scale_x = target_section_width / source_width
            raw_scale_z = target_section_depth / source_depth
            if not 0.5 <= raw_scale_x <= 2.5 or not 0.5 <= raw_scale_z <= 2.5:
                waist_scale_limited = True
            transition = np.clip((fit_fraction - 0.56) / 0.12, 0.0, 1.0)
            transition = transition * transition * (3.0 - 2.0 * transition)
            pants_fit_scale_x.append(
                1.0 + transition * (np.clip(raw_scale_x, 0.5, 2.5) - 1.0)
            )
            pants_fit_scale_z.append(
                1.0 + transition * (np.clip(raw_scale_z, 0.5, 2.5) - 1.0)
            )

        pants_fit_scale_x = _smooth_section_values(
            np.asarray(pants_fit_scale_x, dtype=np.float64)
        )
        pants_fit_scale_z = _smooth_section_values(
            np.asarray(pants_fit_scale_z, dtype=np.float64)
        )
        for index, world_vertices in enumerate(fitted_world_vertices):
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
            target_x = np.interp(
                body_fractions, centerline_fractions, centerline_x
            )
            target_z = np.interp(
                body_fractions, centerline_fractions, centerline_z
            )
            width_scale = np.interp(
                garment_height_fraction,
                pants_fit_fractions,
                pants_fit_scale_x,
                left=1.0,
            )
            depth_scale = np.interp(
                garment_height_fraction,
                pants_fit_fractions,
                pants_fit_scale_z,
                left=1.0,
            )
            world_vertices[:, 0] = target_x + (
                world_vertices[:, 0] - target_x
            ) * width_scale
            world_vertices[:, 2] = target_z + (
                world_vertices[:, 2] - target_z
            ) * depth_scale
            if (
                pants_profile.front_direction is not None
                and pants_profile.posterior_anchor_center_xz is not None
                and pants_profile.posterior_anchor_xz is not None
            ):
                world_vertices = _apply_posterior_waist_anchor(
                    world_vertices,
                    pants_profile.front_direction,
                    pants_profile.posterior_anchor_center_xz,
                    pants_profile.posterior_surface_distance,
                    pants_profile.posterior_clearance,
                    pants_profile.posterior_anchor_y,
                    pants_profile.waist_depth,
                    target_y_low,
                    target_height,
                )
            world_vertices = _apply_waist_contour_clamp(
                world_vertices,
                pants_profile.waist_center_xz,
                pants_profile.waist_contour_radii,
                pants_profile.waist_contour_clearance,
                target_y_low,
                target_height,
            )
            if (
                pants_profile.front_direction is not None
                and pants_profile.waist_center_xz is not None
            ):
                world_vertices = _apply_anterior_waist_clamp(
                    world_vertices,
                    pants_profile.front_direction,
                    pants_profile.waist_center_xz,
                    pants_profile.anterior_surface_distance,
                    pants_profile.posterior_clearance,
                    target_y_low,
                    target_height,
                )
            fitted_world_vertices[index] = world_vertices

    if is_lower and body_landmarks and pants_profile is not None:
        sizes = [len(vertices) for vertices in fitted_world_vertices]
        # Put the garment's crotch at the avatar's crotch (it used to hang lower
        # and leave a panel of fabric between the legs).
        wanted = body_crotch_y(body_landmarks, body_height)
        found = garment_crotch_y(np.concatenate(fitted_world_vertices), center_x, body_height)
        span = target_y_high - target_y_low
        if (
            found is not None
            and target_y_low + 0.1 * span < found < target_y_high - 0.1 * span
            and target_y_low + 0.1 * span < wanted < target_y_high - 0.1 * span
        ):
            for vertices in fitted_world_vertices:
                vertices[:, 1] = np.interp(
                    vertices[:, 1], [target_y_low, found, target_y_high], [target_y_low, wanted, target_y_high]
                )
        shaped, legs_fitted = fit_leg_sections(
            np.concatenate(fitted_world_vertices),
            body_vertices,
            body_landmarks,
            center_x,
            float(target_y_low),
            body_height,
            1.0 + LEG_EASE[garment_type] * looseness,
        )
        fitted_world_vertices = np.split(shaped, np.cumsum(sizes)[:-1])
    else:
        legs_fitted = 0

    if garment_type == "tank" and body_landmarks and "left-shoulder" in body_landmarks:
        # Put the garment's armhole at the avatar's armpit, so the armhole sits
        # where the arm starts instead of above or below it.
        garment_armpit = _garment_armpit_y(np.concatenate(fitted_world_vertices))
        body_armpit = float(
            np.mean([body_landmarks["left-shoulder"][1], body_landmarks["right-shoulder"][1]])
            - 0.06 * body_height
        )
        if garment_armpit is not None and target_y_low < garment_armpit < target_y_high and (
            target_y_low < body_armpit < target_y_high
        ):
            knots_in = [target_y_low, garment_armpit, target_y_high]
            knots_out = [target_y_low, body_armpit, target_y_high]
            # The armhole edge must stay on the torso side of the arm: above the
            # armpit the half width may only grow up to the shoulder joint.
            shoulder_half = float(
                np.mean(
                    [
                        abs(body_landmarks["left-shoulder"][0] - center_x),
                        abs(body_landmarks["right-shoulder"][0] - center_x),
                    ]
                )
            )
            top_half = max(target_width / 2.0, shoulder_half)
            span = max(target_y_high - body_armpit, 1e-6)
            for vertices in fitted_world_vertices:
                vertices[:, 1] = np.interp(vertices[:, 1], knots_in, knots_out)
                rise = np.clip((vertices[:, 1] - body_armpit) / span, 0.0, 1.0)
                limit = target_width / 2.0 + (top_half - target_width / 2.0) * rise**2
                dx = vertices[:, 0] - center_x
                vertices[:, 0] = center_x + np.sign(dx) * np.minimum(np.abs(dx), limit)

    if garment_type == "tank" and has_arm_bones(body_landmarks):
        # The armhole edge must not enter the arm (Blender would project it to
        # the outer side of the arm and leave flaps).
        sizes = [len(vertices) for vertices in fitted_world_vertices]
        cleared, _ = keep_off_arms(
            np.concatenate(fitted_world_vertices),
            center_x,
            body_vertices,
            body_landmarks,
            body_height,
            margin=0.004,
        )
        fitted_world_vertices = np.split(cleared, np.cumsum(sizes)[:-1])

    torso_fitted = False
    if (
        garment_type in UPPER_GARMENT_TYPES
        and body_landmarks
        and "left-shoulder" in body_landmarks
        and "right-shoulder" in body_landmarks
    ):
        # Resize the shirt's torso to the avatar's, level by level: tight/regular/
        # loose then change the silhouette, and the sides stop flaring over the arms.
        sizes = [len(vertices) for vertices in fitted_world_vertices]
        torso_body, _ = without_arms(body_vertices, body_landmarks, body_height)
        shoulder_y = float(
            np.mean([body_landmarks["left-shoulder"][1], body_landmarks["right-shoulder"][1]])
        )
        shaped, torso_fitted = fit_torso_sections(
            np.concatenate(fitted_world_vertices),
            torso_body,
            center_x,
            target_width / 2.0,
            float(target_y_low),
            shoulder_y - 0.06 * body_height,
            body_height,
            SECTION_EASE[garment_type] * looseness,
        )
        fitted_world_vertices = np.split(shaped, np.cumsum(sizes)[:-1])

    sleeves_fitted = 0
    if bend_sleeves:
        sizes = [len(vertices) for vertices in fitted_world_vertices]
        bent, sleeve_info = retarget_sleeves(
            np.concatenate(fitted_world_vertices),
            center_x,
            target_width / 2.0,
            body_vertices,
            body_landmarks,
            body_height,
            radius_margin=1.06 + 0.10 * looseness,
            # Sleeve length scales like the garment's height, not like its width.
            length_scale=scale_y / scale_x,
        )
        fitted_world_vertices = np.split(bent, np.cumsum(sizes)[:-1])
        sleeves_fitted = sleeve_info["sleeves_fitted"]

    if pattern is not None:
        # Applied after the automatic fit, which would otherwise undo them.
        sizes = [len(vertices) for vertices in fitted_world_vertices]
        garment_data, segmentation = pattern
        before = np.concatenate(fitted_world_vertices)
        edited = apply_edits(before, garment_data.faces, garment_data.weld, segmentation, edits)
        edit_report = validate(before, edited, garment_data.faces, garment_data.weld)
        fitted_world_vertices = np.split(edited, np.cumsum(sizes)[:-1])

    for node, world_vertices in zip(scene_nodes, fitted_world_vertices):
        node_transform, geometry_name = scene.graph[node]
        inverse_transform = np.linalg.inv(node_transform)
        scene.geometry[geometry_name].vertices = trimesh.transform_points(
            world_vertices,
            inverse_transform,
        )

    if bend_sleeves:
        armpit_y = (
            float(np.mean([body_landmarks["left-shoulder"][1], body_landmarks["right-shoulder"][1]]))
            - 0.06 * body_height
        )
        # Start the simulation with the sleeves already outside the arms and the
        # closed armpit; Blender then only has to drape the cloth.
        resolve_overlaps(
            scene,
            BodyVolume(body_vertices, np.asarray(body_mesh.faces)),
            margin=max(0.004, body_height * 0.0025),
            min_y=body_min_y + 0.5 * body_height,
            # A widened sleeve must not be pulled back onto the arm.
            max_gap=body_height * (0.007 + 0.008 * looseness)
            + 0.05 * max(
                [0.0] + [e["width"] - 1.0 for k, e in (edits or {}).items() if k.startswith("sleeve")]
            ),
            gap_min_y=armpit_y,
        )

    fit_region = "cadera y piernas" if is_lower else "torso"
    warnings = [
        f"La geometría recibida se ajustó por secciones de {fit_region} SAM 3D y luego se simuló; no se reconstruyó desde una foto.",
        "Antes de simular, Blender proyecta fuera del cuerpo los vértices de la prenda que empiezan en penetración.",
    ]
    if is_lower and (
        leg_centers is None
        or (garment_leg_centers is None and rig_offsets is None)
    ):
        warnings.append(
            "La malla corporal no permitió separar ambas piernas; se aplicó un centrado general por altura."
        )
    if is_lower and (
        pants_profile is not None and not pants_profile.landmark_anchored
    ):
        warnings.append(
            "El avatar no conservó anclas MHR; el pantalón se ajustó solo con secciones de la malla corporal."
        )
    if waist_scale_limited:
        warnings.append(
            "El ajuste de cintura alcanzó el límite de deformación permitido para conservar la estabilidad de la malla."
        )
    if mesh_format == "obj":
        warnings.append(
            "Un OBJ cargado sin sus archivos MTL/texturas conserva la geometría, pero puede quedar sin textura; usa GLB para materiales embebidos."
        )

    metrics: dict[str, int | float | str] = {
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
        "fit_body_arm_vertices_excluded": int(arm_excluded),
        "fit_garment_rig": (
            "skin_joint_retarget" if rig_offsets is not None else "none"
        ),
        "fit_garment_rig_joints": int(rig_joint_count),
    }
    metrics["fit_ease"] = fit
    metrics["fit_legs_fitted"] = legs_fitted
    if pattern is not None and edits:
        metrics["fit_pattern_method"] = pattern[1].method
        metrics["fit_pattern_edits"] = ",".join(sorted(edits))
        metrics["fit_pattern_seam_gap"] = round(edit_report["max_seam_gap"], 6)
        metrics["fit_pattern_flipped_faces"] = edit_report["flipped_faces"]
    metrics["fit_torso_sections"] = bool(torso_fitted)
    if bend_sleeves:
        metrics["fit_sleeves_fitted"] = sleeves_fitted
        if sleeves_fitted < 2:
            warnings.append(
                "No se detectaron ambas mangas (la camisa debe tener los brazos extendidos fuera del torso); las mangas no se ajustaron a los brazos."
            )
    if pants_profile is not None:
        metrics.update(
            {
                "fit_anchor_source": (
                    "mhr70_keypoints"
                    if pants_profile.landmark_anchored
                    else "body_mesh_sections"
                ),
                "fit_waist_fraction": round(pants_profile.waist_fraction, 5),
                "fit_waist_y": round(float(target_y_high), 5),
                "fit_waist_section_width": round(
                    pants_profile.waist_width * PANTS_WAIST_CLEARANCE_FACTOR, 5
                ),
                "fit_waist_section_depth": round(
                    pants_profile.waist_depth * PANTS_WAIST_CLEARANCE_FACTOR, 5
                ),
                "fit_posterior_rise_units": round(
                    pants_profile.posterior_rise, 5
                ),
                "fit_posterior_offset_units": round(
                    pants_profile.posterior_surface_distance
                    + pants_profile.posterior_clearance
                    if pants_profile.posterior_anchor_xz is not None
                    else 0.0,
                    5,
                ),
                "fit_anterior_surface_distance_units": round(
                    pants_profile.anterior_surface_distance, 5
                ),
                "fit_anterior_clearance_units": round(
                    pants_profile.posterior_clearance, 5
                ),
                "fit_waist_contour_clearance_units": round(
                    pants_profile.waist_contour_clearance, 5
                ),
            }
        )
        if pants_profile.posterior_anchor_xz is not None:
            metrics.update(
                {
                    "fit_posterior_anchor_x": round(
                        float(pants_profile.posterior_anchor_xz[0]), 5
                    ),
                    "fit_posterior_anchor_y": round(
                        pants_profile.posterior_anchor_y, 5
                    ),
                    "fit_posterior_anchor_z": round(
                        float(pants_profile.posterior_anchor_xz[1]), 5
                    ),
                    "fit_posterior_clearance_units": round(
                        pants_profile.posterior_clearance, 5
                    ),
                }
            )

    return GarmentBuildResult(
        scene=scene,
        metrics=metrics,
        warnings=tuple(warnings),
        pattern=pattern,
    )
