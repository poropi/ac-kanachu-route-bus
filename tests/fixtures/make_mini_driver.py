# blender -b --python make_mini_driver.py -- OUT.blend [BREAK]
# BONES の全骨を A ポーズで置き、箱のメッシュを付けた、規約を満たす最小の運転手 .blend を作る。
# BREAK で 1 か所だけ壊す: missing_bone / extra_bone / wrong_parent / unweighted / no_modifier /
#   head_not_bone / bad_material / no_uv / tall / unpacked_image / missing_mesh
# 座標: +Y が前、+X がキャラの左、+Z が上、足が原点。
import os
import sys

import bmesh
import bpy
from mathutils import Vector

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools"))
from driver_skeleton import BONES, HEAD_MESHES, SKINNED_MESHES  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
out = a[0]
brk = a[1] if len(a) > 1 else ""
bpy.ops.wm.read_factory_settings(use_empty=True)
col = bpy.context.scene.collection

# 骨の頭の位置（A ポーズ）。左は +X、右は -X。
SPINE = {"DRIVER:DRIVER": (0, 0, 0), "DRIVER:RIG_Center": (0, 0, 0.95), "DRIVER:RIG_Hips": (0, 0, 0.95),
         "DRIVER:RIG_Cest": (0, 0, 1.15), "DRIVER:RIG_Nek": (0, 0, 1.40), "DRIVER:RIG_Head": (0, 0, 1.46)}
ARM = {"Clave": (0.04, 0, 1.38), "Shoulder": (0.10, 0, 1.40), "Arm": (0.18, 0, 1.38), "ForeArm": (0.30, 0, 1.12),
       "ForeArm_END": (0.38, 0, 0.94), "HAND": (0.42, 0, 0.86)}
LEG = {"Leg": (0.09, 0, 0.92), "Shin": (0.09, 0, 0.50), "Hill": (0.09, -0.04, 0.08), "Foot": (0.09, 0.08, 0.05)}
FINGER_SHIFT = {"Thumb": -0.04, "Index": -0.02, "Middle": 0.0, "Ring": 0.02, "Pinkie": 0.04}


def head_pos(name):
    if name in SPINE:
        return Vector(SPINE[name])
    if name == "DRIVER:RIG_Tail":   # extra_bone 用の余計な骨
        return Vector((0, -0.15, 0.95))
    s = name.split(":", 1)[1]
    side = 1.0 if s.endswith("_L") else -1.0
    base = s[:-2]
    if s.startswith("RIG_") and base[4:] in ARM:
        x, y, z = ARM[base[4:]]
    elif s.startswith("RIG_") and base[4:] in LEG:
        x, y, z = LEG[base[4:]]
    else:   # 指: HAND_L_Thumb1 / HAND_Index4 など。番号 1-3 が左、4-6 が右
        side = -1.0 if any(c in s for c in "456") or s.startswith("HAND_R_") else 1.0
        digit = int(s[-1])
        kind = next(k for k in FINGER_SHIFT if k in s)
        x, y, z = ARM["HAND"]
        x += FINGER_SHIFT[kind] * 0.3
        z -= 0.03 * ((digit - 1) % 3 + 1)
        y += FINGER_SHIFT[kind] * 0.5
    return Vector((side * x, y, z))


def build_armature():
    bones = [(n, p) for n, p in BONES]
    if brk == "missing_bone":
        bones = [(n, p) for n, p in bones if n != "DRIVER:HAND_Index5"]
        bones = [(n, p if p != "DRIVER:HAND_Index5" else "DRIVER:HAND_Index4") for n, p in bones]
    if brk == "extra_bone":
        bones.append(("DRIVER:RIG_Tail", "DRIVER:RIG_Hips"))
    if brk == "wrong_parent":
        bones = [(n, "DRIVER:RIG_Hips" if n == "DRIVER:RIG_Foot_L" else p) for n, p in bones]
    ad = bpy.data.armatures.new("driver_armature")
    ob = bpy.data.objects.new("DRIVER:DRIVER", ad)
    col.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    heads = {n: head_pos(n) for n, _ in bones}
    kids = {}
    for n, p in bones:
        kids.setdefault(p, []).append(n)
    for n, p in bones:
        eb = ad.edit_bones.new(n)
        eb.head = heads[n]
        if kids.get(n):
            tail = sum((heads[k] for k in kids[n]), Vector()) / len(kids[n])
        else:
            tail = heads[n] + (heads[n] - heads[p]) * 0.5 if p else heads[n] + Vector((0, 0, 0.1))
        if (tail - eb.head).length < 0.02:
            tail = eb.head + Vector((0, 0, -0.03 if n.startswith("DRIVER:HAND_") else 0.05))
        eb.tail = tail
        if p:
            eb.parent = ad.edit_bones[p]
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def box(name, center, size, material, weights, arm, skinned=True):
    """weights(z) -> 骨名。箱を 1 つ作り、頂点ごとに 1 本の骨へ重み 1 を付ける。"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0, calc_uvs=True)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0] + center[0], v.co.y * size[1] + center[1], v.co.z * size[2] + center[2]))
    bm.to_mesh(me); bm.free()
    if brk == "no_uv" and name == "DRIVER:HAIR":
        while me.uv_layers:
            me.uv_layers.remove(me.uv_layers[0])
    elif not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    if not (brk == "no_material" and name == "DRIVER:CAP"):
        mname = "mystery" if (brk == "bad_material" and name == "DRIVER:CAP") else material
        m = bpy.data.materials.get(mname) or bpy.data.materials.new(mname)
        me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    col.objects.link(o)
    if skinned:
        for v in me.vertices:
            gname = weights(v.co.z)
            vg = o.vertex_groups.get(gname) or o.vertex_groups.new(name=gname)
            if brk == "unweighted" and name == "DRIVER:BODY" and v.index == 0:
                continue
            vg.add([v.index], 1.0, "REPLACE")
        if not (brk == "no_modifier" and name == "DRIVER:BODY"):
            mod = o.modifiers.new("Armature", "ARMATURE"); mod.object = arm
    return o


arm = build_armature()
bpy.context.view_layer.update()

if brk != "missing_mesh":
    box("DRIVER:BODY", (0, 0, 0.78), (0.34, 0.20, 1.35), "driver_suit",
        lambda z: "DRIVER:RIG_Cest" if z > 1.2 else "DRIVER:RIG_Hips", arm)
box("DRIVER:GLOVES", (0.42, 0, 0.84), (0.08, 0.08, 0.10), "driver_gloves", lambda z: "DRIVER:RIG_HAND_L", arm)
top = 1.62 if brk != "tall" else 1.90
for n, c in zip(HEAD_MESHES, ((0, 0.01, top - 0.09), (0, -0.02, top - 0.05), (0, 0, top - 0.02))):
    o = box(n, c, (0.20, 0.22, 0.16 if n == HEAD_MESHES[0] else 0.06), "driver_skin" if n == HEAD_MESHES[0] else "driver_hair",
            None, arm, skinned=False)
    if brk == "head_not_bone" and n == "DRIVER:HAIR":
        o.parent = arm
    else:
        o.parent = arm; o.parent_type = "BONE"; o.parent_bone = "DRIVER:RIG_Head"
        # ボーン親子は尾からの相対になるので、元の位置に戻す補正を逆行列で入れる
        o.matrix_parent_inverse = (arm.matrix_world @ arm.data.bones["DRIVER:RIG_Head"].matrix_local).inverted()

if brk == "unpacked_image":
    img = bpy.data.images.new("driver_tex", 4, 4)
    img.filepath_raw = os.path.join(os.path.dirname(out), "driver_tex_unpacked.png")
    img.file_format = "PNG"; img.save()
    img.source = "FILE"   # パックしない
else:
    img = bpy.data.images.new("driver_tex", 4, 4)
    img.filepath_raw = os.path.join(os.path.dirname(out), "driver_tex_packed.png")
    img.file_format = "PNG"; img.save()
    img.source = "FILE"
    img.pack()   # パック済み
img.use_fake_user = True   # 使われていない画像が保存で消えないように
bpy.ops.wm.save_as_mainfile(filepath=out)
