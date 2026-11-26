import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import driver_pose as dp
import knh
import paths
from driver_skeleton import BONES

ROOT = Path(__file__).resolve().parent.parent
COCKPIT = json.loads((ROOT / "design/driver/cockpit.json").read_text(encoding="utf-8"))
pytestmark = pytest.mark.skipif(not (paths.BLENDER and Path(paths.BLENDER).exists()), reason="Blender not found")


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pose")
    blend, kn5 = tmp / "mini.blend", tmp / "mini.kn5"
    for args in (["--python", str(ROOT / "tests/fixtures/make_mini_driver.py"), "--", str(blend)],
                 [str(blend), "--python", str(ROOT / "tools/driver_to_kn5.py"), "--", "--out", str(kn5)]):
        subprocess.run([paths.BLENDER, "-b", *args], capture_output=True, text=True)
    assert kn5.exists()
    rest = dp.rest_from_kn5(kn5)
    report = {}
    local = dp.solve_seated(rest, COCKPIT, report=report)
    return rest, local, report, kn5


def dist_to_rim_circle(p):
    """点 p とリムの管の中心線（円）の距離。"""
    c, n, r = np.array(COCKPIT["wheel_center"]), np.array(COCKPIT["wheel_axis"]), COCKPIT["rim_radius"]
    d = p - c
    off = float(np.dot(d, n))
    return float(np.hypot(np.linalg.norm(d - off * n) - r, off))


def test_seated_eye_and_hands(solved):
    rest, local, report, _ = solved
    W = dp.fk(local)
    eye = np.linalg.norm(dp.eye_position(local, rest) - COCKPIT["eye"])
    palms = {a: dp.palm_center(W, a) for a in "LR"}
    hands = {a: dist_to_rim_circle(palms[a]) for a in "LR"}
    print("目の距離 %.4f m、手のひら-リム L %.4f R %.4f m、拡大率 %.3f、握り角 %s"
          % (eye, hands["L"], hands["R"], report["scale"], report["grip_deg"]))
    assert eye <= 0.03
    assert max(hands.values()) <= 0.02
    assert np.linalg.norm(palms["L"] - palms["R"]) > 0.15      # 両手が同じ点に重ならない（左右が別の側）


def test_seated_no_intersection_proxy(solved):
    rest, local, report, _ = solved
    W = dp.fk(local)
    hips = W["DRIVER:RIG_Hips"][3, :3]
    h = hips[1] - COCKPIT["seat_point"][1]
    assert 0.05 <= h <= 0.20, h
    box = COCKPIT["column_box"]
    lo, hi = np.array(box["min"]), np.array(box["max"])
    for a in "LR":
        knee = W["DRIVER:RIG_Shin_" + a][3, :3]
        assert not (np.all(knee >= lo) and np.all(knee <= hi)), (a, knee)


def test_feet_on_pedals_one_each(solved):
    _, local, _, _ = solved
    W = dp.fk(local)
    ped = {"accel": np.array(COCKPIT["pedal_accel"]), "brake": np.array(COCKPIT["pedal_brake"])}
    hit = set()
    for a in "LR":
        ball = W["DRIVER:RIG_Foot_" + a][3, :3]
        name, d = min(((k, np.linalg.norm(ball - v)) for k, v in ped.items()), key=lambda kv: kv[1])
        assert d <= 0.02, (a, name, d)
        hit.add(name)
    assert hit == {"accel", "brake"}


def test_scale_only_in_center_and_knh_roundtrip(solved, tmp_path):
    rest, local, report, _ = solved
    for n, p in BONES:
        s = np.linalg.norm(np.asarray(local[n])[0, :3])
        if n == dp.CENTER:
            assert s == pytest.approx(report["scale"], rel=1e-6)
        elif p is not None:
            assert s == pytest.approx(1.0, abs=1e-5), n      # 拡大率は RIG_Center だけが持つ
    out = tmp_path / "driver_base_pos.knh"
    knh.write(dp.to_knh(local), out)
    nodes = {k.name: k for k in knh.walk(knh.read(out))}
    assert set(nodes) == {n for n, _ in BONES}
    for n, _ in BONES:
        assert np.allclose(np.array(nodes[n].matrix).reshape(4, 4), local[n], atol=1e-6)


def test_cli(solved, tmp_path):
    _, _, _, kn5 = solved
    out = tmp_path / "x" / "driver_base_pos.knh"
    r = subprocess.run([sys.executable, str(ROOT / "tools/driver_pose.py"), "--kn5", str(kn5), "--cockpit",
                        str(ROOT / "design/driver/cockpit.json"), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert len(list(knh.walk(knh.read(out)))) == len(BONES)


def test_cockpit_json_shape():
    for k in ("eye", "wheel_center", "wheel_axis", "seat_point", "pedal_accel", "pedal_brake"):
        assert len(COCKPIT[k]) == 3
    assert COCKPIT["eye"] == [-0.642, 1.985, 3.407]
    c, e, n = np.array(COCKPIT["wheel_center"]), np.array(COCKPIT["eye"]), np.array(COCKPIT["wheel_axis"])
    assert np.linalg.norm(n) == pytest.approx(1.0, abs=1e-3)
    assert np.dot(n, c - e) > 0                      # 運転手から遠ざかる向き
    assert 0.15 < COCKPIT["rim_radius"] < 0.30
    assert COCKPIT["pedal_accel"][0] < COCKPIT["pedal_brake"][0]   # 右（kn5 の -x 側）がアクセル
    assert COCKPIT["notes"]
