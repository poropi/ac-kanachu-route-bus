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


REAL_BLEND = ROOT / "design/driver/kanachu_driver.blend"


def _export(tmp, blend):
    kn5 = tmp / (blend.stem + ".kn5")
    subprocess.run([paths.BLENDER, "-b", str(blend), "--python", str(ROOT / "tools/driver_to_kn5.py"), "--", "--out", str(kn5)],
                   capture_output=True, text=True)
    assert kn5.exists()
    return kn5


@pytest.fixture(scope="module", params=["fixture", "real"])
def solved(request, tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pose")
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
    report = {}
    local = dp.solve_seated(rest, COCKPIT, report=report)
    return rest, local, report, kn5


def dist_to_rim_circle(p):
    """点 p とリムの管の中心線（円）の距離。"""
    c, n, r = np.array(COCKPIT["wheel_center"]), np.array(COCKPIT["wheel_axis"]), COCKPIT["rim_radius"]
    d = p - c
    off = float(np.dot(d, n))
    return float(np.hypot(np.linalg.norm(d - off * n) - r, off))


def test_seated_pose_constraints(solved):
    rest, local, report, _ = solved
    W = dp.fk(local)
    # 拡大なし: どの行列も 3x3 が直交（行列式 +1）
    for n, m in local.items():
        R = np.asarray(m)[:3, :3]
        assert np.allclose(R @ R.T, np.eye(3), atol=1e-4), n
        assert np.linalg.det(R) == pytest.approx(1.0, abs=1e-4), n
    # 腰: 座面の範囲（前後 ±0.24、左右も座面の中）で、座面の上 0.05〜0.20
    hips = W["DRIVER:RIG_Hips"][3, :3]
    seat = np.array(COCKPIT["seat_point"])
    assert 0.05 <= hips[1] - seat[1] <= 0.20
    assert abs(hips[2] - seat[2]) <= 0.24 + 1e-6 and abs(hips[0] - seat[0]) <= 0.25
    lean = dp.torso_lean_deg(W)
    assert lean <= 20.0, lean
    bends = dp.elbow_bends(W)
    assert min(bends.values()) >= 15.0, bends
    head = W["DRIVER:RIG_Head"][3, :3]
    assert head[1] < COCKPIT["eye"][1]
    palms = {a: dp.palm_center(W, a) for a in "LR"}
    hands = {a: dist_to_rim_circle(palms[a]) for a in "LR"}
    assert max(hands.values()) <= 0.02, hands
    assert 60.0 <= report["grip_deg"] <= 100.0
    assert np.linalg.norm(palms["L"] - palms["R"]) > 0.15      # 両手が同じ点に重ならない
    print("握り角 %.0f 度、前傾（腰から首）%.1f 度（解の前傾 %.0f 度）、腰の前後のずれ %+.2f m、肘の曲げ L %.1f R %.1f 度、"
          "手のひら-リム L %.4f R %.4f m、頭の高さ %.3f（目 %.3f）"
          % (report["grip_deg"], lean, report["lean_deg"], report["pelvis_slide_m"], bends["L"], bends["R"],
             hands["L"], hands["R"], head[1], COCKPIT["eye"][1]))


def test_knee_outside_column_and_feet_on_pedals(solved):
    _, local, _, _ = solved
    W = dp.fk(local)
    box = COCKPIT["column_box"]
    lo, hi = np.array(box["min"]), np.array(box["max"])
    ped = {"accel": np.array(COCKPIT["pedal_accel"]), "brake": np.array(COCKPIT["pedal_brake"])}
    hit = set()
    for a in "LR":
        knee = W["DRIVER:RIG_Shin_" + a][3, :3]
        assert not (np.all(knee >= lo) and np.all(knee <= hi)), (a, knee)
        ball = W["DRIVER:RIG_Foot_" + a][3, :3]
        name, d = min(((k, np.linalg.norm(ball - v)) for k, v in ped.items()), key=lambda kv: kv[1])
        assert d <= 0.02, (a, name, d)
        hit.add(name)
    assert hit == {"accel", "brake"}


def test_knh_roundtrip(solved, tmp_path):
    _, local, _, _ = solved
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
