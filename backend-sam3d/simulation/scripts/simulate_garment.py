import argparse
import math
import sys

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree


SIMULATION_PROFILES = {
    "tshirt": {
        "frames": 18,
        "quality": 4,
        "mass": 0.3,
        "tension": 18.0,
        "compression": 18.0,
        "shear": 8.0,
        "bending": 0.6,
        "collision_distance": 0.004,
        "pin_fraction": 0.12,
    },
    "pants": {
        "frames": 24,
        "quality": 5,
        "mass": 0.4,
        "tension": 22.0,
        "compression": 22.0,
        "shear": 10.0,
        "bending": 0.8,
        "collision_distance": 0.004,
        "pin_fraction": 0.08,
    },
}


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--body", required=True)
    parser.add_argument("--garment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--type", choices=SIMULATION_PROFILES, default="tshirt")
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(args)


def import_meshes(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    return [
        obj
        for obj in bpy.data.objects
        if obj not in before and obj.type == "MESH"
    ]


def simplify_collision_copy(obj, max_vertices=16000):
    vertex_count = len(obj.data.vertices)
    if vertex_count <= max_vertices:
        return
    modifier = obj.modifiers.new(name="CollisionSimplification", type="DECIMATE")
    modifier.ratio = max(0.1, max_vertices / vertex_count)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)


def add_collision(obj, distance):
    obj.modifiers.new(name="BodyCollision", type="COLLISION")
    obj.collision.thickness_outer = distance
    obj.collision.thickness_inner = distance
    obj.collision.damping = 0.1
    obj.collision.cloth_friction = 5.0


def weld_garment_mesh(obj):
    vertex_count_before = len(obj.data.vertices)
    if vertex_count_before < 2:
        raise RuntimeError(f"La malla {obj.name} no tiene suficientes vértices.")

    merge_distance = max(obj.dimensions) * 1e-5
    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bmesh.ops.remove_doubles(
            bm,
            verts=bm.verts,
            dist=merge_distance,
        )
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(obj.data)
    finally:
        bm.free()
    obj.data.update()
    print(
        f"WELDED_MESH[{obj.name}]={vertex_count_before}->{len(obj.data.vertices)}"
    )


def clear_garment_penetrations(body_trees, garment_objects, clearance):
    for obj in garment_objects:
        world_to_local = obj.matrix_world.inverted()
        projected = 0
        for vertex in obj.data.vertices:
            world_position = obj.matrix_world @ vertex.co
            nearest_candidates = [
                tree.find_nearest(world_position) for tree in body_trees
            ]
            nearest_candidates = [
                candidate for candidate in nearest_candidates if candidate is not None
            ]
            if not nearest_candidates:
                raise RuntimeError(
                    f"No se encontró una superficie corporal para {obj.name}."
                )
            nearest_position, normal, _, _ = min(
                nearest_candidates,
                key=lambda candidate: candidate[3],
            )
            if normal.length_squared < 1e-12:
                raise RuntimeError(
                    f"La malla corporal tiene una normal inválida cerca de {obj.name}."
                )
            normal.normalize()
            signed_distance = (world_position - nearest_position).dot(normal)
            if signed_distance < clearance:
                corrected_position = nearest_position + normal * clearance
                vertex.co = world_to_local @ corrected_position
                projected += 1
        obj.data.update()
        print(f"BODY_CLEARANCE_VERTICES[{obj.name}]={projected}")


def fit_body_surface_clearance(
    body_trees,
    garment_objects,
    body_min_height,
    body_height,
    clearance,
    lower_fraction,
    upper_fraction,
    blend_width,
    max_correction_fraction,
    region_name,
):
    if body_height <= 0:
        raise RuntimeError(
            f"El cuerpo no tiene una altura válida para ajustar {region_name.lower()}."
        )

    max_correction = body_height * max_correction_fraction

    for obj in garment_objects:
        world_to_local = obj.matrix_world.inverted()
        tightened = 0
        for vertex in obj.data.vertices:
            world_position = obj.matrix_world @ vertex.co
            height_fraction = (
                world_position.z - body_min_height
            ) / body_height
            if not lower_fraction < height_fraction < upper_fraction:
                continue

            nearest_candidates = [
                tree.find_nearest(world_position) for tree in body_trees
            ]
            nearest_candidates = [
                candidate for candidate in nearest_candidates if candidate is not None
            ]
            if not nearest_candidates:
                raise RuntimeError(
                    f"No se encontró una superficie corporal para ajustar {obj.name}."
                )
            nearest_position, normal, _, distance = min(
                nearest_candidates,
                key=lambda candidate: candidate[3],
            )
            if distance <= clearance or normal.length_squared < 1e-12:
                continue

            displacement = world_position - nearest_position
            normal.normalize()
            if displacement.dot(normal) <= 0:
                continue

            blend = min(
                (height_fraction - lower_fraction) / blend_width,
                (upper_fraction - height_fraction) / blend_width,
                1.0,
            )
            blend = max(blend, 0.0)
            blend = blend * blend * (3.0 - 2.0 * blend)
            correction = min(distance - clearance, max_correction) * blend
            if correction <= 1e-8:
                continue

            displacement.normalize()
            corrected_position = world_position - displacement * correction
            vertex.co = world_to_local @ corrected_position
            tightened += 1

        obj.data.update()
        print(f"{region_name}_TIGHTENED_VERTICES[{obj.name}]={tightened}")


def fit_pants_surface_regions(
    body_trees,
    garment_objects,
    body_min_height,
    body_height,
    profile,
):
    fit_body_surface_clearance(
        body_trees,
        garment_objects,
        body_min_height,
        body_height,
        max(profile["collision_distance"] * 2, body_height * 0.004),
        0.30,
        0.54,
        0.06,
        0.06,
        "PELVIS",
    )
    fit_body_surface_clearance(
        body_trees,
        garment_objects,
        body_min_height,
        body_height,
        max(profile["collision_distance"] * 1.5, body_height * 0.003),
        0.50,
        0.63,
        0.035,
        0.04,
        "WAIST",
    )


def add_top_edge_pins(obj, settings, pin_fraction, group_name):
    world_vertices = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    max_height = max(vertex.z for vertex in world_vertices)
    min_height = min(vertex.z for vertex in world_vertices)
    garment_height = max_height - min_height
    if garment_height <= 0:
        raise RuntimeError(f"La prenda {obj.name} no tiene altura válida.")

    pin_group = obj.vertex_groups.new(name=group_name)
    pin_start = max_height - garment_height * pin_fraction
    pinned_vertices = 0
    for index, vertex in enumerate(world_vertices):
        weight = min(
            max(
                (vertex.z - pin_start) / (garment_height * pin_fraction * 0.5),
                0.0,
            ),
            1.0,
        )
        if weight > 0:
            pin_group.add([index], weight, "REPLACE")
            pinned_vertices += 1
    settings.vertex_group_mass = pin_group.name
    settings.pin_stiffness = 1.0
    print(f"ANCHOR_PIN_VERTICES[{obj.name}]={pinned_vertices}")


def count_surface_intersections(body_objects, garment_objects, depsgraph):
    collision_trees = [BVHTree.FromObject(obj, depsgraph) for obj in body_objects]
    intersections = {}
    for obj in garment_objects:
        evaluated = obj.evaluated_get(depsgraph)
        garment_tree = BVHTree.FromObject(evaluated, depsgraph)
        intersections[obj.name] = sum(
            len(collision_tree.overlap(garment_tree))
            for collision_tree in collision_trees
        )
    return intersections


def main():
    args = parse_arguments()
    profile = SIMULATION_PROFILES[args.type]

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    body_objects = import_meshes(args.body)
    if not body_objects:
        raise RuntimeError("El GLB corporal no contiene mallas.")
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    body_trees = [BVHTree.FromObject(obj, depsgraph) for obj in body_objects]
    if not body_trees or any(tree is None for tree in body_trees):
        raise RuntimeError("No se pudo crear el acelerador geométrico del cuerpo.")
    body_bounds = [
        obj.matrix_world @ Vector(corner)
        for obj in body_objects
        for corner in obj.bound_box
    ]
    body_min_height = min(point.z for point in body_bounds)
    body_max_height = max(point.z for point in body_bounds)
    body_height = body_max_height - body_min_height
    if body_height <= 0:
        raise RuntimeError("No se pudo determinar la altura del cuerpo.")

    garment_objects = import_meshes(args.garment)
    if not garment_objects:
        raise RuntimeError("El GLB de prenda no contiene mallas.")

    for obj in garment_objects:
        weld_garment_mesh(obj)
    clear_garment_penetrations(
        body_trees,
        garment_objects,
        profile["collision_distance"] * 3,
    )
    if args.type == "pants":
        fit_pants_surface_regions(
            body_trees,
            garment_objects,
            body_min_height,
            body_height,
            profile,
        )
    for obj in body_objects:
        simplify_collision_copy(obj)
        add_collision(obj, profile["collision_distance"])

    for obj in garment_objects:
        cloth = obj.modifiers.new(name="GarmentCloth", type="CLOTH")
        settings = cloth.settings
        settings.quality = profile["quality"]
        settings.mass = profile["mass"]
        settings.tension_stiffness = profile["tension"]
        settings.compression_stiffness = profile["compression"]
        settings.shear_stiffness = profile["shear"]
        settings.bending_stiffness = profile["bending"]
        settings.air_damping = 2.0
        collision = cloth.collision_settings
        collision.use_collision = True
        collision.use_self_collision = True
        collision.collision_quality = 3
        collision.distance_min = profile["collision_distance"]
        collision.self_distance_min = profile["collision_distance"]
        add_top_edge_pins(
            obj,
            settings,
            profile["pin_fraction"],
            "WaistbandAnchor" if args.type == "pants" else "ShoulderHold",
        )

    scene = bpy.context.scene
    scene.gravity = (0.0, 0.0, -9.81)
    scene.frame_start = 1
    scene.frame_end = profile["frames"]
    scene.frame_set(1)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    initial_intersections = count_surface_intersections(
        body_objects, garment_objects, depsgraph
    )
    print(f"INITIAL_INTERSECTIONS={sum(initial_intersections.values())}")
    for object_name, object_pairs in initial_intersections.items():
        print(f"INITIAL_INTERSECTIONS[{object_name}]={object_pairs}")
    for frame in range(2, scene.frame_end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()

    if args.type == "pants":
        fit_pants_surface_regions(
            body_trees,
            garment_objects,
            body_min_height,
            body_height,
            profile,
        )

    depsgraph = bpy.context.evaluated_depsgraph_get()
    final_intersections = count_surface_intersections(
        body_objects, garment_objects, depsgraph
    )
    penetration_pairs = sum(final_intersections.values())
    for object_name, object_pairs in final_intersections.items():
        print(f"PENETRATION_TRIANGLE_PAIRS[{object_name}]={object_pairs}")
    for obj in garment_objects:
        evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        evaluated_mesh = evaluated.to_mesh()
        try:
            for vertex in evaluated_mesh.vertices:
                coordinate = evaluated.matrix_world @ vertex.co
                if not all(math.isfinite(value) for value in coordinate):
                    raise RuntimeError(
                        f"La simulación produjo coordenadas inválidas en {obj.name}."
                    )
        finally:
            evaluated.to_mesh_clear()

    print(f"PENETRATION_TRIANGLE_PAIRS={penetration_pairs}")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in garment_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = garment_objects[0]
    bpy.ops.export_scene.gltf(
        filepath=args.output,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
    )
    print(f"STATIC_GARMENT_EXPORTED={args.output}")


if __name__ == "__main__":
    main()
