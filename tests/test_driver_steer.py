import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

import driver_pose as dp
import driver_steer as ds
import ksanim
import paths
from driver_skeleton import BONES

ROOT = Path(__file__).resolve().parent.parent
COCKPIT = json.loads((ROOT / "design/driver/cockpit.json").read_text(encoding="utf-8"))
REAL_BLEND = ROOT / "design/driver/kanachu_driver.blend"
pytestmark = pytest.mark.skipif(not (paths.BLENDER and Path(paths.BLENDER).exists()), reason="Blender not found")


def _export(tmp, blend):
    kn5 = tmp / (blend.stem + ".kn5")
    subprocess.run([paths.BLENDER, "-b", str(blend), "--python", str(ROOT / "tools/driver_to_kn5.py"), "--", "--out", str(kn5)],
                   capture_output=True, text=True)
    assert kn5.exists()
    return kn5


@pytest.fixture(scope="module", params=["fixture", "real"])
def steer(request, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("steer")
    if request.param == "real":
        if not REAL_BLEND.exists():
            pytest.skip("本物のモデルが無い")
        kn5 = _export(tmp, REAL_BLEND)
    else:
        blend = tmp / "mini.blend"
        subprocess.run([paths.BLENDER, "-b", "--python", str(ROOT / "tests/fixtures/make_mini_driver.py"), "--", str(blend)],
                       capture_output=True, text=True)
        kn5 = _export(tmp, blend)
    rest = dp.rest_from_kn5(kn5)
    seated = dp.solve_seated(rest, COCKPIT)
    tracks = ds.build_steer(seated, rest, COCKPIT, 180.0)
    return rest, seated, tracks, kn5


def world_at(tracks, i):
    return dp.fk({n: ksanim.to_matrix(f[i]) for n, f in tracks.items()})


def dist_to_rim_circle(p):
    c, n, r = np.array(COCKPIT["wheel_center"]), np.array(COCKPIT["wheel_axis"]), COCKPIT["rim_radius"]
    d = p - c
    off = float(np.dot(d, n))
    return float(np.hypot(np.linalg.norm(d - off * n) - r, off))


def test_all_bones_and_frames(steer):
    _, _, tracks, _ = steer
    assert list(tracks) == [n for n, _ in BONES] and len(BONES) == 56
    assert all(len(v) == 101 for v in tracks.values())


def test_hands_on_rim_all_frames(steer):
    _, _, tracks, _ = steer
    for i in range(101):          # 0 / 50 / 100 コマ = ±90° / 0° / ∓90°
        W = world_at(tracks, i)
        for a in "LR":
            assert dist_to_rim_circle(dp.palm_center(W, a)) <= 0.02, (i, a)


def test_seated_grip_at_zero_and_monotonic(steer):
    _, seated, tracks, _ = steer
    W, Ws = world_at(tracks, 50), dp.fk(seated)
    for a in "LR":
        assert np.linalg.norm(dp.palm_center(W, a) - dp.palm_center(Ws, a)) <= 1e-3
    ph = ds.grip_angles(seated, COCKPIT)
    for a in "LR":
        d = np.diff(ph[a])
        assert np.all(d <= 1e-9) or np.all(d >= -1e-9), a        # 行ったり来たりしない
        assert ph[a][50] == pytest.approx(0.0, abs=1e-9)


def test_elbow_bend_min(steer):
    _, _, tracks, _ = steer
    assert min(min(dp.elbow_bends(world_at(tracks, i)).values()) for i in range(101)) >= 15.0


def test_no_ik_flip(steer):
    _, _, tracks, _ = steer
    prev = None
    for i in range(101):
        W = world_at(tracks, i)
        cur = {"bend": dp.elbow_bends(W),
               "elbow": {a: W[dp.side_bones(a)[1]][3, :3] for a in "LR"}}
        if prev is not None:
            for a in "LR":
                assert abs(cur["bend"][a] - prev["bend"][a]) <= 10.0, (i, a)
                assert np.linalg.norm(cur["elbow"][a] - prev["elbow"][a]) <= 0.05, (i, a)
        prev = cur


def test_other_bones_static(steer):
    _, seated, tracks, _ = steer
    moving = set()
    for a in "LR":
        arm = dp.side_bones(a)[0]
        moving |= set(dp._desc(arm))
    assert dp.side_bones("L")[0] in moving and len(moving) > 10      # 指まで含む
    for n, _ in BONES:
        if n in moving:
            continue
        ref = ksanim.from_matrix(seated[n])
        for f in tracks[n]:
            assert np.allclose(ksanim.to_matrix(f), ksanim.to_matrix(ref), atol=1e-5), n


def test_frame_direction_frame0_is_clockwise(steer):
    """コマ 0 = ハンドルを時計回り（右へ）いっぱい。運転手の右側の手は、0 コマのほうが 100 コマより低い。"""
    _, _, tracks, _ = steer
    W0, W100 = world_at(tracks, 0), world_at(tracks, 100)
    a = min("LR", key=lambda s: dp.palm_center(W0, s)[0])      # kn5 の -x 側 = 運転手の右
    assert dp.palm_center(W0, a)[1] < dp.palm_center(W100, a)[1] - 0.1


def test_large_lock_no_flip_and_on_rim(steer):
    rest, seated, _, _ = steer
    t = ds.build_steer(seated, rest, COCKPIT, 450.0)
    prev = None
    for i in range(101):
        W = world_at(t, i)
        for a in "LR":
            assert dist_to_rim_circle(dp.palm_center(W, a)) <= 0.02, (i, a)
        el = {a: W[dp.side_bones(a)[1]][3, :3] for a in "LR"}
        if prev:
            assert all(np.linalg.norm(el[a] - prev[a]) <= 0.05 for a in "LR"), i
        prev = el


def test_cli(steer, tmp_path):
    _, _, _, kn5 = steer
    out = tmp_path / "steer.ksanim"
    r = subprocess.run(["python3", str(ROOT / "tools/driver_steer.py"), "--kn5", str(kn5), "--cockpit",
                        str(ROOT / "design/driver/cockpit.json"), "--lock", "180", "--out", str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    t = ksanim.read(out)
    assert len(t) == 56 and all(len(v) == 101 for v in t.values())
