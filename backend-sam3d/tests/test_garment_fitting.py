import io
import os
import unittest
from unittest.mock import patch

import numpy as np
import trimesh

from garment_fitting import build_fitted_garment, extract_garment_mask
from services.blender_service import (
    BlenderBusyError,
    BlenderUnavailableError,
    _resolve_blender_executable,
    STEAM_BLENDER_PATH,
)


BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
TEMPLATES_DIR = os.path.join(BACKEND_DIR, "templates")


def make_body_glb() -> bytes:
    body = trimesh.creation.icosphere(subdivisions=2, radius=1)
    body.apply_scale([0.26, 0.89, 0.20])
    body.apply_translation([0, 0.89, 0])
    return body.export(file_type="glb")


def make_garment_image(garment_type: str) -> tuple[np.ndarray, np.ndarray]:
    pixels = np.zeros((100, 100, 4), dtype=np.uint8)
    pixels[:, :, :3] = [80, 120, 180]
    pixels[:, :, 3] = 255
    mask = np.zeros((100, 100), dtype=bool)

    if garment_type == "shirt":
        mask[10:88, 12:88] = True
    else:
        mask[8:48, 30:70] = True
        mask[48:96, 22:44] = True
        mask[48:96, 56:78] = True

    pixels[mask, :3] = [180, 50, 90]
    return pixels, mask


class FittedGarmentTests(unittest.TestCase):
    def build(self, garment_type: str) -> tuple[trimesh.Trimesh, str]:
        pixels, mask = make_garment_image(garment_type)
        scene, detected_type = build_fitted_garment(
            make_body_glb(),
            pixels,
            mask,
            TEMPLATES_DIR,
        )
        return next(iter(scene.geometry.values())), detected_type

    def test_shirt_template_is_fitted_and_textured(self) -> None:
        pixels, mask = make_garment_image("shirt")
        scene, detected_type = build_fitted_garment(
            make_body_glb(),
            pixels,
            mask,
            TEMPLATES_DIR,
        )
        garment = scene.geometry["fitted_garment"]

        self.assertEqual(detected_type, "shirt")
        self.assertEqual(len(scene.geometry), 1)
        self.assertGreater(len(garment.faces), 1000)
        original_template = trimesh.load(
            os.path.join(TEMPLATES_DIR, "base_shirt.glb"),
            force="mesh",
        )
        self.assertLess(len(garment.faces), len(original_template.faces))
        self.assertEqual(garment.visual.uv.shape, (len(garment.vertices), 2))
        self.assertIsNotNone(garment.visual.material.baseColorTexture)
        self.assertEqual(garment.visual.material.alphaMode, "BLEND")
        self.assertAlmostEqual(
            garment.bounds[0, 1],
            0.89 + (0.50 - 0.5) * 1.78,
            delta=1e-5,
        )
        self.assertAlmostEqual(
            garment.bounds[1, 1],
            0.89 + (0.85 - 0.5) * 1.78,
            delta=1e-5,
        )
        body = trimesh.creation.icosphere(subdivisions=2, radius=1)
        body.apply_scale([0.26, 0.89, 0.20])
        body.apply_translation([0, 0.89, 0])
        region = body.vertices[
            (body.vertices[:, 1] >= 0.50 * 1.78)
            & (body.vertices[:, 1] <= 0.85 * 1.78)
        ]
        expected_width = np.ptp(np.percentile(region[:, 0], [5, 95]))
        expected_depth = np.ptp(np.percentile(region[:, 2], [5, 95]))
        self.assertAlmostEqual(garment.extents[0], expected_width, delta=1e-5)
        self.assertAlmostEqual(garment.extents[2], expected_depth, delta=1e-5)
        texture = np.asarray(garment.visual.material.baseColorTexture)
        self.assertTrue(np.any(texture[:, :, 3] == 0))
        self.assertTrue(np.any(texture[:, :, 3] == 255))

        exported = scene.export(file_type="glb")
        loaded = trimesh.load(
            io.BytesIO(exported),
            file_type="glb",
            force="mesh",
        )
        self.assertIsInstance(loaded, trimesh.Trimesh)
        self.assertEqual(loaded.visual.material.alphaMode, "BLEND")
        self.assertIsNotNone(loaded.visual.material.baseColorTexture)

    def test_pants_template_is_fitted_to_lower_body(self) -> None:
        garment, detected_type = self.build("pants")

        self.assertEqual(detected_type, "pants")
        self.assertEqual(garment.visual.uv.shape, (len(garment.vertices), 2))
        self.assertAlmostEqual(garment.bounds[0, 1], 0.89 + (0.03 - 0.5) * 1.78, delta=0.02)
        self.assertAlmostEqual(garment.bounds[1, 1], 0.89 + (0.55 - 0.5) * 1.78, delta=0.02)

    def test_rejects_non_glb_body(self) -> None:
        pixels, mask = make_garment_image("shirt")

        with self.assertRaisesRegex(ValueError, "archivo GLB válido"):
            build_fitted_garment(b"not-glb", pixels, mask, TEMPLATES_DIR)

    def test_blender_missing_from_path_is_reported(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "services.blender_service.shutil.which",
            return_value=None,
        ), patch("services.blender_service.os.path.isfile", return_value=False):
            with self.assertRaises(BlenderUnavailableError):
                _resolve_blender_executable()

    def test_blender_uses_steam_installation_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "services.blender_service.shutil.which",
            return_value=None,
        ), patch("services.blender_service.os.path.isfile", return_value=True):
            self.assertEqual(_resolve_blender_executable(), STEAM_BLENDER_PATH)

    def test_extracts_alpha_mask(self) -> None:
        pixels = np.zeros((40, 40, 4), dtype=np.uint8)
        pixels[8:32, 12:28, 3] = 255

        mask = extract_garment_mask(pixels)

        self.assertTrue(mask[20, 20])
        self.assertFalse(mask[0, 0])


if __name__ == "__main__":
    unittest.main()
