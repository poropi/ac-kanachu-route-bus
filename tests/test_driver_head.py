"""運転士の頭（2026-11-26、ユーザー判断）: 首・頭の骨を AC の軸にしても、どの姿勢でも見た目（頂点の世界位置）が変わらないこと。

首の肌は骨で動く BODY_SUB3 から頭の骨の固定メッシュ NECK に変えたので、別に上限（6 mm）を置く。
基準は、骨の向きを変える前の書き出し（c0d03d2 の tools/driver_to_kn5.py）で本物のモデルを書き出し、
今の座らせ方（driver_pose）・ハンドルの動き（driver_steer）で動かしたもの。座った姿勢と ksanim のコマ 0・50・100 で、
同じ名前のメッシュの頂点の世界位置が 1e-5 m 以内（点の集合として比べる。頭のメッシュは頭の骨のローカルで統合するので並びが変わりうる）。
"""
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

import driver_pose as dp
import driver_posed
import driver_steer as ds
import kn5io
import paths

ROOT = Path(__file__).resolve().parent.parent
COCKPIT = json.loads((ROOT / "design/driver/cockpit.json").read_text(encoding="utf-8"))
REAL_BLEND = ROOT / "design/driver/kanachu_driver.blend"
BASE_COMMIT = "c0d03d2"          # 骨の向きを変える前
pytestmark = pytest.mark.skipif(not (paths.BLENDER and Path(paths.BLENDER).exists()), reason="Blender not found")


def _export(script, blend, out):
    r = subprocess.run([paths.BLENDER, "-b", str(blend), "--python", str(script), "--", "--out", str(out)],
                       capture_output=True, text=True)
    assert out.exists(), r.stdout[-800:] + r.stderr[-800:]
    return kn5io.read(out)


def _poses(kn5_path):
    rest = dp.rest_from_kn5(kn5_path)
    seated = dp.solve_seated(rest, COCKPIT)
    tracks = ds.build_steer(seated, rest, COCKPIT, 90.0)
    return [("seated", dp.fk(seated))] + [("frame%d" % i, driver_posed.steer_worlds(tracks, i)) for i in (0, 50, 100)]


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    if not REAL_BLEND.exists():
        pytest.skip("本物のモデルが無い")
    src = subprocess.run(["git", "-C", str(ROOT), "show", BASE_COMMIT + ":tools/driver_to_kn5.py"], capture_output=True, text=True)
    if src.returncode != 0:
        pytest.skip("git history (%s) not available" % BASE_COMMIT)
    tmp = tmp_path_factory.mktemp("head")
    old_script = tmp / "driver_to_kn5_base.py"
    old_script.write_text("import sys; sys.path.insert(0, %r)\n" % str(ROOT / "tools") + src.stdout)
    old, new = tmp / "old.kn5", tmp / "new.kn5"
    return (_export(old_script, REAL_BLEND, old), old), (_export(ROOT / "tools/driver_to_kn5.py", REAL_BLEND, new), new)


def test_neck_and_head_bones_have_ac_axes(pair):
    """新しい書き出しの首・頭の骨の世界の回転は単位行列（AC の軸: Y 上・Z 前・X = 運転手の左）。位置は前のまま。"""
    (_, old), (_, new) = pair
    Wo, Wn = dp.fk(dp.rest_from_kn5(old)), dp.fk(dp.rest_from_kn5(new))
    for b in ("DRIVER:RIG_Nek", "DRIVER:RIG_Head"):
        assert np.allclose(Wn[b][:3, :3], np.eye(3), atol=1e-6), b
        assert np.allclose(Wn[b][3, :3], Wo[b][3, :3], atol=1e-6), b
    for b in Wo:                                     # ほかの骨はそのまま
        if b not in ("DRIVER:RIG_Nek", "DRIVER:RIG_Head"):
            assert np.allclose(Wn[b], Wo[b], atol=1e-6), b


def test_posed_vertices_unchanged(pair):
    (ko, old), (kn, new) = pair
    for (label, Wo), (_, Wn) in zip(_poses(old), _poses(new)):
        mo, mn = driver_posed.posed_meshes(ko, Wo), driver_posed.posed_meshes(kn, Wn)
        same = [n for n in mo if n in mn]
        assert len(same) >= 10, (label, sorted(mo), sorted(mn))
        for n in same:
            d = driver_posed.max_point_set_distance(mo[n], mn[n])
            assert d <= 1e-5, (label, n, d)
        # 首の肌: 前は骨で動く BODY_SUB3（重みは RIG_Cest・RIG_Nek）、今は頭の骨の固定メッシュ NECK。座った姿勢では頭は前傾を
        # 打ち消して正面を向き、首は上体と一緒に約 5° 前傾するので、その差だけ動く（実測の最大 4.9 mm）。上限 6 mm
        assert "DRIVER:BODY_SUB3" not in mn and len(mn["DRIVER:NECK"]) == len(mo["DRIVER:BODY_SUB3"])
        d = driver_posed.max_point_set_distance(mo["DRIVER:BODY_SUB3"], mn["DRIVER:NECK"])
        assert d <= 0.006, (label, d)
        print("%s: 首の肌の移動 最大 %.1f mm" % (label, 1000 * d))


def test_probe_eye_is_spec_eye():
    """試走の probe（tools/ac/KanachuProbe/KanachuProbe.lua）の EYE は spec の eye_*（= car.ini の DRIVEREYES）と同じ。"""
    import re
    import spec
    lua = (ROOT / "tools/ac/KanachuProbe/KanachuProbe.lua").read_text(encoding="utf-8")
    m = re.search(r"^local EYE = \{([^}]*)\}", lua, re.M)
    s = spec.load()
    assert [float(x) for x in m.group(1).split(",")] == [s["eye_x"], s["eye_y"], s["eye_z"]]
