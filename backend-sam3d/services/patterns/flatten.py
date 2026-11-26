"""PatternGenerator: flat 2D patterns for every piece, and the seams between them.

LSCM + ARAP parameterisation. LSCM gives a flat starting shape that keeps
angles; ARAP ("as rigid as possible", local/global) then restores edge
lengths. A tube (sleeve, collar) is first opened along one line. The garment's
UV layout is deliberately not used as the pattern: on the test shirt it
distorts edge lengths ten times more than this.
Limit: a doubly curved surface cannot be flattened exactly; the reported
distortion says how far each pattern is from the 3D lengths. No darts are added.
"""
from __future__ import annotations

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import factorized, spsolve

from services.patterns.analyzer import (
    GarmentMesh,
    boundary_edges,
    boundary_loops,
    connected_faces,
    face_adjacency,
)
from services.patterns.segmenter import Segmentation


def open_tube(points: np.ndarray, faces: np.ndarray, underarm: bool) -> tuple[np.ndarray, np.ndarray]:
    """Cut a tube along one line. Returns (new faces, source vertex of every new vertex).

    The line runs where the angle around the tube axis wraps: the underarm of a
    sleeve (as sewn, which leaves the sleeve cap whole) or the back of a collar.
    The axis joins the centres of the tube's two openings.
    """
    openings = sorted(boundary_loops(boundary_edges(faces)), key=len, reverse=True)[:2]
    first, second = (points[loop].mean(0) for loop in openings)
    center = (first + second) / 2
    axis = second - first
    if not underarm or np.linalg.norm(axis) < 1e-9:
        axis = np.linalg.svd(points - points.mean(0), full_matrices=False)[2][2]  # ring normal
        center = points.mean(0)
    axis /= np.linalg.norm(axis)
    seam_direction = np.array([0.0, -1.0, 0.0]) if underarm else np.array([0.0, 0.0, -1.0])
    seam_direction = seam_direction - axis * (seam_direction @ axis)
    seam_direction /= np.linalg.norm(seam_direction)
    side = np.cross(axis, seam_direction)
    offsets = points[faces].mean(1) - center
    angle = np.arctan2(offsets @ side, -(offsets @ seam_direction))  # +-pi on the seam
    pairs = face_adjacency(faces)
    keep = pairs[np.abs(angle[pairs[:, 0]] - angle[pairs[:, 1]]) < np.pi]

    # A vertex is copied once per fan of faces still connected around it.
    corners = np.arange(faces.size).reshape(faces.shape)
    links = []
    for first, second in keep:
        for vertex in np.intersect1d(faces[first], faces[second]):
            links.append(
                (corners[first][faces[first] == vertex][0], corners[second][faces[second] == vertex][0])
            )
    links = np.array(links) if links else np.zeros((0, 2), dtype=int)
    group = connected_faces(faces.size, links)
    unique, first_index, new_ids = np.unique(group, return_index=True, return_inverse=True)
    return new_ids.reshape(faces.shape), faces.ravel()[first_index]


def _local_triangles(points: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Each triangle laid out isometrically in its own 2D frame: (m, 3, 2)."""
    a, b, c = (points[faces[:, i]] for i in range(3))
    e1, e2 = b - a, c - a
    length = np.maximum(np.linalg.norm(e1, axis=1), 1e-12)
    x = e1 / length[:, None]
    along = np.sum(e2 * x, axis=1)
    height = np.linalg.norm(e2 - x * along[:, None], axis=1)
    zero = np.zeros(len(faces))
    return np.stack(
        [np.stack([zero, zero], 1), np.stack([length, zero], 1), np.stack([along, height], 1)], axis=1
    )


def _lscm(points: np.ndarray, faces: np.ndarray, local: np.ndarray) -> np.ndarray:
    count = len(points)
    area2 = np.abs(local[:, 1, 0] * local[:, 2, 1])
    weight = 1.0 / np.sqrt(np.maximum(area2, 1e-12))
    # Complex edge coefficients of the conformality condition.
    z = local[..., 0] + 1j * local[..., 1]
    coefficient = np.stack([z[:, 2] - z[:, 1], z[:, 0] - z[:, 2], z[:, 1] - z[:, 0]], 1) * weight[:, None]
    rows = np.repeat(np.arange(len(faces)), 3)
    real = sparse.coo_matrix((coefficient.real.ravel(), (rows, faces.ravel())), shape=(len(faces), count))
    imag = sparse.coo_matrix((coefficient.imag.ravel(), (rows, faces.ravel())), shape=(len(faces), count))
    system = sparse.bmat([[real, -imag], [imag, real]]).tocsc()

    # Pin two far apart vertices.
    first = int(np.argmax(np.linalg.norm(points - points.mean(0), axis=1)))
    second = int(np.argmax(np.linalg.norm(points - points[first], axis=1)))
    pinned = np.array([first, second, first + count, second + count])
    values = np.array([0.0, np.linalg.norm(points[first] - points[second]), 0.0, 0.0])
    free = np.setdiff1d(np.arange(2 * count), pinned)
    matrix = system[:, free]
    right = -(system[:, pinned] @ values)
    solution = np.zeros(2 * count)
    solution[pinned] = values
    normal = (matrix.T @ matrix + 1e-10 * sparse.eye(len(free))).tocsc()
    solution[free] = spsolve(normal, matrix.T @ right)
    return np.stack([solution[:count], solution[count:]], axis=1)


def _arap(uv: np.ndarray, faces: np.ndarray, local: np.ndarray, iterations: int = 30) -> np.ndarray:
    count = len(uv)
    edges = [(1, 2, 0), (2, 0, 1), (0, 1, 2)]
    rows, cols, cot, source = [], [], [], []
    for i, j, opposite in edges:
        u, v = local[:, i] - local[:, opposite], local[:, j] - local[:, opposite]
        cross = np.abs(u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0])
        weight = np.clip(np.sum(u * v, axis=1) / np.maximum(cross, 1e-12), 1e-3, 1e3) / 2
        rows.append(faces[:, i])
        cols.append(faces[:, j])
        cot.append(weight)
        source.append(local[:, i] - local[:, j])
    rows, cols = np.concatenate(rows), np.concatenate(cols)
    cot, source = np.concatenate(cot), np.concatenate(source)
    face_of = np.tile(np.arange(len(faces)), 3)

    weights = sparse.coo_matrix(
        (np.r_[cot, cot], (np.r_[rows, cols], np.r_[cols, rows])), shape=(count, count)
    ).tocsr()
    laplacian = (sparse.diags(np.asarray(weights.sum(1)).ravel()) - weights).tocsc()
    solve = factorized(laplacian[1:, 1:].tocsc())

    result = uv.copy()
    for _ in range(iterations):
        # Local step: best rotation of every triangle.
        current = result[rows] - result[cols]
        covariance = np.zeros((len(faces), 2, 2))
        np.add.at(covariance, face_of, cot[:, None, None] * current[:, :, None] * source[:, None, :])
        u, _, vt = np.linalg.svd(covariance)
        flip = np.linalg.det(u @ vt) < 0
        u[flip, :, -1] *= -1
        rotation = u @ vt
        # Global step: positions that best match the rotated triangles.
        target = cot[:, None] * np.einsum("nij,nj->ni", rotation[face_of], source)
        right = np.zeros((count, 2))
        np.add.at(right, rows, target)
        np.add.at(right, cols, -target)
        right -= laplacian[:, [0]].toarray() * result[0]
        for axis in range(2):
            result[1:, axis] = solve(right[1:, axis])
    return result


def _upright(uv: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Rotate (and unmirror) a pattern so that "up" in 3D is +v."""
    centered = uv - uv.mean(0)
    gradient = np.linalg.lstsq(centered, points[:, 1] - points[:, 1].mean(), rcond=None)[0]
    norm = np.linalg.norm(gradient)
    if norm < 1e-9:
        return centered
    up = gradient / norm
    rotation = np.array([[up[1], -up[0]], [up[0], up[1]]])
    return centered @ rotation.T


def flatten(points: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Flat (n, 2) coordinates of a disk-like mesh, in the units of `points`."""
    local = _local_triangles(points, faces)
    return _upright(_arap(_lscm(points, faces, local), faces, local), points)


def _distortion(points: np.ndarray, flat: np.ndarray, faces: np.ndarray) -> dict:
    edges = faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2)
    original = np.linalg.norm(points[edges[:, 0]] - points[edges[:, 1]], axis=1)
    flat_length = np.linalg.norm(flat[edges[:, 0]] - flat[edges[:, 1]], axis=1)
    keep = original > 1e-9
    error = np.abs(flat_length[keep] / original[keep] - 1.0)
    return {"median": round(float(np.median(error)), 4), "p95": round(float(np.percentile(error, 95)), 4)}


def build_patterns(mesh: GarmentMesh, segmentation: Segmentation) -> dict[str, dict]:
    """One pattern per piece: vertices (indices into the mesh), faces and 2D coords."""
    points = mesh.welded_vertices
    patterns = {}
    for index, name in enumerate(segmentation.pieces):
        selected = segmentation.labels == index
        # UV pieces keep the file's own cuts (they are already open); otherwise
        # work on the welded surface and open tubes here.
        topology = mesh.faces if segmentation.method == "uv" else mesh.welded_faces
        source = mesh.vertices if segmentation.method == "uv" else points
        vertex_ids, faces = np.unique(topology[selected], return_inverse=True)
        faces = faces.reshape(-1, 3)
        faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2])
                      & (faces[:, 0] != faces[:, 2])]
        # Stray islands cannot be flattened together with the piece.
        region = connected_faces(len(faces), face_adjacency(faces))
        faces = faces[region == np.bincount(region).argmax()]
        used, faces = np.unique(faces, return_inverse=True)
        faces, vertex_ids = faces.reshape(-1, 3), vertex_ids[used]
        tube = len([l for l in boundary_loops(boundary_edges(faces)) if len(l) >= 8]) >= 2
        if tube and name.startswith(("sleeve", "collar", "cuff")):
            faces, copied = open_tube(source[vertex_ids], faces, underarm=name != "collar")
            vertex_ids = vertex_ids[copied]
        positions = source[vertex_ids]
        flat = flatten(positions, faces)
        boundary = boundary_edges(faces)
        patterns[name] = {
            "faces": faces,
            "flat": flat,
            "positions": positions,
            "vertex_ids": vertex_ids,
            "outline": np.concatenate([flat[boundary[:, 0]], flat[boundary[:, 1]]], axis=1),
            "distortion": _distortion(positions, flat, faces),
        }
    return patterns


def find_seams(mesh: GarmentMesh, segmentation: Segmentation) -> list[dict]:
    """Edges shared by two different pieces: the sewing lines."""
    faces = mesh.welded_faces
    edges = np.sort(faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1)
    owner = np.repeat(segmentation.labels, 3)
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owner = edges[order], owner[order]
    same = np.all(edges[1:] == edges[:-1], axis=1) & (owner[1:] != owner[:-1])
    points = mesh.welded_vertices
    lengths = np.linalg.norm(points[edges[:-1, 0]] - points[edges[:-1, 1]], axis=1)
    seams: dict[tuple[int, int], float] = {}
    for position in np.flatnonzero(same):
        key = tuple(sorted((int(owner[position]), int(owner[position + 1]))))
        seams[key] = seams.get(key, 0.0) + float(lengths[position])
    return [
        {"a": segmentation.pieces[a], "b": segmentation.pieces[b], "length": length}
        for (a, b), length in sorted(seams.items())
    ]
