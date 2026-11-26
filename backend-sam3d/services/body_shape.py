"""Make the avatar's build follow the person in the photo.

SAM 3D Body predicts a body from a statistical model, so unusual builds (very
muscular, large bust) come out close to the average. This module measures how
wide each body part looks in the photo compared with the predicted mesh, and
reshapes that part around its bone. The skeleton (joints) is not moved.

Why not just optimise the model's shape parameters against the silhouette: it
matches the outline but fills it with fat (a bodybuilder comes out obese).

Limits:
- measurements come from the silhouette, so loose clothes read as body;
- depth (bust, belly, buttocks) is barely visible in one photo: the bust is only
  estimated in turned (3/4) views. Every factor can be corrected by hand.
"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

from services.body_skeleton import PART_ARM, PART_LEG, PART_TORSO, label_body_vertices

# Factor limits: 1.0 keeps the predicted shape.
FACTOR_RANGES = {
    "chest": (0.85, 1.4),  # chest, back and shoulders
    "waist": (0.8, 1.35),
    "hips": (0.85, 1.4),
    "arms": (0.8, 1.7),
    "legs": (0.8, 1.5),
    "bust": (0.7, 1.8),
}
NEUTRAL = {name: 1.0 for name in FACTOR_RANGES}
SEGMENTS = {
    "arms": (("shoulder", "elbow"), ("elbow", "wrist")),
    "legs": (("hip", "knee"), ("knee", "ankle")),
}


def segmentation_model_path() -> Path:
    configured = os.environ.get("ONDRESSME_SEGMENTATION_MODEL")
    return Path(configured) if configured else Path.home() / ".rembg" / "models" / "u2net_human_seg" / "u2net_human_seg.onnx"


def person_mask(image_rgb: np.ndarray) -> np.ndarray | None:
    """Boolean mask of the person, or None when the segmentation model is absent."""
    path = segmentation_model_path()
    if not path.is_file():
        return None
    network = cv2.dnn.readNetFromONNX(str(path))
    height, width = image_rgb.shape[:2]
    small = cv2.resize(image_rgb, (320, 320)).astype(np.float32)
    small /= max(float(small.max()), 1.0)
    small = (small - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    network.setInput(small.transpose(2, 0, 1)[None].astype(np.float32))
    output = network.forward(network.getUnconnectedOutLayersNames()[0])[0, 0]
    output = (output - output.min()) / max(float(np.ptp(output)), 1e-6)
    mask = cv2.resize(output, (width, height)) > 0.5
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    if count <= 1:
        return None
    return labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))


def vertex_parts(vertices: np.ndarray, landmarks: dict[str, np.ndarray]):
    """Per vertex: part code (0 other, 1 torso, 2 arms, 3 legs)."""
    # "Up" of the labelling is the body's own axis, whatever the coordinate system.
    height = _body_height(vertices, landmarks)
    labels = label_body_vertices(vertices, landmarks, height)
    codes = np.zeros(len(vertices), dtype=np.int32)
    if labels is None:
        return codes
    codes[labels == PART_TORSO] = 1
    codes[labels == PART_ARM] = 2
    codes[labels == PART_LEG] = 3
    return codes


def _body_height(vertices: np.ndarray, landmarks) -> float:
    # Pose independent: about 4 times the neck-to-hip distance.
    hip = (landmarks["left-hip"] + landmarks["right-hip"]) / 2
    return float(3.4 * np.linalg.norm(landmarks["neck"] - hip))


def _along_segment(points, start, end):
    axis = end - start
    t = (points - start) @ axis / max(float(axis @ axis), 1e-12)
    radial = points - start - np.outer(np.clip(t, 0.0, 1.0), axis)
    return t, radial


def _torso_frame(landmarks):
    hip = (landmarks["left-hip"] + landmarks["right-hip"]) / 2
    up = landmarks["neck"] - hip
    length = float(np.linalg.norm(up))
    up = up / length
    lateral = landmarks["left-shoulder"] - landmarks["right-shoulder"]
    lateral = lateral - up * (lateral @ up)
    lateral /= np.linalg.norm(lateral)
    forward = np.cross(lateral, up)
    if (landmarks["nose"] - landmarks["neck"]) @ forward < 0:
        forward = -forward
    return hip, up, length, lateral, forward


def _project(points, focal, size):
    width, height = size
    return np.stack(
        [focal * points[:, 0] / points[:, 2] + width / 2, focal * points[:, 1] / points[:, 2] + height / 2], axis=1
    )


def _part_image(pixels, depth, faces, codes, size):
    """Which part is visible at every pixel (painter's algorithm); 0 = background."""
    width, height = size
    image = np.zeros((height, width), dtype=np.uint8)
    order = np.argsort(-depth[faces].mean(axis=1))
    face_code = codes[faces[:, 0]] + 1  # 1 = other body, 2 torso, 3 arm, 4 leg
    triangles = np.round(pixels[faces]).astype(np.int32)
    for index in order:
        cv2.fillConvexPoly(image, triangles[index], int(face_code[index]))
    return image


def _edge_offset(origin, direction, parts, mask, wanted, limit):
    """(offset beyond the mesh edge, mesh half width) in pixels, or None if hidden."""
    height, width = mask.shape

    def inside(step):
        x, y = np.round(origin + direction * step).astype(int)
        return (x, y) if 0 <= x < width and 0 <= y < height else None

    step = 0
    while True:
        point = inside(step)
        if point is None:
            return None
        if parts[point[1], point[0]] != wanted:
            break
        step += 1
        if step > limit:
            return None
    # Another body part beside this one hides the real outline.
    if parts[point[1], point[0]] != 0 or step < 2:
        return None
    edge = step
    if mask[point[1], point[0]]:
        while step - edge < 0.8 * edge:
            point = inside(step)
            if point is None:
                return None
            if parts[point[1], point[0]] != 0:
                return None
            if not mask[point[1], point[0]]:
                break
            step += 1
        return step - edge, edge
    while step > 0.4 * edge:
        point = inside(step)
        if point is not None and mask[point[1], point[0]]:
            break
        step -= 1
    return step - edge, edge


def _skin_pixels(image_rgb, landmarks, focal, size) -> np.ndarray:
    """Pixels with the colour of this person's face."""
    chroma = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2YCrCb)[:, :, 1:].astype(np.int16)
    nose, neck = _project(np.stack([landmarks["nose"], landmarks["neck"]]), focal, size)
    reach = max(int(0.18 * np.linalg.norm(nose - neck)), 2)
    x, y = np.clip(np.round(nose).astype(int), reach, np.array(size) - reach - 1)
    face = chroma[y - reach : y + reach, x - reach : x + reach].reshape(-1, 2)
    reference = np.median(face, axis=0)
    return np.all(np.abs(chroma - reference) <= (13, 13), axis=2)


def measure_factors(
    vertices: np.ndarray,
    faces: np.ndarray,
    landmarks: dict[str, np.ndarray],
    focal: float,
    mask: np.ndarray,
    image_rgb: np.ndarray | None = None,
) -> dict[str, float]:
    """Compare the mesh with the photo. Everything in camera coordinates."""
    height, width = mask.shape
    size = (width, height)
    codes = vertex_parts(vertices, landmarks)
    pixels = _project(vertices, focal, size)
    parts = _part_image(pixels, vertices[:, 2], faces, codes, size)
    limit = int(0.5 * height)

    def widths(start, end, wanted, positions):
        a, b = _project(np.stack([start, end]), focal, size)
        axis = b - a
        if np.linalg.norm(axis) < 4:
            return []
        normal = np.array([-axis[1], axis[0]]) / np.linalg.norm(axis)
        found = []
        for t in positions:
            origin = a + axis * t
            for sign in (-1, 1):
                result = _edge_offset(origin, normal * sign, parts, mask, wanted, limit)
                if result is not None:
                    found.append((t, result[0] / result[1]))
        return found

    factors = dict(NEUTRAL)
    for name, segments in SEGMENTS.items():
        samples = []
        for side in ("left", "right"):
            for first, second in segments:
                samples += [
                    v for _, v in widths(
                        landmarks[f"{side}-{first}"], landmarks[f"{side}-{second}"],
                        {"arms": 3, "legs": 4}[name], np.linspace(0.3, 0.7, 7),
                    )
                ]
        if len(samples) >= 4:
            factors[name] = 1.0 + float(np.percentile(samples, 60))

    hip, up, length, _, _ = _torso_frame(landmarks)
    for name, low, high in (("hips", -0.05, 0.12), ("waist", 0.28, 0.48), ("chest", 0.6, 0.82)):
        found = widths(hip, hip + up * length, 2, np.linspace(low, high, 6))
        if len(found) >= 3:
            factors[name] = 1.0 + float(np.median([v for _, v in found]))

    factors["bust"] = _measure_bust(vertices, faces, landmarks, focal, mask, codes, parts)

    if image_rgb is not None:
        # A wide outline over bare skin is the body; over clothes it is mostly
        # cloth, so only part of the extra width is believed.
        skin = _skin_pixels(image_rgb, landmarks, focal, size)
        for names, code, trust in ((("chest", "waist", "hips"), 2, 0.4), (("arms",), 3, 0.25), (("legs",), 4, 0.35)):
            region = (parts == code) & mask
            exposed = float(skin[region].mean()) if region.any() else 0.0
            weight = trust + (1.0 - trust) * min(exposed / 0.6, 1.0)
            for name in names:
                if factors[name] > 1.0:
                    # Limit first: an outline far wider than any body is clothing.
                    seen = min(factors[name], FACTOR_RANGES[name][1])
                    factors[name] = 1.0 + (seen - 1.0) * weight
        factors["bust"] = min(factors["bust"], 1.6)
    return {k: round(float(np.clip(v, *FACTOR_RANGES[k])), 2) for k, v in factors.items()}


def _measure_bust(vertices, faces, landmarks, focal, mask, codes, parts) -> float:
    """Only in turned views, where the chest draws part of the outline."""
    hip, up, length, lateral, forward = _torso_frame(landmarks)
    view = -(hip + up * 0.65 * length)  # towards the camera at the origin
    view /= np.linalg.norm(view)
    turn = float(np.degrees(np.arccos(np.clip(forward @ view, -1, 1))))
    if not 20 <= turn <= 80:
        return 1.0
    size = (mask.shape[1], mask.shape[0])
    a, b = _project(np.stack([hip + up * 0.55 * length, hip + up * 0.8 * length]), focal, size)
    axis = b - a
    normal = np.array([-axis[1], axis[0]]) / max(np.linalg.norm(axis), 1e-6)
    ahead = _project(np.stack([hip + up * 0.68 * length + forward * 0.3]), focal, size)[0]
    if (ahead - (a + b) / 2) @ normal < 0:
        normal = -normal
    protrusion = []
    for t in np.linspace(0.0, 1.0, 9):
        result = _edge_offset(a + axis * t, normal, parts, mask, 2, int(0.5 * mask.shape[0]))
        if result is not None:
            depth = float((hip + up * 0.68 * length)[2])
            protrusion.append(result[0] * depth / focal)  # metres
    if len(protrusion) < 3:
        return 1.0
    seen = float(np.percentile(protrusion, 75)) / max(np.sin(np.radians(turn)), 0.35)
    return 1.0 + seen / 0.11 if seen > 0.008 else 1.0


def _smooth(values: np.ndarray, edges: np.ndarray, rounds: int) -> np.ndarray:
    degree = np.maximum(np.bincount(edges.ravel(), minlength=len(values)), 1)[:, None]
    for _ in range(rounds):
        total = np.zeros_like(values)
        np.add.at(total, edges[:, 0], values[edges[:, 1]])
        np.add.at(total, edges[:, 1], values[edges[:, 0]])
        values = 0.5 * values + 0.5 * total / degree
    return values


def sculpt(
    vertices: np.ndarray,
    faces: np.ndarray,
    landmarks: dict[str, np.ndarray],
    factors: dict[str, float],
) -> np.ndarray:
    """New vertices with each part widened around its bone. Joints stay put."""
    factors = {k: float(np.clip(factors.get(k, 1.0), *FACTOR_RANGES[k])) for k in FACTOR_RANGES}
    if all(abs(v - 1.0) < 1e-3 for v in factors.values()):
        return vertices.copy()
    codes = vertex_parts(vertices, landmarks)
    move = np.zeros_like(vertices)
    edges = np.unique(np.sort(faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1), axis=0)

    hip, up, length, lateral, forward = _torso_frame(landmarks)
    torso = np.flatnonzero(codes == 1)
    s = (vertices[torso] - hip) @ up / length
    # Cross-section centre per height, so the back is not pushed out unevenly.
    knots = np.linspace(s.min(), s.max(), 14)
    centres = []
    for knot in knots:
        slab = vertices[torso[np.abs(s - knot) < 0.08]]
        centres.append((slab.min(0) + slab.max(0)) / 2 if len(slab) else hip + up * knot * length)
    centre = np.stack([np.interp(s, knots, np.array(centres)[:, k]) for k in range(3)], axis=1)
    offset = vertices[torso] - centre
    profile = np.interp(
        s, [-0.25, 0.02, 0.38, 0.7, 0.92, 1.05],
        [factors["hips"], factors["hips"], factors["waist"], factors["chest"], factors["chest"], 1.0],
    ) - 1.0
    move[torso] = (
        np.outer(profile * (offset @ lateral), np.ones(3)) * lateral
        + np.outer(0.55 * profile * (offset @ forward), np.ones(3)) * forward
    )

    for name, segments in SEGMENTS.items():
        part = np.flatnonzero(codes == {"arms": 2, "legs": 3}[name])
        if not len(part) or abs(factors[name] - 1.0) < 1e-3:
            continue
        best = np.full(len(part), np.inf)
        shift = np.zeros((len(part), 3))
        for side in ("left", "right"):
            for number, (first, second) in enumerate(segments):
                t, radial = _along_segment(
                    vertices[part], landmarks[f"{side}-{first}"], landmarks[f"{side}-{second}"]
                )
                distance = np.linalg.norm(radial, axis=1)
                better = distance < best
                best[better] = distance[better]
                # Muscle belly in the middle of the bone; joints change less.
                bulge = 0.35 + 0.65 * np.sin(np.pi * np.clip(t, 0.08, 0.92))
                strength = 1.0 if number == 0 else 0.7  # forearm and calf grow less
                # Beyond the wrist or ankle (hands, feet) nothing changes.
                fade = np.clip((1.15 - t) / 0.2, 0.0, 1.0) if number == 1 else 1.0
                shift[better] = (radial * ((factors[name] - 1.0) * strength * bulge * fade)[:, None])[better]
        move[part] = shift
    move = _smooth(move, edges, 8)

    if abs(factors["bust"] - 1.0) > 1e-3:
        amount = (factors["bust"] - 1.0) * 0.11  # metres
        base = hip + up * 0.68 * length
        front = np.flatnonzero((codes == 1) & ((vertices - base) @ forward > 0.0))
        relative = vertices[front] - base
        across, rise = relative @ lateral, relative @ up
        bump = np.zeros(len(front))
        for centre_across in (-0.085, 0.085):
            # Softer above than below the centre, like a real profile.
            vertical = np.where(rise > 0, rise / 0.075, rise / 0.055)
            bump = np.maximum(bump, np.exp(-(((across - centre_across) / 0.065) ** 2 + vertical ** 2)))
        push = np.zeros_like(move)
        push[front] = np.outer(bump * amount, forward) - np.outer(0.25 * bump * max(amount, 0.0), up)
        move += _smooth(push, edges, 3)
    return vertices + move
