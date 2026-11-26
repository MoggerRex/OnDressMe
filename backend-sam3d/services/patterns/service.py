"""Everything the pattern panel needs about one uploaded shirt."""
from __future__ import annotations

import base64

import numpy as np
import trimesh

from services.garment_pipeline import (
    UPPER_GARMENT_TYPES,
    GarmentPipelineError,
    load_garment_mesh,
    read_garment_scene,
)
from services.patterns.analyzer import analyze, from_scene
from services.patterns.fitting import measure
from services.patterns.flatten import build_patterns, find_seams
from services.patterns.segmenter import PIECE_NAMES, SegmentationError, segment

PIECE_COLORS = {
    "front": "#e5484d",
    "back": "#3e9be0",
    "sleeve_left_front": "#46b96b",
    "sleeve_left_back": "#1f7a45",
    "sleeve_right_front": "#f0b429",
    "sleeve_right_back": "#b97d0a",
    "collar": "#b46ae0",
    "cuff_left": "#2ec4c9",
    "cuff_right": "#e87bb0",
}
PREVIEW_HEIGHT = 1.1  # where the viewer looks


def pieces_glb(mesh, segmentation, scale: float) -> bytes:
    """The pieces as separate coloured meshes, pulled apart for inspection."""
    center = (mesh.vertices.min(0) + mesh.vertices.max(0)) / 2
    scene = trimesh.Scene()
    for index, name in enumerate(segmentation.pieces):
        used, faces = np.unique(mesh.faces[segmentation.labels == index], return_inverse=True)
        points = (mesh.vertices[used] - center) * scale
        offset = points.mean(0) * 0.35
        if name.endswith(("front", "back")):
            depth = 0.12 if name in ("front", "back") else 0.06
            offset[2] += depth if name.endswith("front") else -depth
        piece = trimesh.Trimesh(points + offset + [0.0, PREVIEW_HEIGHT, 0.0], faces.reshape(-1, 3), process=False)
        # glTF colour factors are linear; the panel's hex colours are sRGB.
        color = [round(255 * (int(PIECE_COLORS[name][i : i + 2], 16) / 255) ** 2.2) for i in (1, 3, 5)]
        piece.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                name=name, baseColorFactor=[*color, 255], doubleSided=True, metallicFactor=0.0,
                roughnessFactor=0.9,
            )
        )
        scene.add_geometry(piece, node_name=name, geom_name=name)
    return bytes(scene.export(file_type="glb"))


def inspect_shirt(
    contents: bytes,
    filename: str,
    garment_type: str = "tshirt",
    body_mesh: trimesh.Trimesh | None = None,
    body_landmarks: dict[str, np.ndarray] | None = None,
    fit: str = "regular",
) -> dict:
    """Analysis, pieces, 2D patterns, seams and (with an avatar) measurements."""
    if garment_type not in UPPER_GARMENT_TYPES:
        raise GarmentPipelineError("Los patrones solo están disponibles para camisas.")
    scene = read_garment_scene(contents, filename)[0]
    mesh = from_scene(scene)
    try:
        segmentation = segment(mesh)
    except SegmentationError as error:
        raise GarmentPipelineError(str(error)) from error

    scale, body_report = 1.0, None
    if body_mesh is not None and body_landmarks:
        build = load_garment_mesh(
            contents, filename, body_mesh, garment_type, body_landmarks=body_landmarks, fit=fit, edits={}
        )
        # Pattern sizes follow the size the garment gets on this avatar.
        scale = float(build.metrics["fit_scale_y"])
        fitted_data, fitted_segmentation = build.pattern
        body_report = measure(
            from_scene(build.scene).vertices,
            fitted_data.faces,
            fitted_segmentation,
            np.asarray(body_mesh.vertices),
            body_landmarks,
            fit,
        )

    patterns = build_patterns(mesh, segmentation)
    pieces = []
    for name in segmentation.pieces:
        pattern = patterns[name]
        flat = pattern["flat"] * scale * 100  # centimetres
        pieces.append({
            "id": name,
            "name": PIECE_NAMES[name],
            "color": PIECE_COLORS[name],
            "faces": int(len(pattern["faces"])),
            "width_cm": round(float(np.ptp(flat[:, 0])), 1),
            "height_cm": round(float(np.ptp(flat[:, 1])), 1),
            "distortion": pattern["distortion"],
            # Boundary segments [x1, y1, x2, y2] in cm, y up.
            "outline": np.round(pattern["outline"] * scale * 100, 2).tolist(),
        })
    return {
        "method": segmentation.method,
        "analysis": analyze(mesh),
        "pieces": pieces,
        "seams": [
            {"a": s["a"], "b": s["b"], "length_cm": round(s["length"] * scale * 100, 1)}
            for s in find_seams(mesh, segmentation)
        ],
        "body": body_report,
        "pieces_glb": base64.b64encode(pieces_glb(mesh, segmentation, scale)).decode("ascii"),
    }
