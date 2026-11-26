"""外装 .blend の規約検査（Blender の中で実行）。

blender -b X.blend --python tools/check_design.py -- --json out.json
blender -b --python tools/check_design.py -- --blend X.blend --json out.json   （.blend を自分で開く）
blender -b --python tools/check_design.py -- --blend design/interior/kanachu_interior.blend --interior --json out.json   （内装）
check(blend_path=None) -> 問題のリスト（空なら合格）。blend_path が None なら今開いている .blend を検査する。
check_interior(blend_path=None) -> 内装の問題のリスト。
座標は Blender のまま（+Y が前、+X が右、+Z が上、m）。
"""
import json
import re
import sys

import bpy
import numpy as np

REQUIRED = (["ROOT"] + ["WHEEL_" + k for k in ("LF", "RF", "LR", "RR")] + ["SUSP_" + k for k in ("LF", "RF", "LR", "RR")]
            + ["LIGHT_" + k for k in "BRAKE_L BRAKE_R HEAD_L HEAD_R IND_FL IND_FR IND_RL IND_RR REVERSE_L REVERSE_R TAIL_L TAIL_R".split()]
            + ["DEST_FRONT", "DEST_SIDE", "DEST_REAR", "DOOR_FRONT", "DOOR_MID"])
MATERIALS = {"paint", "trim_black", "chrome", "glass", "glass_light", "light_emit", "dest_led", "tyre", "rim", "rubber"}
MATERIAL_PREFIXES = ("interior_",)   # 内装用
INTERIOR_REQUIRED = ["COCKPIT_HR", "STEER_HR", "ARROW_SPEED", "ARROW_RPM", "DRIVER_EYE"]
INTERIOR_MAX_TRIS = 150000   # 内装単体（外装と合わせて主 kn5 は 30 万以下）
MAX_KN5_TRIS = 300000
# M1 の Task 3 と同じ値（Blender 座標 X, Y, Z）
WHEEL_POS = {"LF": (-1.0325, 2.65, 0.478), "RF": (1.0325, 2.65, 0.478),
             "LR": (-0.91, -2.65, 0.478), "RR": (0.91, -2.65, 0.478)}
POS_TOL = 0.005
BODY_DIMS = (2.485, 10.430, 3.105)   # X, Y, Z
DIM_TOL = 0.02
OUTSIDE_BODY = re.compile(r"^(Mirror|Wiper|FrontPlate|RearPlate)", re.I)   # 外接箱から除く物
MAX_VERTS = 65535
UV_GRID = (2048, 1024)
UV_OVERLAP_TOL = 0.0005   # 塗装 UV が占める面積に対する、重なった面積の割合


def mesh_arrays(ob):
    me = ob.data
    v = np.empty(len(me.vertices) * 3, "f4")
    me.vertices.foreach_get("co", v)
    return v.reshape(-1, 3)


def world_points(ob):
    M = np.array(ob.matrix_world, "f8")
    return mesh_arrays(ob).astype("f8") @ M[:3, :3].T + M[:3, 3]


def export_vertex_count(ob):
    """kn5 に書くときの頂点数（位置・法線・UV が同じ角を統合した数）。blend_to_kn5.py と同じ丸め。"""
    me = ob.data
    nl = len(me.loops)
    if nl == 0 or not me.uv_layers:
        return len(me.vertices)
    LV = np.empty(nl, "i8"); me.loops.foreach_get("vertex_index", LV)
    N = np.empty(nl * 3, "f4"); me.corner_normals.foreach_get("vector", N); N = np.round(N.reshape(-1, 3), 3)
    UV = np.empty(nl * 2, "f4"); me.uv_layers[0].data.foreach_get("uv", UV)
    key = np.c_[LV, N, UV.reshape(-1, 2)]
    return len(np.unique(key, axis=0))


def paint_uv_problems(objs):
    """paint の UV が 0〜1 に収まり、別の三角形と重ならないか。"""
    bad = []
    W, H = UV_GRID
    count = np.zeros((H, W), np.int16)
    covered_total = 0
    for ob in objs:
        me = ob.data
        if not me.uv_layers:
            continue
        me.calc_loop_triangles()
        nl = len(me.loops)
        UV = np.empty(nl * 2, "f4"); me.uv_layers[0].data.foreach_get("uv", UV); UV = UV.reshape(-1, 2).astype("f8")
        slots = [s.material.name if s.material else None for s in ob.material_slots]
        tri = np.empty(len(me.loop_triangles) * 3, "i8"); me.loop_triangles.foreach_get("loops", tri)
        tri = tri.reshape(-1, 3)
        tm = np.empty(len(me.loop_triangles), "i8"); me.loop_triangles.foreach_get("material_index", tm)
        for t, mi in zip(tri, tm):
            if mi >= len(slots) or slots[mi] != "paint":
                continue
            p = UV[t]
            if p.min() < -1e-6 or p.max() > 1 + 1e-6:
                bad.append("paint の UV が 0〜1 の外: %s" % ob.name)
                break
            x = p[:, 0] * W; y = p[:, 1] * H
            xs = np.arange(max(0, int(np.floor(x.min()))), min(W, int(np.ceil(x.max()))) + 0)
            ys = np.arange(max(0, int(np.floor(y.min()))), min(H, int(np.ceil(y.max()))) + 0)
            if len(xs) == 0 or len(ys) == 0:
                continue
            gx, gy = np.meshgrid(xs + 0.5, ys + 0.5)
            d = (x[1] - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (y[1] - y[0])
            if abs(d) < 1e-12:
                continue
            w1 = ((gx - x[0]) * (y[2] - y[0]) - (x[2] - x[0]) * (gy - y[0])) / d
            w2 = ((x[1] - x[0]) * (gy - y[0]) - (gx - x[0]) * (y[1] - y[0])) / d
            m = (w1 > 0) & (w2 > 0) & (w1 + w2 < 1)
            count[ys[0]:ys[0] + len(ys), xs[0]:xs[0] + len(xs)] += m
    covered = int((count > 0).sum()); over = int((count > 1).sum())
    if bad:
        return bad
    if covered and over / covered > UV_OVERLAP_TOL:
        bad.append("paint の UV が重なっている: 重なり %d / 使用 %d px (%.3f%%)" % (over, covered, 100.0 * over / covered))
    return bad


def check(blend_path=None):
    if blend_path:
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    O = bpy.data.objects
    bad = []
    for n in REQUIRED:
        if n not in O:
            bad.append("オブジェクトが無い: " + n)
    meshes = [o for o in O if o.type == "MESH"]
    for k, p in WHEEL_POS.items():
        for pre in ("WHEEL_", "SUSP_"):
            o = O.get(pre + k)
            if o is None:
                continue
            t = np.array(o.matrix_world.translation)
            if np.abs(t - np.array(p)).max() > POS_TOL:
                bad.append("%s の位置が契約値と違う: %s（契約 %s）" % (o.name, tuple(round(float(x), 4) for x in t), p))
    for o in meshes:
        names = [s.material.name for s in o.material_slots if s.material]
        if not names:
            bad.append("マテリアルが無い: " + o.name)
        for m in names:
            if m not in MATERIALS and not m.startswith(MATERIAL_PREFIXES):
                bad.append("許可リストに無いマテリアル '%s' (%s)" % (m, o.name))
        if not o.data.uv_layers:
            bad.append("UV が無い: " + o.name)
    body = [o for o in meshes if not OUTSIDE_BODY.search(o.name) and len(o.data.vertices)]
    if body:
        pts = np.vstack([world_points(o) for o in body])
        dims = pts.max(0) - pts.min(0)
        if np.abs(dims - np.array(BODY_DIMS)).max() > DIM_TOL:
            bad.append("車体の外接箱 %s が %s ±%s と違う（ミラー・ワイパー・ナンバーを除く）"
                       % (tuple(round(float(x), 4) for x in dims), BODY_DIMS, DIM_TOL))
    else:
        bad.append("車体のメッシュが無い")
    for o in meshes:
        if len(o.data.vertices) > MAX_VERTS or export_vertex_count(o) > MAX_VERTS:
            bad.append("頂点が %d を超える: %s" % (MAX_VERTS, o.name))
    bad += paint_uv_problems(meshes)
    return bad


def ancestors(o):
    while o.parent is not None:
        o = o.parent
        yield o


def check_interior(blend_path=None):
    """内装 .blend の規約検査。必須の空（COCKPIT_HR の子孫であること）、interior_ のマテリアルだけ、UV、頂点数、三角形数。"""
    if blend_path:
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    bpy.context.view_layer.update()
    O = bpy.data.objects
    bad = []
    for n in INTERIOR_REQUIRED:
        if n not in O:
            bad.append("オブジェクトが無い: " + n)
    top = O.get("COCKPIT_HR")
    if top is not None:
        if top.parent is not None:
            bad.append("COCKPIT_HR に親がある（内装の根でなければならない）")
        if np.abs(np.array(top.matrix_world) - np.eye(4)).max() > 1e-6:
            bad.append("COCKPIT_HR が原点・回転なし・スケール 1 ではない")
        for o in O:
            if o is not top and top not in ancestors(o):
                bad.append("COCKPIT_HR の子孫ではない: " + o.name)
    for n in ("STEER_HR", "ARROW_SPEED", "ARROW_RPM", "DRIVER_EYE"):
        if n in O and O[n].type != "EMPTY":
            bad.append("%s は空（Empty）でなければならない" % n)
    tris = 0
    for o in O:
        if o.type != "MESH":
            continue
        names = [s.material.name for s in o.material_slots if s.material]
        if not names:
            bad.append("マテリアルが無い: " + o.name)
        for m in names:
            if not m.startswith(MATERIAL_PREFIXES):
                bad.append("interior_ で始まらないマテリアル '%s' (%s)" % (m, o.name))
        if not o.data.uv_layers:
            bad.append("UV が無い: " + o.name)
        if len(o.data.vertices) > MAX_VERTS or export_vertex_count(o) > MAX_VERTS:
            bad.append("頂点が %d を超える: %s" % (MAX_VERTS, o.name))
        o.data.calc_loop_triangles()
        tris += len(o.data.loop_triangles)
    if tris > INTERIOR_MAX_TRIS:
        bad.append("内装の三角形が %d を超える: %d" % (INTERIOR_MAX_TRIS, tris))
    return bad


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    opt = lambda f, d=None: argv[argv.index(f) + 1] if f in argv else d
    problems = (check_interior if "--interior" in argv else check)(opt("--blend"))
    js = opt("--json")
    if js:
        with open(js, "w", encoding="utf8") as fh:
            json.dump(problems, fh, ensure_ascii=False, indent=1)
    print("CHECK", "OK" if not problems else "%d problems" % len(problems))
    for p in problems:
        print("NG", p)
    sys.exit(1 if problems else 0)
