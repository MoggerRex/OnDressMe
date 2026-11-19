"""Skeleton-aware segmentation of the SAM 3D body mesh.

SAM 3D Body returns 70 MHR keypoints (the "bones" of the avatar). Garment
fitting used to measure the body only by height slices, so hands resting near
the hips were counted as hips. Here every body vertex is assigned to its
nearest bone (distance normalised by the bone's radius, like a rough skinning
weight), which lets the fitter ignore arms and hands when it works on pants.
"""
from __future__ import annotations

import numpy as np


# Keypoints exported by the server. All of them are optional for the pipeline;
# when the arm bones are missing it falls back to the old height-slice logic.
BODY_LANDMARK_NAMES = (
    "left-hip",
    "right-hip",
    "left-knee",
    "right-knee",
    "left-ankle",
    "right-ankle",
    "nose",
    "neck",
    "left-shoulder",
    "right-shoulder",
    "left-elbow",
    "right-elbow",
    "left-wrist",
    "right-wrist",
    "left-middle-tip",
    "right-middle-tip",
    "left-index-tip",
    "right-index-tip",
    "left-pinky-tip",
    "right-pinky-tip",
    "left-thumb-tip",
    "right-thumb-tip",
    "left-big-toe-tip",
    "right-big-toe-tip",
    "left-heel",
    "right-heel",
)

PART_TORSO = "torso"
PART_LEG = "leg"
PART_ARM = "arm"
PART_HEAD = "head"

# (start, end, part, radius as a fraction of body height). Pairs whose
# landmarks are missing are skipped. "hip-center" is the midpoint of both hips.
_BONES = (
    ("hip-center", "neck", PART_TORSO, 0.085),
    ("left-hip", "right-hip", PART_TORSO, 0.050),
    ("left-shoulder", "right-shoulder", PART_TORSO, 0.060),
    ("neck", "nose", PART_HEAD, 0.070),
    ("left-hip", "left-knee", PART_LEG, 0.052),
    ("right-hip", "right-knee", PART_LEG, 0.052),
    ("left-knee", "left-ankle", PART_LEG, 0.036),
    ("right-knee", "right-ankle", PART_LEG, 0.036),
    ("left-ankle", "left-big-toe-tip", PART_LEG, 0.030),
    ("right-ankle", "right-big-toe-tip", PART_LEG, 0.030),
    ("left-ankle", "left-heel", PART_LEG, 0.030),
    ("right-ankle", "right-heel", PART_LEG, 0.030),
    ("left-shoulder", "left-elbow", PART_ARM, 0.032),
    ("right-shoulder", "right-elbow", PART_ARM, 0.032),
    ("left-elbow", "left-wrist", PART_ARM, 0.026),
    ("right-elbow", "right-wrist", PART_ARM, 0.026),
    ("left-wrist", "left-middle-tip", PART_ARM, 0.032),
    ("right-wrist", "right-middle-tip", PART_ARM, 0.032),
    ("left-wrist", "left-index-tip", PART_ARM, 0.022),
    ("right-wrist", "right-index-tip", PART_ARM, 0.022),
    ("left-wrist", "left-pinky-tip", PART_ARM, 0.022),
    ("right-wrist", "right-pinky-tip", PART_ARM, 0.022),
    ("left-wrist", "left-thumb-tip", PART_ARM, 0.022),
    ("right-wrist", "right-thumb-tip", PART_ARM, 0.022),
)

_ARM_LANDMARKS = ("elbow", "wrist")


def _landmark_point(
    landmarks: dict[str, np.ndarray], name: str
) -> np.ndarray | None:
    if name == "hip-center":
        left = _landmark_point(landmarks, "left-hip")
        right = _landmark_point(landmarks, "right-hip")
        if left is None or right is None:
            return None
        return (left + right) * 0.5
    value = landmarks.get(name)
    if value is None:
        return None
    point = np.asarray(value, dtype=np.float64)
    if point.shape != (3,) or not np.isfinite(point).all():
        return None
    return point


def has_arm_bones(landmarks: dict[str, np.ndarray] | None) -> bool:
    """True when both arms have at least an elbow and a wrist bone."""
    if not landmarks:
        return False
    return all(
        _landmark_point(landmarks, f"{side}-{joint}") is not None
        for side in ("left", "right")
        for joint in _ARM_LANDMARKS
    )


def _segment_distances(
    points: np.ndarray, start: np.ndarray, end: np.ndarray
) -> np.ndarray:
    axis = end - start
    length_sq = float(axis @ axis)
    if length_sq < 1e-12:
        return np.linalg.norm(points - start, axis=1)
    t = np.clip(((points - start) @ axis) / length_sq, 0.0, 1.0)
    closest = start + t[:, np.newaxis] * axis
    return np.linalg.norm(points - closest, axis=1)


def label_body_vertices(
    vertices: np.ndarray,
    landmarks: dict[str, np.ndarray],
    body_height: float | None = None,
) -> np.ndarray | None:
    """Return one part label per vertex, or None if the skeleton is unusable."""
    if not has_arm_bones(landmarks):
        return None
    vertices = np.asarray(vertices, dtype=np.float64)
    if body_height is None:
        body_height = float(vertices[:, 1].max() - vertices[:, 1].min())
    if body_height <= 0:
        return None

    scores = []
    parts = []
    for start_name, end_name, part, radius in _BONES:
        start = _landmark_point(landmarks, start_name)
        end = _landmark_point(landmarks, end_name)
        if start is None or end is None:
            continue
        distance = _segment_distances(vertices, start, end)
        scores.append(distance / (radius * body_height))
        parts.append(part)
    if not scores:
        return None

    winner = np.argmin(np.stack(scores, axis=1), axis=1)
    return np.asarray(parts, dtype=object)[winner]


def arm_vertex_mask(
    vertices: np.ndarray,
    landmarks: dict[str, np.ndarray] | None,
    body_height: float | None = None,
) -> np.ndarray | None:
    """Boolean mask of vertices that belong to arms and hands."""
    if not landmarks:
        return None
    labels = label_body_vertices(vertices, landmarks, body_height)
    if labels is None:
        return None
    return labels == PART_ARM


def without_arms(
    vertices: np.ndarray,
    landmarks: dict[str, np.ndarray] | None,
    body_height: float | None = None,
) -> tuple[np.ndarray, int]:
    """Vertices with arm/hand vertices removed, and how many were removed.

    Falls back to the untouched vertices when no skeleton is available or when
    removing the arms would leave too little geometry to measure.
    """
    mask = arm_vertex_mask(vertices, landmarks, body_height)
    if mask is None:
        return vertices, 0
    kept = vertices[~mask]
    if len(kept) < max(30, len(vertices) // 4):
        return vertices, 0
    return kept, int(mask.sum())


def body_without_arms(body_mesh, landmarks):
    """Copy of a trimesh body with arm/hand triangles removed.

    Used as the collision/projection surface for pants so the cloth is never
    pushed onto a hand that rests next to the hip. Returns (mesh, removed
    vertex count). The original mesh is returned when no skeleton is usable.
    """
    import trimesh

    vertices = np.asarray(body_mesh.vertices, dtype=np.float64)
    mask = arm_vertex_mask(vertices, landmarks)
    if mask is None or not mask.any():
        return body_mesh, 0
    faces = np.asarray(body_mesh.faces)
    keep_faces = ~mask[faces].any(axis=1)
    if keep_faces.sum() < len(faces) // 2:
        return body_mesh, 0
    reduced = trimesh.Trimesh(
        vertices=vertices,
        faces=faces[keep_faces],
        process=False,
    )
    reduced.remove_unreferenced_vertices()
    return reduced, int(mask.sum())
