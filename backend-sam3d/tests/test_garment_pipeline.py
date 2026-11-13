import unittest

import numpy as np
import trimesh

from services.garment_pipeline import (
    GarmentPipelineError,
    _bilateral_section_centers,
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
        self.assertAlmostEqual(result.metrics["fit_torso_y_max"], 1.14, places=4)
        self.assertAlmostEqual(float(result.scene.bounds[:, 1].min()), 0.04, places=4)
        self.assertAlmostEqual(float(result.scene.bounds[:, 1].max()), 1.14, places=4)

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
