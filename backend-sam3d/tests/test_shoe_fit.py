import json
import unittest
from pathlib import Path

import numpy as np
import trimesh

from services.garment_library import process_or_reuse_garment
from services.garment_pipeline import GarmentPipelineError, load_garment_mesh
from tests.test_skeleton_fit import arm_landmarks, make_body_with_hands_at_hips, skinned_glb

FOOT_X = 0.12
HEEL_Z, TOE_Z = -0.06, 0.20


def landmarks():
    points = arm_landmarks()
    for side, sign in (("left", -1), ("right", 1)):
        points[f"{side}-ankle"] = np.array([sign * FOOT_X, 0.10, 0.0])
        points[f"{side}-heel"] = np.array([sign * FOOT_X, 0.03, HEEL_Z])
        points[f"{side}-big-toe-tip"] = np.array([sign * FOOT_X, 0.03, TOE_Z])
    return points


FOOT_LENGTH = 0.28


def make_body_with_feet(left_yaw=0.0, right_yaw=0.0):
    """Body standing on two box feet; each foot can be turned by a yaw angle."""
    body, _ = make_body_with_hands_at_hips()
    body.apply_translation([0.0, 0.12, 0.0])  # lift the torso off the floor
    feet = []
    for sign, yaw in ((-1, left_yaw), (1, right_yaw)):
        foot = trimesh.creation.box(extents=[0.08, 0.06, FOOT_LENGTH])
        for _ in range(3):  # a real foot has a dense footprint
            foot = trimesh.Trimesh(*trimesh.remesh.subdivide(foot.vertices, foot.faces), process=False)
        foot.apply_transform(
            trimesh.transformations.rotation_matrix(np.radians(yaw), [0, 1, 0])
        )
        foot.apply_translation([sign * FOOT_X, 0.03, (TOE_Z + HEEL_Z) / 2])
        feet.append(foot)
    return trimesh.util.concatenate([body, *feet])


def make_shoe(offset_x=0.0):
    """Long sole (+Z is the toe) with a tall collar at the heel end."""
    sole = trimesh.creation.box(extents=[0.10, 0.04, 0.30])
    sole.apply_translation([0.0, 0.02, 0.0])
    collar = trimesh.creation.box(extents=[0.10, 0.10, 0.08])
    collar.apply_translation([0.0, 0.09, -0.11])
    shoe = trimesh.util.concatenate([sole, collar])
    shoe.apply_translation([offset_x, 0.0, 0.0])
    return shoe


def to_glb(mesh, yaw_degrees=0.0, scale=1.0):
    mesh = mesh.copy()
    mesh.apply_transform(
        trimesh.transformations.rotation_matrix(np.radians(yaw_degrees), [0, 1, 0])
    )
    mesh.apply_scale(scale)
    return mesh.export(file_type="glb")


def fit(mesh, body_landmarks=None, **kwargs):
    body = make_body_with_feet()
    return load_garment_mesh(
        to_glb(mesh, **kwargs),
        "shoes.glb",
        body,
        "shoes",
        body_landmarks=body_landmarks or landmarks(),
    )


def shoe_vertices(result, sign):
    """Vertices of the shoe on one side, grouped by connected piece (a turned
    shoe can reach across x=0, so a plain X split is not enough)."""
    pieces = result.scene.to_geometry().split(only_watertight=False)
    chosen = [p.vertices for p in pieces if p.vertices[:, 0].mean() * sign > 0]
    return np.concatenate(chosen)


class ShoeFitTests(unittest.TestCase):
    def assert_fits_foot(self, vertices, sign):
        length = float(np.ptp(vertices[:, 2]))
        self.assertAlmostEqual(length, 1.18 * FOOT_LENGTH, delta=0.015)
        self.assertAlmostEqual(float(vertices[:, 1].min()), 0.0, delta=1e-6)
        self.assertAlmostEqual(float(np.ptp(vertices[:, 2]) / 2 + vertices[:, 2].min() - (TOE_Z + HEEL_Z) / 2), 0.0, delta=0.03)
        self.assertAlmostEqual(float(vertices[:, 0].mean()), sign * FOOT_X, delta=0.02)
        # The tall collar must end up on the heel side, not the toe side.
        tall = vertices[vertices[:, 1] > vertices[:, 1].max() * 0.8]
        self.assertLess(float(tall[:, 2].mean()), (TOE_Z + HEEL_Z) / 2)

    def test_pair_is_placed_on_each_foot(self):
        pair = trimesh.util.concatenate([make_shoe(-0.30), make_shoe(0.30)])
        result = fit(pair)

        self.assertEqual(result.metrics["fit_shoe_layout"], "pair_x")
        for sign in (-1, 1):
            self.assert_fits_foot(shoe_vertices(result, sign), sign)

    def test_pair_in_any_orientation_and_size(self):
        pair = trimesh.util.concatenate([make_shoe(-0.30), make_shoe(0.30)])
        for yaw, scale in ((180, 1.0), (90, 1.0), (-90, 0.01), (37, 2.5)):
            with self.subTest(yaw=yaw, scale=scale):
                result = fit(pair, yaw_degrees=yaw, scale=scale)
                for sign in (-1, 1):
                    self.assert_fits_foot(shoe_vertices(result, sign), sign)

    def test_keypoints_only_choose_which_end_of_the_footprint_is_the_toe(self):
        swapped = landmarks()
        for side in ("left", "right"):
            swapped[f"{side}-heel"], swapped[f"{side}-big-toe-tip"] = (
                swapped[f"{side}-big-toe-tip"],
                swapped[f"{side}-heel"],
            )

        result = fit(make_shoe(), body_landmarks=swapped)

        for sign in (-1, 1):
            vertices = shoe_vertices(result, sign)
            tall = vertices[vertices[:, 1] > vertices[:, 1].max() * 0.8]
            # Toe is now at -Z, so the collar (heel) sits on the +Z side.
            self.assertGreater(float(tall[:, 2].mean()), (TOE_Z + HEEL_Z) / 2)
            self.assertAlmostEqual(float(np.ptp(vertices[:, 2])), 1.18 * FOOT_LENGTH, delta=0.015)

    def test_single_shoe_is_mirrored_for_the_other_foot(self):
        result = fit(make_shoe())

        self.assertEqual(result.metrics["fit_shoe_layout"], "single_mirrored")
        for sign in (-1, 1):
            self.assert_fits_foot(shoe_vertices(result, sign), sign)
        self.assertTrue(any("reflej" in warning for warning in result.warnings))

    def test_rigged_shoe_uses_its_toe_bone_for_direction(self):
        # Flat shoe with no height cue: only the toe bone says where the toe is.
        # The toe end is narrower, which lets us check the result.
        body = make_body_with_feet()
        for yaw in (0, 180, 90, -90):
            with self.subTest(yaw=yaw):
                sole = trimesh.creation.box(extents=[0.10, 0.06, 0.24])
                toe = trimesh.creation.box(extents=[0.05, 0.06, 0.08])
                toe.apply_translation([0.0, 0.0, 0.16])
                shoe = trimesh.util.concatenate([sole, toe])
                shoe.apply_translation([0.0, 0.03, 0.0])
                rotation = trimesh.transformations.rotation_matrix(
                    np.radians(yaw), [0, 1, 0]
                )[:3, :3]
                shoe.vertices = np.asarray(shoe.vertices) @ rotation.T
                joints = (
                    ("mixamorig:LeftFoot", None, tuple(rotation @ [0.0, 0.05, -0.05])),
                    ("mixamorig:LeftToeBase", 0, tuple(rotation @ [0.0, 0.03, 0.14])),
                )
                glb = skinned_glb(shoe, np.zeros(len(shoe.vertices), dtype=int), joints)

                result = load_garment_mesh(
                    glb, "shoe.glb", body, "shoes", body_landmarks=landmarks()
                )

                self.assertEqual(result.metrics["fit_shoe_orientation"], "rig")
                vertices = shoe_vertices(result, 1)
                narrow_end = vertices[:, 2] > vertices[:, 2].max() - 0.05
                wide_end = vertices[:, 2] < vertices[:, 2].min() + 0.05
                self.assertLess(
                    np.ptp(vertices[narrow_end, 0]), np.ptp(vertices[wide_end, 0])
                )

    def test_shoes_fit_without_keypoints_using_only_the_foot_footprint(self):
        body = make_body_with_feet()
        result = load_garment_mesh(to_glb(make_shoe()), "s.glb", body, "shoes")

        self.assertEqual(result.metrics["fit_anchor_source"], "foot_footprint_foot_profile")
        for sign in (-1, 1):
            self.assert_fits_foot(shoe_vertices(result, sign), sign)

    def test_turned_feet_orient_each_shoe_along_its_own_foot(self):
        # Keypoints deliberately point straight ahead: the footprint must win.
        for left_yaw, right_yaw in ((0, 0), (25, -12), (-30, 18)):
            with self.subTest(left=left_yaw, right=right_yaw):
                body = make_body_with_feet(left_yaw, right_yaw)
                pair = trimesh.util.concatenate([make_shoe(-0.30), make_shoe(0.30)])
                result = load_garment_mesh(
                    to_glb(pair), "s.glb", body, "shoes", body_landmarks=landmarks()
                )
                for sign, yaw in ((-1, left_yaw), (1, right_yaw)):
                    vertices = shoe_vertices(result, sign)
                    xz = vertices[:, [0, 2]] - vertices[:, [0, 2]].mean(axis=0)
                    axis = np.linalg.eigh(np.cov(xz.T))[1][:, -1]
                    angle = np.degrees(np.arctan2(axis[0], axis[1])) % 180
                    difference = abs(angle - yaw % 180)
                    self.assertLess(min(difference, 180 - difference), 2.0)
                    # The tall collar stays on the heel side of the turned foot.
                    forward = np.array([np.sin(np.radians(yaw)), np.cos(np.radians(yaw))])
                    tall = vertices[vertices[:, 1] > vertices[:, 1].max() * 0.8][:, [0, 2]]
                    self.assertLess(float(((tall - xz.mean(axis=0) - vertices[:, [0, 2]].mean(axis=0)) @ forward).mean()), 0.0)

    def test_library_stores_shoes_without_blender(self):
        import tempfile
        from unittest.mock import patch

        body = make_body_with_feet()
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"ONDRESSME_WARDROBE_DIR": directory}
        ):
            result = process_or_reuse_garment(
                body, landmarks(), to_glb(make_shoe()), "botas.glb", "shoes"
            )
            again = process_or_reuse_garment(
                body, landmarks(), to_glb(make_shoe()), "botas.glb", "shoes"
            )
        info = json.loads(result.pipeline_info)
        self.assertEqual(info["metrics"]["garment_type"], "shoes")
        self.assertEqual(info["metrics"]["simulation"], "rigid_fit")
        self.assertFalse(result.cached)
        self.assertTrue(again.cached)


REAL_DIR = Path(__file__).resolve().parents[2].parent / "Ropa_glb_prueba"


@unittest.skipUnless(
    (REAL_DIR / "shoe.glb").is_file() and (REAL_DIR / "AVATAR_PRUEBA.glb").is_file(),
    "real shoe/avatar test files are not available",
)
class RealAssetShoeTests(unittest.TestCase):
    """AVATAR_PRUEBA has no keypoints and both feet turned outwards."""

    @classmethod
    def setUpClass(cls):
        avatar = trimesh.load(REAL_DIR / "AVATAR_PRUEBA.glb", force="scene").to_geometry()
        cls.body = np.asarray(avatar.vertices)
        cls.result = load_garment_mesh(
            (REAL_DIR / "shoe.glb").read_bytes(), "shoe.glb", avatar, "shoes"
        )
        cls.shoes = np.asarray(cls.result.scene.to_geometry().vertices)

    @staticmethod
    def footprint_axis(points):
        xz = points[:, [0, 2]]
        axis = np.linalg.eigh(np.cov((xz - xz.mean(axis=0)).T))[1][:, -1]
        along = (xz - xz.mean(axis=0)) @ axis
        return axis, np.percentile(along, [0.5, 99.5]) + 0, xz.mean(axis=0)

    def test_each_shoe_has_the_same_turn_as_its_foot(self):
        for sign in (-1, 1):
            floor = self.body[(self.body[:, 1] < 0.03) & (self.body[:, 0] * sign > 0)]
            shoe = self.shoes[self.shoes[:, 0] * sign > 0]
            foot_axis, _, _ = self.footprint_axis(floor)
            shoe_axis, _, _ = self.footprint_axis(shoe[shoe[:, 1] < shoe[:, 1].min() + 0.02])
            cosine = abs(float(foot_axis @ shoe_axis))
            self.assertGreater(cosine, np.cos(np.radians(4)), f"side {sign}")

    def test_feet_turn_differently_and_the_metrics_report_it(self):
        left = self.result.metrics["fit_foot_angle_left_deg"]
        right = self.result.metrics["fit_foot_angle_right_deg"]
        self.assertLess(left, -15)
        self.assertGreater(right, 5)

    def test_shoes_are_larger_than_the_feet_and_stand_on_the_floor(self):
        for sign in (-1, 1):
            floor = self.body[(self.body[:, 1] < 0.03) & (self.body[:, 0] * sign > 0)]
            shoe = self.shoes[self.shoes[:, 0] * sign > 0]
            axis, foot_range, centre = self.footprint_axis(floor)
            along = (shoe[:, [0, 2]] - centre) @ axis
            self.assertLessEqual(along.min(), foot_range[0])  # covers the heel point
            self.assertGreaterEqual(along.max(), foot_range[1])  # covers the toe point
            self.assertGreater(np.ptp(along), 1.1 * np.ptp(foot_range))
        self.assertAlmostEqual(float(self.shoes[:, 1].min()), float(self.body[:, 1].min()), delta=2e-3)


if __name__ == "__main__":
    unittest.main()
