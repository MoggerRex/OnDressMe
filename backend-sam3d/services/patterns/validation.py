"""ClothValidation: geometric checks of a modified garment."""
from __future__ import annotations

import numpy as np
import trimesh

from services.body_volume import BodyVolume
from services.patterns.analyzer import boundary_edges
from services.patterns.segmenter import Segmentation


def _normals_and_areas(vertices, faces):
    cross = np.cross(
        vertices[faces[:, 1]] - vertices[faces[:, 0]], vertices[faces[:, 2]] - vertices[faces[:, 0]]
    )
    size = np.linalg.norm(cross, axis=1)
    return cross / np.maximum(size, 1e-12)[:, None], size / 2


def validate(
    before: np.ndarray,
    after: np.ndarray,
    faces: np.ndarray,
    weld: np.ndarray,
    segmentation: Segmentation | None = None,
    body: trimesh.Trimesh | None = None,
) -> dict:
    """Compare a garment before and after editing (same vertex order)."""
    count = int(weld.max()) + 1
    low = np.full((count, 3), np.inf)
    high = np.full((count, 3), -np.inf)
    np.minimum.at(low, weld, after)
    np.maximum.at(high, weld, after)
    normals_before, areas_before = _normals_and_areas(before, faces)
    normals_after, areas_after = _normals_and_areas(after, faces)
    solid = areas_before > 1e-10
    report = {
        "finite": bool(np.isfinite(after).all()),
        # Distance between the copies of a seam vertex: 0 means no holes opened.
        "max_seam_gap": float(np.max(high - low)),
        "open_edges": int(len(boundary_edges(weld[faces]))),
        "flipped_faces": int((np.sum(normals_before * normals_after, axis=1)[solid] < 0).sum()),
    }
    if segmentation is not None:
        report["area_change"] = {
            name: round(float(
                areas_after[segmentation.labels == i].sum()
                / max(areas_before[segmentation.labels == i].sum(), 1e-12)
            ), 4)
            for i, name in enumerate(segmentation.pieces)
        }
    if body is not None:
        volume = BodyVolume(body.vertices, body.faces, close_gaps=False)
        report["vertices_inside_body"] = int((volume.signed_distance(after) < -0.005).sum())
    return report
