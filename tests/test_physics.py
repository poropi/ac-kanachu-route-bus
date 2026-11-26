import math
from pathlib import Path
import pytest
import physics, spec


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    names = physics.build(out)
    return out, names


def ini(data, name):
    return physics.read_ini(data[0] / name, strict=True)


def test_core_values(data):
    car = ini(data, "car.ini")
    assert float(car["BASIC"]["TOTALMASS"]) == 9865
    s = ini(data, "suspensions.ini")
    assert float(s["BASIC"]["WHEELBASE"]) == 5.3
    assert float(s["FRONT"]["TRACK"]) == 2.065 and float(s["REAR"]["TRACK"]) == 1.82
    assert float(s["BASIC"]["CG_LOCATION"]) == 0.40
    t = ini(data, "tyres.ini")
    assert float(t["FRONT"]["RADIUS"]) == 0.478 and float(t["REAR"]["WIDTH"]) == 0.6
    assert float(t["FRONT"]["RIM_RADIUS"]) == 0.298 and float(t["FRONT"]["WIDTH"]) == 0.275
    assert float(t["FRONT"]["DY0"]) == float(t["FRONT"]["DY_REF"]) == 0.72 and float(t["FRONT"]["DX0"]) == 0.90
    d = ini(data, "drivetrain.ini")
    g = d["GEARS"]
    assert [float(g["GEAR_%d" % i]) for i in range(1, 7)] == [3.486, 1.864, 1.409, 1.0, 0.749, 0.652]
    assert int(g["COUNT"]) == 6
    assert float(g["FINAL"]) == 6.5 and float(g["GEAR_R"]) == -5.027
    assert d["TRACTION"]["TYPE"] == "RWD"
    assert d["AUTOCLUTCH"]["FORCED_ON"] == "1"
    assert (float(d["AUTOCLUTCH"]["MIN_RPM"]), float(d["AUTOCLUTCH"]["MAX_RPM"])) == (700, 1200)
    e = ini(data, "engine.ini")
    assert float(e["ENGINE_DATA"]["LIMITER"]) == 2550 and float(e["ENGINE_DATA"]["MINIMUM"]) == 600
    assert float(e["ENGINE_DATA"]["INERTIA"]) == 1.2
    c = ini(data, "car.ini")["CONTROLS"]
    assert float(c["STEER_LOCK"]) == 900
    assert float(c["STEER_RATIO"]) == pytest.approx(-900 / 39.68, abs=0.01)


def test_power_curve(data):
    lut = physics.read_lut(data[0] / "power.lut")
    d = dict(lut)
    sp = spec.load()
    f = sp["torque_loss_factor"]
    assert d[1600] == pytest.approx(sp["torque_peak"] * f, abs=1)      # lut は意図的に 773×0.87 を持つ
    assert d[2150] == pytest.approx(sp["power_kw"] * 1000 / (sp["power_rpm"] * 2 * math.pi / 60) * f, abs=1)
    assert d[600] == pytest.approx(sp["torque_idle"] * f, abs=0.1)
    assert d[1000] == pytest.approx(sp["torque_1000rpm"] * f, abs=0.1)
    assert min(d) == 600 and max(d) == 2500  # limiter 2550 だが lut は 100 rpm 刻みで 2500 まで（要確認: 2500〜2550 の扱い）
    assert [r for r, _ in lut] == sorted(r for r, _ in lut)
    # 1000-1600 は線形に上がる
    sl = [(d[r + 100] - d[r]) for r in range(1000, 1600, 100)]
    assert max(sl) - min(sl) < 0.5 and min(sl) > 0
    power = {r: v * r * 2 * math.pi / 60 for r, v in lut}
    rpm_max = max(power, key=power.get)
    assert 2000 <= rpm_max <= 2300


def test_static_deflection(data):
    car = ini(data, "car.ini"); s = ini(data, "suspensions.ini"); t = ini(data, "tyres.ini")
    total = float(car["BASIC"]["TOTALMASS"]); cg = float(s["BASIC"]["CG_LOCATION"])
    for sec, share, tsec in (("FRONT", cg, "FRONT"), ("REAR", 1 - cg, "REAR")):
        S = s[sec]
        m = total * share / 2 - float(S["HUB_MASS"])
        k = float(S["SPRING_RATE"])
        defl = m * 9.81 / k
        assert defl == pytest.approx(0.173, abs=0.01)
        assert math.sqrt(k / m) / (2 * math.pi) == pytest.approx(1.2, abs=0.02)
        # 静止時の輪荷重 = FZ0
        T = t[tsec]
        assert float(T["FZ0"]) == pytest.approx(total * share / 2 * 9.81, rel=1e-3)
        # 静止時の最低地上高: 車体底面(PICKUP_*_HEIGHT) − 接地点
        r_loaded = float(T["RADIUS"]) - float(T["FZ0"]) / float(T["RATE"])
        wheel_y = float(S["BASEY"]) - (float(S["ROD_LENGTH"]) - defl)
        ground = wheel_y - r_loaded
        pick = float(car["RIDE"]["PICKUP_%s_HEIGHT" % sec])
        assert pick - ground == pytest.approx(0.130, abs=0.02)
        assert float(S["BUMPSTOP_UP"]) >= 0.08
        assert float(S["BUMPSTOP_DN"]) > 0
    # GRAPHICS_OFFSET: kn5 原点(地面) → 物理原点。底面は kn5 の高さ 0.130
    go = [float(x) for x in car["BASIC"]["GRAPHICS_OFFSET"].split(",")]
    assert go[1] + 0.130 == pytest.approx(float(car["RIDE"]["PICKUP_FRONT_HEIGHT"]), abs=1e-6)
    # 前軸の物理 z = (1-CG)*WB = kn5 z(2.65) + GO_z
    assert go[2] + 2.65 == pytest.approx((1 - cg) * 5.3, abs=1e-6)


def test_damping(data):
    s = ini(data, "suspensions.ini"); car = ini(data, "car.ini")
    cg = float(s["BASIC"]["CG_LOCATION"]); total = float(car["BASIC"]["TOTALMASS"])
    for sec, share in (("FRONT", cg), ("REAR", 1 - cg)):
        S = s[sec]; m = total * share / 2 - float(S["HUB_MASS"]); k = float(S["SPRING_RATE"])
        assert float(S["DAMP_BUMP"]) == pytest.approx(2 * 0.3 * math.sqrt(k * m), rel=0.01)
        assert float(S["DAMP_REBOUND"]) == pytest.approx(2 * 0.45 * math.sqrt(k * m), rel=0.01)


def test_brakes(data):
    b = ini(data, "brakes.ini")["DATA"]
    # AC は FRONT_SHARE で前後を分け、輪あたり MAX_TORQUE×share(前)/(1-share)(後) = 合計 2×MAX_TORQUE
    total = 2 * float(b["MAX_TORQUE"])
    assert total == pytest.approx(9865 * 9.81 * 0.8 * 0.478, rel=0.01)
    assert float(b["FRONT_SHARE"]) == 0.55


def test_aero(data):
    w = ini(data, "aero.ini")["WING_0"]
    assert float(w["CHORD"]) * float(w["SPAN"]) == pytest.approx(2.485 * (3.105 - 0.130), abs=0.01)
    cd = dict(physics.read_lut(data[0] / w["LUT_AOA_CD"]))
    assert cd[0] * float(w["CD_GAIN"]) == pytest.approx(0.6)


def test_shifter_window(data):
    d = ini(data, "drivetrain.ini"); e = ini(data, "engine.ini")
    up = float(d["AUTO_SHIFTER"]["UP"]); dn = float(d["AUTO_SHIFTER"]["DOWN"])
    assert (up, dn) == (2300, 1200)
    assert 600 < dn < up < float(e["ENGINE_DATA"]["LIMITER"])


def test_required(data):
    names = data[1]
    for n in ("car.ini suspensions.ini tyres.ini drivetrain.ini engine.ini power.lut brakes.ini aero.ini "
              "electronics.ini damage.ini setup.ini lods.ini colliders.ini cameras.ini dash_cam.ini mirrors.ini "
              "lights.ini sounds.ini ambient_shadows.ini ai.ini fuel_cons.ini").split():
        assert n in names and (data[0] / n).is_file()
    assert ini(data, "lods.ini")["LOD_0"]["FILE"] == "kanachu_route_bus.kn5"
    assert "LOD_1" not in ini(data, "lods.ini")


def test_all_files_parse(data):
    out, names = data
    for n in names:
        p = out / n
        if n.endswith(".ini"):
            physics.read_ini(p, strict=True)        # 重複キー・重複セクションは ValueError
        elif n.endswith(".lut"):
            assert physics.read_lut(p)
    t = physics.read_ini(out / "tyres.ini")
    for sec in ("FRONT", "REAR"):
        assert (out / t[sec]["WEAR_CURVE"]).is_file()
    for sec in ("THERMAL_FRONT", "THERMAL_REAR"):
        assert (out / t[sec]["PERFORMANCE_CURVE"]).is_file()
    assert (out / physics.read_ini(out / "engine.ini")["HEADER"]["POWER_CURVE"]).is_file()


def test_read_ini_strips_comments_and_detects_dups(tmp_path):
    p = tmp_path / "a.ini"
    p.write_text("[A]\nX=1 ; c\n;full\nY = a=b\n[B]\nX=2\n")
    assert physics.read_ini(p) == {"A": {"X": "1", "Y": "a=b"}, "B": {"X": "2"}}
    p.write_text("[A]\nX=1\nX=2\n")
    with pytest.raises(ValueError):
        physics.read_ini(p, strict=True)
    assert physics.read_ini(p)["A"]["X"] == "2"


DWB_KEYS = ("WBCAR_TOP_FRONT WBCAR_TOP_REAR WBCAR_BOTTOM_FRONT WBCAR_BOTTOM_REAR WBTYRE_TOP WBTYRE_BOTTOM "
            "WBCAR_STEER WBTYRE_STEER STRUT_CAR STRUT_TYRE").split()


def test_front_dwb_default(data):
    f = ini(data, "suspensions.ini")["FRONT"]
    assert f["TYPE"] == "DWB"
    for k in DWB_KEYS:
        assert k in f, k
    s = spec.load()
    g = physics.front_dwb_points(s, 0.478)
    import math as m
    for arm in (g["arm_low"], g["arm_up"]):
        assert m.degrees(m.asin(max(s["bumpstop_up"], s["bumpstop_dn"]) / arm)) < 25
    assert g["xl"] < s["track_f"] / 2 and g["yu"] > g["yl"]


def test_front_axle_switch(tmp_path, monkeypatch):
    real = spec.load
    monkeypatch.setattr(spec, "load", lambda: {**real(), "front_susp_type": "AXLE"})
    physics.build(tmp_path)
    f = physics.read_ini(tmp_path / "suspensions.ini", strict=True)["FRONT"]
    assert f["TYPE"] == "AXLE" and "WBCAR_TOP_FRONT" not in f and "SPRING_RATE" in f


def test_sounds_backfire_keys(data):
    """AC が KEY_NOT_FOUND: [BACKFIRE] MAXGAS/MINRPM/MAXRPM/TRIGGERGAS をログに出す。ディーゼルなので実質オフ。"""
    b = ini(data, "sounds.ini")["BACKFIRE"]
    assert float(b["MAXGAS"]) == 0.0
    assert float(b["MINRPM"]) == 1800
    assert float(b["MAXRPM"]) == 2600
    assert float(b["TRIGGERGAS"]) == 0.8


def test_rolling_resistance_not_load_scaled(data):
    sp = spec.load(); t = ini(data, "tyres.ini")
    for sec in ("FRONT", "REAR"):
        T = t[sec]
        assert float(T["ROLLING_RESISTANCE_0"]) == sp["rr0"]
        assert float(T["ROLLING_RESISTANCE_1"]) == sp["rr1"]
        assert float(T["ROLLING_RESISTANCE_SLIP"]) == sp["rr_slip"]
        # AC が荷重で内部スケールするので、荷重倍した値を入れない（再発防止）
        assert float(T["ROLLING_RESISTANCE_0"]) <= 20
        assert float(T["ROLLING_RESISTANCE_1"]) <= 0.002
        assert float(T["ROLLING_RESISTANCE_SLIP"]) <= 6000


def test_linear_steer_rod_ratio(data):
    s = spec.load(); delta = spec.derived(s)["steer_angle_deg"]
    lin = float(ini(data, "car.ini")["CONTROLS"]["LINEAR_STEER_ROD_RATIO"])
    arm = physics.front_dwb_points(s, 0.478)["steer_arm"]
    f = ini(data, "suspensions.ini")["FRONT"]
    assert abs(float(f["WBTYRE_STEER"].split(",")[2])) == arm
    gain = s["steer_rod_gain"]
    travel = delta * lin
    assert travel < arm                                   # asin の引数 < 1（てこ腕が 90° を超えない）
    assert lin == pytest.approx(arm * math.sin(math.radians(delta)) / delta * gain, rel=1e-3)
    # ゲインはアッカーマンで外輪が目標より小さく切れる分の補正: ゲイン込みの目標角に asin が一致
    assert math.degrees(math.asin(travel / arm)) == pytest.approx(
        math.degrees(math.asin(math.sin(math.radians(delta)) * gain)), abs=0.1)
    assert gain == pytest.approx(1.097, abs=0.005)
    assert s["torque_loss_factor"] == 0.80


def test_analog_instruments(data):
    a = ini(data, "analog_instruments.ini")
    sp, rp = a["SPEED_INDICATOR"], a["RPM_INDICATOR"]
    assert sp["OBJECT_NAME"] == "ARROW_SPEED" and rp["OBJECT_NAME"] == "ARROW_RPM"
    assert float(sp["ZERO"]) == 0 and float(rp["ZERO"]) == 0
    # 内装の報告の振れ角（時計回り）: 速度 208 deg (160 km/h)、回転 171 deg (4000 rpm)。HT81S と同じく STEP は正
    assert float(sp["STEP"]) == pytest.approx(1.3) and float(rp["STEP"]) == pytest.approx(0.04275)
    assert float(sp["STEP"]) * 160 == pytest.approx(208, abs=1e-3)
    assert float(rp["STEP"]) * 4000 == pytest.approx(171, abs=1e-3)


def test_driver_eyes_from_interior_driver_eye(data):
    # DRIVER_EYE は Blender (0.642, 3.407, 1.985) -> kn5 (-bx, bz, by)。DRIVEREYES は kn5 座標（GRAPHICS_OFFSET は足さない）
    eyes = [float(x) for x in ini(data, "car.ini")["GRAPHICS"]["DRIVEREYES"].split(",")]
    assert eyes == pytest.approx([-0.642, 1.985, 3.407], abs=1e-6)
    dash = [float(x) for x in ini(data, "dash_cam.ini")["DASH_CAM"]["POS"].split(",")]
    assert dash == pytest.approx([-0.642, 1.985, 3.407 + 0.04], abs=1e-6)


def test_onboard_pitch(data):
    g = ini(data, "car.ini")["GRAPHICS"]
    assert float(g["ON_BOARD_PITCH_ANGLE"]) == spec.load()["onboard_pitch_deg"] == -9


def test_rear_chase_cameras_clear_of_the_body(data):
    """F1 の追従カメラは全車共通で、バスでは後面の直前に来る。代わりの F6 カメラ 2 台が後端より 7 m 以上後ろ・屋根より上から前を向くこと。"""
    s = spec.load(); d = physics.derived(s) if hasattr(physics, "derived") else None
    cams = ini(data, "cameras.ini")
    pos = [[float(v) for v in c["POSITION"].split(",")] for c in cams.values()]
    fwd = [[float(v) for v in c["FORWARD"].split(",")] for c in cams.values()]
    assert len(cams) == 6                    # AC は F6 を 6 台までしか読まない
    zroof = pos[5][2]                        # 5 番（屋根の後ろ寄りから後ろ）は車体の上にある
    rear = [(p, f) for p, f in zip(pos, fwd) if p[2] < zroof - 7]
    assert len(rear) == 2
    for p, f in rear:
        assert p[1] > s["height"] and f[2] > 0.8 and f[1] < 0   # 屋根より上から、前・やや下を見る
