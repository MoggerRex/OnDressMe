import unittest

import numpy as np

from services.body_shape import FACTOR_RANGES, NEUTRAL, sculpt
from tests.test_garment_types import make_body_with_arms


def body():
    mesh, landmarks = make_body_with_arms()
    landmarks = dict(landmarks)
    shoulder = (landmarks["left-shoulder"] + landmarks["right-shoulder"]) / 2
    landmarks.setdefault("neck", shoulder + [0.0, 0.03, 0.0])
    landmarks["nose"] = landmarks["neck"] + [0.0, 0.12, 0.1]  # faces +z
    return np.asarray(mesh.vertices), np.asarray(mesh.faces), landmarks


class SculptTests(unittest.TestCase):
    def test_neutral_factors_change_nothing(self):
        vertices, faces, landmarks = body()
        np.testing.assert_array_equal(sculpt(vertices, faces, landmarks, NEUTRAL), vertices)

    def test_bigger_arms_widen_the_arms_and_not_the_legs(self):
        vertices, faces, landmarks = body()
        result = sculpt(vertices, faces, landmarks, {"arms": 1.5})
        shoulder, elbow = landmarks["left-shoulder"], landmarks["left-elbow"]
        middle = (shoulder + elbow) / 2
        arm = np.linalg.norm(vertices - middle, axis=1) < 0.06
        spread = lambda points: float(np.ptp(points[arm, 2]))
        self.assertGreater(spread(result), 1.2 * spread(vertices))

        legs = vertices[:, 1] < landmarks["left-knee"][1]
        self.assertLess(float(np.abs(result[legs] - vertices[legs]).max()), 0.005)

    def test_bust_moves_the_front_of_the_chest_forward_only(self):
        vertices, faces, landmarks = body()
        result = sculpt(vertices, faces, landmarks, {"bust": 1.6})
        move = result - vertices
        self.assertGreater(float(move[:, 2].max()), 0.015)  # coarse test mesh
        back = vertices[:, 2] < -0.05
        self.assertLess(float(np.abs(move[back]).max()), 0.005)

    def test_factors_outside_the_limits_are_clamped(self):
        vertices, faces, landmarks = body()
        extreme = sculpt(vertices, faces, landmarks, {"waist": 99.0})
        limit = sculpt(vertices, faces, landmarks, {"waist": FACTOR_RANGES["waist"][1]})
        np.testing.assert_allclose(extreme, limit)


if __name__ == "__main__":
    unittest.main()
