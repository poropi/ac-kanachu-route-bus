import re
import struct
from pathlib import Path

import numpy as np
import pytest

import assemble
import kn5io
import paths

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    not (paths.BLENDER and Path(paths.BLENDER).exists() and (ROOT / "design/exterior/kanachu_exterior.blend").exists()),
    reason="Blender or exterior missing")
INTERIOR_BLEND = ROOT / "design/interior/kanachu_interior.blend"
ALLOWED = {"paint", "trim_black", "chrome", "glass", "glass_tint", "glass_light", "light_emit", "dest_led", "tyre", "rim", "rubber", "mirror"}   # mirror は kn5_mirrors が書き出し後に鏡面へ付ける
OUTSIDE = re.compile(r"^(Mirror|Wiper|FrontPlate|RearPlate)", re.I)


@pytest.fixture(scope="module")
def kn5(tmp_path_factory):
    t = tmp_path_factory.mktemp("ext")
    import textures
    tex = t / "tex"
    textures.make_default_textures(tex)
    out = t / "main.kn5"
    assemble.export_exterior(out, tex, t)
    return kn5io.read(out)


def world(node, parent=np.eye(4)):
    M = parent
    if node.cls == 1 and node.matrix is not None:
        M = parent @ np.array(node.matrix).reshape(4, 4).T
    if node.cls == 2 and len(node.vertices):
        v = np.frombuffer(node.vertices, "<f4").reshape(-1, 11)[:, :3]
        yield node, v @ M[:3, :3].T + M[:3, 3]
    for c in node.children:
        yield from world(c, M)


def test_node_names(kn5):
    nodes = list(kn5io.walk(kn5.root))
    names = [n.name for n in nodes]
    assert kn5.root.name == "kanachu_route_bus"
    need = (["WHEEL_" + k for k in ("LF", "RF", "LR", "RR")] + ["SUSP_" + k for k in ("LF", "RF", "LR", "RR")]
            + ["DEST_FRONT", "DEST_SIDE", "DEST_REAR", "DOOR_FRONT", "DOOR_MID", "STEER_HR", "COCKPIT_HR", "ARROW_SPEED", "ARROW_RPM", "DRIVER_EYE"]
            + ["LIGHT_" + k for k in "BRAKE_L BRAKE_R HEAD_L HEAD_R IND_FL IND_FR IND_RL IND_RR REVERSE_L REVERSE_R TAIL_L TAIL_R".split()])
    for n in need:
        assert n in names, n
    assert not any(n.startswith("PHOTO_") for n in names)
    assert names.count("ROOT") == 0
    assert "INTERIOR_PLACEHOLDER" not in names
    assert len(nodes) > 450
    assert len(names) == len(set(names)), "ノード名が重複している"


def test_cockpit_hierarchy_and_pivots(kn5):
    by = {n.name: n for n in kn5io.walk(kn5.root)}
    cockpit = by["COCKPIT_HR"]
    below = {n.name for n in kn5io.walk(cockpit)}
    for n in ("STEER_HR", "ARROW_SPEED", "ARROW_RPM", "DRIVER_EYE"):
        assert n in below, n
    # COCKPIT_HR は原点・回転なし
    M = np.array(cockpit.matrix).reshape(4, 4)
    assert M == pytest.approx(np.eye(4), abs=1e-6)
    # 回転の中心（Blender (0.642, 4.098, 1.392) -> kn5 (-bx, bz, by)）
    t = lambda n: np.array(by[n].matrix)[12:15]
    assert t("STEER_HR") == pytest.approx([-0.642, 1.392, 4.098], abs=1e-4)
    assert t("ARROW_SPEED") == pytest.approx([-0.772, 1.52262, 4.41279], abs=1e-4)
    assert t("ARROW_RPM") == pytest.approx([-0.512, 1.52262, 4.41279], abs=1e-4)
    assert t("DRIVER_EYE") == pytest.approx([-0.642, 1.985, 3.407], abs=1e-4)
    # 針・ハンドルのメッシュはそれぞれの下にある
    assert any(n.cls == 2 for n in kn5io.walk(by["STEER_HR"]))
    assert any(n.cls == 2 for n in kn5io.walk(by["ARROW_SPEED"]))
    assert any(n.cls == 2 for n in kn5io.walk(by["ARROW_RPM"]))


def world_matrix(root, name):
    def find(n, M):
        if n.cls == 1 and n.matrix is not None:
            M = M @ np.array(n.matrix).reshape(4, 4).T
        if n.name == name:
            return M
        for c in n.children:
            r = find(c, M)
            if r is not None:
                return r
    return find(root, np.eye(4))


def world_pos(root, name):
    return world_matrix(root, name)[:3, 3]


def test_rotation_axes_point_away_from_driver(kn5):
    import validate
    assert validate.axis_problems(kn5.root) == []
    by = {n.name: n for n in kn5io.walk(kn5.root)}
    eye = world_pos(kn5.root, "DRIVER_EYE")
    for n in ("ARROW_SPEED", "ARROW_RPM", "STEER_HR"):
        M = world_matrix(kn5.root, n)
        z = M[:3, 2]
        assert np.linalg.norm(z) == pytest.approx(1.0, abs=1e-5)
        assert z @ (M[:3, 3] - eye) > 0.3, (n, z)           # 運転手から遠ざかる
        pts = np.vstack([np.frombuffer(m.vertices, "<f4").reshape(-1, 11)[:, :3] for m in kn5io.walk(by[n]) if m.cls == 2])
        ext = pts.max(0) - pts.min(0)
        assert ext[2] < ext[0] and ext[2] < ext[1], (n, ext)   # 文字盤・リム面の法線がローカル Z
    # ハンドルの回転軸はほぼコラム方向（下向き・前向き）。世界 Y 成分は負、Z 成分は正
    z = world_matrix(kn5.root, "STEER_HR")[:3, 2]
    assert z == pytest.approx([0, -0.914, 0.407], abs=0.01)
    # 子の世界位置は保たれている: 子メッシュの重心が回転中心の近く
    for n in ("ARROW_SPEED", "ARROW_RPM", "STEER_HR"):
        M = world_matrix(kn5.root, n)
        pts = np.vstack([np.frombuffer(m.vertices, "<f4").reshape(-1, 11)[:, :3] for m in kn5io.walk(by[n]) if m.cls == 2])
        w = pts @ M[:3, :3].T + M[:3, 3]
        assert np.linalg.norm(w.mean(0) - M[:3, 3]) < 0.3, n


def test_car_ini_eyes_match_kn5_driver_eye(kn5, tmp_path):
    import physics
    by = {n.name: n for n in kn5io.walk(kn5.root)}
    eye = np.array(by["DRIVER_EYE"].matrix)[12:15]
    physics.build(tmp_path)
    got = [float(x) for x in physics.read_ini(tmp_path / "car.ini")["GRAPHICS"]["DRIVEREYES"].split(",")]
    assert got == pytest.approx(list(eye), abs=1e-4)


def test_analog_matches_interior_report(tmp_path):
    """spec の針の角度が、内装 .blend のカスタムプロパティ（盤面の時計回り角 0 と最大）と一致する。"""
    import json, subprocess, physics
    js = tmp_path / "arrows.json"
    code = ("import bpy, json; O = bpy.data.objects; "
            "json.dump({n: {k: O[n][k] for k in ('face_angle_zero_clockwise_from_12', 'face_angle_max_clockwise_from_12', 'maximum')} "
            "for n in ('ARROW_SPEED', 'ARROW_RPM')}, open(%r, 'w'))" % str(js))
    subprocess.run([paths.BLENDER, "-b", str(INTERIOR_BLEND), "--python-expr", code], capture_output=True, check=True)
    arr = json.loads(js.read_text())
    physics.build(tmp_path / "d")
    a = physics.read_ini(tmp_path / "d" / "analog_instruments.ini")
    for node, sec in (("ARROW_SPEED", "SPEED_INDICATOR"), ("ARROW_RPM", "RPM_INDICATOR")):
        p = arr[node]
        sweep = p["face_angle_max_clockwise_from_12"] - p["face_angle_zero_clockwise_from_12"]   # 時計回りが正
        assert float(a[sec]["STEP"]) * p["maximum"] == pytest.approx(sweep, abs=1e-3), node


def test_materials_and_textures(kn5):
    mats = {m.name for m in kn5.materials}
    assert ALLOWED <= mats
    inter = mats - ALLOWED
    assert len(inter) >= 40 and all(m.startswith("interior_") for m in inter), inter
    tex = {t.name: t.data for t in kn5.textures}
    for n, d in tex.items():
        assert d[:4] == b"DDS ", n
    h, w, mips = struct.unpack_from("<I", tex["paint.dds"], 12)[0], struct.unpack_from("<I", tex["paint.dds"], 16)[0], struct.unpack_from("<I", tex["paint.dds"], 28)[0]
    assert (w, h, mips) == (4096, 2048, 13)
    assert "Kanachu_dot_matrix.dds" in tex
    assert struct.unpack_from("<I", tex["Kanachu_dot_matrix.dds"], 28)[0] > 1


def test_every_dds_has_full_mip_chain(kn5):
    import math
    for t in kn5.textures:
        h, w, mips = (struct.unpack_from("<I", t.data, o)[0] for o in (12, 16, 28))
        assert mips == int(math.log2(max(w, h))) + 1 or max(w, h) == 1, (t.name, w, h, mips)


def dds_alpha(data):
    """無圧縮 A8R8G8B8 DDS の最上位ミップの A（最小・最大, 0〜255）。"""
    h, w = struct.unpack_from("<I", data, 12)[0], struct.unpack_from("<I", data, 16)[0]
    a = np.frombuffer(data, np.uint8, count=h * w * 4, offset=128).reshape(-1, 4)[:, 3]
    return int(a.min()), int(a.max())


def test_blended_materials_are_translucent(kn5):
    tex = {t.name: t.data for t in kn5.textures}
    blended = [m for m in kn5.materials if m.blend == 1]
    assert {"glass", "glass_tint", "glass_light", "interior_guardglass"} <= {m.name for m in blended}
    for m in blended:
        for _slot, _i, tname in m.tex:
            assert dds_alpha(tex[tname])[1] < 255, (m.name, tname)
    mat = {m.name: m for m in kn5.materials}
    g = dds_alpha(tex[mat["glass"].tex[0][2]])
    assert 0.1 * 255 <= g[0] == g[1] <= 0.25 * 255, g          # 風防・運転席窓: 薄い
    tint = dds_alpha(tex[mat["glass_tint"].tex[0][2]])
    assert 0.55 * 255 <= tint[0] == tint[1] <= 0.75 * 255, tint  # 客室窓など: 濃い
    assert mat["glass"].tex[0][2] != mat["glass_tint"].tex[0][2]
    lens = dds_alpha(tex["glass_light.dds"])
    assert 0.45 * 255 <= lens[0] <= 0.65 * 255
    guard = dds_alpha(tex["interior_guardglass.dds"])
    assert 0.2 * 255 <= guard[0] <= 0.3 * 255
    assert mat["glass"].tex[0][2] == "glass.dds" and mat["glass_tint"].tex[0][2] == "glass_tint.dds"


def test_glass_groups(kn5):
    mats = [m.name for m in kn5.materials]
    by_mat = {}
    for n in kn5io.walk(kn5.root):
        if n.cls == 2 and mats[n.matid] in ("glass", "glass_tint"):
            by_mat.setdefault(n.name, []).append(mats[n.matid])
    assert len(by_mat) == 18 and all(len(v) == 1 for v in by_mat.values())   # 各ガラスはちょうど 1 グループ
    light = {n for n, v in by_mat.items() if v[0] == "glass"}
    assert light == {"Windshield", "Right_Window_01_Glass", "Entrance_Leaf_1_Glass", "Entrance_Leaf_2_Glass"}   # 薄い 4 / 濃い 14
    assert sum(v == ["glass_tint"] for v in by_mat.values()) == 14
    for n in ("RearWindow", "Sliding_Pane_Glass", "Left_Window_01_Glass", "Left_Window_03_Glass", "Right_Window_05_Glass"):
        assert by_mat[n] == ["glass_tint"], n


def test_no_mesh_has_children(kn5):
    meshes = [n for n in kn5io.walk(kn5.root) if n.cls == 2]
    assert not [n.name for n in meshes if n.children]
    by = {n.name: n for n in kn5io.walk(kn5.root)}
    for d in ("DOOR_FRONT", "DOOR_MID"):
        assert by[d].cls == 1 and by[d + "_GEO"].cls == 2


def test_triangles_and_vertex_limit(kn5):
    meshes = [n for n in kn5io.walk(kn5.root) if n.cls == 2]
    tris = sum(len(m.indices) // 3 for m in meshes)
    assert 200_000 <= tris <= 300_000, tris
    assert all(len(m.vertices) // 44 <= 65535 for m in meshes)


def test_bounding_box_and_wheels(kn5):
    wv = list(world(kn5.root))
    body = np.vstack([v for n, v in wv if not OUTSIDE.search(n.name)])
    d = body.max(0) - body.min(0)
    # kn5 座標: x=幅, y=高さ, z=長さ（前が +z）
    assert d[0] == pytest.approx(2.485, abs=0.02)
    assert d[1] == pytest.approx(3.105, abs=0.02)
    assert d[2] == pytest.approx(10.430, abs=0.02)
    assert body[:, 1].min() >= -0.002
    by = {n.name: n for n in kn5io.walk(kn5.root)}
    t = lambda n: np.array(by[n].matrix)[12:15]
    assert t("WHEEL_LF") == pytest.approx([1.0325, 0.478, 2.65], abs=0.005)
    assert t("WHEEL_RF") == pytest.approx([-1.0325, 0.478, 2.65], abs=0.005)
    assert t("WHEEL_LR") == pytest.approx([0.91, 0.478, -2.65], abs=0.005)
    assert t("WHEEL_RR") == pytest.approx([-0.91, 0.478, -2.65], abs=0.005)
    for n in ("WHEEL_LF", "SUSP_RR"):
        M = np.array(by[n].matrix).reshape(4, 4)
        assert M[:3, :3] == pytest.approx(np.eye(3), abs=1e-5)
