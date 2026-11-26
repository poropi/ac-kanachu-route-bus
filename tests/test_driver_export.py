import subprocess
from pathlib import Path

import numpy as np
import pytest

import kn5io
import paths
from driver_skeleton import BONES, HEAD_MESHES, SKINNED_MESHES

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (paths.BLENDER and Path(paths.BLENDER).exists()), reason="Blender not found")


def blender(*args):
    return subprocess.run([paths.BLENDER, "-b", *args], capture_output=True, text=True)


def make(tmp, brk=""):
    out = tmp / ((brk or "ok") + ".blend")
    r = blender("--python", str(ROOT / "tests/fixtures/make_mini_driver.py"), "--", str(out), *([brk] if brk else []))
    assert out.exists(), r.stdout + r.stderr
    return out


def export(blend, tmp):
    out = tmp / (blend.stem + ".kn5")
    r = blender(str(blend), "--python", str(ROOT / "tools/driver_to_kn5.py"), "--", "--out", str(out))
    return r, out


@pytest.fixture(scope="module")
def kn5(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("drv")
    r, out = export(make(tmp), tmp)
    assert out.exists(), r.stdout + r.stderr
    return kn5io.read(out), out


def world_matrices(root):
    """行ベクトル規約（世界 = 自分 @ 親）の世界行列。種類 1 以外は単位。"""
    W = {}

    def go(n, P):
        M = np.array(n.matrix).reshape(4, 4) if n.cls == 1 else np.eye(4)
        W[n.name] = M @ P
        for c in n.children:
            go(c, W[n.name])
    go(root, np.eye(4))
    return W


def skinned(k):
    return {n.name: n for n in kn5io.walk(k.root) if n.cls == 3}


def test_bone_hierarchy_matches_skeleton(kn5):
    k, _ = kn5
    assert k.root.name == "DRIVER:DRIVER"
    bone_names = {n for n, _ in BONES}
    parent, count = {}, 0

    def go(n, p):
        nonlocal count
        if n.cls == 1 and n.name in bone_names:
            parent[n.name] = p
            p = n.name
            count += 1
        for c in n.children:
            go(c, p)
    go(k.root, None)
    assert parent == dict(BONES) and count == len(BONES)


def test_skinned_layout_like_kunos(kn5):
    k, _ = kn5
    sk = skinned(k)
    assert set(sk) == set(SKINNED_MESHES)
    for n in sk.values():
        assert len(n.vertices) % 76 == 0 and n.indices
    for name in SKINNED_MESHES:   # <名前>（種類 1）の子が <名前>（種類 3）
        dummy = next(n for n in k.root.children if n.name == name)
        assert dummy.cls == 1 and [c.cls for c in dummy.children] == [3] and dummy.children[0].name == name


def test_skinned_weights_valid(kn5):
    k, _ = kn5
    for n in skinned(k).values():
        v = np.frombuffer(n.vertices, "<f4").reshape(-1, 19)
        w, idx = v[:, 11:15], v[:, 15:19]
        assert np.allclose(w.sum(1), 1, atol=1e-4)
        assert np.all(idx == np.round(idx)) and idx.max() < len(n.bones) and idx.min() >= -1
        assert np.all((w > 0) == (idx >= 0))   # 使わない枠は重み 0・骨番号 -1（Kunos と同じ）
        assert np.all(np.isfinite(v))


def test_bind_pose_identity(kn5):
    k, _ = kn5
    W = world_matrices(k.root)
    for n in skinned(k).values():
        assert n.bones
        for bn, bm in n.bones:
            B = np.frombuffer(bm, "<f4").reshape(4, 4).astype(float)
            assert np.abs(W[bn] @ B - np.eye(4)).max() < 1e-4, bn


def test_skinned_vertices_follow_bind_pose(kn5):
    """頂点は kn5 の世界座標（-bx, bz, by）。BODY の箱は Blender で x ±0.17、y ±0.10、z 0.105〜1.455。"""
    k, _ = kn5
    v = np.frombuffer(skinned(k)["DRIVER:BODY"].vertices, "<f4").reshape(-1, 19)
    lo, hi = v[:, :3].min(0), v[:, :3].max(0)
    assert np.allclose(lo, [-0.17, 0.105, -0.10], atol=1e-4) and np.allclose(hi, [0.17, 1.455, 0.10], atol=1e-4)
    assert np.allclose(np.linalg.norm(v[:, 3:6], axis=1), 1, atol=1e-3)


def test_head_meshes_under_head_bone(kn5):
    k, _ = kn5
    head = next(n for n in kn5io.walk(k.root) if n.name == "DRIVER:RIG_Head")
    kids = {c.name: c for c in head.children if c.cls == 2}
    assert set(kids) == set(HEAD_MESHES)
    # 頂点は頭の骨のローカル座標。世界に戻すと Blender 上の位置（顔の箱は x ±0.10、上向き 1.48〜1.64）。
    # 箱の中心 1.53 ではなく +0.03 なのは、Blender の骨の親子が尾の位置を基準にするため（試験 .blend の逆行列は頭の位置で補正している）
    W = world_matrices(k.root)["DRIVER:RIG_Head"]
    v = np.frombuffer(kids["DRIVER:GEO_Driver_FACE"].vertices, "<f4").reshape(-1, 11)
    p = np.c_[v[:, :3], np.ones(len(v))] @ W
    assert np.allclose([p[:, 0].min(), p[:, 0].max()], [-0.10, 0.10], atol=1e-4)
    assert np.allclose([p[:, 1].min(), p[:, 1].max()], [1.48, 1.64], atol=1e-4)


def test_materials_and_textures(kn5):
    k, _ = kn5
    names = {t.name for t in k.textures}
    for m in k.materials:
        assert m.tex and m.tex[0][0] == "txDiffuse" and m.tex[0][2] in names
    assert all(t.data[:4] == b"DDS " for t in k.textures)


def test_more_than_four_influences_truncated(tmp_path):
    var = tmp_path / "five.blend"
    r = blender(str(make(tmp_path)), "--python", str(ROOT / "tests/fixtures/weight_variant.py"), "--", str(var), "five_influence")
    assert var.exists(), r.stdout + r.stderr
    r, out = export(var, tmp_path)
    assert out.exists(), r.stdout + r.stderr
    n = skinned(kn5io.read(out))["DRIVER:BODY"]
    v = np.frombuffer(n.vertices, "<f4").reshape(-1, 19)
    names = [b for b, _ in n.bones]
    rows = v[(v[:, 11:15] > 0).sum(1) == 4]   # 重みが 4 本そろうのは頂点 0 だけ
    assert len(rows) >= 1
    top = {"DRIVER:RIG_Cest": 0.4, "DRIVER:RIG_Hips": 0.3, "DRIVER:RIG_Nek": 0.15, "DRIVER:RIG_Head": 0.1}
    got = {names[int(i)]: w for w, i in zip(rows[0][11:15], rows[0][15:19])}
    assert set(got) == set(top)   # 5 本目（RIG_Center）は捨てる
    for b, w in top.items():
        assert got[b] == pytest.approx(w / 0.95, abs=1e-4)
    assert rows[0][11:15].sum() == pytest.approx(1, abs=1e-4)


def test_unweighted_vertex_is_error(tmp_path):
    r, out = export(make(tmp_path, "unweighted"), tmp_path)
    assert r.returncode != 0 and not out.exists()
    assert "no bone weight" in r.stdout + r.stderr


def test_roundtrip_bytes(kn5, tmp_path):
    k, out = kn5
    again = tmp_path / "again.kn5"
    kn5io.write(kn5io.read(out), again)
    assert again.read_bytes() == out.read_bytes()


def test_shaders_by_node_type(kn5):
    """骨で動くメッシュ（種類 3）は ksSkinnedMesh、頭の固定メッシュ（種類 2）は ksPerPixel。"""
    k, _ = kn5
    used = {2: set(), 3: set()}
    for n in kn5io.walk(k.root):
        if n.cls in used:
            used[n.cls].add(n.matid)
    assert used[2] and used[3]
    assert {k.materials[i].shader for i in used[3]} == {"ksSkinnedMesh"}
    assert {k.materials[i].shader for i in used[2]} == {"ksPerPixel"}
    for i in used[3]:   # Kunos の骨で動くマテリアルと同じ基本の ks* と bones を持つ
        props = {p[0] for p in k.materials[i].props}
        assert {"bones", "ksAmbient", "ksDiffuse", "ksSpecular", "ksSpecularEXP", "ksEmissive", "ksAlphaRef"} <= props


def test_skinned_material_complete(kn5):
    """ksSkinnedMesh の定義（cbBones・cbMaterial・cbCarPaint とテクスチャ 4 枠）を全部埋める。共有テクスチャは 1 回ずつ。"""
    k, _ = kn5
    used = {n.matid for n in kn5io.walk(k.root) if n.cls == 3}
    names = [t.name for t in k.textures]
    shared = ["driver_flat_nm.dds", "driver_maps.dds", "driver_detail.dds"]
    assert all(names.count(s) == 1 for s in shared)
    want = ["bones", "ksAmbient", "ksDiffuse", "ksSpecular", "ksSpecularEXP", "ksEmissive", "ksAlphaRef", "fresnelC",
            "fresnelEXP", "fresnelMaxLevel", "nmObjectSpace", "isAdditive", "useDetail", "detailUVMultiplier", "boh"]
    for i in used:
        m = k.materials[i]
        assert [p[0] for p in m.props] == want
        assert [t[0] for t in m.tex] == ["txDiffuse", "txNormal", "txMaps", "txDetail"]
        assert [t[1] for t in m.tex] == [0, 1, 2, 3]
        assert [t[2] for t in m.tex][1:] == shared and m.tex[0][2] in names
    for i in {n.matid for n in kn5io.walk(k.root) if n.cls == 2}:   # 頭の固定メッシュは変えない
        assert [t[0] for t in k.materials[i].tex] == ["txDiffuse"]


def variant(tmp, mode):
    var = tmp / (mode + ".blend")
    r = blender(str(make(tmp)), "--python", str(ROOT / "tests/fixtures/weight_variant.py"), "--", str(var), mode)
    assert var.exists(), r.stdout + r.stderr
    return var


def test_posed_armature_exports_same_as_rest(kn5, tmp_path):
    """頭と腕にポーズを付けた .blend でも、レスト位置の書き出しとバイト一致する（頭のメッシュも骨も）。"""
    r, out = export(variant(tmp_path, "pose"), tmp_path)
    assert out.exists(), r.stdout + r.stderr
    assert out.read_bytes() == kn5[1].read_bytes()


def test_mirror_modifier_applied(kn5, tmp_path):
    r, out = export(variant(tmp_path, "mirror"), tmp_path)
    assert out.exists(), r.stdout + r.stderr
    k = kn5io.read(out)
    n, base = skinned(k)["DRIVER:GLOVES"], skinned(kn5[0])["DRIVER:GLOVES"]
    v = np.frombuffer(n.vertices, "<f4").reshape(-1, 19)
    assert len(v) == 2 * (len(base.vertices) // 76)
    assert np.allclose(v[:, 11:15].sum(1), 1, atol=1e-4) and v[:, 15:19].max() < len(n.bones)
    assert v[:, 0].min() < -0.3 and v[:, 0].max() > 0.3   # 両側に頂点がある


# --- マテリアルごとに分ける（Kunos の DRIVER:HELMET → DRIVER:HELMET_SUB0 / _SUB1 と同じ形） ---

@pytest.fixture(scope="module")
def multi(tmp_path_factory):
    """DRIVER:BODY が 3 枠（真ん中は未使用）・DRIVER:HAIR が 2 枠のマテリアルを使う .blend の書き出し。"""
    tmp = tmp_path_factory.mktemp("multi")
    r, out = export(variant(tmp, "multi_material"), tmp)
    assert out.exists(), r.stdout + r.stderr
    return kn5io.read(out)


def by_name(k):
    return {n.name: n for n in kn5io.walk(k.root)}


def bone_of_position(n):
    """種類 3 の頂点の位置（丸め） -> 重み 1 の骨名の集合。"""
    v = np.frombuffer(n.vertices, "<f4").reshape(-1, 19)
    names = [b for b, _ in n.bones]
    out = {}
    for row_ in v:
        key = tuple(np.round(row_[:3], 4))
        out.setdefault(key, set()).update(names[int(i)] for w, i in zip(row_[11:15], row_[15:19]) if w > 0)
    return out


def test_multi_material_skinned_split(kn5, multi):
    k, base = multi, kn5[0]
    dummy = next(n for n in k.root.children if n.name == "DRIVER:BODY")
    assert dummy.cls == 1
    assert [(c.cls, c.name) for c in dummy.children] == [(3, "DRIVER:BODY_SUB0"), (3, "DRIVER:BODY_SUB1")]
    s0, s1 = dummy.children
    assert [k.materials[s.matid].name for s in (s0, s1)] == ["driver_suit_skinned", "driver_shoes_skinned"]
    assert all(k.materials[s.matid].shader == "ksSkinnedMesh" for s in (s0, s1))
    # 同じ画像を使う 2 つのマテリアルは、kn5 のテクスチャ 1 枚を共有する
    tnames = [t.name for t in k.textures]
    assert tnames.count("driver_tex.dds") == 1 and len(tnames) == len(set(tnames))
    assert [k.materials[s.matid].tex[0][2] for s in (s0, s1)] == ["driver_tex.dds", "driver_tex.dds"]
    assert "driver_unused" not in {t.name[:-4] for t in k.textures} | {m.name.replace("_skinned", "") for m in k.materials}
    # 頂点数・三角形数の合計は 1 マテリアルの書き出しと同じ
    one = skinned(base)["DRIVER:BODY"]
    assert sum(len(s.vertices) // 76 for s in (s0, s1)) == len(one.vertices) // 76
    assert sum(len(s.indices) for s in (s0, s1)) == len(one.indices)
    # 骨はその部分が使うものだけで、番号は部分ごとに振り直す（上面は RIG_Cest だけ）
    assert [b for b, _ in s1.bones] == ["DRIVER:RIG_Cest"]
    assert [b for b, _ in s0.bones] == ["DRIVER:RIG_Hips", "DRIVER:RIG_Cest"]
    W = world_matrices(k.root)
    for s in (s0, s1):
        v = np.frombuffer(s.vertices, "<f4").reshape(-1, 19)
        assert np.allclose(v[:, 11:15].sum(1), 1, atol=1e-4)
        assert v[:, 15:19].max() < len(s.bones) and v[:, 15:19].min() >= -1
        for bn, bm in s.bones:
            B = np.frombuffer(bm, "<f4").reshape(4, 4).astype(float)
            assert np.abs(W[bn] @ B - np.eye(4)).max() < 1e-4
    # 各頂点の骨は 1 マテリアルの書き出しと同じ骨を指す
    ref = bone_of_position(one)
    for s in (s0, s1):
        for key, bones in bone_of_position(s).items():
            assert ref[key] == bones, key
    # 骨で動くもう一方のメッシュ（1 マテリアル）は今までどおり
    gl = next(n for n in k.root.children if n.name == "DRIVER:GLOVES")
    assert [(c.cls, c.name) for c in gl.children] == [(3, "DRIVER:GLOVES")]


def test_multi_material_head_split(kn5, multi):
    k, base = multi, kn5[0]
    head = next(n for n in kn5io.walk(k.root) if n.name == "DRIVER:RIG_Head")
    kids = {c.name: c for c in head.children}
    hair = kids["DRIVER:HAIR"]
    assert hair.cls == 1 and np.allclose(np.array(hair.matrix).reshape(4, 4), np.eye(4))
    assert [(c.cls, c.name) for c in hair.children] == [(2, "DRIVER:HAIR_SUB0"), (2, "DRIVER:HAIR_SUB1")]
    s0, s1 = hair.children
    assert [k.materials[s.matid].name for s in (s0, s1)] == ["driver_hair", "driver_skin"]
    assert all(k.materials[s.matid].shader == "ksPerPixel" for s in (s0, s1))
    # 顔と共有する driver_skin はマテリアルもテクスチャも 1 回だけ
    assert s1.matid == kids["DRIVER:GEO_Driver_FACE"].matid
    mnames, tnames = [m.name for m in k.materials], [t.name for t in k.textures]
    assert len(mnames) == len(set(mnames)) and len(tnames) == len(set(tnames))
    # 1 マテリアルの頭のメッシュはそのまま種類 2
    assert kids["DRIVER:GEO_Driver_FACE"].cls == 2 and kids["DRIVER:CAP"].cls == 2
    for s in (s0, s1):
        c = np.frombuffer(s.vertices, "<f4").reshape(-1, 11)[:, :3]
        assert np.linalg.norm(c - s.bsphere[:3], axis=1).max() <= s.bsphere[3] + 1e-5
    # 頂点の世界位置は 1 マテリアルの書き出しと同じ
    def world_rows(k_, nodes):
        W = world_matrices(k_.root)
        rows = []
        for n in nodes:
            v = np.frombuffer(n.vertices, "<f4").reshape(-1, 11)
            rows.append(np.c_[v[:, :3], np.ones(len(v))] @ W[n.name])
        p = np.round(np.vstack(rows)[:, :3], 5)
        return p[np.lexsort(p.T[::-1])]
    one = by_name(base)["DRIVER:HAIR"]
    assert np.array_equal(world_rows(k, [s0, s1]), world_rows(base, [one]))
    assert sum(len(s.indices) for s in (s0, s1)) == len(one.indices)


def test_single_material_unchanged(kn5, tmp_path):
    """1 マテリアルだけの .blend は、マテリアルで分ける前のコード（bd94908）とバイト一致する。
    使わない枠が増えても（面が 1 つの枠だけを使えば）同じ。"""
    k, out = kn5
    head = next(n for n in kn5io.walk(k.root) if n.name == "DRIVER:RIG_Head")
    assert [(c.cls, c.name) for c in head.children] == [(2, n) for n in HEAD_MESHES]
    assert [(n.cls, n.name, [(c.cls, c.name) for c in n.children]) for n in k.root.children if n.name in SKINNED_MESHES] \
        == [(1, n, [(3, n)]) for n in SKINNED_MESHES]
    r, extra = export(variant(tmp_path, "single_slot_extra"), tmp_path)
    assert extra.exists(), r.stdout + r.stderr
    assert extra.read_bytes() == out.read_bytes()
    src = subprocess.run(["git", "-C", str(ROOT), "show", "bd94908:tools/driver_to_kn5.py"], capture_output=True, text=True)
    if src.returncode != 0:
        pytest.skip("git history (bd94908) not available")
    old = tmp_path / "driver_to_kn5_bd94908.py"
    old.write_text("import sys; sys.path.insert(0, %r)\n" % str(ROOT / "tools") + src.stdout)
    blend = tmp_path / "base.blend"
    make(tmp_path)
    (tmp_path / "ok.blend").rename(blend)
    ref = tmp_path / "ref.kn5"
    r = blender(str(blend), "--python", str(old), "--", "--out", str(ref))
    assert ref.exists(), r.stdout + r.stderr
    assert ref.read_bytes() == out.read_bytes()
