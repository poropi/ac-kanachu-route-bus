# blender -b IN.blend --python weight_variant.py -- OUT.blend MODE
# 試験用: 最小の運転手 .blend を 1 か所変えて保存する。
#   five_influence: DRIVER:BODY の頂点 0 の 5 本の骨に重み 0.4, 0.3, 0.15, 0.1, 0.05 を付ける（合計は 1 に足りない並び）
#   pose / mirror / multi_material / neck_material / single_slot_extra: 下の各分岐を参照
import sys

import bpy

out, mode = sys.argv[sys.argv.index("--") + 1:][:2]
ob = bpy.data.objects["DRIVER:BODY"]
if mode == "five_influence":
    names = ["DRIVER:RIG_Cest", "DRIVER:RIG_Hips", "DRIVER:RIG_Nek", "DRIVER:RIG_Head", "DRIVER:RIG_Center"]
    for vg in ob.vertex_groups:
        vg.remove([0])
    for n, w in zip(names, (0.4, 0.3, 0.15, 0.1, 0.05)):
        vg = ob.vertex_groups.get(n) or ob.vertex_groups.new(name=n)
        vg.add([0], w, "REPLACE")
elif mode == "pose":   # 頭と左腕にポーズを付ける（レスト位置の書き出しと同じになるはず）
    arm = bpy.data.objects["DRIVER:DRIVER"]
    for n, q in (("DRIVER:RIG_Head", (0.8, 0.5, 0.2, 0.1)), ("DRIVER:RIG_Arm_L", (0.7, 0.0, 0.5, 0.5))):
        pb = arm.pose.bones[n]; pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = q
    bpy.context.view_layer.update()
elif mode == "mirror":   # 骨で動くメッシュ DRIVER:GLOVES に X の Mirror を付ける（頂点が倍になる）
    mod = bpy.data.objects["DRIVER:GLOVES"].modifiers.new("Mirror", "MIRROR")
    mod.use_axis[0] = True
elif mode == "multi_material":
    # 1 つのメッシュに複数のマテリアル。各メッシュの上面（法線が +Z の面）だけを最後の枠にする。
    #   DRIVER:BODY: [driver_suit, driver_unused（どの面も使わない）, driver_shoes]。上面の頂点は全部 RIG_Cest なので、
    #     上面だけの部分は骨が RIG_Cest 1 本になる（骨番号の振り直しを確かめる）
    #   DRIVER:HAIR: [driver_hair, driver_skin]。driver_skin は顔と共有（kn5 には 1 回だけ）
    for name, extra in (("DRIVER:BODY", ("driver_unused", "driver_shoes")), ("DRIVER:HAIR", ("driver_skin",))):
        me = bpy.data.objects[name].data
        for mn in extra:
            me.materials.append(bpy.data.materials.get(mn) or bpy.data.materials.new(mn))
        for p in me.polygons:
            if p.normal.z > 0.5:
                p.material_index = len(me.materials) - 1
    # driver_suit と driver_shoes に同じパック画像（driver_tex）を付ける（kn5 のテクスチャは driver_suit.dds の 1 枚だけになるはず）
    for mn in ("driver_suit", "driver_shoes"):
        m = bpy.data.materials[mn]; m.use_nodes = True
        nd = m.node_tree.nodes.new("ShaderNodeTexImage"); nd.image = bpy.data.images["driver_tex"]
elif mode == "neck_material":   # DRIVER:BODY の上面（法線が +Z、頂点は RIG_Cest）を首の肌のマテリアル driver_neck にする
    me = ob.data
    me.materials.append(bpy.data.materials.new("driver_neck"))
    for p in me.polygons:
        if p.normal.z > 0.5:
            p.material_index = len(me.materials) - 1
elif mode == "single_slot_extra":   # 枠が 2 つあっても面が 1 つの枠しか使わなければ、分けずに今までどおり
    me = bpy.data.objects["DRIVER:HAIR"].data
    me.materials.append(bpy.data.materials.new("driver_unused"))
else:
    raise SystemExit("unknown mode " + mode)
bpy.ops.wm.save_as_mainfile(filepath=out)
