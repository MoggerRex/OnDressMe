"""Bend long sleeves onto the avatar's arm bones.

A long-sleeve shirt is usually modelled with its arms stretched out (T/A pose),
while the avatar's arms hang. The sleeve of the shirt is mapped along the arm
polyline shoulder -> elbow -> wrist: a vertex keeps its position along the
sleeve and its offset around the sleeve axis, but the axis becomes the bone
chain and the offset is scaled to the avatar's arm radius.
"""
from __future__ import annotations

import numpy as np

from services.body_skeleton import PART_ARM, label_body_vertices

ARM_RADIUS_MARGIN = 1.15  # sleeve radius relative to the arm radius
BINS = 12
SLABS = 14


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _rotation_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    cross, cosine = np.cross(a, b), float(np.clip(a @ b, -1.0, 1.0))
    sine = float(np.linalg.norm(cross))
    if sine < 1e-9:
        return np.eye(3) if cosine > 0 else np.diag([1.0, -1.0, -1.0])
    skew = np.array(
        [[0, -cross[2], cross[1]], [cross[2], 0, -cross[0]], [-cross[1], cross[0], 0]]
    )
    return np.eye(3) + skew + skew @ skew * ((1.0 - cosine) / sine**2)


class _ArmChain:
    """Shoulder -> elbow -> wrist polyline with arclength lookup."""

    def __init__(self, shoulder, elbow, wrist):
        self.points = np.array([shoulder, elbow, wrist], dtype=np.float64)
        self.segments = np.diff(self.points, axis=0)
        self.lengths = np.linalg.norm(self.segments, axis=1)
        self.total = float(self.lengths.sum())

    def at(self, tau: np.ndarray):
        """Point and unit tangent at fractions `tau` (0..1) of the chain."""
        distance = np.clip(tau, 0.0, 1.0) * self.total
        edge = np.minimum(np.searchsorted(np.cumsum(self.lengths), distance), 1)
        start = np.where(edge == 0, 0.0, self.lengths[0])
        along = (distance - start) / self.lengths[edge]
        tangent = self.segments[edge] / self.lengths[edge][:, None]
        return self.points[edge] + self.segments[edge] * along[:, None], tangent

    def parameter(self, points: np.ndarray):
        """(tau, distance) of the closest point of the chain to each point."""
        best_tau = np.zeros(len(points))
        best_distance = np.full(len(points), np.inf)
        offset = 0.0
        for index in range(2):
            start, segment = self.points[index], self.segments[index]
            t = np.clip(((points - start) @ segment) / (segment @ segment), 0.0, 1.0)
            distance = np.linalg.norm(points - (start + t[:, None] * segment), axis=1)
            better = distance < best_distance
            best_tau[better] = (offset + t[better] * self.lengths[index]) / self.total
            best_distance[better] = distance[better]
            offset += self.lengths[index]
        return best_tau, best_distance


def _rotate_between(offsets: np.ndarray, source: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Rotate each offset by the rotation taking unit vector `source` to `target` (row-wise)."""
    cross = np.cross(source, target)
    sine = np.linalg.norm(cross, axis=1, keepdims=True)
    cosine = np.sum(source * target, axis=1, keepdims=True)
    axis = cross / np.maximum(sine, 1e-12)
    rotated = (
        offsets * cosine
        + np.cross(axis, offsets) * sine
        + axis * np.sum(axis * offsets, axis=1, keepdims=True) * (1.0 - cosine)
    )
    return np.where(sine > 1e-9, rotated, offsets)


class _Centerline:
    """Polyline through the centres of a sleeve cross-sections."""

    def __init__(self, points: np.ndarray):
        self.points = points
        self.segments = np.diff(points, axis=0)
        self.lengths = np.linalg.norm(self.segments, axis=1)
        self.tangents = self.segments / self.lengths[:, None]
        self.starts = np.r_[0.0, np.cumsum(self.lengths)[:-1]]
        self.total = float(self.lengths.sum())

    def locate(self, points: np.ndarray):
        """(arclength s, segment index) per point; s extends past both ends."""
        best = np.full(len(points), np.inf)
        s_out = np.zeros(len(points))
        seg_out = np.zeros(len(points), dtype=int)
        last = len(self.lengths) - 1
        for index in range(len(self.lengths)):
            start, tangent = self.points[index], self.tangents[index]
            along = (points - start) @ tangent
            if index > 0:
                along = np.maximum(along, 0.0)
            if index < last:
                along = np.minimum(along, self.lengths[index])
            distance = np.linalg.norm(points - (start + along[:, None] * tangent), axis=1)
            better = distance < best
            best[better] = distance[better]
            s_out[better] = self.starts[index] + along[better]
            seg_out[better] = index
        return s_out, seg_out


def _sleeve_centerline(sleeve_points, axis, origin, sign, torso_center_x, torso_half_width):
    """Centres of the sleeve tube's cross-sections, extended back to the torso edge."""
    centers = None
    for _ in range(3):
        along = (sleeve_points - origin) @ axis
        low, top = float(np.quantile(along, 0.02)), float(np.quantile(along, 0.995))
        if top - low <= 0:
            return None
        found = []
        # Only the tube (outer 70%): near the shoulder the cloth is not a tube.
        for position in np.linspace(0.3, 1.0, SLABS):
            centre = low + position * (top - low)
            slab = sleeve_points[np.abs(along - centre) <= 0.35 * (top - low) / SLABS * 2]
            if len(slab) >= 8:
                found.append(slab.mean(axis=0))
        if len(found) < 4:
            return None
        centers = np.array(found)
        direction = np.linalg.svd(centers - centers.mean(axis=0))[2][0]
        if direction[0] * sign < 0:
            direction = -direction
        if direction[0] * sign <= 0.2:
            return None
        axis, origin = direction, centers.mean(axis=0)
    centers[1:-1] = 0.25 * centers[:-2] + 0.5 * centers[1:-1] + 0.25 * centers[2:]
    first = centers[2] - centers[0]
    first /= np.linalg.norm(first)
    reach = (centers[0][0] - torso_center_x) * sign - torso_half_width
    if first[0] * sign > 0.1 and reach > 0:
        centers = np.vstack((centers[0] - first * (reach / (first[0] * sign)), centers))
    keep = np.r_[True, np.linalg.norm(np.diff(centers, axis=0), axis=1) > 1e-6]
    centers = centers[keep]
    return centers if len(centers) >= 3 else None


def retarget_sleeves(
    vertices: np.ndarray,
    torso_center_x: float,
    torso_half_width: float,
    body_vertices: np.ndarray,
    landmarks: dict[str, np.ndarray],
    body_height: float,
    radius_margin: float = ARM_RADIUS_MARGIN,
    length_scale: float = 1.0,
) -> tuple[np.ndarray, dict[str, int]]:
    """Return garment vertices with each sleeve bent onto its arm."""
    result = vertices.copy()
    labels = label_body_vertices(body_vertices, landmarks, body_height)
    arm_vertices = body_vertices[labels == PART_ARM] if labels is not None else None
    if arm_vertices is None or len(arm_vertices) == 0:
        return result, {"sleeves_fitted": 0}

    shoulder_x = {s: landmarks[f"{s}-shoulder"][0] for s in ("left", "right")}
    sides = sorted(shoulder_x, key=shoulder_x.get)  # [smaller X, larger X]
    fitted = 0
    for sign, side in zip((-1, 1), sides):
        relative_x = (vertices[:, 0] - torso_center_x) * sign
        # Sleeve vertices are clearly outside the torso; the torso side wall
        # (x == half width) must not be mistaken for sleeve.
        sleeve = relative_x > torso_half_width * 1.05
        if sleeve.sum() < 30:
            continue

        outer = float(np.quantile(relative_x[sleeve], 0.96))
        near = sleeve & (relative_x <= np.quantile(relative_x[sleeve], 0.15))
        tip_band = relative_x >= outer
        if near.sum() < 5 or tip_band.sum() < 5:
            continue
        near_center = vertices[near].mean(axis=0)
        axis = vertices[tip_band].mean(axis=0) - near_center
        length = float(np.linalg.norm(axis))
        if length < 0.05 * body_height or axis[0] * sign <= 0.2 * length:
            continue
        axis /= length
        # Sleeves are often curved: follow the centres of their cross-sections.
        centers = _sleeve_centerline(
            vertices[sleeve], axis, near_center, sign, torso_center_x, torso_half_width
        )
        if centers is None:
            continue
        centerline = _Centerline(centers)

        chain = _ArmChain(
            landmarks[f"{side}-shoulder"], landmarks[f"{side}-elbow"], landmarks[f"{side}-wrist"]
        )
        if chain.total <= 0 or min(chain.lengths) <= 1e-6 or centerline.total <= 0:
            continue

        s, segment = centerline.locate(vertices)
        closest = centerline.points[segment] + centerline.tangents[segment] * (
            s - centerline.starts[segment]
        )[:, None]
        offset = vertices - closest
        radius = np.linalg.norm(offset, axis=1)
        reach = 1.5 * float(np.quantile(radius[sleeve], 0.9))
        weight = _smoothstep((s + 0.1 * centerline.total) / (0.2 * centerline.total)) * (
            1.0 - _smoothstep((radius / reach - 1.0) / 0.5)
        )
        weight[~(relative_x > 0)] = 0.0
        active = weight > 1e-3
        if not active.any():
            continue

        # A sleeve that is most of an arm long ends at the wrist; a short one
        # keeps its own length along the arm.
        reach_fraction = min(centerline.total * length_scale / chain.total, 1.0)
        tau_max = 1.0 if reach_fraction > 0.7 else reach_fraction
        fraction = s / centerline.total
        t_clip = np.clip(fraction, 0.0, 1.0)
        arm_side = arm_vertices[(arm_vertices[:, 0] - torso_center_x) * sign > 0]
        arm_tau, arm_distance = chain.parameter(arm_side)
        # The hand and the shoulder cap project onto the chain ends: not arm tube.
        tube = (arm_tau > 0.001) & (arm_tau < 0.999)
        arm_tau, arm_distance = arm_tau[tube], arm_distance[tube]
        bin_edges = np.linspace(0.0, 1.0, BINS + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        # Arm radius along the chain, indexed by the sleeve fraction it will cover.
        arm_radius = np.array(
            [
                np.median(arm_distance[(arm_tau >= lo * tau_max) & (arm_tau <= hi * tau_max)])
                if ((arm_tau >= lo * tau_max) & (arm_tau <= hi * tau_max)).sum() >= 5 else np.nan
                for lo, hi in zip(bin_edges[:-1], bin_edges[1:])
            ]
        )
        garment_radius = np.array(
            [
                np.median(radius[active & (t_clip >= lo) & (t_clip <= hi)])
                if (active & (t_clip >= lo) & (t_clip <= hi)).sum() >= 5 else np.nan
                for lo, hi in zip(bin_edges[:-1], bin_edges[1:])
            ]
        )
        for values in (arm_radius, garment_radius):
            known = np.isfinite(values)
            if not known.any():
                break
            values[:] = np.interp(bin_centers, bin_centers[known], values[known])
        else:
            scale = np.clip(
                (arm_radius * radius_margin) / np.maximum(garment_radius, 1e-6), 0.45, 1.8
            )
            # Only the middle of the tube measures the sleeve reliably: the ends
            # are shoulder slope and a slanted cuff rim.
            inner = slice(2, BINS - 2)
            trusted = np.convolve(np.pad(scale[inner], 1, mode="edge"), np.ones(3) / 3, mode="valid")
            scale = np.r_[
                np.full(2, trusted[0]), trusted, np.full(2, trusted[-1])
            ]
            arc = fraction * tau_max * chain.total  # distance along the arm chain
            tau = np.clip(arc / chain.total, 0.0, 1.0)
            point, tangent = chain.at(tau)
            factor = np.interp(t_clip, bin_centers, scale)
            # The shoulder cap wraps the deltoid, which the arm label does not include.
            factor *= 1.0 + 0.15 * (1.0 - _smoothstep(arc / (0.15 * chain.total)))
            mapped = _rotate_between(
                offset * factor[:, None], centerline.tangents[segment], tangent
            )
            beyond = arc - tau * chain.total
            target = point + mapped + tangent * beyond[:, None]
            result[active] = (
                (1.0 - weight[active, None]) * vertices[active]
                + weight[active, None] * target[active]
            )
            fitted += 1
    return result, {"sleeves_fitted": fitted}


def keep_off_arms(
    vertices: np.ndarray,
    torso_center_x: float,
    body_vertices: np.ndarray,
    landmarks: dict[str, np.ndarray],
    body_height: float,
    margin: float,
) -> tuple[np.ndarray, int]:
    """Move vertices out of the arm tubes without ever dragging them sideways.

    A sleeveless garment's armhole edge must hug the torso. A vertex that lies
    inside an arm is pushed away from the arm axis, but its outward (lateral)
    component is dropped, so it ends up in front of, behind, above or below the
    arm root instead of wrapping around the outside of the arm.
    """
    labels = label_body_vertices(body_vertices, landmarks, body_height)
    if labels is None:
        return vertices, 0
    arm_vertices = body_vertices[labels == PART_ARM]
    result = vertices.copy()
    moved = 0
    shoulder_x = {s: landmarks[f"{s}-shoulder"][0] for s in ("left", "right")}
    for sign, side in zip((-1, 1), sorted(shoulder_x, key=shoulder_x.get)):
        chain = _ArmChain(
            landmarks[f"{side}-shoulder"], landmarks[f"{side}-elbow"], landmarks[f"{side}-wrist"]
        )
        arm_side = arm_vertices[(arm_vertices[:, 0] - torso_center_x) * sign > 0]
        if len(arm_side) < 30 or chain.total <= 0:
            continue
        arm_tau, arm_distance = chain.parameter(arm_side)
        edges = np.linspace(0.0, 1.0, BINS + 1)
        centers = (edges[:-1] + edges[1:]) / 2
        radii = np.array(
            [
                np.median(arm_distance[(arm_tau >= lo) & (arm_tau <= hi)])
                if ((arm_tau >= lo) & (arm_tau <= hi)).sum() >= 5 else np.nan
                for lo, hi in zip(edges[:-1], edges[1:])
            ]
        )
        known = np.isfinite(radii)
        if not known.any():
            continue
        radii = np.interp(centers, centers[known], radii[known])

        near_side = (vertices[:, 0] - torso_center_x) * sign > 0
        tau, distance = chain.parameter(vertices)
        radius = np.interp(tau, centers, radii) + margin
        inside = near_side & (distance < radius) & (tau < 0.6)
        if not inside.any():
            continue
        axis_point, tangent = chain.at(tau[inside])
        direction = vertices[inside] - axis_point
        outward = direction[:, 0] * sign > 0
        direction[outward, 0] = 0.0  # never push to the outer side of the arm
        # Only the part perpendicular to the arm axis moves a point away from it.
        direction -= tangent * np.sum(direction * tangent, axis=1, keepdims=True)
        norm = np.linalg.norm(direction, axis=1, keepdims=True)
        # Degenerate (on the axis): straight forward/back, perpendicular to the arm.
        forward = np.array([0.0, 0.0, 1.0]) - tangent * tangent[:, 2:3]
        forward /= np.maximum(np.linalg.norm(forward, axis=1, keepdims=True), 1e-9)
        direction = np.where(norm > 1e-6, direction / np.maximum(norm, 1e-9), forward)
        result[inside] = axis_point + direction * radius[inside, None]
        moved += int(inside.sum())
    return result, moved
