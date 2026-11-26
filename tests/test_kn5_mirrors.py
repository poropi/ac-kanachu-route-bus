import numpy as np
import kn5_mirrors


def test_mirror_uv_spans_face_and_orientation():
    # 後ろ向き（法線 -z）の鏡面。見る人は鏡の後ろ側に立ち、前（+z）を向いて鏡を見る
    n = (0.0, 0.0, -1.0)
    pos = np.array([[0.2, 1.0, 0], [-0.2, 1.0, 0], [0.2, 1.4, 0], [-0.2, 1.4, 0]])
    uv = kn5_mirrors.mirror_uv(pos, n)
    assert np.allclose(uv[:, 0].min(), 0) and np.allclose(uv[:, 0].max(), 1)
    assert np.allclose(uv[:, 1].min(), -1) and np.allclose(uv[:, 1].max(), 0)
    # 鏡の前に立つ人（視線 +z）の右は kn5 の -x（+x が車の左）→ x=-0.2 の点が u=1
    assert uv[1, 0] > uv[0, 0]
    # 上の点が v=0（上端）
    assert uv[2, 1] > uv[0, 1]


def test_ini_and_ext_follow_the_same_order():
    ini = kn5_mirrors.mirrors_ini()
    ext = kn5_mirrors.real_mirrors_ext()
    for i, n in enumerate(kn5_mirrors.NAMES):
        assert "[MIRROR_%d]\nNAME=%s" % (i, n) in ini
        assert "[REAL_MIRROR_%d]\n; %s" % (i, n) in ext
    assert len(kn5_mirrors.NAMES) == 5
