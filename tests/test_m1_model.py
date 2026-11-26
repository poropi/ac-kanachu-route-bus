import subprocess
from pathlib import Path

import numpy as np
import pytest

import kn5io
import paths
import textures

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (paths.BLENDER and Path(paths.BLENDER).exists()),
                                reason="Blender not found")

def blender(*args):
    return subprocess.run([paths.BLENDER, "-b", *args], capture_output=True, text=True)

def build(script, name, tmp):
    out = tmp / (name + ".blend")
    r = blender("--python", str(ROOT / "blender" / script), "--", "--out", str(out))
    assert out.exists(), r.stdout + r.stderr
    return out

def export(blend, tex, out):
    r = blender(str(blend), "--python", str(ROOT / "tools/blend_to_kn5.py"), "--",
                "--materials", str(ROOT / "tools/materials.json"),
                "--tex-dir", str(tex), "--out", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    return kn5io.read(out)

@pytest.fixture(scope="module")
def kn5s(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("m1")
    tex = tmp / "tex"; textures.make_default_textures(tex)
    bus = export(build("m1_box_bus.py", "bus", tmp), tex, tmp / "bus.kn5")
    col = export(build("m1_collider.py", "col", tmp), tex, tmp / "col.kn5")
    return bus, col

def verts(node):
    return np.frombuffer(node.vertices, "<f4").reshape(-1, 11)[:, :3]

def world_verts(node, parent=np.eye(4)):
    """(名前, ワールド座標の頂点) を列挙。dummy の matrix は転置（行ベクトル規約）で保存されている。"""
    M = parent
    if node.cls == 1 and node.matrix is not None:
        M = parent @ np.array(node.matrix).reshape(4, 4).T
    if node.cls == 2 and len(node.vertices):
        v = verts(node)
        yield node.name, v @ M[:3, :3].T + M[:3, 3]
    for c in node.children:
        yield from world_verts(c, M)

def test_box_bus_kn5(kn5s):
    bus, _ = kn5s
    nodes = list(kn5io.walk(bus.root))
    wv = list(world_verts(bus.root))
    allv = np.vstack([v for _, v in wv])
    lo, hi = allv.min(0), allv.max(0)
    assert hi[0] - lo[0] == pytest.approx(2.485, abs=0.02)
    assert hi[1] - lo[1] == pytest.approx(3.105, abs=0.02)
    assert hi[2] - lo[2] == pytest.approx(10.430, abs=0.02)
    body = np.vstack([v for n, v in wv if not n.startswith(("TYRE", "RIM"))])
    assert body[:, 1].min() >= 0.130 - 0.002
    by = {n.name: n for n in nodes}
    for n in ("SUSP_LF", "SUSP_RF", "SUSP_LR", "SUSP_RR", "STEER_HR", "COCKPIT_HR",
              "WHEEL_LF", "WHEEL_RF", "WHEEL_LR", "WHEEL_RR"):
        assert n in by, n
    def t(n):  # 行列は行優先 4x4 の転置で保存されている（x,y,z は m[12:15]）
        return np.array(by[n].matrix)[12:15]
    assert t("WHEEL_LF") == pytest.approx([1.0325, 0.478, 2.65], abs=0.005)
    assert t("WHEEL_RR") == pytest.approx([-0.91, 0.478, -2.65], abs=0.005)

def test_collider_12_tris(kn5s):
    _, col = kn5s
    meshes = [n for n in kn5io.walk(col.root) if n.cls == 2]
    assert [m.name for m in meshes] == ["COLLIDER_BODY"]
    assert len(meshes[0].indices) == 12 * 3

def world_tris(node, parent=np.eye(4), want=("BODY", "SKIRT")):
    M = parent
    if node.cls == 1 and node.matrix is not None:
        M = parent @ np.array(node.matrix).reshape(4, 4).T
    if node.cls == 2 and node.name in want:
        v = verts(node); v = v @ M[:3, :3].T + M[:3, 3]
        yield v[np.array(node.indices).reshape(-1, 3)]
    for c in node.children:
        yield from world_tris(c, M, want)

def ray_hits(tris, o, d):
    """Moller-Trumbore。tris: (N,3,3)。正方向の交点までの距離の配列。"""
    e1 = tris[:, 1] - tris[:, 0]; e2 = tris[:, 2] - tris[:, 0]
    p = np.cross(d, e2); det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
    tv = o - tris[:, 0]; u = (tv * p).sum(1) * inv
    q = np.cross(tv, e1); w = (q * d).sum(1) * inv
    t = (e2 * q).sum(1) * inv
    return t[ok & (u >= 0) & (w >= 0) & (u + w <= 1) & (t > 1e-6)]

def test_wheel_arches_clear_and_tyres_visible(kn5s):
    bus, _ = kn5s
    tris = np.vstack(list(world_tris(bus.root)))
    cen = tris.mean(1)
    by = {n.name: n for n in kn5io.walk(bus.root)}
    R, TW, DUAL = 0.478, 0.275, 0.16
    for name in ("LF", "RF", "LR", "RR"):
        c = np.array(by["WHEEL_" + name].matrix)[12:15]
        half = TW / 2 + (DUAL if name[1] == "R" else 0)
        r2 = (cen[:, 1] - c[1]) ** 2 + (cen[:, 2] - c[2]) ** 2
        inside = (np.abs(cen[:, 0] - c[0]) < half) & (r2 < (R + 0.08) ** 2)
        assert not inside.any(), name
        allp = tris.reshape(-1, 3)
        r2v = (allp[:, 1] - c[1]) ** 2 + (allp[:, 2] - c[2]) ** 2
        assert not ((np.abs(allp[:, 0] - c[0]) < half) & (r2v < (R + 0.08) ** 2 - 1e-6)).any(), name
        # 側面から、タイヤ外径の高さで輪の中心へ向けた光線が、タイヤに届くまでに車体に当たらない
        side = np.sign(c[0])
        tyre_outer_x = c[0] + side * half
        for dz in (0.0, 0.3):  # 中心高さと、さらに上の高さ
            o = np.array([side * 2.0, c[1], c[2] + dz]); d = np.array([-side, 0.0, 0.0])
            hits = ray_hits(tris, o, d)
            assert not (hits < abs(2.0 - abs(tyre_outer_x)) + 1e-3).any(), (name, dz)


def test_collider_mesh_under_intermediate_dummy(kn5s):
    """AC は root -> mesh の 2 階層 collider で CarAvatar::initPhysics が落ちる。動く車は root -> dummy -> mesh。"""
    _, col = kn5s
    def walk(n, parent, depth):
        yield n, parent, depth
        for c in n.children:
            yield from walk(c, n, depth + 1)
    meshes = [(n, p, d) for n, p, d in walk(col.root, None, 0) if n.cls == 2]
    assert meshes
    for n, p, d in meshes:
        assert p.cls == 1 and p is not col.root, n.name
        assert d == 2, n.name
    assert [m.name for m, _, _ in meshes] == ["COLLIDER_BODY"]
    assert meshes[0][1].name == "COLLIDER_BODY"
