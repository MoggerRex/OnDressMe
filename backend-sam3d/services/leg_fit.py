"""Fit the legs of pants/shorts to the avatar's thighs, with a chosen ease.

The pants fit scales the waist region only; the leg tubes kept the garment's
own proportions. A hem narrower than the thigh starts inside the leg and
Blender then pushes those vertices out in different directions (flared,
spiky hems). Here each leg is scaled around its own axis, level by level, so
its section is the avatar's thigh/calf section times `ease`.
"""
from __future__ import annotations

import numpy as np

from services.body_skeleton import PART_LEG, label_body_vertices

LEVELS = 14
MIN_INNER_GAP = 0.008  # half gap between the legs, share of body height
BAND = 0.018  # slab half height as a share of body height


def body_crotch_y(landmarks: dict[str, np.ndarray], body_height: float) -> float:
    hip_y = float(np.mean([landmarks["left-hip"][1], landmarks["right-hip"][1]]))
    return hip_y - 0.07 * body_height


def garment_crotch_y(vertices: np.ndarray, center_x: float, body_height: float) -> float | None:
    """Height where the garment's two legs join: lowest fabric on the centre line."""
    # Narrowest centre column that still holds fabric (the inner walls of the
    # legs sit just off the centre, so a wide column would reach the hem).
    for half_width in (0.003, 0.005, 0.008, 0.012):
        column = vertices[np.abs(vertices[:, 0] - center_x) < half_width * body_height]
        if len(column) >= 20:
            return float(column[:, 1].min())
    return None


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _section(points: np.ndarray):
    """Centre (x, z) and half extents (x, z) of a horizontal cross-section."""
    x_low, x_high = np.percentile(points[:, 0], [3, 97])
    z_low, z_high = np.percentile(points[:, 2], [3, 97])
    return (
        np.array([(x_low + x_high) / 2, (z_low + z_high) / 2]),
        np.array([(x_high - x_low) / 2, (z_high - z_low) / 2]),
    )


def fit_leg_sections(
    vertices: np.ndarray,
    body_vertices: np.ndarray,
    landmarks: dict[str, np.ndarray],
    center_x: float,
    hem_y: float,
    body_height: float,
    ease: float,
) -> tuple[np.ndarray, int]:
    """Return garment vertices with each leg tube scaled to the avatar's leg.

    Returns (vertices, number of legs fitted).
    """
    labels = label_body_vertices(body_vertices, landmarks, body_height)
    if labels is None:
        return vertices, 0
    crotch_y = body_crotch_y(landmarks, body_height)
    if crotch_y - hem_y < 0.03 * body_height:
        return vertices, 0

    result = vertices.copy()
    levels = np.linspace(hem_y, crotch_y, LEVELS)
    band = BAND * body_height
    fitted = 0
    for sign in (-1, 1):
        body_side = body_vertices[
            (labels == PART_LEG) & ((body_vertices[:, 0] - center_x) * sign > 0)
        ]
        garment_side = (vertices[:, 0] - center_x) * sign > 0
        scales, centers, targets = [], [], []
        for level in levels:
            body_slab = body_side[np.abs(body_side[:, 1] - level) < band]
            garment_slab = vertices[garment_side & (np.abs(vertices[:, 1] - level) < band)]
            if len(body_slab) < 20 or len(garment_slab) < 12:
                scales.append(None)
                continue
            body_center, body_half = _section(body_slab)
            garment_center, garment_half = _section(garment_slab)
            scales.append(
                np.clip(ease * body_half / np.maximum(garment_half, 1e-6), 0.5, 2.2)
            )
            centers.append(garment_center)
            targets.append(body_center)
        known = [i for i, value in enumerate(scales) if value is not None]
        if len(known) < 3:
            continue
        known_levels = levels[known]
        scale_x = np.array([scales[i][0] for i in known])
        scale_z = np.array([scales[i][1] for i in known])
        garment_cx = np.array([c[0] for c in centers])
        garment_cz = np.array([c[1] for c in centers])
        body_cx = np.array([t[0] for t in targets])
        body_cz = np.array([t[1] for t in targets])

        rows = np.flatnonzero(garment_side & (vertices[:, 1] < crotch_y + band))
        y = vertices[rows, 1]
        # Full effect on the legs, fading out through the crotch.
        weight = 1.0 - _smoothstep((y - (crotch_y - 4 * band)) / (5 * band))
        cx = np.interp(y, known_levels, garment_cx)
        cz = np.interp(y, known_levels, garment_cz)
        sx = 1.0 + weight * (np.interp(y, known_levels, scale_x) - 1.0)
        sz = 1.0 + weight * (np.interp(y, known_levels, scale_z) - 1.0)
        # Move the leg axis onto the avatar's leg axis, then resize around it.
        target_x = cx + weight * (np.interp(y, known_levels, body_cx) - cx)
        target_z = cz + weight * (np.interp(y, known_levels, body_cz) - cz)
        new_x = target_x + (vertices[rows, 0] - cx) * sx
        # With ease, the two legs' inner walls would meet and cross in the narrow
        # gap between the thighs (crumpled panel); keep a small gap between them.
        inner = (new_x - center_x) * sign
        new_x = center_x + sign * np.maximum(inner, MIN_INNER_GAP * body_height * weight)
        result[rows, 0] = new_x
        result[rows, 2] = target_z + (vertices[rows, 2] - cz) * sz
        fitted += 1
    return result, fitted
