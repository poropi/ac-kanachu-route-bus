# blender -b IN.blend --python weight_variant.py -- OUT.blend five_influence
# 試験用: 最小の運転手 .blend の DRIVER:BODY の頂点 0 の重みを書き換えて保存する。
#   five_influence: 5 本の骨に重み 0.4, 0.3, 0.15, 0.1, 0.05 を付ける（合計は 1 に足りない並び）
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
else:
    raise SystemExit("unknown mode " + mode)
bpy.ops.wm.save_as_mainfile(filepath=out)
