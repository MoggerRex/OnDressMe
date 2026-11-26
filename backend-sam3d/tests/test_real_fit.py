import unittest

import numpy as np
import trimesh

from services.body_volume import BodyVolume
from services.sleeve_fit import retarget_sleeves
from services.garment_pipeline import (
    _densify_scene,
    _garment_torso_core,
    load_garment_mesh,
)
from tests.test_garment_types import dense, glb, make_body_with_arms


def hanging_sleeve_shirt():
    """Torso 0.4 wide with sleeves that hang outward and reach the hem (A-pose)."""
    torso = dense(trimesh.creation.box(extents=[0.4, 0.6, 0.25]), 5)
    torso.apply_translation([0.0, 0.3, 0.0])
    parts = [torso]
    for sign in (-1, 1):
        sleeve = dense(trimesh.creation.box(extents=[0.12, 0.4, 0.12]), 5)
        sleeve.apply_translation([sign * 0.5, 0.3, 0.0])  # separated from the torso, above the hem
        parts.append(sleeve)
    return trimesh.util.concatenate(parts)


def short_sleeve_shirt(length):
    torso = dense(trimesh.creation.box(extents=[0.5, 0.65, 0.25]))
    torso.apply_translation([0.0, 0.325, 0.0])
    parts = [torso]
    for sign in (-1, 1):
        sleeve = dense(trimesh.creation.box(extents=[length, 0.14, 0.14]))
        sleeve.apply_translation([sign * (0.25 + length / 2), 0.55, 0.0])
        parts.append(sleeve)
    return trimesh.util.concatenate(parts)


class TorsoMeasureTests(unittest.TestCase):
    def test_hanging_sleeves_do_not_count_as_torso_width(self):
        scene = trimesh.Scene(hanging_sleeve_shirt())
        _, center, width = _garment_torso_core(scene)
        self.assertAlmostEqual(width, 0.4, delta=0.03)
        self.assertAlmostEqual(center, 0.0, delta=0.02)

    def test_coarse_garments_are_subdivided(self):
        box = trimesh.creation.box(extents=[0.5, 0.65, 0.25])
        scene = trimesh.Scene(box)
        before = len(box.vertices)
        self.assertGreater(_densify_scene(scene), 0)
        self.assertGreater(len(next(iter(scene.geometry.values())).vertices), before)


class SleeveLengthTests(unittest.TestCase):
    def cuff_y(self, shirt):
        body, landmarks = make_body_with_arms()
        vertices = np.asarray(shirt.vertices) + [0.0, 1.0, 0.0]
        sleeve = vertices[:, 0] > 0.3  # outside the torso (half width 0.25)
        bent, info = retarget_sleeves(vertices, 0.0, 0.25, body.vertices, landmarks, 1.8)
        self.assertEqual(info["sleeves_fitted"], 2)
        return float(bent[sleeve][:, 1].min()), landmarks

    def test_a_short_sleeve_stays_short_and_a_long_one_reaches_the_wrist(self):
        short_y, landmarks = self.cuff_y(short_sleeve_shirt(0.14))
        long_y, _ = self.cuff_y(short_sleeve_shirt(0.45))
        self.assertGreater(short_y, landmarks["left-elbow"][1])
        self.assertLess(long_y, landmarks["left-elbow"][1] - 0.1)


class TorsoSectionTests(unittest.TestCase):
    def test_tight_is_narrower_than_loose_below_the_armpit(self):
        body, landmarks = make_body_with_arms()
        widths = {}
        for fit in ("tight", "loose"):
            result = load_garment_mesh(
                glb(short_sleeve_shirt(0.14)), "s.glb", body, "tshirt", body_landmarks=landmarks, fit=fit
            )
            self.assertTrue(result.metrics["fit_torso_sections"])
            vertices = np.asarray(result.scene.to_geometry().vertices)
            slab = vertices[np.abs(vertices[:, 1] - 1.0) < 0.03]
            widths[fit] = float(np.ptp(slab[:, 0]))
        self.assertLess(widths["tight"], widths["loose"])


class PullInTests(unittest.TestCase):
    def test_only_far_points_above_the_limit_height_come_back(self):
        sphere = trimesh.creation.icosphere(subdivisions=3, radius=0.3)
        volume = BodyVolume(sphere.vertices, sphere.faces, close_gaps=False)
        points = np.array(
            [[0.0, 0.0, 0.3 + 0.002], [0.0, 0.0, 0.3 + 0.03], [0.0, -0.31, 0.0], [0.0, 0.0, 0.3 + 0.03]]
        )
        points[3, 1] = 0.0
        points[1, 2] = 0.3 + 0.03
        displacement, moved = volume.pull_in(points, max_gap=0.02, min_y=-0.2)
        self.assertEqual(moved, 2)  # point 2 is below min_y, point 0 is already close
        self.assertLess(displacement[1, 2], -0.005)
        self.assertEqual(float(np.abs(displacement[0]).max()), 0.0)
        self.assertEqual(float(np.abs(displacement[2]).max()), 0.0)


class SeamTests(unittest.TestCase):
    def test_duplicated_seam_vertices_move_together(self):
        from services.body_volume import _smooth_displacement

        # Two panels that meet along x == 0 with their own copies of the seam vertices.
        left = trimesh.creation.box(extents=[1.0, 1.0, 0.01])
        left = trimesh.Trimesh(*trimesh.remesh.subdivide(left.vertices, left.faces), process=False)
        left.apply_translation([-0.5, 0.0, 0.0])
        right = left.copy()
        right.apply_translation([1.0, 0.0, 0.0])
        mesh = trimesh.util.concatenate([left, right])
        push = np.zeros_like(mesh.vertices)
        on_left_seam = np.isclose(mesh.vertices[:, 0], 0.0) & (np.arange(len(push)) < len(left.vertices))
        push[on_left_seam] = [0.0, 0.0, 0.1]  # only the left copy is pushed

        smoothed = _smooth_displacement(mesh, push)
        seam = np.flatnonzero(np.isclose(mesh.vertices[:, 0], 0.0))
        for index in seam:
            twin = seam[np.all(np.isclose(mesh.vertices[seam], mesh.vertices[index]), axis=1)]
            np.testing.assert_allclose(smoothed[twin], np.tile(smoothed[index], (len(twin), 1)), atol=1e-9)


if __name__ == "__main__":
    unittest.main()
