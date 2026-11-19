"""Read the skeleton (glTF skin) embedded in a garment GLB.

A rigged garment tells us where its own hips, knees and ankles are. The
pipeline uses those joints to retarget each part of the garment onto the
matching bone of the SAM 3D body, instead of guessing legs from height slices.
Only the standard library and numpy are used.
"""
from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass

import numpy as np


PART_PELVIS = "pelvis"
PART_SPINE = "spine"
PART_THIGH = "thigh"
PART_SHIN = "shin"
PART_FOOT = "foot"
PART_ARM = "arm"
PART_OTHER = "other"

_COMPONENT_DTYPES = {
    5120: np.int8,
    5121: np.uint8,
    5122: np.int16,
    5123: np.uint16,
    5125: np.uint32,
    5126: np.float32,
}
_TYPE_SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
_NORMALIZERS = {
    np.dtype(np.uint8): 255.0,
    np.dtype(np.uint16): 65535.0,
}


@dataclass(frozen=True)
class GarmentRig:
    joint_names: tuple[str, ...]
    joint_parts: tuple[str, ...]
    joint_positions: np.ndarray  # (J, 3) in the same frame as vertex_positions
    vertex_positions: np.ndarray  # (N, 3) rest positions
    vertex_weights: np.ndarray  # (N, J) normalised skin weights


def classify_joint(name: str) -> str:
    """Map a bone name (Mixamo, Blender, Unreal, VRM...) to a body part."""
    lowered = re.sub(r"^.*[:|]", "", name.lower())
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    if any(
        token in compact
        for token in (
            "arm", "hand", "shoulder", "elbow", "wrist", "clavicle",
            "thumb", "index", "middle", "ring", "pinky", "finger",
        )
    ) and "leg" not in compact:
        return PART_ARM
    if any(token in compact for token in ("toe", "foot", "ankle", "heel")):
        return PART_FOOT
    if any(token in compact for token in ("upleg", "thigh", "upperleg", "femur")):
        return PART_THIGH
    if any(token in compact for token in ("calf", "shin", "lowerleg", "knee", "tibia")):
        return PART_SHIN
    if "leg" in compact:
        return PART_SHIN
    if any(token in compact for token in ("hips", "hip", "pelvis")):
        return PART_PELVIS
    if any(token in compact for token in ("spine", "chest", "waist", "torso")):
        return PART_SPINE
    return PART_OTHER


def _split_glb(contents: bytes) -> tuple[dict, bytes] | None:
    if len(contents) < 20 or contents[:4] != b"glTF":
        return None
    offset = 12
    document = None
    binary = b""
    while offset + 8 <= len(contents):
        chunk_length, chunk_type = struct.unpack_from("<II", contents, offset)
        chunk = contents[offset + 8 : offset + 8 + chunk_length]
        if chunk_type == 0x4E4F534A:
            document = json.loads(chunk.decode("utf-8"))
        elif chunk_type == 0x004E4942 and not binary:
            binary = bytes(chunk)
        offset += 8 + chunk_length + (-chunk_length % 4)
    if document is None:
        return None
    return document, binary


def _read_accessor(document: dict, binary: bytes, index: int) -> np.ndarray:
    accessor = document["accessors"][index]
    dtype = np.dtype(_COMPONENT_DTYPES[accessor["componentType"]])
    width = _TYPE_SIZES[accessor["type"]]
    count = accessor["count"]
    if "bufferView" not in accessor:
        return np.zeros((count, width), dtype=dtype)
    view = document["bufferViews"][accessor["bufferView"]]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    element_bytes = dtype.itemsize * width
    stride = view.get("byteStride") or element_bytes
    raw = np.frombuffer(
        binary, dtype=np.uint8, count=stride * (count - 1) + element_bytes,
        offset=start,
    ) if count else np.empty(0, dtype=np.uint8)
    rows = np.lib.stride_tricks.as_strided(
        raw, shape=(count, element_bytes), strides=(stride, 1)
    )
    data = np.ascontiguousarray(rows).view(dtype).reshape(count, width)
    return data


def _local_matrix(node: dict) -> np.ndarray:
    if "matrix" in node:
        return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
    matrix = np.eye(4)
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    rotation = np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
    scale = np.asarray(node.get("scale", (1.0, 1.0, 1.0)), dtype=np.float64)
    matrix[:3, :3] = rotation * scale
    matrix[:3, 3] = node.get("translation", (0.0, 0.0, 0.0))
    return matrix


def _world_matrices(document: dict) -> list[np.ndarray]:
    nodes = document.get("nodes", [])
    parents = {}
    for index, node in enumerate(nodes):
        for child in node.get("children", []):
            parents[child] = index
    cache: dict[int, np.ndarray] = {}

    def world(index: int) -> np.ndarray:
        if index not in cache:
            local = _local_matrix(nodes[index])
            parent = parents.get(index)
            cache[index] = local if parent is None else world(parent) @ local
        return cache[index]

    return [world(index) for index in range(len(nodes))]


def read_garment_rig(contents: bytes) -> GarmentRig | None:
    """Return the first skinned mesh's skeleton, or None if the GLB has no rig.

    Vertex positions are expressed in the frame trimesh uses for the scene
    (mesh-node world transform applied to rest positions), and joint positions
    are the bind-pose joint locations in that same frame, so both can be
    compared directly after trimesh has loaded the file.
    """
    try:
        parsed = _split_glb(contents)
        if parsed is None:
            return None
        document, binary = parsed
        skins = document.get("skins") or []
        if not skins:
            return None
        nodes = document.get("nodes", [])
        world = _world_matrices(document)

        positions_per_mesh = []
        weights_per_mesh = []
        skin_index = None
        for node_index, node in enumerate(nodes):
            if "mesh" not in node or "skin" not in node:
                continue
            if skin_index is None:
                skin_index = node["skin"]
            elif node["skin"] != skin_index:
                continue
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                attributes = primitive.get("attributes", {})
                if (
                    "POSITION" not in attributes
                    or "JOINTS_0" not in attributes
                    or "WEIGHTS_0" not in attributes
                ):
                    continue
                points = _read_accessor(
                    document, binary, attributes["POSITION"]
                ).astype(np.float64)
                joints = _read_accessor(
                    document, binary, attributes["JOINTS_0"]
                ).astype(np.int64)
                weights_raw = _read_accessor(
                    document, binary, attributes["WEIGHTS_0"]
                )
                weights = weights_raw.astype(np.float64)
                normalizer = _NORMALIZERS.get(weights_raw.dtype)
                if normalizer:
                    weights /= normalizer
                matrix = world[node_index]
                positions_per_mesh.append(
                    points @ matrix[:3, :3].T + matrix[:3, 3]
                )
                weights_per_mesh.append((joints, weights))

        if skin_index is None or not positions_per_mesh:
            return None

        skin = skins[skin_index]
        joint_nodes = skin["joints"]
        joint_count = len(joint_nodes)
        if "inverseBindMatrices" in skin:
            inverse_bind = _read_accessor(
                document, binary, skin["inverseBindMatrices"]
            ).astype(np.float64).reshape(-1, 4, 4).transpose(0, 2, 1)
            joint_positions = np.array(
                [np.linalg.inv(matrix)[:3, 3] for matrix in inverse_bind]
            )
            # Bind space is the space of the skinned mesh node.
            mesh_node = next(
                index
                for index, node in enumerate(nodes)
                if node.get("skin") == skin_index and "mesh" in node
            )
            mesh_matrix = world[mesh_node]
            joint_positions = (
                joint_positions @ mesh_matrix[:3, :3].T + mesh_matrix[:3, 3]
            )
        else:
            joint_positions = np.array(
                [world[index][:3, 3] for index in joint_nodes]
            )

        total = sum(len(points) for points in positions_per_mesh)
        dense = np.zeros((total, joint_count), dtype=np.float64)
        cursor = 0
        for points, (joints, weights) in zip(positions_per_mesh, weights_per_mesh):
            for slot in range(joints.shape[1]):
                valid = (joints[:, slot] < joint_count) & (weights[:, slot] > 0)
                rows = np.flatnonzero(valid) + cursor
                np.add.at(
                    dense, (rows, joints[valid, slot]), weights[valid, slot]
                )
            cursor += len(points)
        sums = dense.sum(axis=1, keepdims=True)
        dense = np.divide(dense, sums, out=np.zeros_like(dense), where=sums > 1e-9)

        names = tuple(
            str(nodes[index].get("name", f"joint_{index}")) for index in joint_nodes
        )
        return GarmentRig(
            joint_names=names,
            joint_parts=tuple(classify_joint(name) for name in names),
            joint_positions=np.asarray(joint_positions, dtype=np.float64),
            vertex_positions=np.concatenate(positions_per_mesh, axis=0),
            vertex_weights=dense,
        )
    except (KeyError, ValueError, IndexError, TypeError, np.linalg.LinAlgError):
        return None


def lookup_vertex_weights(
    rig: GarmentRig, points: np.ndarray, tolerance: float
) -> np.ndarray | None:
    """Skin weights for `points`, matched by nearest rest position.

    trimesh may merge or reorder vertices while loading, so weights are
    transferred through a nearest-neighbour lookup instead of by index.
    Returns None when the geometry does not match the rigged mesh.
    """
    from scipy.spatial import cKDTree

    distances, indices = cKDTree(rig.vertex_positions).query(points)
    if float(np.max(distances)) > tolerance:
        return None
    return rig.vertex_weights[indices]


def _body_target_positions(
    landmarks: dict[str, np.ndarray],
) -> dict[str, np.ndarray] | None:
    names = (
        "left-hip", "right-hip", "left-knee", "right-knee",
        "left-ankle", "right-ankle",
    )
    try:
        points = {name: np.asarray(landmarks[name], dtype=np.float64) for name in names}
    except KeyError:
        return None
    if any(point.shape != (3,) or not np.isfinite(point).all() for point in points.values()):
        return None
    return points


def retarget_offsets(
    rig: GarmentRig,
    weights: np.ndarray,
    landmarks: dict[str, np.ndarray],
    joint_positions: np.ndarray,
) -> tuple[np.ndarray, int] | None:
    """Per-vertex XZ displacement that moves garment bones onto body bones.

    `joint_positions` are the garment joints already in body space (after the
    global scale/rotation). Returns (offsets (N, 3) with Y = 0, mapped joint
    count) or None when the rig has no usable legs.
    """
    body = _body_target_positions(landmarks)
    if body is None:
        return None

    parts = rig.joint_parts
    pelvis_ids = [i for i, part in enumerate(parts) if part == PART_PELVIS]
    thigh_ids = [i for i, part in enumerate(parts) if part == PART_THIGH]
    shin_ids = [i for i, part in enumerate(parts) if part == PART_SHIN]
    foot_ids = [i for i, part in enumerate(parts) if part == PART_FOOT]
    if len(thigh_ids) < 2:
        return None

    def by_side(ids: list[int]) -> list[int]:
        # Left/right is decided by position (smaller X first), which is
        # independent of naming and of which way the garment faces.
        return sorted(ids, key=lambda index: joint_positions[index, 0])

    body_sides = sorted(
        (("left", "right")), key=lambda side: body[f"{side}-hip"][0]
    )
    targets: dict[int, np.ndarray] = {}
    for ids, joint in ((thigh_ids, "hip"), (shin_ids, "knee"), (foot_ids, "ankle")):
        ordered = by_side(ids)
        if len(ordered) < 2:
            continue
        # Only the two outermost joints per slot are meaningful (toe bones etc.
        # share the foot slot), so assign by side of the body.
        half = len(ordered) // 2
        for index in ordered[:half]:
            targets[index] = body[f"{body_sides[0]}-{joint}"]
        for index in ordered[len(ordered) - half :]:
            targets[index] = body[f"{body_sides[1]}-{joint}"]

    hip_center = (body["left-hip"] + body["right-hip"]) * 0.5
    for index in pelvis_ids:
        targets[index] = hip_center

    offsets = np.zeros((len(parts), 3), dtype=np.float64)
    mapped = np.zeros(len(parts), dtype=bool)
    for index, target in targets.items():
        offsets[index] = target - joint_positions[index]
        mapped[index] = True
    offsets[:, 1] = 0.0

    default = (
        offsets[pelvis_ids].mean(axis=0) if pelvis_ids else np.zeros(3)
    )
    for index in range(len(parts)):
        if not mapped[index]:
            offsets[index] = default

    return weights @ offsets + (
        (1.0 - weights.sum(axis=1, keepdims=True)) * default
    ), int(mapped.sum())
