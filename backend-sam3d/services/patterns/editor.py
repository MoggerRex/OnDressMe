"""PatternEditor + GarmentReconstruction.

An edit changes one piece's width and/or length in its own frame:
- front/back: width around the torso's vertical axis, length below the armpit;
  both fade out towards the shoulders so neck and armholes keep their shape.
- sleeves: width around the armhole-to-cuff axis (none at the armhole), length
  along it.
- collar: radius around its centre; length is the band height.

Reconstruction keeps one position per welded vertex, so seams cannot open.
Where an edited piece meets an unedited one, the seam follows the edited piece
and the difference is spread smoothly (harmonically) over the neighbour.
Limit: this deforms the existing triangles; large factors stretch them, and no
fabric or darts are added. The 3D change approximates the 2D pattern change.
"""
from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve

from services.patterns.analyzer import boundary_edges, boundary_loops
from services.patterns.segmenter import PIECE_NAMES, Segmentation

MIN_FACTOR, MAX_FACTOR = 0.7, 1.4


def parse_edits(raw) -> dict[str, dict[str, float]]:
    """Validate {"piece": {"width": 1.1, "length": 0.9}}; drop neutral edits."""
    if not isinstance(raw, dict):
        raise ValueError("Las modificaciones deben ser un objeto {pieza: {width, length}}.")
    edits = {}
    for piece, values in raw.items():
        if piece not in PIECE_NAMES or not isinstance(values, dict):
            raise ValueError(f"Pieza desconocida: {piece}.")
        clean = {}
        for key, value in values.items():
            if key not in ("width", "length") or isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("Cada pieza admite solo 'width' y 'length' numéricos.")
            if not MIN_FACTOR <= value <= MAX_FACTOR:
                raise ValueError(f"Los factores deben estar entre {MIN_FACTOR} y {MAX_FACTOR}.")
            clean[key] = float(value)
        if any(abs(value - 1.0) > 1e-3 for value in clean.values()):
            edits[piece] = {"width": clean.get("width", 1.0), "length": clean.get("length", 1.0)}
    return edits


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _piece_vertices(faces: np.ndarray, segmentation: Segmentation) -> dict[str, np.ndarray]:
    return {
        name: np.unique(faces[segmentation.labels == index])
        for index, name in enumerate(segmentation.pieces)
    }


def _piece_displacement(name, ids, edit, points, pieces, openings) -> np.ndarray:
    width, length = edit["width"] - 1.0, edit["length"] - 1.0
    p = points[ids]
    move = np.zeros_like(p)
    torso = np.concatenate([pieces[k] for k in ("front", "back") if k in pieces])

    if name in ("front", "back"):
        sleeves = [pieces[k] for k in ("sleeve_left", "sleeve_right") if k in pieces]
        low, high = points[torso, 1].min(), points[torso, 1].max()
        armpit = low + 0.65 * (high - low)
        if sleeves:
            seam = np.intersect1d(torso, np.concatenate(sleeves))
            if len(seam):
                armpit = float(points[seam, 1].min())
        center = (points[torso].min(0) + points[torso].max(0)) / 2
        weight = 1.0 - _smoothstep((p[:, 1] - armpit) / max(high - armpit, 1e-6))
        move[:, 0] = width * weight * (p[:, 0] - center[0])
        move[:, 2] = width * weight * (p[:, 2] - center[2])
        move[:, 1] = -length * np.maximum(armpit - p[:, 1], 0.0)
    elif name.startswith("sleeve"):
        # Both halves share one axis: measure the whole sleeve.
        side = name.rsplit("_", 1)[0]
        whole = np.unique(np.concatenate([v for k, v in pieces.items() if k.startswith(side)]))
        armhole = np.intersect1d(whole, torso)
        if not len(armhole):
            return move
        start = points[armhole].mean(0)
        inside = [loop for loop in openings if np.isin(loop, whole).mean() > 0.8]
        distance = np.linalg.norm(points[whole] - start, axis=1)
        far = whole[np.argsort(-distance)[: max(len(whole) // 20, 3)]]
        end = points[max(inside, key=len)].mean(0) if inside else points[far].mean(0)
        axis = end - start
        size = float(np.linalg.norm(axis))
        if size < 1e-9:
            return move
        axis /= size
        t = (p - start) @ axis / size
        radial = p - start - np.outer(t * size, axis)
        move = width * _smoothstep(t / 0.35)[:, None] * radial
        move += np.outer(length * np.maximum(t, 0.0) * size, axis)
    else:  # collar and cuffs
        center = p.mean(0)
        radial = p - center
        move[:, 0] = width * radial[:, 0]
        move[:, 2] = width * radial[:, 2]
        move[:, 1] = length * (p[:, 1] - p[:, 1].min())
    return move


def _graph_laplacian(faces: np.ndarray, count: int) -> sparse.csr_matrix:
    edges = faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2)
    matrix = sparse.coo_matrix(
        (np.ones(len(edges) * 2), (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
        shape=(count, count),
    ).tocsr()
    matrix.data[:] = 1.0
    return sparse.diags(np.asarray(matrix.sum(1)).ravel()) - matrix


def apply_edits(
    vertices: np.ndarray,
    faces: np.ndarray,
    weld: np.ndarray,
    segmentation: Segmentation,
    edits: dict[str, dict[str, float]],
) -> np.ndarray:
    """Return new vertex positions. `vertices` (any pose) is not modified."""
    edits = {name: edit for name, edit in edits.items() if name in segmentation.pieces}
    if not edits:
        return vertices.copy()
    count = int(weld.max()) + 1
    points = np.zeros((count, 3))
    np.add.at(points, weld, vertices)
    points /= np.bincount(weld, minlength=count)[:, None]
    welded = weld[faces]
    pieces = _piece_vertices(welded, segmentation)
    openings = [loop for loop in boundary_loops(boundary_edges(welded)) if len(loop) >= 8]

    own = {
        name: (
            _piece_displacement(name, ids, edits[name], points, pieces, openings)
            if name in edits else np.zeros((len(ids), 3))
        )
        for name, ids in pieces.items()
    }
    # A sleeve rides along with its armhole: at each height it takes the shift of
    # the edited torso panel there (the underarm moves out, the shoulder stays),
    # otherwise widening the torso would fold the sleeve at the armpit.
    for name, ids in pieces.items():
        if not name.startswith("sleeve"):
            continue
        shared, shift = [], []
        for panel in ("front", "back"):
            if panel in edits and panel in pieces:
                common, _, rows = np.intersect1d(ids, pieces[panel], return_indices=True)
                shared.append(common)
                shift.append(own[panel][rows])
        if not shared or not sum(map(len, shared)):
            continue
        shared, shift = np.concatenate(shared), np.concatenate(shift)
        # Average per height band: front and back shifts at one height are mixed.
        heights = points[shared, 1]
        edges = np.linspace(heights.min(), heights.max() + 1e-9, 9)
        band = np.clip(np.digitize(heights, edges) - 1, 0, 7)
        used = np.unique(band)
        level = np.array([heights[band == k].mean() for k in used])
        mean = np.array([shift[band == k].mean(axis=0) for k in used])
        for axis in range(3):
            own[name][:, axis] += np.interp(points[ids, 1], level, mean[:, axis])
    # Seam vertices: follow the edited pieces that share them.
    total, weight, owners = np.zeros((count, 3)), np.zeros(count), np.zeros(count)
    for name, ids in pieces.items():
        strength = 1.0 if name in edits else 1e-6
        total[ids] += strength * own[name]
        weight[ids] += strength
        owners[ids] += 1
    seam_target = total / np.maximum(weight, 1e-12)[:, None]

    result = np.zeros((count, 3))
    for index, (name, ids) in enumerate(pieces.items()):
        local = np.searchsorted(ids, welded[segmentation.labels == index])
        on_seam = owners[ids] > 1
        correction = np.zeros((len(ids), 3))
        if on_seam.any():
            correction[on_seam] = seam_target[ids[on_seam]] - own[name][on_seam]
            free = np.flatnonzero(~on_seam)
            if len(free):
                laplacian = _graph_laplacian(local, len(ids)).tocsr()
                system = laplacian[free][:, free] + 1e-9 * sparse.eye(len(free))
                right = -(laplacian[free][:, np.flatnonzero(on_seam)] @ correction[on_seam])
                correction[free] = spsolve(system.tocsc(), right)
        result[ids] = own[name] + correction
    seam = owners > 1
    result[seam] = seam_target[seam]
    return vertices + result[weld]
