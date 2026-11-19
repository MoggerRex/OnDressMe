"""Rigid fitting of shoes onto the SAM 3D feet.

Each foot is defined by two fixed points measured on the body mesh: the start
(heel) and the end (toe) of its footprint, so a foot turned in or out is followed.
The shoe is oriented, scaled and placed between those points with a rigid
similarity transform; shoes are not cloth, so Blender is not involved.

Supported shoe meshes: a pair (side by side along X or Z), or a single shoe,
which is mirrored for the other foot. A skinned shoe uses its own toe bone to
decide which end is the toe; otherwise the lower end of the sole is the toe.
"""
from __future__ import annotations

import numpy as np
import trimesh

from services.garment_pipeline import (
    GarmentBuildResult,
    GarmentPipelineError,
    _validate_body_mesh,
    read_garment_scene,
)
from services.garment_rig import read_garment_rig

SHOE_LENGTH_MARGIN = 1.18  # shoe length relative to the foot (heel point to toe point)
SHOE_WIDTH_MARGIN = 1.12  # shoe width relative to the foot width


def _landmark_xz(landmarks, name):
    point = None if landmarks is None else landmarks.get(name)
    if point is None:
        return None
    point = np.asarray(point, dtype=np.float64)
    if point.shape != (3,) or not np.isfinite(point).all():
        return None
    return point[[0, 2]]


def _body_feet(vertices: np.ndarray, landmarks: dict[str, np.ndarray] | None):
    """Start (heel) and end (toe) point of each foot, measured on the body mesh.

    The footprint of each foot (its lowest vertices) gives the foot's own
    axis, so a foot that is turned outwards or inwards is followed exactly. The
    MHR heel/toe keypoints, when present, only pick which end is the toe; without
    them the toe is the flatter end (the heel end carries the ankle column).
    Returns two dicts ordered by X (smaller X first).
    """
    height = float(np.ptp(vertices[:, 1]))
    floor_y = float(vertices[:, 1].min())
    xz = vertices[:, [0, 2]]

    seeds = [_landmark_xz(landmarks, f"{side}-ankle") for side in ("left", "right")]
    if any(seed is None for seed in seeds):
        sole = xz[vertices[:, 1] < floor_y + 0.02 * height]
        if len(sole) < 10:
            raise GarmentPipelineError("No se encontraron los pies en la malla corporal.")
        side = sole[:, 0] < sole[:, 0].mean()
        if side.all() or not side.any():
            raise GarmentPipelineError("No se pudieron separar los dos pies en la malla.")
        seeds = [sole[side].mean(axis=0), sole[~side].mean(axis=0)]
    seeds = np.asarray(seeds)
    nearest = np.argmin(np.linalg.norm(xz[:, None] - seeds[None], axis=2), axis=1)
    close = np.linalg.norm(xz - seeds[nearest], axis=1) <= 0.16 * height

    feet = []
    for index in range(2):
        mine = close & (nearest == index) & (vertices[:, 1] < floor_y + 0.12 * height)
        if mine.sum() < 20:
            raise GarmentPipelineError("La malla corporal no tiene suficientes vértices en el pie.")
        local_floor = float(vertices[mine, 1].min())
        sole_y = local_floor
        footprint = vertices[mine & (vertices[:, 1] < local_floor + 0.03 * height)]
        points = footprint[:, [0, 2]]
        mean = points.mean(axis=0)
        eigenvalues, eigenvectors = np.linalg.eigh(np.cov((points - mean).T))
        axis = eigenvectors[:, int(np.argmax(eigenvalues))]
        side_axis = np.array([-axis[1], axis[0]])
        along = (points - mean) @ axis
        across = (points - mean) @ side_axis
        t_lo, t_hi = np.percentile(along, [0.5, 99.5])
        w_lo, w_hi = np.percentile(across, [0.5, 99.5])
        length, width = float(t_hi - t_lo), float(w_hi - w_lo)
        if not 0.05 * height <= length <= 0.30 * height:
            raise GarmentPipelineError(
                "La huella del pie no tiene una longitud válida para ajustar zapatos."
            )

        side_name = ("left", "right")[index]
        heel_hint = _landmark_xz(landmarks, f"{side_name}-heel")
        toe_hint = _landmark_xz(landmarks, f"{side_name}-big-toe-tip")
        if heel_hint is not None and toe_hint is not None and np.linalg.norm(toe_hint - heel_hint) > 1e-6:
            positive = float(axis @ (toe_hint - heel_hint)) >= 0
            source = "keypoints"
        else:
            # Heel end: carries the ankle column, so its vertices sit higher.
            region = vertices[mine]
            projection = (region[:, [0, 2]] - mean) @ axis
            low_end = region[projection <= t_lo + 0.25 * length, 1].mean()
            high_end = region[projection >= t_hi - 0.25 * length, 1].mean()
            positive = bool(high_end <= low_end)
            source = "foot_profile"
        forward = axis if positive else -axis
        start_t, end_t = (t_lo, t_hi) if positive else (t_hi, t_lo)
        centre = mean + side_axis * (w_lo + w_hi) / 2
        heel = centre + axis * start_t
        toe = centre + axis * end_t
        feet.append(
            {
                "heel": np.array([heel[0], sole_y, heel[1]]),
                "toe": np.array([toe[0], sole_y, toe[1]]),
                "length": length,
                "width": width,
                "forward": np.array([forward[0], 0.0, forward[1]]),
                "sole_y": sole_y,
                "source": source,
            }
        )
    feet.sort(key=lambda foot: float((foot["heel"][0] + foot["toe"][0]) / 2))
    return feet


def _split_pair(geometries) -> tuple[int, float] | None:
    """Return (axis, threshold) when two shoes sit apart along X or Z.

    A split exists where no triangle crosses the cut, with a real share of the
    triangles on both sides (works on sparse meshes, unlike a vertex gap).
    """
    best = None
    for axis in (0, 2):
        spans = np.concatenate(
            [
                np.stack(
                    (
                        np.asarray(g.vertices)[np.asarray(g.faces), axis].min(axis=1),
                        np.asarray(g.vertices)[np.asarray(g.faces), axis].max(axis=1),
                    ),
                    axis=1,
                )
                for g in geometries
            ]
        )
        spans = spans[np.argsort(spans[:, 0])]
        extent = float(spans[:, 1].max() - spans[:, 0].min())
        reach = np.maximum.accumulate(spans[:, 1])
        for index in range(int(len(spans) * 0.2), int(len(spans) * 0.8)):
            gap = float(spans[index + 1, 0] - reach[index])
            if extent > 0 and gap / extent > 0.05 and (best is None or gap / extent > best[0]):
                best = (gap / extent, axis, float(reach[index] + gap / 2))
    return None if best is None else (best[1], best[2])


def _shoe_frame(points: np.ndarray, toe_hint: np.ndarray | None):
    """Return the shoe's 3D heel-to-toe axis, centre, length and bottom Y."""
    xz = points[:, [0, 2]]
    mean = xz.mean(axis=0)
    eigenvalues, eigenvectors = np.linalg.eigh(np.cov((xz - mean).T))
    axis = eigenvectors[:, int(np.argmax(eigenvalues))]
    along = (xz - mean) @ axis
    side = np.array([-axis[1], axis[0]])
    across = (xz - mean) @ side
    t_min, t_max = float(along.min()), float(along.max())
    length = t_max - t_min
    if length <= 0:
        raise GarmentPipelineError("La malla del zapato no tiene longitud válida.")

    if toe_hint is not None and float(np.linalg.norm(toe_hint)) > 1e-9:
        hint = np.asarray(toe_hint, dtype=np.float64)
        forward_xz = axis if float(axis @ hint) >= 0 else -axis
        source = "rig"
    else:
        heel_end = points[along <= t_min + 0.2 * length, 1].mean()
        toe_end = points[along >= t_max - 0.2 * length, 1].mean()
        # The toe box is lower than the heel collar.
        forward_xz = axis if toe_end <= heel_end else -axis
        source = (
            "height_heuristic"
            if abs(toe_end - heel_end) > 0.02 * float(np.ptp(points[:, 1]))
            else "uncertain"
        )
    center = mean + axis * (t_min + t_max) / 2 + side * (float(across.min()) + float(across.max())) / 2
    forward = np.array([forward_xz[0], 0.0, forward_xz[1]])
    center_3d = np.array([center[0], float(points[:, 1].min()), center[1]])
    width = float(across.max() - across.min())
    return forward, center_3d, length, float(points[:, 1].min()), source, width


def _rotation_between(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Return the shortest 3D rotation that aligns two direction vectors."""
    source = source / np.linalg.norm(source)
    target = target / np.linalg.norm(target)
    cross = np.cross(source, target)
    sine = float(np.linalg.norm(cross))
    cosine = float(np.clip(source @ target, -1.0, 1.0))
    if sine < 1e-9:
        if cosine > 0:
            return np.eye(3)
        axis = np.array([0.0, 1.0, 0.0])
        axis -= source * float(axis @ source)
        if np.linalg.norm(axis) < 1e-9:
            axis = np.array([1.0, 0.0, 0.0])
            axis -= source * float(axis @ source)
        axis /= np.linalg.norm(axis)
        return 2.0 * np.outer(axis, axis) - np.eye(3)

    skew = np.array(
        [
            [0.0, -cross[2], cross[1]],
            [cross[2], 0.0, -cross[0]],
            [-cross[1], cross[0], 0.0],
        ]
    )
    return np.eye(3) + skew + skew @ skew * ((1.0 - cosine) / sine**2)


def _rig_toe_direction(rig, shoe_points: np.ndarray):
    """Ankle->toe direction (xz) from the garment's own bones, nearest to a shoe."""
    if rig is None:
        return None
    centre = shoe_points[:, [0, 2]].mean(axis=0)
    toes = [i for i, n in enumerate(rig.joint_names) if "toe" in n.lower()]
    ankles = [
        i for i, n in enumerate(rig.joint_names)
        if rig.joint_parts[i] == "foot" and "toe" not in n.lower()
    ]
    if not toes or not ankles:
        return None
    ankle = min(ankles, key=lambda i: np.linalg.norm(rig.joint_positions[i][[0, 2]] - centre))
    toe = min(toes, key=lambda i: np.linalg.norm(rig.joint_positions[i] - rig.joint_positions[ankle]))
    direction = rig.joint_positions[toe][[0, 2]] - rig.joint_positions[ankle][[0, 2]]
    return direction if np.linalg.norm(direction) > 1e-6 else None


def fit_shoes(contents, filename, body_mesh, body_landmarks) -> GarmentBuildResult:
    scene, mesh_format, vertex_count, face_count, _, _ = read_garment_scene(
        contents, filename, require_upright=False
    )
    body_vertices = _validate_body_mesh(body_mesh)
    feet = _body_feet(body_vertices, body_landmarks)
    rig = read_garment_rig(contents) if mesh_format == "glb" else None

    # Bake node transforms so every geometry lives in world coordinates.
    geometries = []
    for node in scene.graph.nodes_geometry:
        matrix, name = scene.graph[node]
        geometry = scene.geometry[name].copy()
        geometry.vertices = trimesh.transform_points(
            np.asarray(geometry.vertices, dtype=np.float64), matrix
        )
        geometries.append(geometry)
    all_points = np.concatenate([np.asarray(g.vertices) for g in geometries])

    split = _split_pair(geometries)
    labels = [np.zeros(len(g.vertices), dtype=int) for g in geometries]
    if split is not None:
        axis, threshold = split
        labels = [(np.asarray(g.vertices)[:, axis] > threshold).astype(int) for g in geometries]
        layout = "pair_x" if axis == 0 else "pair_z"
        shoe_order = None
    else:
        # A single shoe: mirror it across its own long axis for the other foot.
        xz = all_points[:, [0, 2]]
        mean = xz.mean(axis=0)
        eigenvalues, eigenvectors = np.linalg.eigh(np.cov((xz - mean).T))
        axis_u = eigenvectors[:, int(np.argmax(eigenvalues))]
        side = np.array([-axis_u[1], axis_u[0]])
        for geometry, geometry_labels in list(zip(geometries, labels)):
            mirrored = geometry.copy()
            vertices = np.asarray(mirrored.vertices, dtype=np.float64).copy()
            offset = (vertices[:, [0, 2]] - mean) @ side
            vertices[:, [0, 2]] -= 2.0 * offset[:, None] * side
            mirrored.vertices = vertices
            mirrored.faces = np.asarray(mirrored.faces)[:, ::-1]
            geometries.append(mirrored)
            labels.append(np.ones(len(vertices), dtype=int))
        layout = "single_mirrored"
        shoe_order = {0: 1, 1: 0}  # original -> right foot, mirror -> left foot

    centers = {}
    for label in (0, 1):
        pts = [np.asarray(g.vertices)[l == label] for g, l in zip(geometries, labels)]
        pts = np.concatenate(pts)
        if len(pts) < 8:
            raise GarmentPipelineError("No se encontraron dos zapatos en la malla.")
        centers[label] = pts[:, [0, 2]].mean(axis=0)
    if shoe_order is None:
        by_x = sorted((0, 1), key=lambda label: centers[label][0])
        shoe_order = {label: index for index, label in enumerate(by_x)}

    updated = [np.asarray(g.vertices, dtype=np.float64).copy() for g in geometries]
    scales, sources = [], []
    for label in (0, 1):
        foot = feet[shoe_order[label]]
        pts = np.concatenate(
            [np.asarray(g.vertices)[l == label] for g, l in zip(geometries, labels)]
        )
        forward, center, length, bottom_y, source, shoe_width = _shoe_frame(
            pts, _rig_toe_direction(rig, pts)
        )
        by_length = SHOE_LENGTH_MARGIN * foot["length"] / length
        by_width = SHOE_WIDTH_MARGIN * foot["width"] / shoe_width
        scale = max(by_length, min(by_width, 1.3 * by_length))
        rotation = _rotation_between(forward, foot["forward"])
        target = (foot["heel"] + foot["toe"]) / 2
        masks = [geometry_labels == label for geometry_labels in labels]
        transformed_parts = [
            (vertices[mask] - center) @ rotation.T * scale + target
            for vertices, mask in zip(updated, masks)
        ]
        vertical_offset = foot["sole_y"] - min(
            float(part[:, 1].min()) for part in transformed_parts if len(part)
        )
        for vertices, mask, transformed in zip(updated, masks, transformed_parts):
            transformed[:, 1] += vertical_offset
            vertices[mask] = transformed
        scales.append(scale)
        sources.append(source)

    fitted = trimesh.Scene()
    for geometry, vertices in zip(geometries, updated):
        geometry.vertices = vertices
        fitted.add_geometry(geometry)

    warnings = [
        "Los zapatos se colocaron como cuerpo rígido entre el punto inicial (talón) y final (punta) de la huella de cada pie, siguiendo su giro; no se simulan como tela.",
    ]
    if layout == "single_mirrored":
        warnings.append(
            "La malla traía un solo zapato; se reflejó para el otro pie."
        )
    if "uncertain" in sources:
        warnings.append(
            "No se pudo distinguir la punta del talón del zapato; revisa su orientación o sube un GLB con huesos."
        )
    if mesh_format == "obj":
        warnings.append(
            "Un OBJ cargado sin sus archivos MTL/texturas conserva la geometría, pero puede quedar sin textura; usa GLB para materiales embebidos."
        )
    metrics = {
        "geometry_source": "uploaded_garment_mesh",
        "garment_type": "shoes",
        "source_format": mesh_format,
        "image_use": (
            "embedded_or_mesh_materials" if mesh_format == "glb" else "none_or_external_obj"
        ),
        "garment_vertex_count": vertex_count,
        "garment_face_count": face_count,
        "fit_anchor_source": "foot_footprint_" + feet[0]["source"],
        "fit_shoe_layout": layout,
        "fit_shoe_orientation": "rig" if "rig" in sources else sources[0],
        "fit_shoe_alignment": "heel_toe_3d",
        "fit_shoe_scale_min": round(float(min(scales)), 6),
        "fit_shoe_scale_max": round(float(max(scales)), 6),
        "fit_foot_angle_left_deg": round(float(np.degrees(np.arctan2(feet[0]["forward"][0], feet[0]["forward"][2]))), 2),
        "fit_foot_angle_right_deg": round(float(np.degrees(np.arctan2(feet[1]["forward"][0], feet[1]["forward"][2]))), 2),
        "fit_sole_y": round(float(min(f["sole_y"] for f in feet)), 5),
        "simulation": "rigid_fit",
    }
    return GarmentBuildResult(scene=fitted, metrics=metrics, warnings=tuple(warnings))
