"""運転手 .blend の規約検査（Blender の中で実行）。

blender -b --python tools/check_driver.py -- --blend design/driver/kanachu_driver.blend --json out.json
check(blend_path=None) -> 問題のリスト（空なら合格）。blend_path が None なら今開いている .blend を検査する。
座標は Blender のまま（+Y が前、キャラの左が -X・右が +X、+Z が上、足が原点、m。kn5 では左が +x）。
骨名・メッシュ名の定義は tools/driver_skeleton.py（Blender の Python からは --python の場所が
sys.path に入らないので、このファイルの隣から読む）。
"""
import json
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from driver_skeleton import BONES, HEAD_MESHES, SKINNED_MESHES  # noqa: E402

ARMATURE_NAME = "DRIVER:DRIVER"
HEAD_BONE = "DRIVER:RIG_Head"
MAX_VERTS = 60000
HEIGHT_RANGE = (1.55, 1.70)   # 立ち姿の頭頂の z（m）
MATERIAL_PREFIX = "driver_"
IGNORED_IMAGES = ("Render Result", "Viewer Node")


def export_vertex_count(ob):
    """kn5 に書くときの頂点数（位置・法線・UV が同じ角を統合した数）。check_design.py と同じ丸め。"""
    me = ob.data
    nl = len(me.loops)
    if nl == 0 or not me.uv_layers:
        return len(me.vertices)
    LV = np.empty(nl, "i8"); me.loops.foreach_get("vertex_index", LV)
    N = np.empty(nl * 3, "f4"); me.corner_normals.foreach_get("vector", N); N = np.round(N.reshape(-1, 3), 3)
    UV = np.empty(nl * 2, "f4"); me.uv_layers[0].data.foreach_get("uv", UV)
    return len(np.unique(np.c_[LV, N, UV.reshape(-1, 2)], axis=0))


def world_points(ob):
    me = ob.data
    v = np.empty(len(me.vertices) * 3, "f4")
    me.vertices.foreach_get("co", v)
    M = np.array(ob.matrix_world, "f8")
    return v.reshape(-1, 3).astype("f8") @ M[:3, :3].T + M[:3, 3]


def skeleton_problems(arm):
    bad = []
    want = dict(BONES)
    have = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
    for n in want:
        if n not in have:
            bad.append("骨が無い: " + n)
    for n in have:
        if n not in want:
            bad.append("余計な骨: " + n)
    for n, p in have.items():
        if n in want and want[n] != p:
            bad.append("骨の親が違う: %s（親 %s、契約 %s）" % (n, p, want[n]))
    return bad


SIDE_BONES = ("Clave", "Shoulder", "Arm", "ForeArm", "HAND", "Leg", "Shin", "Foot")


def side_problems(arm):
    """左右と向きの検査（レスト位置のワールド座標）。キャラは +Y を向き、左手は -X・右手は +X。
    向き: 足の骨（Foot = 爪先側）が踵の骨（Hill）より +Y にあること（顔のメッシュは形が自由で頑健に判定できないので使わない）。"""
    bad = []
    M = np.array(arm.matrix_world, "f8")
    head = {b.name: M[:3, :3] @ np.array(b.head_local) + M[:3, 3] for b in arm.data.bones}
    for base in SIDE_BONES:
        for side, sign, word in (("L", -1, "左 -X"), ("R", 1, "右 +X")):
            n = "DRIVER:RIG_%s_%s" % (base, side)
            if n in head and head[n][0] * sign <= 0:
                bad.append("左右が逆: %s は %s 側（x=%.3f）のはず。キャラは +Y を向き、左は -X、右は +X" % (n, word, head[n][0]))
    for side in "LR":
        toe, heel = "DRIVER:RIG_Foot_" + side, "DRIVER:RIG_Hill_" + side
        if toe in head and heel in head and head[toe][1] <= head[heel][1]:
            bad.append("向きが逆: %s が %s より前（+Y）にない。キャラは +Y を向く" % (toe, heel))
    return bad


def skinned_problems(ob, arm):
    bad = []
    mods = [m for m in ob.modifiers if m.type == "ARMATURE"]
    if not mods:
        bad.append("Armature モディファイアが無い: " + ob.name)
    elif mods[0].object != arm:
        bad.append("Armature モディファイアが %s を指していない: %s" % (ARMATURE_NAME, ob.name))
    bone_names = {n for n, _ in BONES}
    for vg in ob.vertex_groups:
        if vg.name not in bone_names:
            bad.append("骨名ではない頂点グループ '%s' (%s)" % (vg.name, ob.name))
    unweighted = 0
    for v in ob.data.vertices:
        if not any(g.weight > 0 and ob.vertex_groups[g.group].name in bone_names for g in v.groups):
            unweighted += 1
    if unweighted:
        bad.append("重みの無い頂点が %d 個: %s" % (unweighted, ob.name))
    return bad


def check(blend_path=None):
    if blend_path:
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    bpy.context.view_layer.update()
    O = bpy.data.objects
    bad = []
    arm = O.get(ARMATURE_NAME)
    if arm is None or arm.type != "ARMATURE":
        bad.append("アーマチュアのオブジェクトが無い: " + ARMATURE_NAME)
        arm = None
    else:
        bad += skeleton_problems(arm)
        bad += side_problems(arm)

    for n in SKINNED_MESHES + HEAD_MESHES:
        if n not in O or O[n].type != "MESH":
            bad.append("メッシュが無い: " + n)
    if arm is not None:
        for n in SKINNED_MESHES:
            if n in O and O[n].type == "MESH":
                bad += skinned_problems(O[n], arm)
    for n in HEAD_MESHES:
        o = O.get(n)
        if o is None or o.type != "MESH":
            continue
        if not (arm is not None and o.parent == arm and o.parent_type == "BONE" and o.parent_bone == HEAD_BONE):
            bad.append("%s が %s に骨で親子付けされていない" % (n, HEAD_BONE))

    meshes = [o for o in O if o.type == "MESH"]
    for o in meshes:
        if not o.data.uv_layers:
            bad.append("UV が無い: " + o.name)
        if len(o.data.vertices) > MAX_VERTS or export_vertex_count(o) > MAX_VERTS:
            bad.append("頂点が %d を超える: %s" % (MAX_VERTS, o.name))
        names = [s.material.name for s in o.material_slots if s.material]
        if not names:
            bad.append("マテリアルが無い: " + o.name)
        for m in names:
            if not m.startswith(MATERIAL_PREFIX):
                bad.append("%s で始まらないマテリアル '%s' (%s)" % (MATERIAL_PREFIX, m, o.name))
    for img in bpy.data.images:
        if img.name in IGNORED_IMAGES or img.source != "FILE":
            continue
        if img.packed_file is None:
            bad.append("テクスチャがパックされていない: " + img.name)

    pts = [world_points(o) for o in meshes if len(o.data.vertices)]
    if pts:
        top = float(np.vstack(pts)[:, 2].max())
        if not HEIGHT_RANGE[0] <= top <= HEIGHT_RANGE[1]:
            bad.append("立ち姿の頭頂の高さ %.3f m が %s の外" % (top, HEIGHT_RANGE))
    return bad


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = lambda f, d=None: argv[argv.index(f) + 1] if f in argv else d
    problems = check(opt("--blend"))
    js = opt("--json")
    if js:
        with open(js, "w", encoding="utf8") as fh:
            json.dump(problems, fh, ensure_ascii=False, indent=1)
    print("CHECK", "OK" if not problems else "%d problems" % len(problems))
    for p in problems:
        print("NG", p)
    sys.exit(1 if problems else 0)
