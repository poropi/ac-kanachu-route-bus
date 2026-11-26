# blender -b --python blender/m1_collider.py -- --out blender/m1_collider.blend
import bpy, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import spec

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[argv.index("--out") + 1]
S = spec.load(); D = spec.derived(S)
Y_FRONT = D["axle_z_front"] + S["overhang_f"]; Y_REAR = D["axle_z_rear"] - S["overhang_r"]
CLR, H, W = S["ground_clearance"], S["height"], S["width"]

bpy.ops.wm.read_factory_settings(use_empty=True)
root = bpy.data.objects.new("ROOT", None)
bpy.context.scene.collection.objects.link(root)
root["kn5_name"] = "kanachu_route_bus"
bpy.ops.mesh.primitive_cube_add(size=1.0)
o = bpy.context.active_object
o.name = "COLLIDER_BODY"
o.dimensions = (W, Y_FRONT - Y_REAR, H - CLR)
bpy.ops.object.transform_apply(scale=True)
# AC は root -> mesh の 2 階層だと initPhysics で落ちる。動く車と同じ root -> dummy -> mesh にする
body = bpy.data.objects.new("COLLIDER_BODY_DUMMY", None)
bpy.context.scene.collection.objects.link(body)
body.parent = root
body["kn5_name"] = "COLLIDER_BODY"
o.parent = body
o.location = (0, (Y_FRONT + Y_REAR) / 2, (CLR + H) / 2)
o["kn5_name"] = "COLLIDER_BODY"; o["kn5_material"] = "trim_black"
m = bpy.data.materials.new("trim_black"); o.data.materials.append(m)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
