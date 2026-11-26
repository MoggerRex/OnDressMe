"""Fit the body of a shirt to the avatar's torso, level by level.

A shirt scaled with one width and depth is a box: wider than the avatar at the
waist and hips, so its sides flop over the hanging arms. Here every level of
the shirt below the armpit is resized to the avatar's torso section (arms
excluded) times (1 + ease), so "tight", "regular" and "loose" really change the
silhouette.
"""
from __future__ import annotations

import numpy as np

LEVELS = 12
BAND = 0.02  # slab half height, share of body height


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _section(points: np.ndarray):
    x_low, x_high = np.percentile(points[:, 0], [2, 98])
    z_low, z_high = np.percentile(points[:, 2], [2, 98])
    return (
        np.array([(x_low + x_high) / 2, (z_low + z_high) / 2]),
        np.array([(x_high - x_low) / 2, (z_high - z_low) / 2]),
    )


def fit_torso_sections(
    vertices: np.ndarray,
    body_vertices: np.ndarray,
    center_x: float,
    torso_half_width: float,
    hem_y: float,
    armpit_y: float,
    body_height: float,
    ease: float,
) -> tuple[np.ndarray, bool]:
    """Resize the shirt's torso below `armpit_y`. `body_vertices` must not contain arms.

    Returns (vertices, fitted).
    """
    if armpit_y - hem_y < 0.1 * body_height:
        return vertices, False
    band = BAND * body_height
    levels = np.linspace(hem_y, armpit_y - 2 * band, LEVELS)
    # Vertices of the torso itself; hanging sleeves lie further out.
    in_torso = np.abs(vertices[:, 0] - center_x) <= torso_half_width * 1.12
    central_body = np.abs(body_vertices[:, 0] - center_x) <= torso_half_width * 1.6

    known, scale_x, scale_z, garment_c, body_c = [], [], [], [], []
    for level in levels:
        body_slab = body_vertices[central_body & (np.abs(body_vertices[:, 1] - level) < band)]
        garment_slab = vertices[in_torso & (np.abs(vertices[:, 1] - level) < band)]
        if len(body_slab) < 20 or len(garment_slab) < 12:
            continue
        body_center, body_half = _section(body_slab)
        garment_center, garment_half = _section(garment_slab)
        known.append(level)
        scale_x.append(np.clip((1.0 + ease) * body_half[0] / max(garment_half[0], 1e-6), 0.5, 1.6))
        scale_z.append(np.clip((1.0 + ease) * body_half[1] / max(garment_half[1], 1e-6), 0.5, 1.6))
        garment_c.append(garment_center)
        body_c.append(body_center)
    if len(known) < 3:
        return vertices, False

    known = np.array(known)
    garment_c, body_c = np.array(garment_c), np.array(body_c)
    rows = np.flatnonzero(in_torso & (vertices[:, 1] < armpit_y + band))
    y = vertices[rows, 1]
    # Full effect up to just under the armpit, fading out through it.
    weight = 1.0 - _smoothstep((y - (armpit_y - 4 * band)) / (4 * band))
    sx = 1.0 + weight * (np.interp(y, known, scale_x) - 1.0)
    sz = 1.0 + weight * (np.interp(y, known, scale_z) - 1.0)
    gx, gz = np.interp(y, known, garment_c[:, 0]), np.interp(y, known, garment_c[:, 1])
    bx, bz = np.interp(y, known, body_c[:, 0]), np.interp(y, known, body_c[:, 1])
    target_x = gx + weight * (bx - gx)
    target_z = gz + weight * (bz - gz)

    result = vertices.copy()
    result[rows, 0] = target_x + (vertices[rows, 0] - gx) * sx
    result[rows, 2] = target_z + (vertices[rows, 2] - gz) * sz
    return result, True
