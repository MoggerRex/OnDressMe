import json
import struct
import unittest

import numpy as np
import trimesh

from services.blender_simulator import simulate_static_garment
from services.body_skeleton import (
    PART_ARM,
    arm_vertex_mask,
    body_without_arms,
    has_arm_bones,
    label_body_vertices,
)
from services.garment_pipeline import _body_pants_profile, load_garment_mesh
from services.garment_rig import (
    PART_FOOT,
    PART_PELVIS,
    PART_SHIN,
    PART_SPINE,
    PART_THIGH,
    PART_ARM as RIG_PART_ARM,
    classify_joint,
    lookup_vertex_weights,
    read_garment_rig,
)


HAND_X = 0.25


def make_body_with_hands_at_hips():
    """Slim body whose hands rest right beside the hips."""
    torso = trimesh.creation.icosphere(subdivisions=3)
    torso.apply_scale([0.18, 1.0, 0.12])
    torso.apply_translation([0.0, 1.0, 0.0])
    hands = []
    for side in (-1, 1):
        hand = trimesh.creation.icosphere(subdivisions=2, radius=0.05)
        hand.apply_scale([1.0, 2.0, 1.0])
        hand.apply_translation([side * HAND_X, 1.0, 0.0])
        hands.append(hand)
    return trimesh.util.concatenate([torso, *hands]), torso


def base_landmarks():
    return {
        "left-hip": np.array([-0.10, 1.05, 0.0]),
        "right-hip": np.array([0.10, 1.05, 0.0]),
        "left-knee": np.array([-0.12, 0.55, 0.0]),
        "right-knee": np.array([0.12, 0.55, 0.0]),
        "left-ankle": np.array([-0.12, 0.10, 0.0]),
        "right-ankle": np.array([0.12, 0.10, 0.0]),
        "nose": np.array([0.0, 1.80, 0.10]),
        "neck": np.array([0.0, 1.60, 0.0]),
    }


def arm_landmarks():
    landmarks = base_landmarks()
    for side, sign in (("left", -1), ("right", 1)):
        landmarks[f"{side}-shoulder"] = np.array([sign * 0.20, 1.60, 0.0])
        landmarks[f"{side}-elbow"] = np.array([sign * HAND_X, 1.32, 0.0])
        landmarks[f"{side}-wrist"] = np.array([sign * HAND_X, 1.10, 0.0])
        landmarks[f"{side}-middle-tip"] = np.array([sign * HAND_X, 0.92, 0.0])
    return landmarks


def make_box_garment_bytes():
    mesh = trimesh.creation.box(extents=[0.55, 0.65, 0.25])
    return mesh.export(file_type="glb")


# --------------------------------------------------------------- rigged GLB --

JOINTS = (
    ("Hips", None, (0.0, 0.50, 0.0)),
    ("mixamorig:LeftUpLeg", 0, (-0.10, 0.45, 0.0)),
    ("mixamorig:RightUpLeg", 0, (0.10, 0.45, 0.0)),
    ("mixamorig:LeftLeg", 1, (-0.10, 0.25, 0.0)),
    ("mixamorig:RightLeg", 2, (0.10, 0.25, 0.0)),
    ("mixamorig:LeftFoot", 3, (-0.10, 0.02, 0.0)),
    ("mixamorig:RightFoot", 4, (0.10, 0.02, 0.0)),
)


def make_rigged_pants_glb(x_shift=0.0):
    """Two box legs skinned to thigh/shin/foot bones, plus a hips block."""
    pieces = []
    weights_by_piece = []
    for side, sign in (("L", -1), ("R", 1)):
        thigh, shin, foot = (1, 3, 5) if side == "L" else (2, 4, 6)
        for y_low, y_high, joint in ((0.30, 0.50, thigh), (0.10, 0.30, shin), (0.0, 0.10, foot)):
            box = trimesh.creation.box(extents=[0.12, y_high - y_low, 0.14])
            box.apply_translation([sign * 0.10, (y_low + y_high) / 2, 0.0])
            pieces.append(box)
            weights_by_piece.append(joint)
    mesh = trimesh.util.concatenate(pieces)
    owner = np.concatenate(
        [np.full(len(p.vertices), j) for p, j in zip(pieces, weights_by_piece)]
    )
    return skinned_glb(mesh, owner, JOINTS, x_shift)


def skinned_glb(mesh, owner, JOINTS, x_shift=0.0):
    """Pack a mesh rigidly skinned (one joint per vertex) into a GLB."""
    positions = np.asarray(mesh.vertices, dtype=np.float32)
    positions[:, 0] += np.float32(x_shift)
    indices = np.asarray(mesh.faces, dtype=np.uint16).reshape(-1)
    joints = np.zeros((len(positions), 4), dtype=np.uint8)
    joints[:, 0] = owner
    weights = np.zeros((len(positions), 4), dtype=np.float32)
    weights[:, 0] = 1.0
    ibm = np.zeros((len(JOINTS), 4, 4), dtype=np.float32)
    for i, (_, _, position) in enumerate(JOINTS):
        matrix = np.eye(4, dtype=np.float32)
        matrix[:3, 3] = -np.asarray(position, dtype=np.float32)
        ibm[i] = matrix.T  # glTF stores column-major

    blobs = [positions.tobytes(), indices.tobytes(), joints.tobytes(), weights.tobytes(), ibm.tobytes()]
    buffer = b""
    views = []
    for blob in blobs:
        buffer += b"\0" * (-len(buffer) % 4)
        views.append({"buffer": 0, "byteOffset": len(buffer), "byteLength": len(blob)})
        buffer += blob
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0, len(JOINTS)]}],
        "nodes": [
            {"name": name, "translation": list(position)}
            for name, _, position in JOINTS
        ],
        "buffers": [{"byteLength": len(buffer)}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": len(positions), "type": "VEC3",
             "min": positions.min(axis=0).tolist(), "max": positions.max(axis=0).tolist()},
            {"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
            {"bufferView": 2, "componentType": 5121, "count": len(joints), "type": "VEC4"},
            {"bufferView": 3, "componentType": 5126, "count": len(weights), "type": "VEC4"},
            {"bufferView": 4, "componentType": 5126, "count": len(JOINTS), "type": "MAT4"},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "JOINTS_0": 2, "WEIGHTS_0": 3}, "indices": 1}]}],
        "skins": [{"joints": list(range(len(JOINTS))), "inverseBindMatrices": 4}],
    }
    # Hips (node 0) is the parent of both thighs etc., expressed with local
    # translations relative to their parents.
    parents = {i: p for i, (_, p, _) in enumerate(JOINTS)}
    for i, (_, parent, position) in enumerate(JOINTS):
        if parent is not None:
            parent_position = np.asarray(JOINTS[parent][2])
            document["nodes"][i]["translation"] = (
                np.asarray(position) - parent_position
            ).tolist()
            document["nodes"][parent].setdefault("children", []).append(i)
    document["nodes"].append({"name": "Pants", "mesh": 0, "skin": 0})
    # Node 7 is Pants; scene roots are Hips (0) and the mesh node (7).
    document["scenes"] = [{"nodes": [0, len(JOINTS)]}]
    del parents

    json_chunk = json.dumps(document).encode("utf-8")
    json_chunk += b" " * (-len(json_chunk) % 4)
    buffer += b"\0" * (-len(buffer) % 4)
    total = 12 + 8 + len(json_chunk) + 8 + len(buffer)
    return (
        struct.pack("<4sII", b"glTF", 2, total)
        + struct.pack("<II", len(json_chunk), 0x4E4F534A)
        + json_chunk
        + struct.pack("<II", len(buffer), 0x004E4942)
        + buffer
    )


class BodySkeletonTests(unittest.TestCase):
    def test_arm_bones_detected(self):
        self.assertFalse(has_arm_bones(base_landmarks()))
        self.assertTrue(has_arm_bones(arm_landmarks()))
        self.assertIsNone(arm_vertex_mask(np.zeros((40, 3)), base_landmarks()))

    def test_hands_next_to_the_hips_are_labelled_as_arm_not_hip(self):
        body, torso = make_body_with_hands_at_hips()
        vertices = np.asarray(body.vertices)
        labels = label_body_vertices(vertices, arm_landmarks())

        hand_vertices = np.abs(vertices[:, 0]) > HAND_X - 0.02
        hand_vertices &= np.abs(vertices[:, 1] - 1.0) < 0.12
        self.assertGreater(hand_vertices.sum(), 20)
        self.assertGreater(np.mean(labels[hand_vertices] == PART_ARM), 0.9)

        torso_count = len(torso.vertices)
        torso_labels = labels[:torso_count]
        hip_band = np.abs(vertices[:torso_count, 1] - 1.05) < 0.1
        self.assertLess(np.mean(torso_labels[hip_band] == PART_ARM), 0.02)

    def test_collision_body_drops_hands_but_keeps_the_hips(self):
        body, torso = make_body_with_hands_at_hips()
        reduced, removed = body_without_arms(body, arm_landmarks())

        self.assertGreater(removed, 0)
        self.assertLess(len(reduced.faces), len(body.faces))
        beyond_torso = np.abs(np.asarray(reduced.vertices)[:, 0]) > 0.21
        near_hip = np.abs(np.asarray(reduced.vertices)[:, 1] - 1.0) < 0.1
        self.assertFalse((beyond_torso & near_hip).any())
        self.assertAlmostEqual(
            float(reduced.vertices[:, 1].max()), float(body.vertices[:, 1].max()), places=5
        )

    def test_body_without_arm_bones_is_left_untouched(self):
        body, _ = make_body_with_hands_at_hips()
        same, removed = body_without_arms(body, base_landmarks())
        self.assertIs(same, body)
        self.assertEqual(removed, 0)


class PantsIgnoreHandsTests(unittest.TestCase):
    def test_hands_near_hips_do_not_widen_the_pants_profile(self):
        body, torso = make_body_with_hands_at_hips()
        with_bones = _body_pants_profile(np.asarray(body.vertices), arm_landmarks())
        torso_only = _body_pants_profile(np.asarray(torso.vertices), arm_landmarks())
        without_bones = _body_pants_profile(np.asarray(body.vertices), base_landmarks())

        self.assertAlmostEqual(with_bones.target_width, torso_only.target_width, delta=0.03 * torso_only.target_width)
        self.assertGreater(without_bones.target_width, with_bones.target_width * 1.15)

    def test_fitted_pants_stay_off_the_hands(self):
        body, torso = make_body_with_hands_at_hips()
        fitted = load_garment_mesh(
            make_box_garment_bytes(), "pants.glb", body, "pants",
            body_landmarks=arm_landmarks(),
        )
        unaware = load_garment_mesh(
            make_box_garment_bytes(), "pants.glb", body, "pants",
            body_landmarks=base_landmarks(),
        )

        width = float(np.ptp(fitted.scene.bounds[:, 0]))
        self.assertLess(width, float(np.ptp(unaware.scene.bounds[:, 0])))
        self.assertLess(width, 2 * HAND_X)  # does not reach the hands
        self.assertGreater(fitted.metrics["fit_body_arm_vertices_excluded"], 0)
        self.assertEqual(unaware.metrics["fit_body_arm_vertices_excluded"], 0)


class GarmentRigTests(unittest.TestCase):
    def test_classifies_common_bone_names(self):
        expected = {
            "mixamorig:Hips": PART_PELVIS,
            "mixamorig:Spine1": PART_SPINE,
            "mixamorig:LeftUpLeg": PART_THIGH,
            "thigh_l": PART_THIGH,
            "mixamorig:LeftLeg": PART_SHIN,
            "calf.R": PART_SHIN,
            "mixamorig:RightFoot": PART_FOOT,
            "mixamorig:LeftToeBase": PART_FOOT,
            "mixamorig:LeftHand": RIG_PART_ARM,
            "mixamorig:LeftForeArm": RIG_PART_ARM,
            "mixamorig:LeftHandIndex1": RIG_PART_ARM,
        }
        for name, part in expected.items():
            self.assertEqual(classify_joint(name), part, name)

    def test_reads_skin_joints_and_weights_from_a_glb(self):
        rig = read_garment_rig(make_rigged_pants_glb())

        self.assertIsNotNone(rig)
        self.assertEqual(len(rig.joint_names), len(JOINTS))
        np.testing.assert_allclose(
            rig.joint_positions, [position for *_, position in JOINTS], atol=1e-5
        )
        np.testing.assert_allclose(rig.vertex_weights.sum(axis=1), 1.0, atol=1e-5)
        self.assertEqual(rig.joint_parts[1], PART_THIGH)

    def test_unskinned_glb_has_no_rig(self):
        self.assertIsNone(read_garment_rig(make_box_garment_bytes()))

    def test_weights_survive_trimesh_merging_vertices(self):
        contents = make_rigged_pants_glb()
        rig = read_garment_rig(contents)
        scene = trimesh.load(trimesh.util.wrap_as_stream(contents), file_type="glb", force="scene")
        points = np.concatenate([g.vertices for g in scene.geometry.values()])

        weights = lookup_vertex_weights(rig, points, tolerance=1e-4)

        self.assertIsNotNone(weights)
        self.assertEqual(len(weights), len(points))

    def test_rigged_pants_follow_the_body_legs(self):
        body, _ = make_body_with_hands_at_hips()
        landmarks = arm_landmarks()
        # Widen the body's legs so the garment legs must move outwards.
        for side, sign in (("left", -1), ("right", 1)):
            landmarks[f"{side}-hip"][0] = sign * 0.16
            landmarks[f"{side}-knee"][0] = sign * 0.18
            landmarks[f"{side}-ankle"][0] = sign * 0.18

        rigged = load_garment_mesh(
            make_rigged_pants_glb(), "pants.glb", body, "pants", body_landmarks=landmarks
        )
        self.assertEqual(rigged.metrics["fit_garment_rig"], "skin_joint_retarget")
        self.assertGreaterEqual(rigged.metrics["fit_garment_rig_joints"], 6)

        vertices = np.asarray(rigged.scene.to_geometry().vertices)
        low = vertices[vertices[:, 1] < 0.25]
        left_center = low[low[:, 0] < 0][:, 0].mean()
        right_center = low[low[:, 0] > 0][:, 0].mean()
        self.assertLess(left_center, -0.12)
        self.assertGreater(right_center, 0.12)
        self.assertTrue(np.isfinite(vertices).all())

    def test_unrigged_pants_report_no_rig(self):
        body, _ = make_body_with_hands_at_hips()
        result = load_garment_mesh(
            make_box_garment_bytes(), "pants.glb", body, "pants",
            body_landmarks=arm_landmarks(),
        )
        self.assertEqual(result.metrics["fit_garment_rig"], "none")


class BlenderHandsTests(unittest.TestCase):
    def test_pants_simulation_ignores_hands_resting_at_the_hips(self):
        from tests.test_blender_simulation import BLENDER_AVAILABLE

        if not BLENDER_AVAILABLE:
            self.skipTest("Blender is not installed")
        body, _ = make_body_with_hands_at_hips()
        pants = trimesh.creation.box(extents=[0.55, 0.65, 0.25])
        for _ in range(3):
            vertices, faces = trimesh.remesh.subdivide(pants.vertices, pants.faces)
            pants = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        # Prenda ajustada sin huesos de brazos: queda ancha y llega a las manos,
        # el peor caso para la proyección de Blender.
        build = load_garment_mesh(
            pants.export(file_type="glb"), "pants.glb", body, "pants",
            body_landmarks=base_landmarks(),
        )

        def vertices_on_hands(landmarks):
            glb, _, _ = simulate_static_garment(
                body, build.scene, "pants", body_landmarks=landmarks
            )
            self.assertEqual(glb[:4], b"glTF")
            exported = trimesh.load(
                trimesh.util.wrap_as_stream(glb), file_type="glb", force="scene"
            )
            vertices = np.asarray(exported.to_geometry().vertices)
            near_hand = (np.abs(np.abs(vertices[:, 0]) - HAND_X) < 0.03) & (
                np.abs(vertices[:, 1] - 1.0) < 0.1
            )
            return int(near_hand.sum())

        with_bones = vertices_on_hands(arm_landmarks())
        without_bones = vertices_on_hands(base_landmarks())

        self.assertEqual(with_bones, 0, "pants got pulled onto the hands")
        self.assertGreater(without_bones, 0)


if __name__ == "__main__":
    unittest.main()
