# blender -b --python make_mesh_parent.py -- OUT.blend   メッシュの下にメッシュ（と空）がぶら下がる最小の .blend
import bpy, sys
out = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
root = bpy.data.objects.new("ROOT", None)
bpy.context.scene.collection.objects.link(root)
root["kn5_name"] = "kanachu_route_bus"


def cube(name, loc, parent, scale=1.0):
    bpy.ops.mesh.primitive_cube_add(size=scale, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.parent = parent
    o.matrix_parent_inverse = parent.matrix_world.inverted()
    o["kn5_name"] = name
    o["kn5_material"] = "paint"
    return o


door = cube("DOOR", (0.5, 2.0, 1.0), root)
door.rotation_euler = (0, 0, 0.5)
cube("PANEL", (0.8, 2.0, 1.5), door, 0.2)
e = bpy.data.objects.new("HINGE", None)
bpy.context.scene.collection.objects.link(e)
e.parent = door
e["kn5_name"] = "HINGE"
bpy.ops.wm.save_as_mainfile(filepath=out)
