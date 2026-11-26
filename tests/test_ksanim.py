import numpy as np
import pytest

import knh
import ksanim
from ksanim import Frame

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BORROWED = ROOT / "vendor/driver_jetset/animations/steer.ksanim"
BORROWED_KNH = ROOT / "vendor/driver_jetset/driver_base_pos.knh"


def test_ksanim_roundtrip(tmp_path):
    t = {"A:one": [Frame((0.0, 0.0, 0.0, 1.0), (1.0, 2.0, 3.0), (1.0, 1.0, 1.0)),
                   Frame((0.5, 0.5, 0.5, 0.5), (-1.0, 0.25, 0.5), (1.0, 1.0, 1.0)),
                   Frame((0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 9.0), (2.0, 2.0, 2.0))],
         "B:two": [Frame((0.0, 0.0, 0.7071068, 0.7071068), (4.0, 5.0, 6.0), (1.0, 1.0, 1.0))] * 3}
    p = tmp_path / "a.ksanim"
    ksanim.write(t, p)
    got = ksanim.read(p)
    assert list(got) == list(t)
    for n in t:
        assert len(got[n]) == 3
        for a, b in zip(got[n], t[n]):
            assert np.allclose(a.rot, b.rot, atol=1e-6) and np.allclose(a.pos, b.pos) and np.allclose(a.scale, b.scale)


def test_matrix_conversion_roundtrip():
    rng = np.random.default_rng(1)
    for _ in range(20):
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        fr = Frame(tuple(q), tuple(rng.normal(size=3)), (1.0, 1.0, 1.0))
        M = ksanim.to_matrix(fr)
        assert np.allclose(M[:3, :3] @ M[:3, :3].T, np.eye(3), atol=1e-9)
        fr2 = ksanim.from_matrix(M)
        assert np.allclose(ksanim.to_matrix(fr2), M, atol=1e-9)


@pytest.mark.skipif(not BORROWED.exists(), reason="借り物が無い")
def test_borrowed_file_reads():
    t = ksanim.read(BORROWED)
    assert len(t) == 55 and all(len(v) == 101 for v in t.values())
    # 動かない骨: 四元数の行列の転置が knh の 3x3 と一致する（成分順 x y z w と行ベクトル規約の確認）
    nodes = {n.name: n for n in knh.walk(knh.read(BORROWED_KNH))}
    n = "DRIVER:RIG_Hips"
    M = np.array(nodes[n].matrix).reshape(4, 4)
    assert np.allclose(ksanim.to_matrix(t[n][0]), M, atol=1e-5)


def test_write_keeps_quaternion_hemisphere(tmp_path):
    q = (0.0, 0.0, 0.6, 0.8)
    t = {"A": [Frame(q, (0, 0, 0), (1, 1, 1)), Frame(tuple(-x for x in q), (0, 0, 0), (1, 1, 1))]}
    ksanim.write(t, tmp_path / "a.ksanim")
    r = ksanim.read(tmp_path / "a.ksanim")["A"]
    assert np.dot(r[0].rot, r[1].rot) > 0.99
