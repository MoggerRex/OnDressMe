"""Blender: sew the pattern pieces of a shirt together and drape it on the body.

Input (.npz, glTF axes: Y up, metres):
  start   (n, 3) where every piece vertex begins, around the body
  rest    (n, 3) the shape of the cut pieces: cloth lengths and folds come from it
  faces   (m, 3) triangles of the pieces
  sew     (k, 2) vertex pairs to be sewn (loose edges = Blender sewing springs)
  body_open, body_vertices, body_faces: the avatar with its arms lifted and as
          it really is; the arms close during the simulation
Output (.npz): final (n, 3), same vertex order.
"""
import argparse
import sys

import bpy
import numpy as np
from mathutils.bvhtree import BVHTree


def to_blender(points):
    return np.stack([points[:, 0], -points[:, 2], points[:, 1]], axis=1)


def from_blender(points):
    return np.stack([points[:, 0], points[:, 2], -points[:, 1]], axis=1)


def make_object(name, vertices, edges, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices.tolist(), edges, faces.tolist())
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", type=int, default=140)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    data = np.load(args.input)
    start, rest, faces = data["start"], data["rest"], data["faces"]
    sew = data["sew"]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    frames = args.frames
    body = make_object("Body", to_blender(data["body_open"]), [], data["body_faces"])
    body.shape_key_add(name="Open")
    closed = body.shape_key_add(name="Closed")
    closed.data.foreach_set("co", to_blender(data["body_vertices"]).astype(np.float32).ravel())
    for frame, value in ((1, 0.0), (int(frames * 0.4), 0.0), (int(frames * 0.75), 1.0)):
        closed.value = value
        closed.keyframe_insert("value", frame=frame)
    body.modifiers.new(name="BodyCollision", type="COLLISION")
    body.collision.thickness_outer = 0.004
    body.collision.thickness_inner = 0.02
    body.collision.damping = 0.5
    body.collision.cloth_friction = 15.0

    garment = make_object("Garment", to_blender(start), sew.tolist(), faces)
    garment.shape_key_add(name="Start")
    rest_key = garment.shape_key_add(name="Rest")
    rest_key.data.foreach_set("co", to_blender(rest).astype(np.float32).ravel())
    rest_key.value = 0.0

    cloth = garment.modifiers.new(name="Sewing", type="CLOTH")
    settings = cloth.settings
    settings.quality = 10
    settings.mass = 0.3
    settings.air_damping = 3.0
    settings.tension_stiffness = 15.0
    settings.compression_stiffness = 15.0
    settings.shear_stiffness = 6.0
    settings.bending_stiffness = 0.15
    settings.tension_damping = 10.0
    settings.compression_damping = 10.0
    settings.shear_damping = 8.0
    settings.rest_shape_key = rest_key
    settings.use_sewing_springs = True
    settings.sewing_force_max = 10.0

    collision = cloth.collision_settings
    collision.use_collision = True
    collision.collision_quality = 4
    collision.distance_min = 0.003
    collision.use_self_collision = True
    collision.self_distance_min = 0.0015
    collision.self_friction = 2.0

    # Sew first with little gravity, then let the shirt hang.
    weights = settings.effector_weights
    for frame, value in ((1, 0.05), (int(frames * 0.2), 0.2), (int(frames * 0.35), 1.0)):
        weights.gravity = value
        weights.keyframe_insert("gravity", frame=frame)

    scene.gravity = (0.0, 0.0, -9.81)
    scene.frame_start = 1
    scene.frame_end = args.frames
    cloth.point_cache.frame_start = 1
    cloth.point_cache.frame_end = args.frames
    for frame in range(1, args.frames + 1):
        scene.frame_set(frame)

    evaluated = garment.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    final = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", final)
    evaluated.to_mesh_clear()
    final = from_blender(final.reshape(-1, 3).astype(np.float64))
    if len(final) != len(start) or not np.isfinite(final).all():
        raise RuntimeError("La simulación de costura produjo geometría inválida.")
    np.savez(args.output, final=final)
    gap = np.linalg.norm(final[sew[:, 0]] - final[sew[:, 1]], axis=1) if len(sew) else np.zeros(1)
    triangles = faces.tolist()
    pairs = BVHTree.FromPolygons(to_blender(final).tolist(), triangles).overlap(
        BVHTree.FromPolygons(to_blender(data["body_vertices"]).tolist(), data["body_faces"].tolist())
    )
    print(f"PENETRATION_TRIANGLE_PAIRS={len(pairs)}")
    print(f"SEAM_GAP_MEDIAN={np.median(gap):.5f}")
    print(f"SEAM_GAP_P95={np.percentile(gap, 95):.5f}")


main()
