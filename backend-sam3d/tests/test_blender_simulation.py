import io
import subprocess
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import trimesh

from services.blender_simulator import (
    BLENDER_CANDIDATES,
    simulate_static_garment,
)
from services.garment_pipeline import load_garment_mesh


BLENDER_AVAILABLE = shutil.which("blender") or any(
    Path(candidate).is_file() for candidate in BLENDER_CANDIDATES
)


@unittest.skipUnless(BLENDER_AVAILABLE, "Blender is not installed")
class BlenderSimulationTests(unittest.TestCase):
    def test_simulates_uploaded_mesh_and_exports_valid_glb(self):
        body = trimesh.creation.icosphere(subdivisions=3)
        body.apply_scale([0.3, 1.0, 0.18])
        body.apply_translation([0.0, 1.0, 0.0])
        connected_mesh = trimesh.creation.icosphere(subdivisions=2)
        disconnected_vertices = connected_mesh.vertices[connected_mesh.faces].reshape(
            -1, 3
        )
        input_mesh = trimesh.Trimesh(
            vertices=disconnected_vertices,
            faces=np.arange(len(disconnected_vertices)).reshape(-1, 3),
            process=False,
        )
        mesh_bytes = input_mesh.export(file_type="glb")
        garment = load_garment_mesh(mesh_bytes, "tshirt.glb", body)

        glb, log, intersection_pairs = simulate_static_garment(body, garment.scene)

        self.assertGreater(len(glb), 12)
        self.assertEqual(glb[:4], b"glTF")
        self.assertGreaterEqual(intersection_pairs, 0)
        self.assertIn("PENETRATION_TRIANGLE_PAIRS=", log)
        self.assertRegex(log, r"WELDED_MESH\[.+\]=\d+->\d+")
        self.assertRegex(log, r"BODY_CLEARANCE_VERTICES\[.+\]=\d+")
        exported = trimesh.load(
            file_obj=io.BytesIO(glb),
            file_type="glb",
            force="scene",
        )
        self.assertIsInstance(exported, trimesh.Scene)
        self.assertTrue(exported.geometry)
        self.assertTrue(
            all(
                np.isfinite(mesh.vertices).all()
                for mesh in exported.geometry.values()
            )
        )


class BlenderTimeoutTests(unittest.TestCase):
    def test_blender_has_no_timeout_by_default(self):
        body = trimesh.creation.box()
        garment = trimesh.Scene(trimesh.creation.box())
        output_glb = trimesh.Scene(trimesh.creation.box()).export(file_type="glb")

        def finish_process(command, **kwargs):
            output_path = Path(command[command.index("--output") + 1])
            output_path.write_bytes(output_glb)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="PENETRATION_TRIANGLE_PAIRS=0",
                stderr="",
            )

        with (
            patch(
                "services.blender_simulator._find_blender",
                return_value="blender",
            ),
            patch(
                "services.blender_simulator.subprocess.run",
                side_effect=finish_process,
            ) as run_process,
        ):
            simulate_static_garment(body, garment)

        self.assertIsNone(run_process.call_args.kwargs["timeout"])


if __name__ == "__main__":
    unittest.main()
