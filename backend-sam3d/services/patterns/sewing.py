"""Mount a shirt by sewing its cut pieces on the avatar (cloth simulation).

- rest shape: the pieces as designed, resized to the avatar's girth (plus the
  ease of the chosen fit) and with the user's per-piece changes;
- start: the pieces placed around the body with the arms lifted, almost
  undeformed;
- Blender pulls the seams together (sewing springs) and lets the cloth hang by
  gravity and body contact. Nothing is pinned, so the shoulders rest naturally.

The result keeps the uploaded vertex order, so UVs and materials survive.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree

from services.body_skeleton import PART_ARM, label_body_vertices, without_arms
from services.body_volume import BodyVolume
from services.patterns.analyzer import GarmentMesh, boundary_edges
from services.patterns.editor import apply_edits
from services.patterns.fitting import ARM_EASE, TORSO_EASE, _ellipse_perimeter
from services.patterns.segmenter import Segmentation
from services.sleeve_fit import _ArmChain, _rotate_between

SCRIPT = Path(__file__).resolve().parents[2] / "simulation" / "scripts" / "sew_garment.py"
PIECE_SPREAD = 0.012  # metres each piece starts away from its neighbours
ARM_OPEN_ANGLE = 0.45  # radians the arms are lifted while sewing
SIMULATION_LIMIT = 9000  # piece vertices above which a light copy is simulated
SIMULATION_TARGET = 5000
MAX_SEAM_GAP = 0.05  # metres; 5 % of the stitches may stay wider than this
STITCH_REACH = 0.012  # share of the garment height: slits narrower than this are sewn


def _perimeter(points: np.ndarray) -> float:
    x = np.percentile(points[:, 0], [2, 98])
    z = np.percentile(points[:, 2], [2, 98])
    return _ellipse_perimeter((x[1] - x[0]) / 2, (z[1] - z[0]) / 2)


def _vertices_of(mesh: GarmentMesh, segmentation: Segmentation, prefix) -> np.ndarray:
    wanted = [i for i, name in enumerate(segmentation.pieces) if name.startswith(prefix)]
    if not wanted:
        return np.zeros(0, dtype=int)
    return np.unique(mesh.faces[np.isin(segmentation.labels, wanted)])


def rest_shape(
    mesh: GarmentMesh,
    segmentation: Segmentation,
    scale_y: float,
    body_vertices: np.ndarray,
    landmarks: dict[str, np.ndarray],
    fit: str,
) -> np.ndarray:
    """The designed pieces at the size this avatar needs (metres)."""
    center = (mesh.vertices.min(0) + mesh.vertices.max(0)) / 2
    rest = (mesh.vertices - center) * scale_y
    height = float(np.ptp(body_vertices[:, 1]))
    torso = _vertices_of(mesh, segmentation, ("front", "back"))

    # Torso: widen or narrow so the girth is the avatar's plus the ease.
    body, _ = without_arms(body_vertices, landmarks, height)
    body = body[np.abs(body[:, 0]) < 0.2 * height]
    shoulder = (landmarks["left-shoulder"][1] + landmarks["right-shoulder"][1]) / 2
    hip = (landmarks["left-hip"][1] + landmarks["right-hip"][1]) / 2
    low, high = rest[torso, 1].min(), rest[torso, 1].max()
    # Where each zone falls on the shirt, as a share of its height (hem = 0).
    zones = ((0.12, hip + 0.02 * height), (0.38, hip + 0.35 * (shoulder - hip)),
             (0.66, shoulder - 0.09 * height))
    levels, factors = [], []
    for share, body_y in zones:
        cloth_y = low + share * (high - low)
        cloth = rest[torso[np.abs(rest[torso, 1] - cloth_y) < 0.06 * (high - low)]]
        slab = body[np.abs(body[:, 1] - body_y) < 0.02 * height]
        if len(cloth) >= 12 and len(slab) >= 20:
            levels.append(cloth_y)
            factors.append((_perimeter(slab) + TORSO_EASE[fit]) / _perimeter(cloth))
    if factors:
        # A T-shirt hangs fairly straight: never much narrower than its widest zone.
        factors = np.clip(np.maximum(factors, 0.9 * max(factors)), 0.6, 1.8)
        body_part = _vertices_of(mesh, segmentation, ("front", "back", "collar"))
        scale = np.interp(rest[body_part, 1], levels, factors)
        middle = rest[torso].mean(0)
        # The neckline keeps its size.
        fade = np.clip((high - rest[body_part, 1]) / (0.2 * (high - low)), 0.0, 1.0)
        scale = 1.0 + fade * (scale - 1.0)
        for axis in (0, 2):
            rest[body_part, axis] = middle[axis] + (rest[body_part, axis] - middle[axis]) * scale

    # Sleeves: girth of the upper arm plus ease, measured around each sleeve axis.
    labels = label_body_vertices(body_vertices, landmarks, height)
    arms = body_vertices[labels == PART_ARM] if labels is not None else np.empty((0, 3))
    for side, sign in (("left", 1), ("right", -1)):
        sleeve = _vertices_of(mesh, segmentation, (f"sleeve_{side}",))
        if not len(sleeve) or not len(arms):
            continue
        shared = np.isin(mesh.weld[sleeve], mesh.weld[torso])
        if not shared.any():
            continue
        start = rest[sleeve[shared]].mean(0)
        far = np.linalg.norm(rest[sleeve] - start, axis=1)
        end = rest[sleeve[far >= np.quantile(far, 0.92)]].mean(0)
        axis = (end - start) / np.linalg.norm(end - start)
        along = (rest[sleeve] - start) @ axis
        radial = rest[sleeve] - start - np.outer(along, axis)
        length = float(along.max())
        ring = (along > 0.55 * length) & (along < 0.85 * length)
        shoulder_point, elbow = landmarks[f"{side}-shoulder"], landmarks[f"{side}-elbow"]
        bone = (elbow - shoulder_point) / np.linalg.norm(elbow - shoulder_point)
        reach = float(np.linalg.norm(elbow - shoulder_point))
        arm = arms[arms[:, 0] * sign > 0]
        t = (arm - shoulder_point) @ bone
        off = np.linalg.norm(arm - shoulder_point - np.outer(t, bone), axis=1)
        upper = off[(t > 0.35 * reach) & (t < 0.65 * reach) & (off < 0.1 * height)]
        if ring.sum() < 8 or len(upper) < 8:
            continue
        factor = (2 * np.pi * np.median(upper) + ARM_EASE[fit]) / (
            2 * np.pi * np.median(np.linalg.norm(radial[ring], axis=1))
        )
        factor = float(np.clip(factor, 0.6, 1.6))
        grow = np.clip(along / (0.3 * length), 0.0, 1.0)  # the armhole stays as cut
        rest[sleeve] += radial * (grow * (factor - 1.0))[:, None]
    return rest


def split_pieces(mesh: GarmentMesh, segmentation: Segmentation):
    """Separate the pieces: (faces, welded id of every new vertex, piece of it, seams)."""
    welded = mesh.welded_faces
    faces, source, piece_of, offset = [], [], [], 0
    for index in range(len(segmentation.pieces)):
        ids, local = np.unique(welded[segmentation.labels == index], return_inverse=True)
        faces.append(local.reshape(-1, 3) + offset)
        source.append(ids)
        piece_of.append(np.full(len(ids), index))
        offset += len(ids)
    faces = np.concatenate(faces)
    faces = faces[(faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2])
                  & (faces[:, 0] != faces[:, 2])]
    source = np.concatenate(source)
    order = np.argsort(source, kind="stable")
    # Chain the copies of each seam vertex: one sewing spring per extra piece.
    same = source[order][1:] == source[order][:-1]
    sew = np.stack([order[:-1][same], order[1:][same]], axis=1)
    piece_of = np.concatenate(piece_of)

    # Some collars are modelled with a slit between them and the neckline: stitch
    # the collar's open edges that almost touch another piece. (Not elsewhere:
    # a cuff resting near the side of the torso must stay free.)
    points = mesh.welded_vertices
    open_edge = np.zeros(len(points), dtype=bool)
    open_edge[boundary_edges(welded).ravel()] = True
    loose = np.flatnonzero(open_edge[source])
    collar = segmentation.pieces.index("collar") if "collar" in segmentation.pieces else -1
    if len(loose) and collar >= 0:
        reach = STITCH_REACH * float(np.ptp(points[:, 1]))
        tree = cKDTree(points[source[loose]])
        pairs = tree.query_pairs(reach, output_type="ndarray")
        a, b = loose[pairs[:, 0]], loose[pairs[:, 1]]
        keep = (piece_of[a] != piece_of[b]) & (source[a] != source[b])
        keep &= (piece_of[a] == collar) | (piece_of[b] == collar)
        sew = np.concatenate([sew, np.stack([a[keep], b[keep]], axis=1)])
    return faces, source, piece_of, sew


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def open_arms(points: np.ndarray, weights: np.ndarray, landmarks, angle: float) -> np.ndarray:
    """Lift the arms away from the torso around the shoulder joints.

    `weights` (0..1) says how much each point follows its arm.
    """
    result = points.copy()
    for side in ("left", "right"):
        pivot = landmarks[f"{side}-shoulder"]
        sign = np.sign(pivot[0] - landmarks["neck"][0]) or 1.0
        rows = np.flatnonzero((weights > 0) & ((points[:, 0] - landmarks["neck"][0]) * sign > 0))
        theta = sign * angle * weights[rows]
        offset = points[rows] - pivot
        result[rows, 0] = pivot[0] + np.cos(theta) * offset[:, 0] - np.sin(theta) * offset[:, 1]
        result[rows, 1] = pivot[1] + np.sin(theta) * offset[:, 0] + np.cos(theta) * offset[:, 1]
    return result


def body_arm_weights(body_mesh: trimesh.Trimesh, landmarks) -> np.ndarray:
    """How much each body vertex follows its arm, blended smoothly at the shoulder."""
    vertices = np.asarray(body_mesh.vertices)
    height = float(np.ptp(vertices[:, 1]))
    labels = label_body_vertices(vertices, landmarks, height)
    if labels is None:
        return np.zeros(len(vertices))
    weights = (labels == PART_ARM).astype(float)
    edges = np.asarray(body_mesh.edges_unique)
    degree = np.maximum(np.bincount(edges.ravel(), minlength=len(vertices)), 1)
    for _ in range(12):
        total = np.zeros(len(vertices))
        np.add.at(total, edges[:, 0], weights[edges[:, 1]])
        np.add.at(total, edges[:, 1], weights[edges[:, 0]])
        weights = 0.5 * weights + 0.5 * total / degree
    # Hands and forearms follow completely.
    for side in ("left", "right"):
        elbow = landmarks[f"{side}-elbow"]
        sign = np.sign(elbow[0] - landmarks["neck"][0]) or 1.0
        low = (vertices[:, 1] < elbow[1]) & (labels == PART_ARM) & (vertices[:, 0] * sign > 0)
        weights[low] = 1.0
    return weights


def _welded_mean(values: np.ndarray, weld: np.ndarray) -> np.ndarray:
    total = np.zeros((int(weld.max()) + 1, 3))
    np.add.at(total, weld, values)
    return total / np.bincount(weld, minlength=len(total))[:, None]


def place_pieces(
    mesh: GarmentMesh,
    segmentation: Segmentation,
    rest: np.ndarray,
    body_vertices: np.ndarray,
    landmarks: dict[str, np.ndarray],
    angle: float,
) -> np.ndarray:
    """Put the cut pieces around the body (arms open), without deforming them much.

    Torso pieces keep their shape and follow the lean of the body; each sleeve is
    threaded onto its arm, following shoulder -> elbow -> wrist.
    """
    start = rest.copy()
    height = float(np.ptp(body_vertices[:, 1]))
    body, _ = without_arms(body_vertices, landmarks, height)
    body = body[np.abs(body[:, 0]) < 0.2 * height]
    torso = _vertices_of(mesh, segmentation, ("front", "back"))
    upper = _vertices_of(mesh, segmentation, ("front", "back", "collar"))
    shoulder = (landmarks["left-shoulder"][1] + landmarks["right-shoulder"][1]) / 2

    # Height: the top of the shirt at the base of the neck. Depth: body centre per level.
    start[upper, 1] += shoulder + 0.045 * height - rest[upper, 1].max()
    start[upper, 0] += landmarks["neck"][0] - rest[torso, 0].mean()
    levels = np.linspace(start[torso, 1].min(), shoulder, 16)
    body_z, cloth_z = [], []
    for level in levels:
        slab = body[np.abs(body[:, 1] - level) < 0.025 * height]
        cloth = start[torso[np.abs(start[torso, 1] - level) < 0.04 * height]]
        body_z.append((slab[:, 2].min() + slab[:, 2].max()) / 2 if len(slab) > 10 else np.nan)
        cloth_z.append((cloth[:, 2].min() + cloth[:, 2].max()) / 2 if len(cloth) > 5 else np.nan)
    shift = np.array(body_z) - np.array(cloth_z)
    known = np.isfinite(shift)
    start[upper, 2] += np.interp(start[upper, 1], levels[known], shift[known])

    torso_welded = np.unique(mesh.weld[torso])
    for side in ("left", "right"):
        sleeve = _vertices_of(mesh, segmentation, (f"sleeve_{side}",))
        if not len(sleeve):
            continue
        shared = np.isin(mesh.weld[sleeve], torso_welded)
        if not shared.any():
            continue
        origin = rest[sleeve[shared]].mean(0)
        far = np.linalg.norm(rest[sleeve] - origin, axis=1)
        axis = rest[sleeve[far >= np.quantile(far, 0.92)]].mean(0) - origin
        axis /= np.linalg.norm(axis)
        bones = np.array([landmarks[f"{side}-{name}"] for name in ("shoulder", "elbow", "wrist")])
        sign = np.sign(bones[0, 0] - landmarks["neck"][0]) or 1.0
        theta = sign * angle
        turn = np.array([[np.cos(theta), -np.sin(theta), 0.0], [np.sin(theta), np.cos(theta), 0.0], [0, 0, 1.0]])
        bones = bones[0] + (bones - bones[0]) @ turn.T
        chain = _ArmChain(*bones)
        along = (rest[sleeve] - origin) @ axis
        offset = rest[sleeve] - origin - np.outer(along, axis)
        # Start a little outside the joint, so the cap sits over the deltoid.
        arc = along + 0.02 * height
        tau = np.clip(arc / chain.total, 0.0, 1.0)
        point, tangent = chain.at(tau)
        turned = _rotate_between(offset, np.broadcast_to(axis, tangent.shape), tangent)
        start[sleeve] = point + turned + tangent * (arc - tau * chain.total)[:, None]
    return start


def _smooth(points: np.ndarray, faces: np.ndarray, rounds: int = 3) -> np.ndarray:
    """Taubin smoothing: removes the solver's vertex noise without shrinking."""
    edges = faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2)
    degree = np.maximum(np.bincount(edges.ravel(), minlength=len(points)), 1)[:, None]
    result = points.copy()
    for _ in range(rounds):
        for step in (0.5, -0.53):
            total = np.zeros_like(result)
            np.add.at(total, edges[:, 0], result[edges[:, 1]])
            np.add.at(total, edges[:, 1], result[edges[:, 0]])
            result += step * (total / degree - result)
    return result


def simplify_pieces(rest, start, faces, sew, piece_of, target: int):
    """A lighter copy of the cut pieces for the simulation.

    Vertices of one piece falling in the same cell of a grid (on the rest shape)
    are merged; pieces never merge with each other, so the seams stay separate.
    Returns (rest, start, faces, sew, piece of every vertex).
    """
    triangles = rest[faces]
    area = 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1
    ).sum()
    cell = float(np.sqrt(area / target))
    keys = np.column_stack((piece_of, np.floor(rest / cell).astype(np.int64)))
    cluster = np.unique(keys, axis=0, return_inverse=True)[1].ravel()

    new_faces = cluster[faces]
    new_faces = new_faces[(new_faces[:, 0] != new_faces[:, 1]) & (new_faces[:, 1] != new_faces[:, 2])
                          & (new_faces[:, 0] != new_faces[:, 2])]
    first = np.unique(np.sort(new_faces, axis=1), axis=0, return_index=True)[1]
    new_faces = new_faces[np.sort(first)]
    used, new_faces = np.unique(new_faces, return_inverse=True)
    new_faces = new_faces.reshape(-1, 3)
    index = np.full(int(cluster.max()) + 1, -1)
    index[used] = np.arange(len(used))

    def mean(values):
        total = np.zeros((int(cluster.max()) + 1, 3))
        np.add.at(total, cluster, values)
        return (total / np.maximum(np.bincount(cluster), 1)[:, None])[used]

    pieces = np.zeros(int(cluster.max()) + 1, dtype=int)
    pieces[cluster] = piece_of
    stitches = index[cluster[sew]]
    stitches = stitches[(stitches >= 0).all(axis=1) & (stitches[:, 0] != stitches[:, 1])]
    stitches = np.unique(np.sort(stitches, axis=1), axis=0)
    return mean(rest), mean(start), new_faces, stitches, pieces[used]


def _frames(points: np.ndarray, faces: np.ndarray):
    a, b, c = (points[faces[:, i]] for i in range(3))
    normal = np.cross(b - a, c - a)
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    # The normal axis keeps a fixed length unit so offsets are not stretched.
    normal = normal / np.maximum(length, 1e-12)
    return a, np.stack([b - a, c - a, normal], axis=2), length.ravel()


def transfer(full_rest, full_piece, proxy_rest, proxy_final, proxy_faces, proxy_piece) -> np.ndarray:
    """Carry the simulated motion of the light mesh over to the full one.

    Every full vertex is written in the local frame of the nearest triangles of
    its piece at rest, and rebuilt in the same frames after the simulation.
    """
    result = np.zeros_like(full_rest)
    origin, basis, doubled = _frames(proxy_rest, proxy_faces)
    moved_origin, moved_basis, _ = _frames(proxy_final, proxy_faces)
    edges = proxy_rest[proxy_faces]
    longest = np.max(np.linalg.norm(edges - edges[:, [1, 2, 0]], axis=2), axis=1)
    quality = doubled / np.maximum(longest ** 2, 1e-12)
    face_piece = proxy_piece[proxy_faces[:, 0]]
    centers = edges.mean(axis=1)
    for piece in np.unique(full_piece):
        rows = np.flatnonzero(full_piece == piece)
        candidates = np.flatnonzero((face_piece == piece) & (quality > 0.15))
        if not len(candidates):
            candidates = np.flatnonzero(quality > 0.15)
        count = min(3, len(candidates))
        distance, nearest = cKDTree(centers[candidates]).query(full_rest[rows], k=count)
        distance, nearest = distance.reshape(len(rows), count), nearest.reshape(len(rows), count)
        weight = 1.0 / (distance ** 2 + 1e-8)
        weight /= weight.sum(axis=1, keepdims=True)
        for k in range(count):
            face = candidates[nearest[:, k]]
            local = np.linalg.solve(basis[face], (full_rest[rows] - origin[face])[:, :, None])
            rebuilt = moved_origin[face] + (moved_basis[face] @ local)[:, :, 0]
            result[rows] += weight[:, k, None] * rebuilt
    return result


class SewingError(ValueError):
    """The simulation ran but the shirt did not end up worn."""


def _run_blender(blender: str, timeout_seconds, **arrays) -> tuple[np.ndarray, str]:
    with tempfile.TemporaryDirectory(prefix="ondressme-sew-") as work:
        given, result = Path(work) / "pieces.npz", Path(work) / "sewn.npz"
        np.savez(given, **arrays)
        completed = subprocess.run(
            [blender, "--background", "--factory-startup", "--python-exit-code", "1",
             "--python", str(SCRIPT), "--", "--input", str(given), "--output", str(result)],
            capture_output=True, text=True, timeout=timeout_seconds, check=False,
        )
        if completed.returncode != 0 or not result.is_file():
            raise RuntimeError(
                "Blender no pudo coser la prenda. " + (completed.stderr or completed.stdout)[-2500:]
            )
        return np.load(result)["final"], completed.stdout


def sew_on_body(
    blender: str,
    mesh: GarmentMesh,
    segmentation: Segmentation,
    body_mesh: trimesh.Trimesh,
    landmarks: dict[str, np.ndarray],
    scale_y: float,
    fit: str = "regular",
    edits: dict | None = None,
    timeout_seconds: int | None = None,
) -> tuple[np.ndarray, dict]:
    """Return final positions for `mesh.vertices` and a report."""
    body_vertices = np.asarray(body_mesh.vertices, dtype=np.float64)
    rest = rest_shape(mesh, segmentation, scale_y, body_vertices, landmarks, fit)
    if edits:
        rest = apply_edits(rest, mesh.faces, mesh.weld, segmentation, edits)

    faces, source, piece_of, sew = split_pieces(mesh, segmentation)
    rest_welded = _welded_mean(rest, mesh.weld)
    rest_pieces = rest_welded[source]
    # Sew with the arms open (no cloth trapped against the ribs), then close them.
    arm_weight = body_arm_weights(body_mesh, landmarks)
    body_open = open_arms(body_vertices, arm_weight, landmarks, ARM_OPEN_ANGLE)
    placed = place_pieces(mesh, segmentation, rest, body_vertices, landmarks, ARM_OPEN_ANGLE)
    start = _welded_mean(placed, mesh.weld)[source]
    # Seam vertices of a sleeve belong to the sleeve's copy, not to the average.
    for index in range(len(segmentation.pieces)):
        rows = np.flatnonzero(piece_of == index)
        own = np.unique(mesh.faces[segmentation.labels == index])
        total = np.zeros((int(mesh.weld.max()) + 1, 3))
        count = np.zeros(len(total))
        np.add.at(total, mesh.weld[own], placed[own])
        np.add.at(count, mesh.weld[own], 1.0)
        start[rows] = total[source[rows]] / count[source[rows]][:, None]

    full_rest, full_source, full_piece = rest_pieces, source, piece_of
    simplified = len(source) > SIMULATION_LIMIT
    if simplified:
        # Dense garments would take hours; simulate a light copy instead.
        rest_pieces, start, faces, sew, piece_of = simplify_pieces(
            rest_pieces, start, faces, sew, piece_of, SIMULATION_TARGET
        )

    volume = BodyVolume(body_open, body_mesh.faces, close_gaps=False)
    shoulder = (landmarks["left-shoulder"][1] + landmarks["right-shoulder"][1]) / 2
    height = float(np.ptp(body_vertices[:, 1]))
    # The solver can occasionally let the shirt slip off the shoulders; the check
    # below catches it and a second start (pieces further apart) is tried.
    for spread in (PIECE_SPREAD, 2 * PIECE_SPREAD):
        # Pull the pieces a little apart so none starts crossing its neighbour.
        apart = start.copy()
        for index, name in enumerate(segmentation.pieces):
            rows = piece_of == index
            if name == "front":
                apart[rows, 2] += spread
            elif name == "back":
                apart[rows, 2] -= spread
        apart, _ = volume.push_out(apart, margin=0.006, tolerance=0.0)
        final, output = _run_blender(
            blender, timeout_seconds, start=apart, rest=rest_pieces, faces=faces, sew=sew,
            body_open=body_open, body_vertices=body_vertices, body_faces=np.asarray(body_mesh.faces),
        )
        gap = np.linalg.norm(final[sew[:, 0]] - final[sew[:, 1]], axis=1)
        if np.percentile(final[:, 1], 99) > shoulder - 0.02 * height and np.median(gap) < 0.02:
            break
    else:
        raise SewingError("La prenda no se sostuvo sobre los hombros al coserla.")
    if np.percentile(gap, 95) > MAX_SEAM_GAP:
        # Typical of models whose parts are not really joined (loose collars).
        raise SewingError("Quedaron costuras abiertas al coser la prenda.")

    report = {"seam_vertex_pairs": int(len(sew))}
    for key in ("SEAM_GAP_MEDIAN", "SEAM_GAP_P95", "PENETRATION_TRIANGLE_PAIRS"):
        match = re.search(rf"{key}=([\d.]+)", output)
        if match:
            report[key.lower()] = float(match.group(1))
    if simplified:
        final = transfer(full_rest, full_piece, rest_pieces, final, faces, piece_of)
        source = full_source
    report["simulated_vertices"] = int(len(rest_pieces))
    # Close the seams: both sides of a stitch end at the same point.
    welded = np.zeros((int(mesh.weld.max()) + 1, 3))
    np.add.at(welded, source, final)
    welded /= np.maximum(np.bincount(source, minlength=len(welded)), 1)[:, None]
    welded = _smooth(welded, mesh.welded_faces)
    # Whatever is still inside the avatar is lifted just above its skin.
    volume = BodyVolume(body_vertices, body_mesh.faces, close_gaps=False)
    welded, lifted = volume.push_out(welded, margin=0.003, tolerance=0.001, max_push=0.03)
    report["vertices_lifted"] = int(lifted)
    return welded[mesh.weld], report
