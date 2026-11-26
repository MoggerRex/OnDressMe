"""GarmentSegmenter: split a shirt into sewing pieces (one label per face).

Two methods, chosen automatically. Object and material names are never used.

`uv`       The UV layout of a modelled garment usually *is* its sewing pattern:
           each UV island is one piece and the UV cuts are the seams.
           Limit: only valid when the islands look like garment panels.
`geometry` For welded meshes without such islands. Cuts the sleeves with a plane
           at the armpit, front/back with the mid-depth line (shoulder and side
           seams) and the collar as a band around the neck opening.
           Limit: assumes an upright shirt facing +z with sleeves out to the
           sides; boundaries follow existing triangle edges (no triangle is cut).

The result is only labels: the original geometry is untouched.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import sparse
from scipy.sparse import csgraph

from services.patterns.analyzer import (
    GarmentMesh,
    boundary_edges,
    boundary_loops,
    connected_faces,
    face_adjacency,
)

PIECE_NAMES = {
    "front": "Panel delantero",
    "back": "Panel trasero",
    "sleeve_left_front": "Manga izquierda delantera",
    "sleeve_left_back": "Manga izquierda trasera",
    "sleeve_right_front": "Manga derecha delantera",
    "sleeve_right_back": "Manga derecha trasera",
    # Whole sleeves exist only until they are split into the two halves above.
    "sleeve_left": "Manga izquierda",
    "sleeve_right": "Manga derecha",
    "collar": "Cuello",
    "cuff_left": "Puño izquierdo",
    "cuff_right": "Puño derecho",
}
MIN_ISLAND_SHARE = 0.002  # islands smaller than this are merged into a neighbour


class SegmentationError(ValueError):
    pass


@dataclass
class Segmentation:
    labels: np.ndarray  # (faces,) index into `pieces`
    pieces: list[str]  # piece ids
    method: str


def _face_data(mesh: GarmentMesh):
    triangles = mesh.vertices[mesh.faces]
    centers = triangles.mean(axis=1)
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    return centers, np.linalg.norm(cross, axis=1) / 2


def _compact(ids: list[str], labels: np.ndarray, method: str) -> Segmentation:
    present = [name for name in PIECE_NAMES if any(ids[i] == name for i in np.unique(labels))]
    mapping = np.array([present.index(name) if name in present else -1 for name in ids])
    return Segmentation(mapping[labels], present, method)


def _from_uv_islands(mesh: GarmentMesh) -> Segmentation | None:
    if mesh.uv is None:
        return None
    islands = connected_faces(len(mesh.faces), face_adjacency(mesh.faces))
    count = int(islands.max()) + 1
    if not 2 <= count <= 40:  # 2: front and back of a sleeveless top
        return None
    centers, areas = _face_data(mesh)
    total = areas.sum()
    area = np.bincount(islands, weights=areas, minlength=count)
    center = np.stack(
        [np.bincount(islands, weights=areas * centers[:, k], minlength=count) for k in range(3)], 1
    ) / np.maximum(area, 1e-12)[:, None]

    low, high = mesh.vertices.min(0), mesh.vertices.max(0)
    height, width = high[1] - low[1], high[0] - low[0]
    middle_x = (low[0] + high[0]) / 2
    major = [k for k in range(count) if area[k] > 0.04 * total]
    names: dict[int, str] = {}

    # Collar: a thin island high up, around the centre.
    for k in range(count):
        if area[k] <= MIN_ISLAND_SHARE * total:
            continue
        points = mesh.vertices[np.unique(mesh.faces[islands == k])]
        if (
            center[k, 1] > high[1] - 0.12 * height
            and np.ptp(points[:, 1]) < 0.2 * height
            and abs(center[k, 0] - middle_x) < 0.15 * width
            and area[k] < 0.1 * total
        ):
            names[k] = "collar"
    rest = [k for k in major if k not in names]
    # Sleeves: off to one side. Torso panels: centred, told apart by depth.
    sides = [k for k in rest if abs(center[k, 0] - middle_x) > 0.22 * width]
    torso = sorted((k for k in rest if k not in sides), key=lambda k: area[k], reverse=True)[:2]
    if len(torso) != 2:
        return None
    back, front = sorted(torso, key=lambda k: center[k, 2])
    names[front], names[back] = "front", "back"
    for k in sides:
        # The wearer's left is +x for a garment facing +z.
        names[k] = "sleeve_left" if center[k, 0] > middle_x else "sleeve_right"

    # Every other island joins the named piece nearest to it.
    named = list(names)
    for k in range(count):
        if k not in names:
            nearest = min(named, key=lambda j: np.linalg.norm(center[j] - center[k]))
            names[k] = names[nearest]
    ids = [names[k] for k in range(count)]
    return _compact(ids, islands, "uv")


def _torso_profile(points: np.ndarray):
    """(centre x, levels, torso half width per level, armpit height).

    Below the armpit the sleeves are separate from the torso (a gap in x), so
    the central cluster of each height slab is the torso.
    """
    low, height = points[:, 1].min(), np.ptp(points[:, 1])
    levels, halves, centres, gaps = [], [], [], []
    for level in np.linspace(0.04, 0.9, 44):
        xs = np.sort(points[np.abs((points[:, 1] - low) / height - level) <= 0.02, 0])
        if len(xs) < 8:
            continue
        groups = np.split(xs, np.flatnonzero(np.diff(xs) > 0.05 * height) + 1)
        median = np.median(xs)
        group = next((g for g in groups if g[0] <= median <= g[-1]), max(groups, key=len))
        levels.append(low + level * height)
        halves.append((group[-1] - group[0]) / 2)
        centres.append((group[0] + group[-1]) / 2)
        gaps.append(len(groups) >= 3)
    if len(levels) < 4:
        raise SegmentationError("No se pudo medir el torso de la prenda.")
    levels, halves = np.array(levels), np.array(halves)
    hem = levels < low + 0.35 * height
    centre = float(np.median(np.array(centres)[hem])) if hem.any() else float(centres[0])
    separated = [i for i, gap in enumerate(gaps) if gap]
    if separated:
        armpit = separated[-1]
    else:
        # T pose / sleeves touching: the armpit is where the width jumps.
        base = np.median(halves[hem]) if hem.any() else halves[0]
        wider = np.flatnonzero(halves > 1.2 * base)
        armpit = (int(wider[0]) - 1) if len(wider) else int(np.searchsorted(levels, low + 0.65 * height))
    armpit = max(min(armpit, len(levels) - 1), 0)
    return centre, levels[: armpit + 1], halves[: armpit + 1], float(levels[armpit])


def _largest_region(mask: np.ndarray, pairs: np.ndarray, areas: np.ndarray) -> np.ndarray:
    keep = mask[pairs[:, 0]] & mask[pairs[:, 1]]
    regions = connected_faces(len(mask), pairs[keep])
    weights = np.bincount(regions[mask], weights=areas[mask], minlength=regions.max() + 1)
    return mask & (regions == int(weights.argmax())) if mask.any() else mask


def _vertex_distance(mesh: GarmentMesh, sources: np.ndarray) -> np.ndarray:
    """Geodesic (along edges) distance of every welded vertex to `sources`."""
    points, faces = mesh.welded_vertices, mesh.welded_faces
    edges = np.unique(np.sort(faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1), axis=0)
    lengths = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
    graph = sparse.coo_matrix((lengths, (edges[:, 0], edges[:, 1])), shape=(len(points),) * 2).tocsr()
    return csgraph.dijkstra(graph, directed=False, indices=sources, min_only=True)


def _from_geometry(mesh: GarmentMesh) -> Segmentation:
    centers, areas = _face_data(mesh)
    points = mesh.welded_vertices
    low, high = points.min(0), points.max(0)
    height = high[1] - low[1]
    middle_x, levels_below, halves_below, armpit_y = _torso_profile(points)
    half = float(halves_below[-1])  # torso half width at the armpit
    pairs = face_adjacency(mesh.welded_faces)
    ids = ["front", "back", "sleeve_left", "sleeve_right", "collar"]
    labels = np.zeros(len(mesh.faces), dtype=int)

    # Sleeves: beyond the torso edge below the armpit, and beyond the vertical
    # armhole plane above it.
    edge = np.where(
        centers[:, 1] <= armpit_y,
        np.interp(centers[:, 1], levels_below, halves_below) + 0.012 * height,
        half,
    )
    sleeve_any = np.zeros(len(mesh.faces), dtype=bool)
    for sign, name in ((1, "sleeve_left"), (-1, "sleeve_right")):
        mask = (centers[:, 0] - middle_x) * sign > edge
        mask = _largest_region(mask, pairs, areas)
        if areas[mask].sum() > 0.02 * areas.sum():
            labels[mask] = ids.index(name)
            sleeve_any |= mask

    # Front/back: mid-depth of each height level (side and shoulder seams).
    torso = ~sleeve_any
    levels = np.linspace(low[1], high[1], 25)
    middle_z = []
    for level in levels:
        near = points[(np.abs(points[:, 1] - level) < height / 20)
                      & (np.abs(points[:, 0] - middle_x) < half)]
        middle_z.append((near[:, 2].min() + near[:, 2].max()) / 2 if len(near) else np.nan)
    middle_z = np.array(middle_z)
    known = np.isfinite(middle_z)
    middle_z = np.interp(levels, levels[known], middle_z[known])
    # The top levels contain the neck slope only; hold the value below it there.
    middle_z[levels > high[1] - 0.1 * height] = np.interp(high[1] - 0.1 * height, levels, middle_z)
    behind = centers[:, 2] < np.interp(centers[:, 1], levels, middle_z)
    labels[torso & behind] = ids.index("back")
    labels[torso & ~behind] = ids.index("front")

    # Collar: band around the highest opening.
    loops = boundary_loops(boundary_edges(mesh.welded_faces))
    loops = [loop for loop in loops if len(loop) >= 8]
    if loops:
        neck = max(loops, key=lambda loop: points[loop, 1].mean())
        if points[neck, 1].mean() > high[1] - 0.15 * height:
            distance = _vertex_distance(mesh, neck)[mesh.welded_faces].mean(axis=1)
            collar = torso & (distance < 0.028 * height)
            labels[collar] = ids.index("collar")
    return _compact(ids, labels, "geometry")


def _split_sleeves(mesh: GarmentMesh, segmentation: Segmentation) -> Segmentation:
    """Cut each sleeve into a front and a back half.

    The cut is the vertical plane that contains the sleeve axis (armhole centre
    to cuff centre): it continues the shoulder and side seams down the arm.
    """
    names = np.array(segmentation.pieces, dtype=object)[segmentation.labels]
    centers, areas = _face_data(mesh)
    torso_ids = np.unique(mesh.welded_faces[np.isin(names, ("front", "back"))])
    points = mesh.welded_vertices
    for side in ("left", "right"):
        sleeve = names == f"sleeve_{side}"
        if not sleeve.any():
            continue
        ids = np.unique(mesh.welded_faces[sleeve])
        armhole = np.intersect1d(ids, torso_ids)
        start = points[armhole].mean(0) if len(armhole) else points[ids].mean(0)
        distance = np.linalg.norm(points[ids] - start, axis=1)
        axis = points[ids[distance >= np.quantile(distance, 0.92)]].mean(0) - start
        normal = np.cross(axis, [0.0, 1.0, 0.0])
        if np.linalg.norm(normal) < 1e-9:
            normal = np.array([0.0, 0.0, 1.0])
        normal /= np.linalg.norm(normal)
        if normal[2] < 0:
            normal = -normal
        # Centre of the tube along the normal, so a tilted sleeve is halved evenly.
        weights = areas[sleeve] / areas[sleeve].sum()
        middle = float(weights @ ((centers[sleeve] - start) @ normal))
        ahead = (centers - start) @ normal > middle
        if segmentation.method == "uv" and mesh.uv is not None:
            # The centre line of the sleeve's own pattern follows the mesh rows,
            # giving a clean edge. Used only if it agrees with the plane.
            flat = mesh.uv[mesh.faces].mean(axis=1)
            for axis_index in (0, 1):
                values = flat[:, axis_index]
                line = (values[sleeve].min() + values[sleeve].max()) / 2
                side_a = values > line
                agreement = float((side_a == ahead)[sleeve].mean())
                if max(agreement, 1.0 - agreement) > 0.85:
                    ahead = side_a if agreement > 0.5 else ~side_a
                    break
        names[sleeve & ahead] = f"sleeve_{side}_front"
        names[sleeve & ~ahead] = f"sleeve_{side}_back"
    present = [name for name in PIECE_NAMES if (names == name).any()]
    return Segmentation(np.array([present.index(n) for n in names]), present, segmentation.method)


def segment(mesh: GarmentMesh, method: str = "auto") -> Segmentation:
    if method in ("auto", "uv"):
        result = _from_uv_islands(mesh)
        if result is not None:
            return _split_sleeves(mesh, result)
        if method == "uv":
            raise SegmentationError("La prenda no trae un patronaje utilizable en sus UV.")
    result = _from_geometry(mesh)
    if "front" not in result.pieces or "back" not in result.pieces:
        raise SegmentationError("No se pudieron separar el delantero y la espalda.")
    return _split_sleeves(mesh, result)
