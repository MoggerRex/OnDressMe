import shutil
import unittest
from pathlib import Path

import numpy as np
import trimesh

from services.blender_simulator import BLENDER_CANDIDATES, simulate_static_garment
from services.body_volume import BodyVolume, resolve_overlaps
from services.garment_pipeline import GarmentPipelineError, load_garment_mesh
from tests.test_skeleton_fit import arm_landmarks

BLENDER_AVAILABLE = shutil.which("blender") or any(Path(c).is_file() for c in BLENDER_CANDIDATES)


def dense(mesh, rounds=3):
    for _ in range(rounds):
        mesh = trimesh.Trimesh(*trimesh.remesh.subdivide(mesh.vertices, mesh.faces), process=False)
    return mesh


def make_body_with_arms():
    """Slim torso plus two arms hanging along the shoulder-elbow-wrist bones."""
    torso = trimesh.creation.icosphere(subdivisions=3)
    torso.apply_scale([0.18, 1.0, 0.12])
    torso.apply_translation([0.0, 1.0, 0.0])
    landmarks = arm_landmarks()
    parts = [torso]
    for side in ("left", "right"):
        for a, b in (("shoulder", "elbow"), ("elbow", "wrist")):
            parts.append(
                dense(
                    trimesh.creation.cylinder(
                        radius=0.035,
                        segment=[landmarks[f"{side}-{a}"], landmarks[f"{side}-{b}"]],
                        sections=24,
                    ),
                    4,
                )
            )
        for a, b in (("hip", "knee"), ("knee", "ankle")):
            parts.append(
                dense(
                    trimesh.creation.cylinder(
                        radius=0.06,
                        segment=[landmarks[f"{side}-{a}"], landmarks[f"{side}-{b}"]],
                        sections=24,
                    ),
                    4,
                )
            )
    return trimesh.util.concatenate(parts), landmarks


def glb(mesh):
    return mesh.export(file_type="glb")


def make_shirt(sleeves):
    """T-pose shirt: torso 0.5 wide; sleeves (if any) stretch out along X."""
    torso = dense(trimesh.creation.box(extents=[0.5, 0.65, 0.25]))
    torso.apply_translation([0.0, 0.325, 0.0])
    parts = [torso]
    if sleeves:
        for sign in (-1, 1):
            sleeve = dense(trimesh.creation.box(extents=[0.45, 0.14, 0.14]))
            sleeve.apply_translation([sign * 0.475, 0.55, 0.0])
            parts.append(sleeve)
    return trimesh.util.concatenate(parts)


class NewGarmentTypeTests(unittest.TestCase):
    def test_tank_fits_the_torso_range(self):
        body, landmarks = make_body_with_arms()
        result = load_garment_mesh(glb(make_shirt(False)), "tank.glb", body, "tank", body_landmarks=landmarks)

        self.assertEqual(result.metrics["garment_type"], "tank")
        self.assertAlmostEqual(float(result.scene.bounds[:, 1].mean()), 1.35, delta=0.02)

    def test_shorts_end_above_the_knee_and_pants_below_it(self):
        body, landmarks = make_body_with_arms()
        box = glb(trimesh.creation.box(extents=[0.55, 0.65, 0.25]))
        shorts = load_garment_mesh(box, "s.glb", body, "shorts", body_landmarks=landmarks)
        pants = load_garment_mesh(box, "p.glb", body, "pants", body_landmarks=landmarks)

        knee_y, hip_y = landmarks["left-knee"][1], landmarks["left-hip"][1]
        hem = float(shorts.scene.bounds[0, 1])
        self.assertGreater(hem, knee_y)
        self.assertLess(hem, hip_y)
        self.assertGreater(hem, float(pants.scene.bounds[0, 1]) + 0.3)
        self.assertEqual(shorts.metrics["garment_type"], "shorts")

    def test_shorts_work_without_keypoints(self):
        body, _ = make_body_with_arms()
        box = glb(trimesh.creation.box(extents=[0.55, 0.65, 0.25]))
        result = load_garment_mesh(box, "s.glb", body, "shorts")
        self.assertGreater(float(result.scene.bounds[0, 1]), 0.4)

    def test_long_sleeves_follow_the_arm_bones(self):
        body, landmarks = make_body_with_arms()
        result = load_garment_mesh(
            glb(make_shirt(True)), "long.glb", body, "longsleeve", body_landmarks=landmarks
        )
        self.assertEqual(result.metrics["fit_sleeves_fitted"], 2)
        vertices = np.asarray(result.scene.to_geometry().vertices)

        # Nothing is left sticking out horizontally like in the T-pose.
        self.assertLess(float(np.abs(vertices[:, 0]).max()), 0.45)
        for sign, side in ((-1, "left"), (1, "right")):
            wrist = landmarks[f"{side}-wrist"]
            sleeve = vertices[vertices[:, 0] * sign > 0.2]
            self.assertGreater(len(sleeve), 50)
            cuff = sleeve[np.argsort(sleeve[:, 1])[:30]].mean(axis=0)  # lowest = hanging cuff
            self.assertLess(float(np.linalg.norm(cuff - wrist)), 0.10)

    def test_long_sleeves_need_arm_bones(self):
        body, landmarks = make_body_with_arms()
        for name in ("left-elbow", "right-elbow"):
            del landmarks[name]
        with self.assertRaises(GarmentPipelineError):
            load_garment_mesh(glb(make_shirt(True)), "l.glb", body, "longsleeve", body_landmarks=landmarks)
        with self.assertRaises(GarmentPipelineError):
            load_garment_mesh(glb(make_shirt(True)), "l.glb", body, "longsleeve")

    def test_unknown_type_is_rejected(self):
        body, _ = make_body_with_arms()
        with self.assertRaises(GarmentPipelineError):
            load_garment_mesh(glb(make_shirt(False)), "x.glb", body, "dress")


class FitAndShapeTests(unittest.TestCase):
    def test_looser_fit_widens_the_shorts_legs(self):
        body, landmarks = make_body_with_arms()
        box = glb(dense(trimesh.creation.box(extents=[0.55, 0.65, 0.25]), 3))
        widths = {}
        for fit in ("tight", "regular", "loose"):
            result = load_garment_mesh(box, "s.glb", body, "shorts", body_landmarks=landmarks, fit=fit)
            vertices = np.asarray(result.scene.to_geometry().vertices)
            hem = vertices[vertices[:, 1] < vertices[:, 1].min() + 0.03]
            widths[fit] = float(np.ptp(hem[:, 2]))  # leg depth: not affected by the leg offsets
            self.assertEqual(result.metrics["fit_ease"], fit)
            self.assertEqual(result.metrics["fit_legs_fitted"], 2)
        self.assertLess(widths["tight"], widths["regular"])
        self.assertLess(widths["regular"], widths["loose"])

    def test_unknown_fit_is_rejected(self):
        body, landmarks = make_body_with_arms()
        with self.assertRaises(GarmentPipelineError):
            load_garment_mesh(glb(make_shirt(False)), "t.glb", body, "tank", body_landmarks=landmarks, fit="baggy")

    def test_shorts_crotch_sits_at_the_body_crotch_and_legs_stay_apart(self):
        body, landmarks = make_body_with_arms()
        # A garment whose crotch hangs low: two legs joined by a panel above y=0.2.
        leg = dense(trimesh.creation.box(extents=[0.22, 0.45, 0.25]), 3)
        left, right = leg.copy(), leg.copy()
        left.apply_translation([-0.13, 0.225, 0.0])
        right.apply_translation([0.13, 0.225, 0.0])
        panel = dense(trimesh.creation.box(extents=[0.48, 0.30, 0.25]), 3)
        panel.apply_translation([0.0, 0.60, 0.0])
        shorts = trimesh.util.concatenate([left, right, panel])

        result = load_garment_mesh(glb(shorts), "s.glb", body, "shorts", body_landmarks=landmarks)

        vertices = np.asarray(result.scene.to_geometry().vertices)
        height = float(np.ptp(body.vertices[:, 1]))
        crotch = landmarks["left-hip"][1] - 0.07 * height
        centre_column = vertices[np.abs(vertices[:, 0]) < 0.004 * height]
        # Nothing hangs between the thighs below the avatar's crotch.
        self.assertTrue(len(centre_column) == 0 or float(centre_column[:, 1].min()) > crotch - 0.03)

    def test_tank_armhole_stays_off_the_arms(self):
        body, landmarks = make_body_with_arms()
        result = load_garment_mesh(glb(make_shirt(False)), "tank.glb", body, "tank", body_landmarks=landmarks)
        vertices = np.asarray(result.scene.to_geometry().vertices)

        from services.sleeve_fit import _ArmChain

        for side in ("left", "right"):
            chain = _ArmChain(landmarks[f"{side}-shoulder"], landmarks[f"{side}-elbow"], landmarks[f"{side}-wrist"])
            tau, distance = chain.parameter(vertices)
            on_arm = (tau > 0.05) & (tau < 0.6)
            # The arm radius is 0.035: no tank vertex may sit inside the arm tube.
            self.assertGreater(float(distance[on_arm].min()), 0.03, side)

    def test_keep_off_arms_never_pushes_sideways(self):
        from services.sleeve_fit import keep_off_arms

        body, landmarks = make_body_with_arms()
        shoulder, elbow = landmarks["right-shoulder"], landmarks["right-elbow"]
        inside = (shoulder + elbow) / 2  # on the upper-arm axis
        edge = inside + np.array([0.01, 0.0, 0.0])  # inside the tube, towards outside
        points = np.array([inside, edge])
        height = float(np.ptp(body.vertices[:, 1]))

        moved, count = keep_off_arms(points, 0.0, np.asarray(body.vertices), landmarks, height, 0.004)

        self.assertEqual(count, 2)
        from services.sleeve_fit import _ArmChain

        chain = _ArmChain(landmarks["right-shoulder"], elbow, landmarks["right-wrist"])
        _, distance = chain.parameter(moved)
        self.assertTrue((distance > 0.03).all())  # out of the 3.5 cm arm tube
        # Never wrapped around to the outer side of the arm (outer surface x = 0.28).
        self.assertTrue((moved[:, 0] < 0.285).all())


class BodyVolumeTests(unittest.TestCase):
    def setUp(self):
        # Torso column plus an arm 2 cm away from it (a narrow armpit gap).
        torso = trimesh.creation.cylinder(radius=0.15, height=1.0, sections=48)
        arm = trimesh.creation.cylinder(radius=0.05, height=1.0, sections=32)
        arm.apply_translation([0.15 + 0.02 + 0.05, 0.0, 0.0])
        self.body = trimesh.util.concatenate([torso, arm])
        self.body.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        self.body.apply_translation([0.0, 0.5, 0.0])

    def test_gap_between_arm_and_torso_is_closed_but_far_space_is_not(self):
        closed = BodyVolume(self.body.vertices, self.body.faces)
        opened = BodyVolume(self.body.vertices, self.body.faces, close_gaps=False)
        gap = np.array([[0.16, 0.5, 0.0]])
        far = np.array([[0.50, 0.5, 0.0]])

        self.assertLess(closed.signed_distance(gap)[0], 0.0)
        self.assertGreater(opened.signed_distance(gap)[0], 0.0)
        self.assertGreater(closed.signed_distance(far)[0], 0.0)

    def test_vertices_in_the_arm_and_in_the_gap_end_up_outside(self):
        volume = BodyVolume(self.body.vertices, self.body.faces)
        points = np.array(
            [[0.22, 0.5, 0.0], [0.16, 0.5, 0.0], [0.60, 0.5, 0.0], [0.0, 0.5, 0.40]]
        )
        fixed, moved = volume.push_out(points, margin=0.005)

        self.assertEqual(moved, 2)
        self.assertTrue((volume.signed_distance(fixed) > -volume.pitch).all())
        np.testing.assert_allclose(fixed[2:], points[2:])  # outside points stay put

    def test_resolve_overlaps_moves_garment_vertices_of_a_scene(self):
        volume = BodyVolume(self.body.vertices, self.body.faces)
        sleeve = trimesh.creation.cylinder(radius=0.04, height=0.6, sections=24)
        sleeve.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        sleeve.apply_translation([0.22, 0.5, 0.0])  # inside the arm
        scene = trimesh.Scene(dense(sleeve, 2))

        moved = resolve_overlaps(scene, volume, margin=0.005, min_y=0.0)

        self.assertGreater(moved, 0)
        vertices = np.asarray(scene.to_geometry().vertices)
        self.assertTrue((volume.signed_distance(vertices) > -volume.pitch).all())


@unittest.skipUnless(BLENDER_AVAILABLE, "Blender is not installed")
class NewTypeSimulationTests(unittest.TestCase):
    def test_every_new_type_simulates_and_upper_ones_resolve_overlaps(self):
        body, landmarks = make_body_with_arms()
        cases = {
            "tank": make_shirt(False),
            "longsleeve": make_shirt(True),
            "shorts": dense(trimesh.creation.box(extents=[0.55, 0.65, 0.25])),
        }
        for kind, mesh in cases.items():
            with self.subTest(kind=kind):
                build = load_garment_mesh(glb(mesh), f"{kind}.glb", body, kind, body_landmarks=landmarks)
                exported, log, _ = simulate_static_garment(body, build.scene, kind, body_landmarks=landmarks)
                self.assertEqual(exported[:4], b"glTF")
                self.assertIn("STATIC_GARMENT_EXPORTED", log)
                self.assertEqual("BODY_OVERLAP_RESOLVED" in log, kind != "shorts")


REAL = Path(__file__).resolve().parents[2].parent / "Ropa_glb_prueba"


@unittest.skipUnless(
    BLENDER_AVAILABLE and (REAL / "camisa_star.glb").is_file() and (REAL / "AVATAR_PRUEBA.glb").is_file(),
    "Blender or the real test files are not available",
)
class RealShirtArmpitTests(unittest.TestCase):
    def test_shirt_does_not_go_through_the_arms_or_the_armpit(self):
        avatar = trimesh.load(REAL / "AVATAR_PRUEBA.glb", force="scene").to_geometry()
        build = load_garment_mesh((REAL / "camisa_star.glb").read_bytes(), "camisa_star.glb", avatar, "tshirt")

        exported, log, _ = simulate_static_garment(avatar, build.scene, "tshirt")

        self.assertIn("BODY_OVERLAP_RESOLVED", log)
        shirt = trimesh.load(trimesh.util.wrap_as_stream(exported), file_type="glb", force="scene")
        vertices = np.asarray(shirt.to_geometry().vertices)
        for closed in (False, True):
            volume = BodyVolume(avatar.vertices, avatar.faces, close_gaps=closed)
            deep = int((volume.signed_distance(vertices) < -volume.pitch).sum())
            self.assertEqual(deep, 0, f"closed={closed}")


if __name__ == "__main__":
    unittest.main()
