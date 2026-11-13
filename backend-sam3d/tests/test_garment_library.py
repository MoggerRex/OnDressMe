import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh

from services.garment_library import (
    GarmentLibraryError,
    body_fingerprint,
    get_garment,
    list_garments,
    process_or_reuse_garment,
)


def make_test_body():
    body = trimesh.creation.icosphere(subdivisions=3)
    body.apply_scale([0.3, 1.0, 0.18])
    body.apply_translation([0.0, 1.0, 0.0])
    return body


class GarmentLibraryTests(unittest.TestCase):
    def test_saves_and_reuses_processed_garment_without_running_blender_twice(self):
        body = make_test_body()
        contents = trimesh.creation.box(extents=[0.55, 0.65, 0.25]).export(
            file_type="glb"
        )
        simulated_glb = trimesh.Scene(trimesh.creation.box()).export(file_type="glb")

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {"ONDRESSME_WARDROBE_DIR": directory},
            ):
                with patch(
                    "services.garment_library.simulate_static_garment",
                    return_value=(
                        simulated_glb,
                        "PENETRATION_TRIANGLE_PAIRS=0",
                        0,
                    ),
                ) as simulate:
                    first = process_or_reuse_garment(
                        body,
                        {},
                        contents,
                        r"C:\uploads\favorite_shirt.glb",
                        "tshirt",
                    )
                    second = process_or_reuse_garment(
                        body,
                        {},
                        contents,
                        r"C:\uploads\favorite_shirt.glb",
                        "tshirt",
                    )

                self.assertFalse(first.cached)
                self.assertTrue(second.cached)
                self.assertEqual(first.item["id"], second.item["id"])
                self.assertEqual(first.item["name"], "favorite_shirt")
                self.assertTrue(first.file_path.is_file())
                self.assertEqual(first.file_path.read_bytes(), simulated_glb)
                self.assertEqual(simulate.call_count, 1)

                items = list_garments(body_fingerprint(body, {}))
                self.assertEqual([item["id"] for item in items], [first.item["id"]])
                stored = get_garment(body_fingerprint(body, {}), first.item["id"])
                self.assertIsNotNone(stored)
                self.assertEqual(stored[1].read_bytes(), simulated_glb)

                other_body = body.copy()
                other_body.vertices = np.asarray(other_body.vertices) + [0.01, 0.0, 0.0]
                self.assertEqual(
                    list_garments(body_fingerprint(other_body, {})),
                    [],
                )

    def test_body_fingerprint_changes_when_body_geometry_changes(self):
        first_body = make_test_body()
        second_body = first_body.copy()
        second_body.vertices = np.asarray(second_body.vertices) + [0.01, 0.0, 0.0]

        self.assertNotEqual(
            body_fingerprint(first_body, {}),
            body_fingerprint(second_body, {}),
        )

    def test_reports_corrupt_index_and_missing_glb(self):
        body_id = body_fingerprint(make_test_body(), {})
        item_id = "a" * 32

        with tempfile.TemporaryDirectory() as directory:
            body_directory = Path(directory) / body_id
            body_directory.mkdir()
            manifest_path = body_directory / "manifest.json"

            with patch.dict(os.environ, {"ONDRESSME_WARDROBE_DIR": directory}):
                manifest_path.write_text("{", encoding="utf-8")
                with self.assertRaises(GarmentLibraryError):
                    list_garments(body_id)

                manifest_path.write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "items": [
                                {
                                    "id": item_id,
                                    "name": "sample",
                                    "source_filename": "sample.glb",
                                    "download_filename": "sample_adaptada.glb",
                                    "garment_type": "tshirt",
                                    "source_sha256": "b" * 64,
                                    "created_at": "2026-01-01T00:00:00+00:00",
                                    "pipeline_info": "{}",
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                with self.assertRaises(GarmentLibraryError):
                    list_garments(body_id)


if __name__ == "__main__":
    unittest.main()
