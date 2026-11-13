import unittest

import numpy as np
import trimesh

from services.garment_pipeline import (
    GarmentPipelineError,
    _apply_posterior_waist_anchor,
    _apply_anterior_waist_clamp,
    _bilateral_section_centers,
    _apply_waist_contour_clamp,
    _body_section_centers,
    _body_pants_profile,
    _sample_radial_profile,
    load_garment_mesh,
)


def make_test_body():
    body = trimesh.creation.icosphere(subdivisions=3)
    body.apply_scale([0.3, 1.0, 0.18])
    body.apply_translation([0.0, 1.0, 0.0])
    return body


def make_mesh_bytes(file_type):
    mesh = trimesh.creation.box(extents=[0.55, 0.65, 0.25])
    content = mesh.export(file_type=file_type)
    return content.encode() if isinstance(content, str) else content


def make_mhr_landmarks():
    return {
        "left-hip": np.array([-0.10, 1.05, 0.10]),
        "right-hip": np.array([0.10, 1.05, 0.10]),
        "left-knee": np.array([-0.12, 0.55, 0.0]),
        "right-knee": np.array([0.12, 0.55, 0.0]),
        "left-ankle": np.array([-0.12, 0.10, 0.0]),
        "right-ankle": np.array([0.12, 0.10, 0.0]),
        "nose": np.array([0.0, 1.80, 0.12]),
        "neck": np.array([0.0, 1.60, 0.0]),
    }


class GarmentPipelineTests(unittest.TestCase):
    def test_loads_and_aligns_a_real_garment_mesh(self):
        contents = make_mesh_bytes("glb")

        result = load_garment_mesh(contents, "tshirt.glb", make_test_body())

        self.assertEqual(result.metrics["geometry_source"], "uploaded_garment_mesh")
        self.assertEqual(result.metrics["source_format"], "glb")
        self.assertEqual(result.metrics["image_use"], "embedded_or_mesh_materials")
        self.assertTrue(result.scene.geometry)
        self.assertTrue(
            all(
                np.isfinite(mesh.vertices).all()
                for mesh in result.scene.geometry.values()
            )
        )
        bounds = result.scene.bounds
        self.assertAlmostEqual(float(bounds[:, 1].mean()), 1.35, places=4)

    def test_centers_on_a_slanted_body_torso(self):
        body = make_test_body()
        baseline = load_garment_mesh(make_mesh_bytes("glb"), "shirt.glb", body)

        vertices = np.asarray(body.vertices).copy()
        vertices[:, 0] += 0.12 * (vertices[:, 1] - 1.0)
        vertices[:, 2] += 0.05 * (vertices[:, 1] - 1.0)
        body.vertices = vertices
        slanted = load_garment_mesh(make_mesh_bytes("glb"), "shirt.glb", body)

        baseline_center_x = float(baseline.scene.bounds[:, 0].mean())
        slanted_center_x = float(slanted.scene.bounds[:, 0].mean())
        self.assertGreater(slanted_center_x - baseline_center_x, 0.02)

    def test_fits_pants_to_the_lower_body_range(self):
        body = make_test_body()

        result = load_garment_mesh(
            make_mesh_bytes("glb"),
            "pants.glb",
            body,
            "pants",
        )

        self.assertEqual(result.metrics["garment_type"], "pants")
        self.assertAlmostEqual(result.metrics["fit_torso_y_min"], 0.04, places=4)
        self.assertAlmostEqual(
            result.metrics["fit_torso_y_max"],
            result.metrics["fit_waist_y"],
            places=4,
        )
        self.assertGreaterEqual(result.metrics["fit_waist_fraction"], 0.48)
        self.assertLessEqual(result.metrics["fit_waist_fraction"], 0.60)
        self.assertGreater(result.metrics["fit_waist_section_width"], 0)
        self.assertGreater(result.metrics["fit_waist_section_depth"], 0)
        body_profile = _body_pants_profile(np.asarray(body.vertices))
        self.assertLessEqual(
            result.metrics["fit_waist_section_width"],
            body_profile.waist_width * 1.04,
        )
        self.assertLessEqual(
            result.metrics["fit_waist_section_depth"],
            body_profile.waist_depth * 1.04,
        )
        self.assertAlmostEqual(float(result.scene.bounds[:, 1].min()), 0.04, places=4)
        self.assertAlmostEqual(
            float(result.scene.bounds[:, 1].max()),
            result.metrics["fit_waist_y"],
            places=4,
        )

    def test_tracks_each_leg_center_instead_of_the_gap_between_legs(self):
        vertices = []
        for y in np.linspace(0.1, 0.75, 48):
            for center_x in (-0.16, 0.13):
                for angle in np.linspace(0, 2 * np.pi, 24, endpoint=False):
                    vertices.append(
                        [
                            center_x + 0.055 * np.cos(angle),
                            y,
                            0.045 * np.sin(angle),
                        ]
                    )

        fractions = np.linspace(0.02, 0.57, 18)
        centers = _bilateral_section_centers(
            np.asarray(vertices),
            np.asarray([vertex[1] for vertex in vertices]),
            fractions,
            center_x=-0.015,
        )

        self.assertIsNotNone(centers)
        lower_leg = int(np.argmin(np.abs(fractions - 0.25)))
        self.assertAlmostEqual(centers[lower_leg, 0, 0], -0.16, delta=0.015)
        self.assertAlmostEqual(centers[lower_leg, 1, 0], 0.13, delta=0.015)

    def test_anchors_pants_to_mhr_hips_and_leg_joints(self):
        body = make_test_body()
        landmarks = make_mhr_landmarks()

        profile = _body_pants_profile(np.asarray(body.vertices), landmarks)
        result = load_garment_mesh(
            make_mesh_bytes("glb"),
            "pants.glb",
            body,
            "pants",
            body_landmarks=landmarks,
        )

        self.assertTrue(profile.landmark_anchored)
        self.assertAlmostEqual(profile.waist_fraction, 0.60, delta=0.02)
        self.assertAlmostEqual(profile.center_x, 0.0, places=5)
        self.assertAlmostEqual(profile.center_z, 0.0, delta=0.04)
        self.assertLess(float(np.max(np.abs(profile.leg_centers[:, :, 1]))), 0.04)
        self.assertEqual(result.metrics["fit_anchor_source"], "mhr70_keypoints")
        self.assertGreater(result.metrics["fit_posterior_rise_units"], 0)
        self.assertGreater(result.metrics["fit_posterior_clearance_units"], 0)
        self.assertGreater(result.metrics["fit_anterior_surface_distance_units"], 0)
        self.assertGreater(result.metrics["fit_waist_contour_clearance_units"], 0)
        self.assertIsNotNone(profile.waist_center_xz)
        self.assertAlmostEqual(
            result.metrics["fit_posterior_anchor_y"],
            profile.posterior_anchor_y,
            places=5,
        )
        self.assertIsNotNone(profile.posterior_anchor_xz)

    def test_posterior_waist_anchor_stays_outside_the_measured_body_surface(self):
        body = make_test_body()
        vertices = np.asarray(body.vertices)
        profile = _body_pants_profile(vertices, make_mhr_landmarks())
        anchor_fraction = (
            profile.posterior_anchor_y - profile.body_min_y
        ) / profile.body_height
        landmarks = make_mhr_landmarks()
        center_x = float(
            np.mean(
                [
                    landmarks["left-hip"][0],
                    landmarks["right-hip"][0],
                ]
            )
        )
        central_limit = max(
            float(np.ptp(vertices[:, 0])) * 0.20,
            profile.body_height * 0.14,
        )
        normalized_y = (vertices[:, 1] - profile.body_min_y) / profile.body_height
        sample_mask = (
            (np.abs(normalized_y - anchor_fraction) <= 0.035)
            & (np.abs(vertices[:, 0] - center_x) <= central_limit)
        )
        samples = vertices[sample_mask]
        if len(samples) < 8:
            samples = vertices[
                np.abs(normalized_y - anchor_fraction) <= 0.035
            ]
        rear_direction = -profile.front_direction
        sample_centered = samples[:, [0, 2]] - profile.posterior_anchor_center_xz
        surface_distance = float(
            np.quantile(sample_centered @ rear_direction, 0.95)
        )
        anchor_distance = float(
            (profile.posterior_anchor_xz - profile.posterior_anchor_center_xz)
            @ rear_direction
        )

        self.assertAlmostEqual(
            anchor_distance - surface_distance,
            profile.posterior_clearance,
            places=6,
        )

    def test_anterior_waist_clamp_removes_front_bulge_without_moving_back_or_legs(self):
        body = make_test_body()
        profile = _body_pants_profile(
            np.asarray(body.vertices),
            make_mhr_landmarks(),
        )
        vertices = np.array(
            [
                [0.0, 1.0, profile.anterior_surface_distance + 0.30],
                [0.0, 1.0, profile.anterior_surface_distance - 0.20],
                [0.0, 0.50, profile.anterior_surface_distance + 0.30],
            ]
        )

        adjusted = _apply_anterior_waist_clamp(
            vertices.copy(),
            front_direction=profile.front_direction,
            waist_center_xz=profile.waist_center_xz,
            anterior_surface_distance=profile.anterior_surface_distance,
            clearance=profile.posterior_clearance,
            target_y_low=0.0,
            target_height=1.0,
        )

        self.assertAlmostEqual(
            adjusted[0, 2],
            profile.anterior_surface_distance + profile.posterior_clearance,
            places=6,
        )
        self.assertAlmostEqual(adjusted[1, 2], vertices[1, 2], places=6)
        self.assertAlmostEqual(adjusted[2, 2], vertices[2, 2], places=6)

    def test_posterior_waist_anchor_moves_only_the_rear_upper_section(self):
        vertices = np.array(
            [
                [0.0, 1.0, -0.10],
                [0.0, 1.0, 0.10],
                [0.0, 0.50, -0.10],
            ]
        )

        adjusted = _apply_posterior_waist_anchor(
            vertices.copy(),
            front_direction=np.array([0.0, 1.0]),
            anchor_center_xz=np.array([0.0, 0.0]),
            posterior_surface_distance=0.12,
            clearance=0.02,
            anchor_y=1.10,
            body_depth=0.30,
            target_y_low=0.0,
            target_height=1.0,
        )

        self.assertAlmostEqual(adjusted[0, 1], 1.10, places=6)
        self.assertAlmostEqual(adjusted[0, 2], -0.14, places=6)
        self.assertAlmostEqual(adjusted[1, 1], vertices[1, 1], places=6)
        self.assertAlmostEqual(adjusted[1, 2], vertices[1, 2], places=6)
        self.assertAlmostEqual(adjusted[2, 1], vertices[2, 1], places=6)
        self.assertAlmostEqual(adjusted[2, 2], vertices[2, 2], places=6)

    def test_tightens_the_complete_waist_contour_to_body_surface_clearance(self):
        body = make_test_body()
        profile = _body_pants_profile(
            np.asarray(body.vertices),
            make_mhr_landmarks(),
        )
        angles = np.array([-np.pi, -np.pi / 2, 0.0, np.pi / 2])
        body_radii = _sample_radial_profile(
            angles,
            profile.waist_contour_radii,
        )
        garment_radii = body_radii + 0.12
        top_vertices = np.column_stack(
            (
                profile.waist_center_xz[0] + np.cos(angles) * garment_radii,
                np.ones(len(angles)),
                profile.waist_center_xz[1] + np.sin(angles) * garment_radii,
            )
        )
        lower_vertices = top_vertices.copy()
        lower_vertices[:, 1] = 0.40
        vertices = np.concatenate((top_vertices, lower_vertices))

        adjusted = _apply_waist_contour_clamp(
            vertices.copy(),
            waist_center_xz=profile.waist_center_xz,
            waist_contour_radii=profile.waist_contour_radii,
            clearance=profile.waist_contour_clearance,
            target_y_low=0.0,
            target_height=1.0,
        )

        adjusted_top_radii = np.linalg.norm(
            adjusted[: len(angles), :][:, [0, 2]]
            - profile.waist_center_xz,
            axis=1,
        )
        np.testing.assert_allclose(
            adjusted_top_radii,
            body_radii + profile.waist_contour_clearance,
            atol=1e-6,
        )
        np.testing.assert_allclose(
            adjusted[len(angles) :],
            lower_vertices,
            atol=1e-6,
        )

    def test_pants_centerline_ignores_outstretched_arms(self):
        body = make_test_body()
        arm_points = np.tile(np.array([[0.75, 1.2, 0.8]]), (40, 1))
        vertices = np.concatenate((np.asarray(body.vertices), arm_points))
        fraction = np.array([0.60])

        unfiltered = _body_section_centers(
            vertices,
            fraction,
            body.bounds[0, 1],
            body.bounds[1, 1] - body.bounds[0, 1],
        )[1]
        torso_only = _body_section_centers(
            vertices,
            fraction,
            body.bounds[0, 1],
            body.bounds[1, 1] - body.bounds[0, 1],
            center_x=0.0,
            central_radius=0.25,
        )[1]

        self.assertLess(abs(torso_only[0]), abs(unfiltered[0]))

    def test_accepts_garment3dgen_obj_geometry(self):
        result = load_garment_mesh(
            make_mesh_bytes("obj"),
            "mesh.obj",
            make_test_body(),
        )

        self.assertEqual(result.metrics["source_format"], "obj")
        self.assertTrue(
            any("OBJ" in warning for warning in result.warnings)
        )

    def test_rejects_images_and_corrupt_meshes(self):
        with self.assertRaises(GarmentPipelineError):
            load_garment_mesh(b"not a mesh", "shirt.png", make_test_body())

        with self.assertRaises(GarmentPipelineError):
            load_garment_mesh(b"not a GLB", "shirt.glb", make_test_body())

        with self.assertRaises(GarmentPipelineError):
            load_garment_mesh(
                make_mesh_bytes("glb"),
                "shirt.glb",
                make_test_body(),
                "dress",
            )

    def test_rejects_non_upright_body(self):
        body = make_test_body()
        body.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi / 2, [0, 0, 1])
        )

        with self.assertRaises(GarmentPipelineError):
            load_garment_mesh(make_mesh_bytes("glb"), "shirt.glb", body)


if __name__ == "__main__":
    unittest.main()
