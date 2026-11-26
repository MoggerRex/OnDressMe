"""BodyFitting: compare the fitted garment with the avatar and suggest changes.

Measures the ease (garment perimeter minus body perimeter) at chest, waist, hip
and upper arm, and the width factor that would give the ease wanted for the
chosen fit. Limit: sections are approximated by ellipses (torso) and circles
(arm); the suggestion is a starting point, not a tailor's measurement.
"""
from __future__ import annotations

import numpy as np

from services.body_skeleton import PART_ARM, label_body_vertices, without_arms
from services.patterns.segmenter import Segmentation

# Wanted ease in metres (the avatar is in metres).
TORSO_EASE = {"tight": 0.04, "regular": 0.10, "loose": 0.18}
ARM_EASE = {"tight": 0.025, "regular": 0.05, "loose": 0.09}


def _ellipse_perimeter(a: float, b: float) -> float:
    return float(np.pi * (3 * (a + b) - np.sqrt((3 * a + b) * (a + 3 * b))))


def _section(points: np.ndarray) -> float:
    x = np.percentile(points[:, 0], [3, 97])
    z = np.percentile(points[:, 2], [3, 97])
    return _ellipse_perimeter((x[1] - x[0]) / 2, (z[1] - z[0]) / 2)


def measure(
    vertices: np.ndarray,
    faces: np.ndarray,
    segmentation: Segmentation,
    body_vertices: np.ndarray,
    landmarks: dict[str, np.ndarray],
    fit: str = "regular",
) -> dict:
    height = float(np.ptp(body_vertices[:, 1]))
    pieces = {
        name: np.unique(faces[segmentation.labels == i]) for i, name in enumerate(segmentation.pieces)
    }
    shoulder = (landmarks["left-shoulder"][1] + landmarks["right-shoulder"][1]) / 2
    hip = (landmarks["left-hip"][1] + landmarks["right-hip"][1]) / 2
    torso_body, _ = without_arms(body_vertices, landmarks, height)
    half = abs(landmarks["left-shoulder"][0] - landmarks["right-shoulder"][0]) * 0.85
    torso_body = torso_body[np.abs(torso_body[:, 0]) < max(half, 0.14 * height)]
    garment = vertices[np.concatenate([pieces[k] for k in ("front", "back") if k in pieces])]

    zones = []
    for zone, y in (
        ("pecho", shoulder - 0.09 * height),
        ("cintura", hip + 0.35 * (shoulder - hip)),
        ("cadera", hip + 0.02 * height),
    ):
        band = 0.02 * height
        body_slab = torso_body[np.abs(torso_body[:, 1] - y) < band]
        cloth_slab = garment[np.abs(garment[:, 1] - y) < band]
        if len(body_slab) < 20 or len(cloth_slab) < 12:
            continue
        zones.append((zone, ("front", "back"), _section(body_slab), _section(cloth_slab), TORSO_EASE[fit]))

    labels = label_body_vertices(body_vertices, landmarks, height)
    arms = body_vertices[labels == PART_ARM] if labels is not None else np.empty((0, 3))
    for side in ("left", "right"):
        halves = tuple(k for k in pieces if k.startswith(f"sleeve_{side}"))
        if not halves or not len(arms):
            continue
        start, end = landmarks[f"{side}-shoulder"], landmarks[f"{side}-elbow"]
        axis = (end - start) / np.linalg.norm(end - start)
        reach = float(np.linalg.norm(end - start))

        def ring(points, at):
            t = (points - start) @ axis
            radial = np.linalg.norm(points - start - np.outer(t, axis), axis=1)
            near = (np.abs(t - at) < 0.1 * reach) & (radial < 0.12 * height)
            return 2 * np.pi * float(np.median(radial[near])) if near.sum() >= 8 else None

        cloth = vertices[np.unique(np.concatenate([pieces[k] for k in halves]))]
        arm_ring, cloth_ring = ring(arms, 0.45 * reach), ring(cloth, 0.45 * reach)
        if arm_ring and cloth_ring:
            name = "brazo izquierdo" if side == "left" else "brazo derecho"
            zones.append((name, halves, arm_ring, cloth_ring, ARM_EASE[fit]))

    measurements, wanted = [], {}
    for zone, names, body_size, cloth_size, ease in zones:
        factor = float(np.clip((body_size + ease) / max(cloth_size, 1e-6), 0.7, 1.4))
        measurements.append({
            "zone": zone,
            "body_cm": round(body_size * 100, 1),
            "garment_cm": round(cloth_size * 100, 1),
            "ease_cm": round((cloth_size - body_size) * 100, 1),
            "wanted_ease_cm": round(ease * 100, 1),
        })
        for name in names:
            wanted.setdefault(name, []).append(factor)
    # The tightest zone of a piece decides: use the largest factor it needs.
    suggestions = {
        name: {"width": round(max(factors), 2), "length": 1.0}
        for name, factors in wanted.items()
        if abs(max(factors) - 1.0) >= 0.03
    }
    return {"measurements": measurements, "suggestions": suggestions}
