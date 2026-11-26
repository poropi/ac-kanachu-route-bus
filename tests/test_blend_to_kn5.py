import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import kn5io
import paths
import textures

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (paths.BLENDER and Path(paths.BLENDER).exists()),
                                reason="Blender not found")

def blender(*args):
    return subprocess.run([paths.BLENDER, "-b", *args], capture_output=True, text=True)

@pytest.fixture(scope="module")
def cube_blend(tmp_path_factory):
    out = tmp_path_factory.mktemp("blend") / "cube.blend"
    r = blender("--python", str(ROOT / "tests/fixtures/make_cube.py"), "--", str(out))
    assert out.exists(), r.stdout + r.stderr
    return out

def export(blend, tex_dir, out):
    return blender(str(blend), "--python", str(ROOT / "tools/blend_to_kn5.py"), "--",
                   "--materials", str(ROOT / "tools/materials.json"),
                   "--tex-dir", str(tex_dir), "--out", str(out))

def test_export_cube(cube_blend, tmp_path):
    tex = tmp_path / "tex"
    textures.make_default_textures(tex)
    out = tmp_path / "o.kn5"
    r = export(cube_blend, tex, out)
    assert r.returncode == 0, r.stdout + r.stderr
    k = kn5io.read(out)
    assert k.version == 5 and k.extra is None
    nodes = list(kn5io.walk(k.root))
    assert [n.name for n in nodes] == ["kanachu_route_bus", "BODY_TEST"]
    assert "paint" in [m.name for m in k.materials]
    mesh = nodes[1]
    assert len(mesh.indices) == 12 * 3
    import numpy as np
    v = np.frombuffer(mesh.vertices, "<f4").reshape(-1, 11)
    assert np.allclose(v[:, :3].mean(0), [-0.5, 1.0, 2.0], atol=1e-4)
    texs = [t.name for t in k.textures]
    assert "paint.dds" in texs
    assert all(t.active == 1 and t.data[:4] == b"DDS " for t in k.textures)

def test_missing_texture_fails(cube_blend, tmp_path):
    tex = tmp_path / "empty"; tex.mkdir()
    r = export(cube_blend, tex, tmp_path / "o.kn5")
    assert r.returncode != 0
    assert not (tmp_path / "o.kn5").exists()


def world_pts(node, M=None):
    import numpy as np
    M = np.eye(4) if M is None else M
    if node.cls == 1 and node.matrix is not None:
        M = M @ np.array(node.matrix).reshape(4, 4).T
    if node.cls == 2 and len(node.vertices):
        v = np.frombuffer(node.vertices, "<f4").reshape(-1, 11)[:, :3]
        yield node.name, v @ M[:3, :3].T + M[:3, 3]
    for c in node.children:
        yield from world_pts(c, M)


def test_mesh_with_children_becomes_dummy_with_geo(tmp_path):
    import numpy as np
    b = tmp_path / "mp.blend"
    r = blender("--python", str(ROOT / "tests/fixtures/make_mesh_parent.py"), "--", str(b))
    assert b.exists(), r.stdout + r.stderr
    tex = tmp_path / "tex"; textures.make_default_textures(tex)
    out = tmp_path / "o.kn5"
    r = export(b, tex, out)
    assert r.returncode == 0, r.stdout + r.stderr
    k = kn5io.read(out)
    nodes = list(kn5io.walk(k.root))
    assert not [n.name for n in nodes if n.cls == 2 and n.children], "メッシュに子がある"
    by = {n.name: n for n in nodes}
    assert by["DOOR"].cls == 1 and by["DOOR_GEO"].cls == 2 and by["PANEL"].cls == 2 and by["HINGE"].cls == 1
    assert [c.name for c in by["DOOR"].children][0] == "DOOR_GEO" and {"PANEL", "HINGE"} <= {c.name for c in by["DOOR"].children}
    assert np.array(by["DOOR_GEO"].matrix if by["DOOR_GEO"].matrix else (1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1)).reshape(4, 4) == pytest.approx(np.eye(4))
    # 世界座標: DOOR は (0.5, 2, 1) を中心に z 回転 0.5 rad の立方体（kn5 = (-bx, bz, by)）
    w = dict(world_pts(k.root))
    c = np.cos(0.5); s = np.sin(0.5)
    ctr = w["DOOR_GEO"].mean(0)
    assert ctr == pytest.approx([-0.5, 1.0, 2.0], abs=1e-4)
    assert w["DOOR_GEO"].max(0) - w["DOOR_GEO"].min(0) == pytest.approx([c + s, 1.0, c + s], abs=1e-4)
    assert w["PANEL"].mean(0) == pytest.approx([-0.8, 1.5, 2.0], abs=1e-4)
    assert len(by["DOOR_GEO"].indices) == 36 and len(by["PANEL"].indices) == 36
