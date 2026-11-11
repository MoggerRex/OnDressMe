import os
import sys

import bpy
from mathutils import Vector


body_path, garment_path, output_path = map(os.path.abspath, sys.argv[-3:])
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=body_path)
bpy.ops.import_scene.gltf(filepath=garment_path)

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 600
scene.render.resolution_y = 900
scene.render.resolution_percentage = 100

camera_data = bpy.data.cameras.new("PreviewCamera")
camera = bpy.data.objects.new("PreviewCamera", camera_data)
scene.collection.objects.link(camera)
camera.location = (0, -4.4, 0.95)
camera.rotation_euler = (
    Vector((0, 0, 0.95)) - camera.location
).to_track_quat("-Z", "Y").to_euler()
camera_data.lens = 50
scene.camera = camera

for name, location, energy, size in (
    ("Key", (3, 3, 4), 900, 4),
    ("Fill", (-3, 2, 2), 700, 4),
    ("Rim", (0, 3, -3), 1000, 3),
):
    light_data = bpy.data.lights.new(name, "AREA")
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    scene.collection.objects.link(light)
    light.location = location
    light.rotation_euler = (
        Vector((0, 1, 0)) - light.location
    ).to_track_quat("-Z", "Y").to_euler()

scene.render.image_settings.file_format = "PNG"
scene.render.filepath = output_path
bpy.ops.render.render(write_still=True)
