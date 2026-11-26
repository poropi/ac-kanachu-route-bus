# blender -b --python make_mini_design.py -- OUT.blend [BREAK]
# 規約をすべて満たす最小の外装 .blend を作る。BREAK で 1 か所だけ壊す。
import bpy, sys, bmesh
a = sys.argv[sys.argv.index("--") + 1:]
out = a[0]
brk = a[1] if len(a) > 1 else ""
bpy.ops.wm.read_factory_settings(use_empty=True)
col = bpy.context.scene.collection
mats = {}
def mat(n):
    if n not in mats:
        mats[n] = bpy.data.materials.new(n)
    return mats[n]
def empty(name, loc=(0, 0, 0), parent=None):
    o = bpy.data.objects.new(name, None); o.location = loc; col.objects.link(o)
    if parent: o.parent = parent
    return o
def cube(name, loc, size, material, parent, uv_box=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bm.to_mesh(me); bm.free()
    me.uv_layers.new(name="UVMap")
    u0, v0, u1, v1 = uv_box or (0.0, 0.0, 1.0, 1.0)
    uvd = me.uv_layers[0].data
    for pi, poly in enumerate(me.polygons):   # 6 面を 3x2 の格子に 1 面ずつ（重ならない）
        cu, cv = pi % 3, pi // 3
        for k, li in enumerate(poly.loop_indices):
            ux, uy = ((0, 0), (1, 0), (1, 1), (0, 1))[k]
            uvd[li].uv = (u0 + (cu + 0.05 + 0.9 * ux) / 3 * (u1 - u0), v0 + (cv + 0.05 + 0.9 * uy) / 2 * (v1 - v0))
    me.materials.append(mat(material))
    o = bpy.data.objects.new(name, me); o.location = loc; o.scale = size; col.objects.link(o); o.parent = parent
    return o
root = empty("ROOT")
WH = {"LF": (-1.0325, 2.65), "RF": (1.0325, 2.65), "LR": (-0.91, -2.65), "RR": (0.91, -2.65)}
for k, (x, y) in WH.items():
    empty("WHEEL_" + k, (x, y, 0.478), root); empty("SUSP_" + k, (x, y, 0.478), root)
body = cube("Body", (0, 0.2, 1.5525), (2.485, 10.43, 3.105), "paint", root, (0.0, 0.0, 0.5, 0.5))
side = cube("Side", (0, 0, 2.0), (0.1, 0.1, 0.1), "paint", root, (0.6, 0.0, 0.9, 0.5))
# 外接箱から除く物（ミラー・ワイパー・ナンバー）
cube("Mirror_Port_Foot", (-1.5, 4.0, 2.0), (0.3, 0.1, 0.1), "chrome", root)
cube("WiperBlade_L", (0, 5.2, 1.5), (0.1, 0.1, 0.1), "trim_black", root)
cube("FrontPlate_Type_0", (0, 5.1, 0.6), (0.1, 0.1, 0.1), "trim_black", root)
for n in ("BRAKE_L BRAKE_R HEAD_L HEAD_R IND_FL IND_FR IND_RL IND_RR REVERSE_L REVERSE_R TAIL_L TAIL_R").split():
    cube("LIGHT_" + n, (0, 0, 1.0), (0.05, 0.05, 0.05), "light_emit", root)
for n in ("FRONT", "SIDE", "REAR"):
    cube("DEST_" + n, (0, 0, 2.5), (0.05, 0.05, 0.05), "dest_led", root)
for n in ("FRONT", "MID"):
    cube("DOOR_" + n, (1.2, 0, 1.0), (0.05, 0.05, 0.05), "glass", root)
O = bpy.data.objects
if brk == "missing_object": bpy.data.objects.remove(O["LIGHT_TAIL_L"])
elif brk == "missing_wheel": bpy.data.objects.remove(O["WHEEL_RR"])
elif brk == "bad_material": O["Body"].data.materials[0] = mat("mystery")
elif brk == "no_material":
    O["Body"].data.materials.clear()
elif brk == "wheel_pos": O["WHEEL_LF"].location.x += 0.02
elif brk == "susp_pos": O["SUSP_RR"].location.z += 0.02
elif brk == "bbox": O["Body"].scale.y = 10.60
elif brk == "mirror_not_excluded": O["Mirror_Port_Foot"].name = "Rearview_Port_Foot"; O["Rearview_Port_Foot"].location.x = -2.5
elif brk == "no_uv": O["Side"].data.uv_layers.remove(O["Side"].data.uv_layers[0])
elif brk == "uv_range":
    for l in O["Side"].data.uv_layers[0].data: l.uv = (l.uv[0] + 0.5, l.uv[1])
elif brk == "uv_overlap":
    for l in O["Side"].data.uv_layers[0].data:   # Body の展開 (0..0.5) と同じ範囲へ
        l.uv = ((l.uv[0] - 0.6) / 0.3 * 0.5, l.uv[1] / 0.5 * 0.5)
elif brk == "too_many_verts":
    me = bpy.data.meshes.new("Big"); bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=260, y_segments=260, size=1.0)
    bm.to_mesh(me); bm.free(); me.uv_layers.new(name="UVMap")
    for l in me.uv_layers[0].data: l.uv = (0.0, 0.0)
    me.materials.append(mat("trim_black"))
    o = bpy.data.objects.new("Big", me); col.objects.link(o); o.parent = root; o.location = (0, 0, 1)
bpy.ops.wm.save_as_mainfile(filepath=out)
