# blender -b --python make_cube.py -- OUT.blend
import bpy, sys
out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
root = bpy.data.objects.new("ROOT", None)
bpy.context.scene.collection.objects.link(root)
root["kn5_name"] = "kanachu_route_bus"
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.5, 2.0, 1.0))
cube = bpy.context.active_object
cube.name = "CUBE"
cube.parent = root
cube["kn5_name"] = "BODY_TEST"
cube["kn5_material"] = "paint"
if not cube.data.uv_layers:
    cube.data.uv_layers.new(name="UVMap")
bpy.ops.wm.save_as_mainfile(filepath=out)
