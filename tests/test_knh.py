import struct
from pathlib import Path

import pytest

import knh

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "refs" / "driver_jetset" / "driver_base_pos.knh"


def mat(tx, ty, tz):
    return (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, tx, ty, tz, 1)


def test_knh_roundtrip(tmp_path):
    root = knh.KnhNode("A", mat(0, 0, 0), [
        knh.KnhNode("B", mat(1, 2, 3), [knh.KnhNode("D", mat(0.5, 0.25, -1), [])]),
        knh.KnhNode("C日本", mat(-1, 0, 4), []),
    ])
    p = tmp_path / "t.knh"
    knh.write(root, p)
    assert knh.read(p) == root
    raw = p.read_bytes()
    assert raw[:5] == struct.pack("<i", 1) + b"A"      # 名前は int 長さ + utf8
    assert struct.unpack_from("<3f", raw, 5 + 48) == (0.0, 0.0, 0.0)   # 平行移動は 12〜14 番目


def test_knh_truncated_or_trailing_is_error(tmp_path):
    p = tmp_path / "t.knh"
    knh.write(knh.KnhNode("A", mat(0, 0, 0), []), p)
    p.write_bytes(p.read_bytes() + b"\0")
    with pytest.raises(ValueError):
        knh.read(p)


@pytest.mark.skipif(not REF.exists(), reason="refs/ の借り物の knh が無い")
def test_reads_borrowed_knh_as_57_bones(tmp_path):
    r = knh.read(REF)
    assert len(list(knh.walk(r))) == 57
    out = tmp_path / "copy.knh"
    knh.write(r, out)
    assert out.read_bytes() == REF.read_bytes()      # 無損失
