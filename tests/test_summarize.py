import math
import pytest
import summarize

HEADER = "t,x,y,z,kmh,rpm,gear,roll,pitch\n"


def write(tmp_path, rows):
    p = tmp_path / "log.csv"
    p.write_text(HEADER + "".join(",".join(f"{v:.4f}" for v in r) + "\n" for r in rows))
    return p


R_FRONT = 8.3                                       # 仕様: 外側前輪の旋回半径
WB, TRACK_F, D_REAR = 5.3, 2.065, 0.4 * 5.3
RR = math.sqrt(R_FRONT ** 2 - WB ** 2) - TRACK_F / 2
R_CG = math.sqrt(RR ** 2 + D_REAR ** 2)             # このとき CG の軌跡の半径


def circle_rows(v_kmh=10.0, still=2.0, accel=3.0, turn=12.0):
    """静止 → 直線で加速（操舵前の過渡）→ 定常旋回。CG の半径は R_CG。"""
    v = v_kmh / 3.6
    rows, t, x, z = [], 0.0, 0.0, 0.0
    for i in range(int((still + accel + turn) * 10)):
        t = i * 0.1
        if t < still:
            rows.append((t, 0.0, 0.0, 0.0, 0.0, 800, 0, 0.0, 0.0)); continue
        if t < still + accel:
            sp = v * (t - still) / accel
            z += sp * 0.1
            rows.append((t, 0.0, 0.0, z, sp * 3.6, 1500, 1, 0.0, 0.0)); continue
        if t < still + accel + 0.05:
            a0 = 0.0; z0 = z
        a = v * (t - still - accel) / R_CG
        # 進行方向 +z から +x 側へ曲がる円（中心は x = +R_CG）
        rows.append((t, R_CG * (1 - math.cos(a)), 0.0, z0 + R_CG * math.sin(a), v * 3.6, 1500, 1, 0.0, 0.0))
    return rows


def test_turn_radius_converted(tmp_path):
    s = summarize.summarize(write(tmp_path, circle_rows()))
    assert s["turn_radius_cg_m"] == pytest.approx(R_CG, abs=0.05)
    assert s["turn_radius_outer_front_m"] == pytest.approx(R_FRONT, abs=0.05)
    v = 10 / 3.6
    assert s["max_lat_g"] == pytest.approx(v * v / R_CG / 9.81, abs=0.015)


def test_turn_radius_none_when_not_steady(tmp_path):
    rows = [(i * 0.1, 0.0, 0.0, i * 0.1 * 5, 18.0, 1500, 1, 0.0, 0.0) for i in range(200)]   # 直進
    s = summarize.summarize(write(tmp_path, rows))
    assert s["turn_radius_cg_m"] is None and s["turn_radius_outer_front_m"] is None
    assert s["max_lat_g"] < 0.02


def test_robust_parsing(tmp_path):
    p = tmp_path / "log.csv"
    p.write_text(HEADER + "err,attempt to index a nil value\n" + "1,2,3\n" + "0.0,0,0,0,0,800,0,0,0\n"
                 + "0.1,0,0,0,0,800,0,0,0\nerr,x\n" + "0.2,0,0,0,0,800,0,0,0\n")
    s = summarize.summarize(p)
    assert s["reason"] is None and s["vmax"] == 0.0
    p.write_text(HEADER)
    s = summarize.summarize(p)
    assert s["reason"] and s["vmax"] is None and s["settle_s"] is None
    p.write_text("")
    assert summarize.summarize(p)["reason"]


def test_lat_g_ignores_spawn_jump(tmp_path):
    rows = []
    for i in range(200):
        t = i * 0.1
        z = 0.0 if t < 5 else (t - 5) * 5.0
        x = 0.0
        v = 0.0 if t < 5 else 18.0
        if t >= 5.5:
            x = 3.0                              # 動き出して 0.5 秒後の位置の飛び（出現の名残り）
        rows.append((t, x, 0.0, z, v, 1500, 1, 0.0, 0.0))
    s = summarize.summarize(write(tmp_path, rows))
    assert s["max_lat_g"] < 0.05


def test_lat_g_and_circle_ignore_teleport_while_driving(tmp_path):
    # 36 km/h で +z へ直進中に t=10 s で 430 m 横へ飛び、その後も直進する（実走の drive_yabitsu の飛びと同じ型）
    rows, x, z = [], 0.0, 0.0
    for i in range(200):
        t = i * 0.1
        if t < 3:
            rows.append((t, 0.0, 0.0, 0.0, 0.0, 800, 0, 0.0, 0.0)); continue
        z += 1.0
        if abs(t - 10.0) < 1e-6:
            x += 430.0
        rows.append((t, x, 0.0, z, 36.0, 1500, 1, 0.0, 0.0))
    s = summarize.summarize(write(tmp_path, rows))
    assert s["max_lat_g"] < 0.05
    assert s["turn_radius_cg_m"] is None


def test_jump_detection_does_not_cut_a_real_circle(tmp_path):
    s = summarize.summarize(write(tmp_path, circle_rows()))
    assert s["turn_radius_cg_m"] == pytest.approx(R_CG, rel=0.02)


def test_settle_from_physics_start(tmp_path):
    rows = []
    for i in range(60):
        t = i * 0.1
        if t < 0.5:        # 物理が始まる前: 位置が飛び、ロールも暴れている
            rows.append((t, 100.0 * i, 0.0, 0.0, 0.0, 0, 0, 5.0 * (i % 2), 3.0))
        else:              # 0.5 秒で物理開始。1.0 秒かけて 1° から 0° へ
            rows.append((t, 0.0, 0.0, 0.0, 0.0, 800, 0, max(0.0, 1.0 - (t - 0.5)), 0.0))
    s = summarize.summarize(write(tmp_path, rows))
    assert s["settle_s"] == pytest.approx(1.0, abs=0.1)


def test_t_0_40_linear(tmp_path):
    rows = []
    for i in range(300):
        t = i * 0.1
        v = 0.0 if t < 5 else min(40.0, 4.0 * (t - 5))   # 5 秒静止、その後 10 秒で 40 km/h
        rows.append((t, 0.0, 0.0, 0.0, v, 800 + 50 * v, 1, 0.0, 0.0))
    s = summarize.summarize(write(tmp_path, rows))
    assert s["t_0_40"] == pytest.approx(10.0, abs=0.1)
    assert s["vmax"] == pytest.approx(40.0)
    assert s["max_rpm"] == pytest.approx(800 + 50 * 40)
    assert s["turn_radius_cg_m"] is None          # 直線なので円ではない
    assert s["flipped"] is False


def test_settle(tmp_path):
    rows = []
    for i in range(100):
        t = i * 0.1
        roll = max(0.0, 1.0 - t)    # 1.0 秒かけて 1° から 0° へ、あとは一定
        rows.append((t, 0.0, 0.0, 0.0, 0.0, 800, 0, roll, 0.0))
    s = summarize.summarize(write(tmp_path, rows))
    assert s["settle_s"] == pytest.approx(1.0, abs=0.1)
    assert s["t_0_40"] is None
    assert s["max_roll_deg"] == pytest.approx(1.0)


def test_flipped(tmp_path):
    rows = [(i * 0.1, 0, 0, 0, 0, 800, 0, -60.0 if i > 5 else 0.0, 0.0) for i in range(20)]
    s = summarize.summarize(write(tmp_path, rows))
    assert s["flipped"] is True
    assert s["max_roll_deg"] == pytest.approx(60.0)


def ext_csv(tmp_path, gear, kmh, rpm, rear, brake=0.0, clutch=0.0, n=40):
    cols = summarize.KEYS + summarize.EXT
    lines = [",".join(cols)]
    for i in range(n):
        vals = {k: 0.0 for k in cols}
        vals.update(t=i * 0.1, z=i * 0.5, kmh=kmh, rpm=rpm, gear=gear, brake=brake, clutch=clutch, w2_kmh=rear, w3_kmh=rear)
        lines.append(",".join(str(vals[k]) for k in cols))
    p = tmp_path / "ext.csv"
    p.write_text("\n".join(lines) + "\n")
    return p


GEARS = {1: 3.486, 2: 1.864, 3: 1.409, 4: 1.0, 5: 0.749, 6: 0.652}


def diag(p):
    return summarize.drivetrain_diagnosis(p, GEARS, 6.5, 0.47825)[2]


def test_diag_clutch_slip(tmp_path):
    o = diag(ext_csv(tmp_path, 2, 18.0, 2540, rear=18.0))      # 回転だけ速く、車輪は車速どおり
    assert o["verdict"] == "clutch slip" and o["implied_over_car"] > 1.5 and abs(o["rear_minus_car_kmh"]) < 0.1


def test_diag_wheel_spin(tmp_path):
    o = diag(ext_csv(tmp_path, 2, 18.0, 1340, rear=30.0))
    assert o["verdict"] == "wheel spin" and o["rear_minus_car_kmh"] == pytest.approx(12.0)


def test_diag_brake_and_coupled(tmp_path):
    assert diag(ext_csv(tmp_path, 2, 18.0, 1340, rear=18.0, brake=1.0))["verdict"] == "brake"
    o = diag(ext_csv(tmp_path, 2, 18.0, 1209, rear=18.0))
    assert o["verdict"] == "coupled" and o["implied_over_car"] == pytest.approx(1.0, abs=0.03)


def test_diag_old_format_is_none(tmp_path):
    assert summarize.drivetrain_diagnosis(write(tmp_path, circle_rows())) is None


def test_extended_csv_still_summarizes(tmp_path):
    s = summarize.summarize(ext_csv(tmp_path, 2, 18.0, 1340, rear=18.0))
    assert s["reason"] is None and s["vmax"] == 18.0


def test_circle_with_straight_phase_uses_full_lock_only(tmp_path):
    """直進加速 → 減速 → フルロックの円（probe の circle モードの形）。steer_deg 列で円の区間だけを使う。"""
    cols = summarize.KEYS + summarize.EXT
    lines = [",".join(cols)]
    def add(t, x, z, kmh, steer):
        v = {k: 0.0 for k in cols}
        v.update(t=t, x=x, z=z, kmh=kmh, rpm=1500, gear=1, steer_deg=steer)
        lines.append(",".join(f"{v[k]:.4f}" for k in cols))
    z, t = 0.0, 0.0
    for i in range(20):                                   # 静止
        add(t, 0.0, 0.0, 0.0, 0.0); t += 0.1
    for i in range(150):                                  # 直進で 0 → 45 km/h
        kmh = 45.0 * i / 150
        z += kmh / 3.6 * 0.1; add(t, 0.0, z, kmh, 0.0); t += 0.1
    for i in range(100):                                  # 45 → 12 km/h に減速、まだ直進
        kmh = 45.0 - 33.0 * i / 100
        z += kmh / 3.6 * 0.1; add(t, 0.0, z, kmh, 0.0); t += 0.1
    v = 12.0 / 3.6
    for i in range(150):                                  # フルロックで定常旋回（15 秒）
        a = v * (i * 0.1) / R_CG
        add(t, R_CG * (1 - math.cos(a)), z + R_CG * math.sin(a), 12.0, 450.0); t += 0.1
    p = tmp_path / "circle.csv"
    p.write_text("\n".join(lines) + "\n")
    s = summarize.summarize(p)
    assert s["turn_radius_cg_m"] == pytest.approx(R_CG, abs=0.1)
    assert s["turn_radius_outer_front_m"] == pytest.approx(R_FRONT, abs=0.1)


def test_powershell_scripts_are_ascii():
    """Windows PowerShell 5.1 は BOM の無い .ps1 を CP932 で読む。日本語のコメントが化けて次の行を食い、
    launch.ps1 の待ち合わせの while が消えた（2026-11-26 の試走 20261126_104406）。.ps1 は ASCII だけにする。"""
    from pathlib import Path
    for p in (Path(__file__).resolve().parents[1] / "tools" / "ac").glob("*.ps1"):
        bad = [i + 1 for i, line in enumerate(p.read_bytes().splitlines()) if any(b >= 128 for b in line)]
        assert not bad, f"{p.name}: non-ASCII on lines {bad}"
