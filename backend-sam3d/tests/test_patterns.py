import unittest
from pathlib import Path

import numpy as np
import trimesh

from services.garment_pipeline import read_garment_scene
from services.patterns.analyzer import GarmentMesh, analyze, from_scene, weld_ids
from services.patterns.editor import apply_edits, parse_edits
from services.patterns.flatten import build_patterns, flatten, open_tube
from services.patterns.segmenter import segment
from services.patterns.sewing import simplify_pieces, split_pieces, transfer
from services.patterns.validation import validate

SHIRT = Path(__file__).resolve().parents[3] / "Ropa_buena" / "camisa_manga_corta_1.obj"


def tube(radius=0.1, length=0.3):
    mesh = trimesh.creation.cylinder(radius=radius, height=length, sections=32)
    sides = np.abs(mesh.face_normals[:, 2]) < 0.5
    mesh.update_faces(sides)
    mesh.remove_unreferenced_vertices()
    for _ in range(3):
        mesh = trimesh.Trimesh(*trimesh.remesh.subdivide(mesh.vertices, mesh.faces))
    return np.asarray(mesh.vertices)[:, [2, 1, 0]], np.asarray(mesh.faces)


class FlattenTests(unittest.TestCase):
    def test_a_tube_is_opened_and_flattened_keeping_its_lengths(self):
        points, faces = tube()
        cut_faces, source = open_tube(points, faces, underarm=True)
        positions = points[source]
        flat = flatten(positions, cut_faces)

        edges = cut_faces[:, [[0, 1], [1, 2], [2, 0]]].reshape(-1, 2)
        real = np.linalg.norm(positions[edges[:, 0]] - positions[edges[:, 1]], axis=1)
        drawn = np.linalg.norm(flat[edges[:, 0]] - flat[edges[:, 1]], axis=1)
        self.assertGreater(len(source), len(points))  # the cut duplicated vertices
        self.assertLess(float(np.median(np.abs(drawn / real - 1))), 0.01)


class EditParsingTests(unittest.TestCase):
    def test_neutral_edits_are_dropped_and_bad_ones_rejected(self):
        self.assertEqual(parse_edits({"front": {"width": 1.0}}), {})
        self.assertEqual(parse_edits({"front": {"width": 1.1}})["front"], {"width": 1.1, "length": 1.0})
        for bad in ({"pocket": {"width": 1.1}}, {"front": {"width": 3}}, {"front": {"depth": 1.1}}, []):
            with self.assertRaises(ValueError):
                parse_edits(bad)


@unittest.skipUnless(SHIRT.is_file(), "falta la camisa de prueba en Ropa_buena")
class RealShirtPatternTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mesh = from_scene(read_garment_scene(SHIRT.read_bytes(), SHIRT.name)[0])
        cls.pieces = segment(cls.mesh)

    def names(self, segmentation):
        return np.array(segmentation.pieces)[segmentation.labels]

    def test_uv_layout_gives_the_sewing_pieces_with_halved_sleeves(self):
        self.assertEqual(self.pieces.method, "uv")
        self.assertEqual(
            set(self.pieces.pieces),
            {"front", "back", "sleeve_left_front", "sleeve_left_back",
             "sleeve_right_front", "sleeve_right_back", "collar"},
        )
        counts = np.bincount(self.pieces.labels)
        for side in ("left", "right"):
            front = counts[self.pieces.pieces.index(f"sleeve_{side}_front")]
            back = counts[self.pieces.pieces.index(f"sleeve_{side}_back")]
            self.assertAlmostEqual(front / back, 1.0, delta=0.2)
        self.assertEqual(analyze(self.mesh)["uv_islands"], 5)

    def test_geometric_cut_of_the_welded_mesh_agrees_with_the_designer(self):
        bare = GarmentMesh(self.mesh.vertices, self.mesh.faces, None, weld_ids(self.mesh.vertices))
        by_geometry = segment(bare)
        self.assertEqual(by_geometry.method, "geometry")
        self.assertGreater(float((self.names(by_geometry) == self.names(self.pieces)).mean()), 0.9)

    def test_patterns_keep_edge_lengths(self):
        for name, pattern in build_patterns(self.mesh, self.pieces).items():
            self.assertLess(pattern["distortion"]["median"], 0.01, name)

    def test_widening_the_front_moves_it_without_opening_seams(self):
        mesh = self.mesh
        edited = apply_edits(
            mesh.vertices, mesh.faces, mesh.weld, self.pieces, {"front": {"width": 1.2, "length": 1.0}}
        )
        report = validate(mesh.vertices, edited, mesh.faces, mesh.weld, self.pieces)
        self.assertLess(report["max_seam_gap"], 1e-5)
        self.assertLessEqual(report["flipped_faces"], 8)  # of 8448, in the armpit corner
        self.assertGreater(report["area_change"]["front"], 1.05)
        self.assertAlmostEqual(report["area_change"]["collar"], 1.0, delta=0.03)
        self.assertAlmostEqual(report["area_change"]["sleeve_left_front"], 1.0, delta=0.12)


    def test_cut_pieces_are_stitched_along_every_seam(self):
        faces, source, piece_of, sew = split_pieces(self.mesh, self.pieces)

        # Each stitch joins two copies of the same point in different pieces.
        self.assertTrue(np.all(source[sew[:, 0]] == source[sew[:, 1]]))
        self.assertTrue(np.all(piece_of[sew[:, 0]] != piece_of[sew[:, 1]]))
        copies = np.bincount(source, minlength=int(self.mesh.weld.max()) + 1)
        self.assertEqual(len(sew), int(np.maximum(copies - 1, 0).sum()))
        self.assertEqual(len(faces), len(self.mesh.faces))


class LightSimulationMeshTests(unittest.TestCase):
    def test_a_rigid_motion_of_the_light_mesh_is_carried_to_the_full_one(self):
        points, faces = tube()
        piece_of = np.zeros(len(points), dtype=int)
        rest, start, light_faces, stitches, light_piece = simplify_pieces(
            points, points, faces, np.array([[0, 1]]), piece_of, target=120
        )
        self.assertLess(len(rest), len(points) / 3)
        turn = trimesh.transformations.rotation_matrix(0.8, [1, 2, 3])[:3, :3]
        moved = rest @ turn.T + [0.2, 0.1, -0.3]

        carried = transfer(points, piece_of, rest, moved, light_faces, light_piece)

        np.testing.assert_allclose(carried, points @ turn.T + [0.2, 0.1, -0.3], atol=1e-6)


if __name__ == "__main__":
    unittest.main()
