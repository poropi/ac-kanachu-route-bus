import os
import pytest
import kn5io

# 手元にある任意の kn5（市販・配布物は同梱しない）で、読んで書き戻すとバイト一致することを確かめる
HT81S = os.environ.get("KN5_ROUNDTRIP_SAMPLE", "")


@pytest.mark.skipif(not os.path.exists(HT81S), reason="set KN5_ROUNDTRIP_SAMPLE to a .kn5 file")
def test_roundtrip_ht81s(tmp_path):
    out = tmp_path / "out.kn5"
    kn5io.write(kn5io.read(HT81S), str(out))
    assert open(HT81S, "rb").read() == out.read_bytes()


def test_skinned_mesh_roundtrip(tmp_path):
    """骨で動くメッシュ（種類 3）は末尾に外接球と描画フラグを持たない（AC の content/driver/driver.kn5 で確認）。"""
    import struct
    v = struct.pack("<19f", *([0.0] * 19))           # 76 バイト = 位置・法線・UV・接線・重み 4・骨番号 4
    skin = kn5io.Node(3, "DRIVER:suit", 1, bones=[("DRIVER:RIG_Hips", bytes(64))], vertices=v * 3,
                      indices=[0, 1, 2], matid=0, layer=0)
    root = kn5io.Node(1, "ROOT", 1, children=[skin], matrix=tuple(float(i % 5 == 0) for i in range(16)))
    k = kn5io.Kn5(6, 0, [], [kn5io.Mat("m", "ksPerPixel", 0, 0, 0, [], [])], root)
    a = tmp_path / "a.kn5"; b = tmp_path / "b.kn5"
    kn5io.write(k, str(a))
    kn5io.write(kn5io.read(str(a)), str(b))
    assert a.read_bytes() == b.read_bytes()
    assert kn5io.read(str(a)).root.children[0].bones[0][0] == "DRIVER:RIG_Hips"
