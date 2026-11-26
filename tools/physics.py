#!/usr/bin/env python3
"""物理 ini 一式（data/）を tools/spec.json の諸元から生成する。

書式（セクション・キーの並び）は ZC32S 側の HT81S 展開済み data に合わせた。値は spec からだけ取る。
タイヤの lut（荷重特性・温度特性）の形だけ HT81S のものを写している。

使い方: python3 tools/physics.py --out build/data
"""
import argparse
import math
from pathlib import Path

import kn5_mirrors
import lights
import spec as _spec

G = 9.81
CAR_KN5 = "kanachu_route_bus.kn5"

# HT81S の street_front/rear.lut（摩耗特性）・tcurve_street.lut（温度特性）の形
WEAR_LUT = [(0, 100), (0.25, 100), (0.5, 100), (0.75, 100), (1.25, 99.5), (2.5, 99), (3.75, 98.5),
            (10, 98), (25, 95), (35, 90), (50, 80)]
TCURVE_LUT = [(0, 0.80), (20, 0.97), (40, 0.98), (60, 0.995), (75, 1.0), (85, 1.0), (100, 0.98),
              (110, 0.97), (140, 0.97), (160, 0.95), (220, 0.90), (250, 0.60)]
# HT81S wing_body_AOA_CD.lut（CD=0.36 @0°）を CD 0.6 に拡大。端の 1 はそのまま
_BODY_CD_HT81S = [(-10, 1), (-2, 0.368), (0, 0.36), (2, 0.362), (5, 0.364), (8, 0.368), (10, 0.38),
                  (12, 0.382), (14, 0.39), (16, 0.40), (20, 0.42), (24, 0.46), (26, 0.48), (30, 1)]


# ---------------------------------------------------------------- 読み書き
def read_ini(path, strict=False):
    """ini を dict[section][key] -> str で返す。`;` 以降は注釈。ASCII 以外・`[` で始まらない行頭の飾りは無視。
    strict=True なら重複セクション・重複キーで ValueError。"""
    out, cur = {}, None
    for n, raw in enumerate(Path(path).read_text(encoding="utf8").splitlines(), 1):
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = line[1:-1].strip()
            if cur in out and strict:
                raise ValueError("%s:%d duplicate section [%s]" % (path, n, cur))
            out.setdefault(cur, {})
        elif "=" in line and cur is not None:
            k, v = line.split("=", 1)
            k = k.strip()
            if k in out[cur] and strict:
                raise ValueError("%s:%d duplicate key [%s] %s" % (path, n, cur, k))
            out[cur][k] = v.strip()
    return out


def read_lut(path):
    """lut を [(x, y), ...] で返す（`;` 注釈と空行を無視）。"""
    pts = []
    for raw in Path(path).read_text(encoding="utf8").splitlines():
        line = raw.split(";", 1)[0].strip()
        if "|" in line:
            a, b = line.split("|", 1)
            pts.append((float(a), float(b)))
    return pts


def _f(v, nd=6):
    """数を短く書く（整数なら整数、それ以外は有効 6 桁）。"""
    if isinstance(v, str):
        return v
    if isinstance(v, int) or float(v) == int(v) and abs(v) < 1e12:
        return str(int(v))
    s = ("%.*g" % (nd, v))
    return s


def _vec(*xs):
    return ",".join(_f(round(x, 5)) for x in xs)


def _ini(sections):
    """[(name, [(key, value), ...]), ...] -> 本文。"""
    parts = []
    for name, kvs in sections:
        parts.append("[%s]\n" % name + "".join("%s=%s\n" % (k, _f(v)) for k, v in kvs))
    return "\n".join(parts)


def _lut(pts, crlf=False):
    nl = "\r\n" if crlf else "\n"
    return "".join("%s|%s%s" % (_f(x), _f(y), nl) for x, y in pts)


# ---------------------------------------------------------------- 計算
def _radius(s):
    """タイヤ半径 0.478（kn5 の WHEEL ノードの高さ。外径 0.9565 の半分 0.47825 を mm に丸める）。"""
    return round(_spec.derived(s)["tyre_radius"], 3)


def _axle(s):
    """前後軸それぞれの質量・ばね・減衰・タイヤ荷重と車高の値を計算する。"""
    total = s["mass_vehicle"] + s["driver_mass"]
    k = (2 * math.pi * s["spring_freq_hz"]) ** 2
    out = {}
    for ax, share, hub in (("f", s["cg_front"], s["hub_mass_f"]), ("r", 1 - s["cg_front"], s["hub_mass_r"])):
        wheel_mass = total * share / 2                  # 輪あたりの質量（ハブ込み）
        sprung = wheel_mass - hub                       # ばね上質量
        rate = sprung * k
        defl = sprung * G / rate                        # 静的たわみ = g/(2πf)²
        fz0 = wheel_mass * G                            # 静止時の輪荷重
        zb = 2 * s["damp_ratio_bump"] * math.sqrt(rate * sprung)
        zr = 2 * s["damp_ratio_rebound"] * math.sqrt(rate * sprung)
        tyre_rate = fz0 / s["tyre_deflection"]
        out[ax] = dict(wheel_mass=wheel_mass, sprung=sprung, rate=rate, defl=defl, fz0=fz0,
                       bump=zb, rebound=zr, tyre_rate=tyre_rate,
                       r_loaded=_radius(s) - s["tyre_deflection"])
    return total, out


def _geometry(s):
    """物理原点（重心）と kn5 原点（車軸中点の真下の地面）の関係。
    GRAPHICS_OFFSET: 物理ローカル = kn5 + OFFSET。
      y: 重心高さぶん下げる（地面が物理 y = -cg_height）
      z: 前軸の物理 z = (1-CG_LOCATION)×WB（AC の流儀）に kn5 の前軸 z(= WB/2) を合わせる
    BASEY: 静止時の車輪中心（kn5 の高さ = タイヤ半径）の物理 y。
    ROD_LENGTH: 静止で底面が地上 ground_clearance になるよう、静的たわみ＋タイヤのつぶれで決める。
      静止時の車輪中心 y = BASEY − (ROD_LENGTH − 静的たわみ)。"""
    d = _spec.derived(s)
    r = _radius(s)
    go = (0.0, -s["cg_height"], (1 - s["cg_front"]) * s["wheelbase"] - d["axle_z_front"])
    basey = go[1] + r
    return d, r, go, basey


def _analog_ini(s):
    """針のノード ARROW_SPEED / ARROW_RPM を回す設定（HT81S と同じ書式）。
    AC は ZERO（値 MIN_VALUE のときの角度）から、値 1 あたり STEP 度ずつノードのローカル軸まわりに回す。
    針は内装 .blend で 0 の位置に作ってあるので ZERO=0。STEP = 0→最大の時計回りの振れ角(度) / 最大値（正。HT81S と同じ）。ノードのローカル Z は運転手から遠ざかる向き（tools/kn5_axes.py）。"""
    return _ini([
        ("SPEED_INDICATOR", [("ZERO", 0), ("STEP", round(s["speed_needle_deg"] / s["speed_max_kmh"], 6)),
                             ("OBJECT_NAME", "ARROW_SPEED"), ("OBJECT_NAME_MAX", ""), ("MIN_VALUE", 0)]),
        ("RPM_INDICATOR", [("ZERO", 0), ("STEP", round(s["rpm_needle_deg"] / s["rpm_max"], 6)),
                           ("OBJECT_NAME", "ARROW_RPM"), ("OBJECT_NAME_MAX", ""), ("MIN_VALUE", 0)]),
    ])


def make_power_lut(s, factor=None):
    """rpm|N·m。600〜2600 を 100 rpm 刻み（＋2150）。表示値(クランク)の 2 点を通り、駆動損失 factor を掛ける。"""
    t_peak, r_peak = s["torque_peak"], s["torque_rpm"]
    p_w, r_p = s["power_kw"] * 1000, s["power_rpm"]
    t_pow = p_w / (r_p * 2 * math.pi / 60)              # 750.6
    idle, lim = int(s["idle_rpm"]), int(s["limiter_rpm"])
    factor = s["torque_loss_factor"] if factor is None else factor
    t_lo, r_lo = float(s["torque_1000rpm"]), 1000        # 1000 rpm の値（仮定）。idle→1000 も線形
    t_idle = float(s["torque_idle"])

    def torque(r):
        if r <= r_lo:
            return t_idle + (t_lo - t_idle) * (r - idle) / (r_lo - idle)
        if r <= r_peak:
            return t_lo + (t_peak - t_lo) * (r - r_lo) / (r_peak - r_lo)
        if r <= r_p:
            return t_peak + (t_pow - t_peak) * (r - r_peak) / (r_p - r_peak)
        x = (r - r_p) / (lim - r_p)                       # 出力はほぼ保って 10% まで落とす
        p = p_w * (1 - 0.10 * x * x)
        return p / (r * 2 * math.pi / 60)

    rpms = sorted(set(range(idle, lim + 1, 100)) | {int(r_p)})
    return [(r, round(torque(r) * factor, 1)) for r in rpms]


# ---------------------------------------------------------------- 各ファイル
def _car_ini(s, d, go, total, ax):
    pick = go[1] + s["ground_clearance"]                 # 車体底面の物理 y
    ratio = s["steer_lock_deg"] / d["steer_angle_deg"]
    # AC: ロッド変位 = 切れ角(度) × LINEAR、車輪角 = asin(変位 / てこ腕)。最大切れ角 δ で asin が δ になるように決める
    delta = d["steer_angle_deg"]
    linear = round(front_dwb_points(s, _radius(s))["steer_arm"] * math.sin(math.radians(delta)) / delta * s["steer_rod_gain"], 6)   # ハンドル 900° ↔ 外側前輪 39.68°
    L = s["length"]
    return _ini([
        ("HEADER", [("VERSION", "extended-2")]),
        ("INFO", [("SCREEN_NAME", "Kanachu City Bus (Large Non-step)"), ("SHORT_NAME", "Kanachu Bus")]),
        ("BASIC", [("GRAPHICS_OFFSET", _vec(*go)), ("GRAPHICS_PITCH_ROTATION", 0.0),
                   ("TOTALMASS", total), ("INERTIA", _vec(2.3, 2.5, 9.0))]),
        ("GRAPHICS", [("DRIVEREYES", _vec(s["eye_x"], s["eye_y"], s["eye_z"])),
                      ("ONBOARD_EXPOSURE", 22), ("OUTBOARD_EXPOSURE", 31),
                      ("ON_BOARD_PITCH_ANGLE", s["onboard_pitch_deg"]),
                      ("BUMPER_CAMERA_POS", _vec(0, 0.9, d["axle_z_front"] + s["overhang_f"] - 0.2)),
                      ("BONNET_CAMERA_POS", _vec(0, s["height"] - 0.2, d["axle_z_front"] + s["overhang_f"] - 0.6)),
                      ("MIRROR_POSITION", _vec(-0.3, 2.5, s["design_eye_z"] + 1.3)),   # 設計時の目から（2026-11-26 に目を頭の中へ移しても動かさない）
                      ("VIRTUAL_MIRROR_ENABLED", 0), ("USE_ANIMATED_SUSPENSIONS", 0), ("SHAKE_MUL", 1),
                      ("FUEL_LIGHT_MIN_LITERS", 20),
                      ("BONNET_CAMERA_PITCH", -2.0), ("BUMPER_CAMERA_PITCH", -2.0)]),
        ("CONTROLS", [("FFMULT", 1.0), ("STEER_ASSIST", 1.0), ("STEER_LOCK", s["steer_lock_deg"]),
                      ("STEER_RATIO", -round(ratio, 3)), ("LINEAR_STEER_ROD_RATIO", linear)]),
        ("FUEL", [("CONSUMPTION", 0.0045), ("FUEL", round(s["fuel_l"] * 0.75)), ("MAX_FUEL", s["fuel_l"])]),
        ("FUELTANK", [("POSITION", _vec(0, -0.6, -1.5 + go[2]))]),
        ("RIDE", [("PICKUP_FRONT_HEIGHT", round(pick, 5)), ("PICKUP_REAR_HEIGHT", round(pick, 5))]),
        ("RULES", [("MIN_HEIGHT", 0.1)]),
        ("PIT_STOP", [("TYRE_CHANGE_TIME_SEC", 10), ("FUEL_LITER_TIME_SEC", 0.6), ("BODY_REPAIR_TIME_SEC", 20),
                      ("ENGINE_REPAIR_TIME_SEC", 2), ("SUSP_REPAIR_TIME_SEC", 30)]),
    ])


def front_dwb_points(s, r):
    """前輪 DWB のハードポイント（車輪中心からの相対、x は内向き正）をバスの寸法から導く。
    下アーム: 車体側ピボットを車輪中心の内側 0.90×(前トレッド/2) に置く → 腕長 ≈ 0.83 m。
      腕が水平になる静止位置から ±0.2 m 動いても角度 asin(0.2/0.83) ≈ 14° で、幾何は反転しない。
    上アーム: 0.70×(トレッド/2) まで内側（腕長 ≈ 0.65 m、下より短くキャンバーが少し変わる）。
    高さは下アーム −0.25R、上アーム +0.60R（R=タイヤ半径）。ばね(STRUT_*)は車輪側に寄せ、レバー比を約 1 にして
    SPRING_RATE をそのまま輪のばね定数として扱う。"""
    half = s["track_f"] / 2
    xl, xu = round(0.90 * half, 3), round(0.70 * half, 3)
    yl, yu = round(-0.25 * r, 3), round(0.60 * r, 3)
    steer_arm = 0.22                                   # WBTYRE_STEER の |z|（タイロッドのてこ腕）
    return {
        "steer_arm": steer_arm, "xl": xl, "xu": xu, "yl": yl, "yu": yu, "arm_low": xl - 0.10, "arm_up": xu - 0.08,
        "pts": [("WBCAR_TOP_FRONT", _vec(xu, yu, 0.30)), ("WBCAR_TOP_REAR", _vec(xu, yu, -0.30)),
                ("WBCAR_BOTTOM_FRONT", _vec(xl, yl, 0.35)), ("WBCAR_BOTTOM_REAR", _vec(xl, yl, -0.35)),
                ("WBTYRE_TOP", _vec(0.08, yu, 0)), ("WBTYRE_BOTTOM", _vec(0.10, yl, 0)),
                ("WBCAR_STEER", _vec(round(0.6 * xl, 3), -0.05, -0.30)), ("WBTYRE_STEER", _vec(0.10, -0.05, -steer_arm)),
                ("STRUT_CAR", _vec(0.10, 0.50, 0)), ("STRUT_TYRE", _vec(0.10, yl, 0))],
    }


def _front(s, pre_f, tail_f, r):
    """前軸のセクション。spec の front_susp_type が AXLE なら後軸と同じキー構成（[AXLE] は共有）、DWB なら 4 点ウィッシュボーン。"""
    typ = s["front_susp_type"]
    if typ == "AXLE":
        return [("TYPE", "AXLE")] + pre_f + tail_f
    if typ != "DWB":
        raise ValueError("front_susp_type: %r" % typ)
    return [("TYPE", "DWB")] + pre_f[:5] + front_dwb_points(s, r)["pts"] + pre_f[5:] + tail_f


def _suspensions_ini(s, d, go, basey, ax):
    cg = s["cg_front"]
    out = [
        ("HEADER", [("VERSION", 4)]),
        ("_EXTENSION", [("TORQUE_MODE_EX", 2), ("FIX_PROGRESSIVE_RATE", 1)]),
        ("BASIC", [("WHEELBASE", s["wheelbase"]), ("CG_LOCATION", cg)]),
        # ARB は ばね定数の約 0.45 倍（HT81S の比）。バスのロール剛性は M1 では仮
        ("ARB", [("FRONT", round(ax["f"]["rate"] * 0.45, -2)), ("REAR", round(ax["r"]["rate"] * 0.45, -2))]),
    ]

    def common(a, track, hub, toe):
        x = ax[a]
        rod = x["defl"] + (_radius(s) - x["r_loaded"])     # = 静的たわみ + タイヤのつぶれ
        return [("BASEY", round(basey, 5)), ("TRACK", track), ("ROD_LENGTH", round(rod, 5)),
                ("HUB_MASS", hub), ("RIM_OFFSET", 0.0), ("TOE_OUT", toe), ("STATIC_CAMBER", 0.0)], x

    pre_f, xf = common("f", s["track_f"], s["hub_mass_f"], 0.0)
    tail = lambda x: [("SPRING_RATE", round(x["rate"])), ("PROGRESSIVE_SPRING_RATE", 0),
                      ("BUMP_STOP_RATE", 400000), ("BUMPSTOP_UP", s["bumpstop_up"]),
                      ("BUMPSTOP_DN", s["bumpstop_dn"]), ("PACKER_RANGE", 0.2),
                      ("DAMP_BUMP", round(x["bump"])), ("DAMP_FAST_BUMP", round(x["bump"] * 0.8)),
                      ("DAMP_FAST_BUMPTHRESHOLD", 0.1),
                      ("DAMP_REBOUND", round(x["rebound"])), ("DAMP_FAST_REBOUND", round(x["rebound"] * 0.9)),
                      ("DAMP_FAST_REBOUNDTHRESHOLD", 0.14)]
    out.append(("FRONT", _front(s, pre_f, tail(xf), _radius(s))))
    pre_r, xr = common("r", s["track_r"], s["hub_mass_r"], 0.0)
    out.append(("REAR", [("TYPE", "AXLE")] + pre_r + tail(xr)))
    out += [
        ("AXLE", [("LINK_COUNT", 4),
                  ("J0_CAR", "0.75,-0.1,0.55"), ("J0_AXLE", "0.75,-0.18,-0.02"),
                  ("J1_CAR", "-0.75,-0.1,0.55"), ("J1_AXLE", "-0.75,-0.18,-0.02"),
                  ("J2_CAR", "0,-0.1,0.55"), ("J2_AXLE", "0,0,-0.02"),
                  ("J3_AXLE", "0.55,0.05,-0.12"), ("J3_CAR", "-0.75,0.04,-0.10"),
                  ("TORQUE_REACTION", 0), ("ATTACH_REL_POS", 0.6), ("LEAF_SPRING_LAT_K", 0)]),
        ("GRAPHICS_OFFSETS", [(k, 0.0) for k in ("WHEEL_LF", "SUSP_LF", "WHEEL_RF", "SUSP_RF",
                                                 "WHEEL_LR", "SUSP_LR", "WHEEL_RR", "SUSP_RR")]),
        ("DAMAGE", [("MIN_VELOCITY", 40), ("GAIN", 0.0004), ("MAX_DAMAGE", 0.05), ("DEBUG_LOG", 1)]),
    ]
    return _ini(out)


def _tyres_ini(s, d, ax):
    r = _radius(s)
    base_fz = 2317.0       # HT81S の FZ0。荷重に比例させる値の基準
    secs = [("HEADER", [("VERSION", 10)]), ("VIRTUALKM", [("USE_LOAD", 1)]), ("COMPOUND_DEFAULT", [("INDEX", 0)])]
    for sec, a, width, inertia, wear, psi, ideal in (
            ("FRONT", "f", s["tyre_width"], s["wheel_inertia_f"], "street_front.lut", 32, 39),
            ("REAR", "r", s["tyre_width_rear_phys"], s["wheel_inertia_r"], "street_rear.lut", 30, 37)):
        fz0 = ax[a]["fz0"]; k = fz0 / base_fz; rate = ax[a]["tyre_rate"]
        secs.append((sec, [
            ("NAME", "Truck"), ("SHORT_NAME", "TR"), ("WIDTH", width), ("RADIUS", r), ("RIM_RADIUS", 0.298),
            ("ANGULAR_INERTIA", inertia), ("DAMP", round(500 * k)), ("RATE", round(rate)),
            ("DY0", s["tyre_dy"]), ("DY1", -0.05), ("DX0", 0.90), ("DX1", -0.046),
            ("WEAR_CURVE", wear), ("SPEED_SENSITIVITY", 0.003657), ("RELAXATION_LENGTH", round(0.07137 * r / 0.292, 5)),
            ("ROLLING_RESISTANCE_0", s["rr0"]), ("ROLLING_RESISTANCE_1", s["rr1"]),
            ("ROLLING_RESISTANCE_SLIP", s["rr_slip"]),
            ("FLEX", 0.001113), ("CAMBER_GAIN", 0.11), ("DCAMBER_0", 1.1), ("DCAMBER_1", -13),
            ("FRICTION_LIMIT_ANGLE", 8.9), ("XMU", 0.28),
            ("PRESSURE_STATIC", psi), ("PRESSURE_SPRING_GAIN", round(rate * 7834 / 250675)),
            ("PRESSURE_FLEX_GAIN", 0.45), ("PRESSURE_RR_GAIN", 0.55), ("PRESSURE_D_GAIN", 0.004),
            ("PRESSURE_IDEAL", ideal),
            ("FZ0", round(fz0, 1)), ("LS_EXPY", 0.85), ("LS_EXPX", 0.85), ("DX_REF", 0.90), ("DY_REF", s["tyre_dy"]),
            ("FLEX_GAIN", 0.0315), ("FALLOFF_LEVEL", 0.87), ("FALLOFF_SPEED", 4), ("CX_MULT", 1.02),
            ("RADIUS_ANGULAR_K", 0.01), ("BRAKE_DX_MOD", 0.05)]))
    for sec, sr in (("THERMAL_FRONT", 1.27072), ("THERMAL_REAR", 1.25644)):
        secs.append((sec, [
            ("SURFACE_TRANSFER", 0.014), ("PATCH_TRANSFER", 0.00027), ("CORE_TRANSFER", 0.00052),
            ("INTERNAL_CORE_TRANSFER", 0.0062), ("FRICTION_K", 0.06513), ("ROLLING_K", 0.23),
            ("PERFORMANCE_CURVE", "tcurve_street.lut"), ("GRAIN_GAMMA", 1), ("GRAIN_GAIN", 0.4),
            ("BLISTER_GAMMA", 1), ("BLISTER_GAIN", 0.4), ("COOL_FACTOR", 2.51), ("SURFACE_ROLLING_K", sr)]))
    return _ini(secs)


def _drivetrain_ini(s):
    gears = [("COUNT", 6), ("GEAR_R", -s["gear_reverse"])] + \
            [("GEAR_%d" % i, s["gear_%d" % i]) for i in range(1, 7)] + [("FINAL", s["final_drive"])]
    return _ini([
        ("HEADER", [("VERSION", 3)]),
        ("TRACTION", [("TYPE", "RWD")]),
        ("GEARS", gears),
        ("DIFFERENTIAL", [("POWER", 0.05), ("COAST", 0.05), ("PRELOAD", 0)]),
        ("GEARBOX", [("CHANGE_UP_TIME", 500), ("CHANGE_DN_TIME", 500), ("AUTO_CUTOFF_TIME", 300),
                     ("SUPPORTS_SHIFTER", 1), ("VALID_SHIFT_RPM_WINDOW", 1000), ("CONTROLS_WINDOW_GAIN", 0.4),
                     ("INERTIA", 0.05)]),
        ("CLUTCH", [("MAX_TORQUE", 1500)]),
        ("AUTOCLUTCH", [("UPSHIFT_PROFILE", "NONE"), ("DOWNSHIFT_PROFILE", "DOWNSHIFT_PROFILE"),
                        ("USE_ON_CHANGES", 1), ("MIN_RPM", 700), ("MAX_RPM", 1200), ("FORCED_ON", 1)]),
        ("DOWNSHIFT_PROFILE", [("POINT_0", 50), ("POINT_1", 280), ("POINT_2", 800)]),
        ("AUTOBLIP", [("ELECTRONIC", 0), ("POINT_0", 20), ("POINT_1", 180), ("POINT_2", 200), ("LEVEL", 1.0)]),
        ("DAMAGE", [("RPM_WINDOW_K", 100)]),
        ("AUTO_SHIFTER", [("UP", s["shift_up_rpm"]), ("DOWN", s["shift_down_rpm"]), ("SLIP_THRESHOLD", 0.95),
                          ("GAS_CUTOFF_TIME", 0.3)]),
    ])


def _engine_ini(s):
    lim = s["limiter_rpm"]
    return _ini([
        ("HEADER", [("VERSION", 1), ("POWER_CURVE", "power.lut"), ("COAST_CURVE", "FROM_COAST_REF")]),
        ("ENGINE_DATA", [("ALTITUDE_SENSITIVITY", 0.1), ("INERTIA", s["engine_inertia"]), ("LIMITER", lim),
                         ("LIMITER_HZ", 40), ("MINIMUM", s["idle_rpm"])]),
        ("COAST_REF", [("RPM", lim), ("TORQUE", s["engine_coast_nm"]), ("NON_LINEARITY", 0)]),
        ("COAST_DATA", [("COAST0", 0), ("COAST1", 0), ("COAST", 0.0000015)]),
        ("DAMAGE", [("RPM_THRESHOLD", lim + 400), ("RPM_DAMAGE_K", 0.5)]),
    ])


def _brakes_ini(s, total):
    # MAX_TORQUE の単位: AC は FRONT_SHARE で前後に分け、輪あたり 前 = MAX×share・後 = MAX×(1-share)
    # （= 4 輪の合計は 2×MAX_TORQUE）。HT81S(1500) ×2 = 3000 N·m は 930 kg・半径 0.292 m で 1.13 G 相当、
    # 合計 = MAX とすると 0.56 G で乗用車として低すぎるので前者と判断（ゲームでの減速度は Task 7 で測る）。
    need = total * G * s["brake_decel_g"] * _radius(s)
    mx = round(need / 2)
    return _ini([
        ("HEADER", [("VERSION", 1)]),
        ("DATA", [("MAX_TORQUE", mx), ("FRONT_SHARE", s["brake_split_f"]), ("HANDBRAKE_TORQUE", round(mx * 0.27, -2)),
                  ("COCKPIT_ADJUSTABLE", 0), ("ADJUST_STEP", 0.5)]),
        ("TEMPS_FRONT", [("COOL_TRANSFER", 0.013), ("TORQUE_K", 0.15),
                         ("PERF_CURVE", "(|0=0.85|100=0.93|200=0.98|300=1.00|380=1.00|450=0.96|550=0.84|650=0.67|750=0.46|800=0.325|)"),
                         ("COOL_SPEED_FACTOR", 0.015)]),
        ("TEMPS_REAR", [("COOL_TRANSFER", 0.009), ("TORQUE_K", 0.20),
                        ("PERF_CURVE", "(|0=0.85|100=0.93|200=0.98|300=1.00|380=1.00|450=0.96|550=0.84|650=0.67|750=0.46|800=0.325|)"),
                        ("COOL_SPEED_FACTOR", 0.010)]),
    ])


def _aero_ini(s, go):
    area = s["width"] * (s["height"] - s["ground_clearance"])        # 前面面積 7.39 m²（CHORD 1 × SPAN）
    return _ini([
        ("HEADER", [("VERSION", 3)]),
        ("WING_0", [("NAME", "BODY"), ("CHORD", 1), ("SPAN", round(area, 3)),
                    ("POSITION", _vec(0, (s["height"] + s["ground_clearance"]) / 2 + go[1], 0)),
                    ("LUT_AOA_CL", "wing_body_AOA_CL.lut"), ("LUT_GH_CL", ""), ("CL_GAIN", 0),
                    ("LUT_AOA_CD", "wing_body_AOA_CD.lut"), ("LUT_GH_CD", ""), ("CD_GAIN", 1), ("ANGLE", 0),
                    ("ZONE_FRONT_CL", 0), ("ZONE_FRONT_CD", 0.005), ("ZONE_REAR_CL", 0), ("ZONE_REAR_CD", 0.005),
                    ("ZONE_LEFT_CL", 0), ("ZONE_LEFT_CD", 0.01), ("ZONE_RIGHT_CL", 0), ("ZONE_RIGHT_CD", 0.01),
                    ("YAW_CL_GAIN", 0)]),
    ])


def _body_cd_lut(s):
    k = s["cd"] / 0.36
    return [(a, round(c * k, 4) if c < 0.5 else c) for a, c in _BODY_CD_HT81S]


def _cameras_ini(s, d):
    H = s["height"]; zf = d["axle_z_front"] + s["overhang_f"]; zr = d["axle_z_rear"] - s["overhang_r"]
    # 運転席の後ろ・屋根の前寄りのカメラは設計時の目（内装の DRIVER_EYE）から測る。2026-11-26 に DRIVEREYES を運転士の頭の中へ
    # 0.42 m 前に移したが、これらのカメラは座席・屋根の位置のためのものなので動かさない（目から測ると 2 番が運転士の背中に入る）
    ex, ey, ez = s["design_eye_x"], s["design_eye_y"], s["design_eye_z"]

    def cam(pos, fwd, fov, exp, snd):
        n = math.sqrt(sum(c * c for c in fwd)); f = [c / n for c in fwd]
        # up = 世界の上方向から forward 成分を除いたもの
        up = [-f[1] * f[0], 1 - f[1] * f[1], -f[1] * f[2]]
        m = math.sqrt(sum(c * c for c in up)); up = [c / m for c in up]
        return [("POSITION", _vec(*pos)), ("FORWARD", _vec(*f)), ("UP", _vec(*up)), ("FOV", fov),
                ("EXPOSURE", exp), ("EXTERNAL_SOUND", snd)]

    cams = [
        cam((0, H + 0.6, ez + 0.9), (0, -0.2, 0.98), 60, 27, 1),                 # 屋根の前寄りから前
        cam((1.9, 1.2, zf - 0.8), (-0.09, -0.13, 0.99), 60, 21, 1),               # 前の左外
        cam((ex + 0.25, ey + 0.05, ez - 0.4), (-0.25, -0.07, 0.97), 64, 15, 0),   # 運転席の後ろ
        None, None,                                                               # 3・4 は下の後ろ上方の 2 台
        cam((0, H + 0.6, zr + 2.0), (0, -0.29, -0.957), 60, 27, 1),               # 屋根の後ろ寄りから後ろ
    ]
    # 追従視点の代わり（ユーザー指摘 2026-11-26「視点によっては、バスの後ろで画面が覆われる」）:
    # AC の F1 追従カメラは全車共通の system/cfg/chase_cam.ini（距離 3.0／3.9 m）で、車ごとに伸ばせない。
    # 全長 10.4 m のバスでは後面の直前（重心から約 5.6 m 後ろ、run circle_drift_094555 で実測）に来るので、
    # 後ろ上方から車体の中ほどを見る F6 カメラを近・遠の 2 台にする。
    # AC は F6 を 6 台までしか読まない（Kunos 119 台はすべて CAMERA_0〜5、8 台書いた回 circleramp_drift_20261126_105230 で
    # carCamerasCount=6）ので、運転席の脇（運転席視点とほぼ同じ）と左側面から後ろの 2 台と入れ替える。
    zc = (zf + zr) / 2
    for i, (back, up) in zip((3, 4), ((8.0, 1.8), (13.0, 3.2))):
        pos = (0, H + up, zr - back); tgt = (0, 1.6, zc + 1.5)
        cams[i] = cam(pos, tuple(t - q for t, q in zip(tgt, pos)), 60, 27, 1)
    assert len(cams) == 6 and all(cams)
    return _ini([("CAMERA_%d" % i, c) for i, c in enumerate(cams)])


def _colliders_ini(s, d, go):
    """底面の薄い箱（HT81S と同じ作り）。底面は kn5 の高さ ground_clearance。幅−0.26・長さ−0.78 は ZC32S と同じ縮め方。"""
    zc = (d["axle_z_front"] + s["overhang_f"] + d["axle_z_rear"] - s["overhang_r"]) / 2
    t = 0.1
    return _ini([("COLLIDER_0", [("CENTRE", _vec(0, s["ground_clearance"] + t / 2 + go[1], zc + go[2])),
                                  ("SIZE", _vec(s["width"] - 0.26, t, s["length"] - 0.78)),
                                  ("GROUND_ENABLE", 1)])])


def _setup_ini(s):
    def pr(n, x, y):
        return (n, [("SHOW_CLICKS", 0), ("TAB", "TYRES"), ("NAME", "Pressure " + n[-2:]), ("MIN", 15), ("MAX", 40),
                    ("STEP", 1), ("POS_X", x), ("POS_Y", y), ("HELP", "HELP_%s_PRESSURE" % n[-2:])])
    return _ini([
        ("DISPLAY_METHOD", [("SHOW_CLICKS", 1)]),
        pr("PRESSURE_LF", 0, 2), pr("PRESSURE_RF", 1, 2), pr("PRESSURE_LR", 0, 4), pr("PRESSURE_RR", 1, 4),
        ("FUEL", [("SHOW_CLICKS", 0), ("TAB", "GENERIC"), ("NAME", "Fuel"), ("MIN", 5), ("MAX", s["fuel_l"]),
                  ("STEP", 1), ("POS_X", 0.5), ("POS_Y", 0), ("HELP", "HELP_FUEL")]),
        ("BRAKE_POWER_MULT", [("SHOW_CLICKS", 0), ("TAB", "GENERIC"), ("NAME", "Brake power"), ("MIN", 80),
                              ("MAX", 100), ("STEP", 1), ("POS_X", 0.5), ("POS_Y", 1), ("HELP", "HELP_BRAKE_POWER_MULT")]),
    ])


def _damage_ini():
    secs = [("SCRATCHES", [("MIN_SPEED", 0), ("MAX_SPEED", 20)]), ("DAMAGE", [("INITIAL_LEVEL", 20)])]
    for z in ("FRONT", "REAR", "LEFT", "RIGHT", "CENTER"):
        secs.append(("DAMAGE_GLASS_" + z, [("MIN_SPEED", 20), ("FULL_SPEED", 80)]))
    secs.append(("OSCILLATIONS", [("ENABLED", 0)]))     # M1 の箱には動かすノードが無い
    return _ini(secs)


def build(out_dir):
    """data/ 一式を out_dir に書き、書いたファイル名の一覧を返す。"""
    s = _spec.load()
    d, r, go, basey = _geometry(s)
    total, ax = _axle(s)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # DRIVEREYES・dash_cam の座標は kn5 座標（GRAPHICS_OFFSET を足さない。HT81S の car.ini と元の kn5 で確認、
    # ZC32S の physics も内装を動かしたぶんだけ足す）。spec の eye_* は運転士のモデルの目（2026-11-26、tools/driver_eye.py。
    # 前は内装の DRIVER_EYE = design_eye_*）。dash_cam は目の少し前（目と一緒に動かす）。
    eye = (s["eye_x"], s["eye_y"], s["eye_z"] + 0.04)
    files = {
        "car.ini": _car_ini(s, d, go, total, ax),
        "suspensions.ini": _suspensions_ini(s, d, go, basey, ax),
        "tyres.ini": _tyres_ini(s, d, ax),
        "drivetrain.ini": _drivetrain_ini(s),
        "engine.ini": _engine_ini(s),
        "brakes.ini": _brakes_ini(s, total),
        "aero.ini": _aero_ini(s, go),
        "electronics.ini": _ini([
            ("ABS", [("SLIP_RATIO_LIMIT", 0.11), ("CURVE", ""), ("PRESENT", 1), ("ACTIVE", 1), ("RATE_HZ", 220)]),
            ("TRACTION_CONTROL", [("SLIP_RATIO_LIMIT", 0.14), ("CURVE", ""), ("PRESENT", 0), ("ACTIVE", 0),
                                  ("RATE_HZ", 128), ("MIN_SPEED_KMH", 20)])]),
        "damage.ini": _damage_ini(),
        "setup.ini": _setup_ini(s),
        "lods.ini": _ini([("COCKPIT_HR", [("DISTANCE_SWITCH", 7)]),
                          ("LOD_0", [("FILE", CAR_KN5), ("IN", 0), ("OUT", 2000)])]),
        "colliders.ini": _colliders_ini(s, d, go),
        "cameras.ini": _cameras_ini(s, d),
        "analog_instruments.ini": _analog_ini(s),
        "dash_cam.ini": _ini([("DASH_CAM", [("POS", _vec(*eye)), ("EXP", 26)])]),
        "mirrors.ini": kn5_mirrors.mirrors_ini(),
        "lights.ini": lights.lights_ini(),
        "sounds.ini": _ini([
            ("SKIDS", [("ENTRY_POINT", 0.45), ("MIX_VOLUME", 0.65), ("PITCH_BASE", 0.6), ("PITCH_GAIN", 0.18)]),
            ("WIND", [("SPEED_GAIN_0", 0), ("SPEED_GAIN_1", 0.0003), ("VOLUME_GAIN", 0.7), ("PITCH_REFERENCE", 50),
                      ("PITCH_GAIN", 0.3)]),
            ("TYRE_ROLLING", [("SPEED_GAIN_0", 0.0015), ("SPEED_GAIN_1", 0.0001), ("VOLUME_GAIN", 0.8),
                              ("PITCH_REFERENCE", 45), ("PITCH_GAIN", 0.2)]),
            ("BODY_WORK", [("MIN", 0.2), ("GAIN", 1)]),
            # AC が KEY_NOT_FOUND を出す。ディーゼルのバスなので MAXGAS=0 で実質オフ
            ("BACKFIRE", [("MAXGAS", 0.0), ("MINRPM", 1800), ("MAXRPM", 2600), ("TRIGGERGAS", 0.8)]),
            ("ENGINE", [("POSITION", "rear")])]),
        "ambient_shadows.ini": _ini([("SETTINGS", [("WIDTH", round(s["width"] * 0.62, 2)),
                                                    ("LENGTH", round(s["length"] * 0.72, 2))])]),
        "ai.ini": _ini([
            ("HEADER", [("VERSION", 4)]),
            ("GEARS", [("UP", s["shift_up_rpm"]), ("DOWN", s["shift_down_rpm"]), ("SLIP_THRESHOLD", 0.95),
                       ("GAS_CUTOFF_TIME", 0.3)]),
            ("PEDALS", [("GASGAIN", 3.0), ("BRAKE_HINT", 0.96), ("TRAIL_HINT", 1)]),
            ("LOOKAHEAD", [("BASE", 30), ("GAS_BRAKE_LOOKAHEAD", 0)]),
            ("STEER", [("STEER_GAIN", 1.7)]),
            ("ULTRA_GRIP", [("VALUE", 1.0)]),
            ("PHYSICS_HINTS", [("AERO_HINT", 1)]),
            ("TYRES", [("HINT", 1.0)])]),
        "fuel_cons.ini": _ini([("FUEL_EVAL", [("KM_PER_LITER", 2.5)])]),
    }
    luts = {
        "power.lut": _lut(make_power_lut(s), crlf=True),
        "street_front.lut": _lut(WEAR_LUT), "street_rear.lut": _lut(WEAR_LUT),
        "tcurve_street.lut": _lut(TCURVE_LUT),
        "wing_body_AOA_CD.lut": _lut(_body_cd_lut(s)),
        "wing_body_AOA_CL.lut": _lut([(-10, 0), (0, 0), (10, 0)]),
    }
    names = []
    for n, t in {**files, **luts}.items():
        (out / n).write_text(t, encoding="utf8", newline="")
        names.append(n)
    return names


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="build/data")
    a = ap.parse_args()
    for n in build(a.out):
        print(n)
