import os
import sys

import bpy


MAX_BODY_COLLISION_FACES = 16000
MAX_CLOTH_FACES = 6000


def simplify_mesh(obj, max_faces, name):
    face_count = len(obj.data.polygons)
    if face_count <= max_faces:
        return

    modifier = obj.modifiers.new(name=name, type="DECIMATE")
    modifier.ratio = max_faces / face_count
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)


def import_meshes(path):
    objects_before_import = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    imported_objects = set(bpy.context.scene.objects) - objects_before_import
    meshes = [obj for obj in imported_objects if obj.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"No se encontraron mallas en '{path}'.")
    return meshes


def main():
    arguments = sys.argv[sys.argv.index("--") + 1:]
    if len(arguments) != 3:
        raise ValueError(
            "Uso: simulate_garment.py -- body.glb garment.glb output.glb"
        )

    body_path, garment_path, output_path = map(os.path.abspath, arguments)
    if not os.path.isfile(body_path) or not os.path.isfile(garment_path):
        raise FileNotFoundError("No se encontró el cuerpo o la prenda GLB.")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    body_objects = import_meshes(body_path)
    garment_objects = import_meshes(garment_path)
    scene = bpy.context.scene
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 24
    scene.use_gravity = True

    for body in body_objects:
        simplify_mesh(body, MAX_BODY_COLLISION_FACES, "CollisionMeshReduction")
        body.modifiers.new(name="BodyCollision", type="COLLISION")
        body.collision.thickness_outer = 0.015
        body.collision.thickness_inner = 0.01

    for garment in garment_objects:
        simplify_mesh(garment, MAX_CLOTH_FACES, "ClothMeshReduction")
        cloth = garment.modifiers.new(name="ClothSimulation", type="CLOTH")
        cloth.settings.quality = 5
        cloth.settings.mass = 0.3
        cloth.settings.tension_stiffness = 15
        cloth.settings.compression_stiffness = 15
        cloth.settings.shear_stiffness = 5
        cloth.settings.bending_stiffness = 0.5
        cloth.collision_settings.use_collision = True
        cloth.collision_settings.distance_min = 0.015
        cloth.collision_settings.use_self_collision = (
            len(garment.data.polygons) <= MAX_CLOTH_FACES
        )
        cloth.collision_settings.self_distance_min = 0.01
        cloth.point_cache.frame_start = scene.frame_start
        cloth.point_cache.frame_end = scene.frame_end

    scene.frame_set(scene.frame_start)
    for frame in range(scene.frame_start + 1, scene.frame_end + 1):
        scene.frame_set(frame)

    bpy.ops.object.select_all(action="DESELECT")
    for garment in garment_objects:
        garment.select_set(True)
    bpy.context.view_layer.objects.active = garment_objects[0]
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=output_path,
        export_format="GLB",
        use_selection=True,
    )


if __name__ == "__main__":
    main()
