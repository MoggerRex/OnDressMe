"""Signed-distance volume of the body, with narrow gaps (armpits) closed.

When an arm rests against the torso, the gap between them is thinner than the
fabric: nearest-surface projection and cloth collision push a vertex into the
arm to clear the torso and vice versa, so the shirt appears to go through the
avatar. Closing the gap (morphological closing of the filled body) turns the
armpit into one solid, so fabric bridges it from the outside instead.

Only numpy/scipy/trimesh are needed (no rtree, no embree).
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy import ndimage

DEFAULT_PITCH_FRACTION = 0.003   # voxel size relative to body height
DEFAULT_CLOSING_FRACTION = 0.013  # closes gaps up to ~2x this fraction of height


class BodyVolume:
    def __init__(
        self,
        vertices: np.ndarray,
        faces: np.ndarray,
        close_gaps: bool = True,
        pitch: float | None = None,
        closing_radius: float | None = None,
    ):
        vertices = np.asarray(vertices, dtype=np.float64)
        height = float(np.ptp(vertices[:, 1]))
        self.pitch = pitch or height * DEFAULT_PITCH_FRACTION
        radius = closing_radius or height * DEFAULT_CLOSING_FRACTION
        steps = max(int(round(radius / self.pitch)), 1) if close_gaps else 0

        mesh = trimesh.Trimesh(vertices, np.asarray(faces), process=False)
        margin = steps + 3
        solid, self.origin = self._voxelize(mesh, margin)
        base = solid
        if steps:
            # Closing = dilate then erode, both as distance thresholds (much
            # faster than a ball structuring element on a large grid).
            reach = steps * self.pitch
            grown = ndimage.distance_transform_edt(~solid, sampling=self.pitch) <= reach
            solid = ndimage.distance_transform_edt(grown, sampling=self.pitch) > reach
            solid |= base
        outside = ndimage.distance_transform_edt(~solid, sampling=self.pitch)
        inside, exits = ndimage.distance_transform_edt(
            solid, sampling=self.pitch, return_indices=True
        )
        # Nearest empty voxel for every solid voxel: a robust way out even on
        # the medial axis of a limb, where the distance gradient is zero.
        self.exits = exits.astype(np.int32)
        sdf = ndimage.gaussian_filter(outside - inside, 1.0)
        self.sdf = sdf.astype(np.float32)
        self.gradient = np.stack(np.gradient(self.sdf, self.pitch), axis=-1).astype(np.float32)

    def _voxelize(self, mesh: trimesh.Trimesh, margin: int):
        """Filled voxel grid from surface samples (independent of triangle size)."""
        count = int(min(max(mesh.area / (self.pitch * 0.5) ** 2, 1000), 3_000_000))
        samples = mesh.sample(count)
        samples = np.vstack((samples, mesh.vertices))
        low = samples.min(axis=0) - margin * self.pitch
        shape = np.ceil((samples.max(axis=0) - low) / self.pitch).astype(int) + margin + 1
        cells = np.floor((samples - low) / self.pitch).astype(int)
        shell = np.zeros(shape, dtype=bool)
        shell[tuple(cells.T)] = True
        sealed = ndimage.binary_dilation(shell)  # close tiny sampling holes
        solid = ndimage.binary_erosion(ndimage.binary_fill_holes(sealed))
        return solid, low + 0.5 * self.pitch

    def _index(self, points: np.ndarray) -> tuple[np.ndarray, ...]:
        cells = np.rint((points - self.origin) / self.pitch).astype(int)
        cells = np.clip(cells, 0, np.array(self.sdf.shape) - 1)
        return tuple(cells.T)

    def signed_distance(self, points: np.ndarray) -> np.ndarray:
        return self.sdf[self._index(np.asarray(points, dtype=np.float64))]

    def push_out(
        self,
        points: np.ndarray,
        margin: float,
        min_y: float = -np.inf,
        tolerance: float | None = None,
        max_push: float | None = None,
    ) -> tuple[np.ndarray, int]:
        """Move points deeper than `tolerance` inside the volume to `margin` outside.

        `max_push` caps how far any point moves (sleeveless garments must not
        drag their armhole edge around the arm).
        """
        points = np.asarray(points, dtype=np.float64).copy()
        tolerance = self.pitch if tolerance is None else tolerance
        moved = np.zeros(len(points), dtype=bool)
        for _ in range(6):
            index = self._index(points)
            distance = self.sdf[index].astype(np.float64)
            active = np.flatnonzero((distance < -tolerance) & (points[:, 1] > min_y))
            if not len(active):
                break
            cells = tuple(axis[active] for axis in index)
            exit_cells = self.exits[(slice(None),) + cells].T
            surface = self.origin + exit_cells * self.pitch
            outward = self.gradient[tuple(exit_cells.T)].astype(np.float64)
            norm = np.linalg.norm(outward, axis=1, keepdims=True)
            fallback = surface - points[active]
            fallback /= np.maximum(np.linalg.norm(fallback, axis=1, keepdims=True), 1e-9)
            outward = np.where(norm > 1e-6, outward / np.maximum(norm, 1e-9), fallback)
            target = surface + outward * margin
            if max_push is not None:
                step = target - points[active]
                length = np.linalg.norm(step, axis=1, keepdims=True)
                step *= np.minimum(1.0, max_push / np.maximum(length, 1e-12))
                target = points[active] + step
            points[active] = target
            moved[active] = True
        return points, int(moved.sum())


def _smooth_displacement(geometry, displacement: np.ndarray, rounds: int = 4) -> np.ndarray:
    """Average each vertex's displacement with its mesh neighbours (no spikes)."""
    from scipy import sparse

    edges = np.asarray(geometry.edges_unique)
    count = len(displacement)
    adjacency = sparse.coo_matrix(
        (np.ones(len(edges) * 2), (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
        shape=(count, count),
    ).tocsr()
    degree = np.maximum(np.asarray(adjacency.sum(axis=1)).ravel(), 1.0)[:, None]
    for _ in range(rounds):
        displacement = 0.5 * displacement + 0.5 * (adjacency @ displacement) / degree
    return displacement


def resolve_overlaps(
    scene: trimesh.Scene,
    volume: BodyVolume,
    margin: float,
    min_y: float,
    max_push: float | None = None,
) -> int:
    """Push every garment vertex out of the closed body volume, in place.

    The push is smoothed over the mesh so the fabric bridges the armpit
    gradually, then pushed once more so nothing is left inside.
    """
    total = 0
    for node in scene.graph.nodes_geometry:
        matrix, name = scene.graph[node]
        geometry = scene.geometry[name]
        world = trimesh.transform_points(np.asarray(geometry.vertices, dtype=np.float64), matrix)
        fixed, count = volume.push_out(world, margin, min_y, max_push=max_push)
        if not count:
            continue
        fixed = world + _smooth_displacement(geometry, fixed - world)
        fixed, _ = volume.push_out(
            fixed, margin, min_y, tolerance=volume.pitch * 0.25, max_push=max_push
        )
        geometry.vertices = trimesh.transform_points(fixed, np.linalg.inv(matrix))
        total += count
    return total
