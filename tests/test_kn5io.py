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
