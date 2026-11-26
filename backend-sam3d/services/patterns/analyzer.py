"""GarmentAnalyzer: geometry and topology of an uploaded garment.

Garment files repeat vertices along UV cuts. `GarmentMesh` keeps both views:
the original vertices (what is deformed and exported) and a welded topology
(`weld` maps original -> welded), used for connectivity, boundaries and seams.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh
from scipy import sparse
from scipy.sparse import csgraph

WELD_TOLERANCE = 1e-5  # share of the garment size


@dataclass
class GarmentMesh:
    vertices: np.ndarray  # (n, 3) original vertices
    faces: np.ndarray  # (m, 3) indices into `vertices`
    uv: np.ndarray | None  # (n, 2)
    weld: np.ndarray  # (n,) welded id of each vertex

    @property
    def welded_faces(self) -> np.ndarray:
        return self.weld[self.faces]

    @property
    def welded_vertices(self) -> np.ndarray:
        count = int(self.weld.max()) + 1
        total = np.zeros((count, 3))
        np.add.at(total, self.weld, self.vertices)
        return total / np.bincount(self.weld, minlength=count)[:, None]


def weld_ids(vertices: np.ndarray) -> np.ndarray:
    size = max(float(np.ptp(vertices, axis=0).max()), 1e-9)
    keys = np.round(vertices / (size * WELD_TOLERANCE)).astype(np.int64)
    _, ids = np.unique(keys, axis=0, return_inverse=True)
    return ids.ravel()


def from_scene(scene: trimesh.Scene) -> GarmentMesh:
    """Concatenate the scene geometry in node order (the order the fitting uses)."""
    vertices, faces, uvs, offset = [], [], [], 0
    for node in scene.graph.nodes_geometry:
        matrix, name = scene.graph[node]
        geometry = scene.geometry[name]
        world = trimesh.transform_points(np.asarray(geometry.vertices, dtype=np.float64), matrix)
        vertices.append(world)
        faces.append(np.asarray(geometry.faces) + offset)
        uv = getattr(geometry.visual, "uv", None)
        # Separate objects never share UV space: shift each one apart.
        uvs.append(None if uv is None else np.asarray(uv, dtype=np.float64) + [2.0 * len(uvs), 0.0])
        offset += len(world)
    vertices = np.concatenate(vertices)
    uv = None if any(u is None for u in uvs) else np.concatenate(uvs)
    return GarmentMesh(vertices, np.concatenate(faces), uv, weld_ids(vertices))


def face_adjacency(faces: np.ndarray) -> np.ndarray:
    """Pairs of faces sharing an edge (by the vertex ids given)."""
    edges = np.sort(faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1)
    owners = np.repeat(np.arange(len(faces)), 3)
    order = np.lexsort((edges[:, 1], edges[:, 0]))
    edges, owners = edges[order], owners[order]
    same = np.all(edges[1:] == edges[:-1], axis=1)
    return np.stack([owners[:-1][same], owners[1:][same]], axis=1)


def connected_faces(count: int, pairs: np.ndarray) -> np.ndarray:
    graph = sparse.coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(count, count))
    return csgraph.connected_components(graph, directed=False)[1]


def boundary_edges(faces: np.ndarray) -> np.ndarray:
    edges = np.sort(faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2), axis=1)
    unique, counts = np.unique(edges, axis=0, return_counts=True)
    return unique[(counts == 1) & (unique[:, 0] != unique[:, 1])]


def boundary_loops(edges: np.ndarray) -> list[np.ndarray]:
    """Connected groups of boundary edges, as vertex id arrays."""
    if not len(edges):
        return []
    ids, local = np.unique(edges, return_inverse=True)
    local = local.reshape(-1, 2)
    graph = sparse.coo_matrix(
        (np.ones(len(local)), (local[:, 0], local[:, 1])), shape=(len(ids), len(ids))
    )
    count, labels = csgraph.connected_components(graph, directed=False)
    return [ids[labels == k] for k in range(count)]


def analyze(mesh: GarmentMesh) -> dict:
    welded = mesh.welded_faces
    size = np.ptp(mesh.vertices, axis=0)
    uv_islands = 0
    if mesh.uv is not None:
        uv_islands = int(connected_faces(len(mesh.faces), face_adjacency(mesh.faces)).max()) + 1
    points = mesh.welded_vertices
    loops = boundary_loops(boundary_edges(welded))
    return {
        "vertices": int(len(mesh.vertices)),
        "welded_vertices": int(len(points)),
        "faces": int(len(mesh.faces)),
        "dimensions": [round(float(v), 4) for v in size],
        "up_axis": "y",
        "has_uv": mesh.uv is not None,
        "uv_islands": uv_islands,
        "components": int(connected_faces(len(welded), face_adjacency(welded)).max()) + 1,
        "openings": [
            {"vertices": int(len(loop)), "center": [round(float(v), 4) for v in points[loop].mean(0)]}
            for loop in sorted(loops, key=len, reverse=True)
            if len(loop) >= 8
        ],
    }
