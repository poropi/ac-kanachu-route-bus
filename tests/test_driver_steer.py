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


def _rim_angles(tracks, seated):
    """書いた ksanim から、各手のひらのリム上の角度（座った握り点から、時計回り正、度）と指の向きとの接線のずれ（度）。"""
    c, ax = np.array(COCKPIT["wheel_center"]), dp.unit(np.array(COCKPIT["wheel_axis"]))
    Ws = dp.fk(seated)

    def radial(p):
        d = p - c
        return dp.unit(d - np.dot(d, ax) * ax)

    ang, tan = {a: [] for a in "LR"}, {a: [] for a in "LR"}
    r0 = {a: radial(dp.palm_center(Ws, a)) for a in "LR"}
    for i in range(len(tracks["DRIVER:RIG_Hips"])):
        W = world_at(tracks, i)
        for a in "LR":
            r = radial(dp.palm_center(W, a))
            ang[a].append(float(np.degrees(np.arctan2(np.dot(ax, np.cross(r0[a], r)), np.dot(r0[a], r)))))
            _, _, hand, mid = dp.side_bones(a)
            finger = dp.unit(W[mid][3, :3] - W[hand][3, :3])
            tang = np.cross(ax, r)
            tan[a].append(float(np.degrees(np.arccos(np.clip(abs(np.dot(finger, tang)), 0, 1)))))
    return ang, tan


@pytest.fixture(scope="module", params=[180.0, 450.0])
def written(request, steer, tmp_path_factory):
    """ksanim をファイルに書いて読み戻したもの。"""
    rest, seated, _, _ = steer
    p = tmp_path_factory.mktemp("w") / "steer.ksanim"
    ksanim.write(ds.build_steer(seated, rest, COCKPIT, request.param), p)
    return ksanim.read(p), seated, request.param


def test_written_grip_monotonic_stops_and_follows_tangent(written):
    tracks, seated, lock = written
    ang, tan = _rim_angles(tracks, seated)
    arcs = ds.grip_arcs(seated, COCKPIT)
    for a in "LR":
        v = np.array(ang[a])
        assert abs(v[50]) < 0.5, a                                  # 0° は座った握り点
        d = np.diff(v)
        assert np.all(d <= 0.05) or np.all(d >= -0.05), a           # 行ったり来たりしない
        assert max(tan[a]) <= 15.0, (a, max(tan[a]))                 # 指がリムの接線に沿う
        theta = np.array([ds.FRAME0_SIGN * (lock / 2 - lock * i / 100) for i in range(101)])
        lo, hi = arcs[a]
        for beyond in (theta > hi + 0.5, theta < lo - 0.5):         # 届く区間の外のコマ = 止まっているはずのコマ
            if beyond.any():
                assert np.ptp(v[beyond]) <= 0.5, (a, np.ptp(v[beyond]))     # 止まっている間はリムの角度が変わらない
        assert (theta > hi + 0.5).any() or (theta < lo - 0.5).any(), a      # どちらの手も端で止まる


def test_quaternion_continuity(written):
    tracks, _, _ = written
    for n, fr in tracks.items():
        for f0, f1 in zip(fr, fr[1:]):
            assert np.dot(f0.rot, f1.rot) >= 0, n


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
