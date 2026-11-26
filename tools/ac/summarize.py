"""AC の自動走行の記録（log-<tag>.csv）から値を取り出す。
列: t,x,y,z,kmh,rpm,gear,roll,pitch（0.1 秒ごと）。Lua が書く `err,...` 行や不正な行は読み飛ばす。
python3 tools/ac/summarize.py export/ac/<tag>/log-<tag>.csv [...]

旋回半径: c.position は CG の位置とみなす（CG 前 40 % = 前軸から 0.6×WB 後ろ）。
  turn_radius_cg_m          … 定常旋回の位置に当てはめた円の半径（CG の軌跡）
  turn_radius_outer_front_m … そこから換算した外側前輪の軌跡の半径（仕様の 8.3 m と比べる値）
      後軸中心 Rr = sqrt(R_cg² − (CG から後軸 = cg_front×WB)²)
      外側前輪 = sqrt((Rr + 前トレッド/2)² + WB²)"""
import json
import sys
from pathlib import Path

import numpy as np

STILL_KMH = 0.2         # これ以下なら止まっている
MOVING_KMH = 1.0
FLIP_DEG = 45.0
SETTLE_DEG = 0.05       # 0.1 秒の間にこれ未満しか動かなければ「収まった」
JUMP_M = 0.5            # 静止中に 1 サンプルでこれ以上位置が飛んだら、出現（スポーン）の瞬間
JUMP_MARGIN = 5         # 走行中の位置の飛びの前後、このサンプル数を横 G・円当てはめから除く
IGNORE_S = 2.0          # 動き出してからこの間は横 G と円当てはめに使わない
STEADY_S = 5.0          # 速度とヨー角速度が ±10 % に収まる区間がこれ以上必要
G = 9.81
KEYS = ["t", "x", "y", "z", "kmh", "rpm", "gear", "roll", "pitch"]
EMPTY = {"settle_s": None, "max_rpm": None, "t_0_40": None, "vmax": None, "max_roll_deg": None, "flipped": None,
         "turn_radius_cg_m": None, "turn_radius_outer_front_m": None, "max_lat_g": None}


def _spec():
    try:
        s = json.loads((Path(__file__).resolve().parent.parent / "spec.json").read_text())
        return {k: float(s[k]["v"]) for k in ("wheelbase", "track_f", "cg_front")}
    except Exception:
        return {"wheelbase": 5.3, "track_f": 2.065, "cg_front": 0.4}


EXT = ["gas", "brake", "clutch", "handbrake", "req_gear", "engaged_gear", "steer_deg", "front_steer_deg",
       "cam_x", "cam_y", "cam_z"] + [f"w{i}_{k}" for i in range(4) for k in ("kmh", "slipratio", "slipangle", "load")]


def _load(csv):
    """9 列の旧形式と、後ろに EXT の列を足した新形式（ヘッダー行で判定）の両方を読む。"""
    names = list(KEYS)
    rows = []
    for line in Path(csv).read_text(errors="replace").splitlines():
        p = line.strip().split(",")
        if p and p[0] == "t":
            names = p if p[:len(KEYS)] == KEYS else list(KEYS)
            continue
        if len(p) != len(names):
            continue
        try:
            rows.append([float(v) for v in p])
        except ValueError:
            continue                      # err 行
    if len(rows) < 2:
        return None
    a = np.array(rows)
    a = a[np.argsort(a[:, 0], kind="stable")]
    return {k: a[:, i] for i, k in enumerate(names)}


def _first_moving(d):
    m = np.nonzero(d["kmh"] > MOVING_KMH)[0]
    return int(m[0]) if len(m) else len(d["t"])


def _settle(d):
    """物理が始まった時刻（静止中に位置が最後に飛んだ瞬間。無ければ先頭）から、
    ロール・ピッチが最後に 0.05° 以上動くまでの秒。"""
    n = _first_moving(d)
    if n < 2:
        return 0.0
    pos = np.c_[d["x"][:n], d["y"][:n], d["z"][:n]]
    jumps = np.nonzero(np.linalg.norm(np.diff(pos, axis=0), axis=1) > JUMP_M)[0]
    s = int(jumps[-1]) + 1 if len(jumps) else 0
    t0 = d["t"][s]
    step = np.maximum(np.abs(np.diff(d["roll"][s:n])), np.abs(np.diff(d["pitch"][s:n])))
    big = np.nonzero(step >= SETTLE_DEG)[0]
    return float(d["t"][s + big[-1] + 1] - t0) if len(big) else 0.0


def _t_0_40(d):
    t, v = d["t"], d["kmh"]
    up = np.nonzero(v >= 40.0)[0]
    if not len(up):
        return None
    k = int(up[0])
    still = np.nonzero(v[:k] <= STILL_KMH)[0]
    t0 = t[still[-1]] if len(still) else t[0]
    t1 = t[k] if k == 0 else t[k - 1] + (40.0 - v[k - 1]) / (v[k] - v[k - 1]) * (t[k] - t[k - 1])
    return float(t1 - t0)


def _jumps(d):
    """走行中の位置の飛び（テレポート）の番号。1 サンプルの移動距離が 速度×dt×3 + JUMP_M を超えた点 i（i-1 から i で飛んだ）。"""
    if len(d["t"]) < 2:
        return np.zeros(0, int)
    dt = np.diff(d["t"])
    dist = np.hypot(np.diff(d["x"]), np.diff(d["z"]))
    v = np.maximum(d["kmh"][:-1], d["kmh"][1:]) / 3.6
    return np.nonzero(dist > v * dt * 3 + JUMP_M)[0] + 1


def _segments(d):
    """位置の飛びで切った (開始, 終了) の組。"""
    cuts = [0] + [int(j) for j in _jumps(d)] + [len(d["t"])]
    return [(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]


def _yaw_seg(t, x, z, win_s):
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.1
    dt = dt or 0.1
    k = max(1, int(round(win_s / dt)))
    n = len(t)
    if n <= 2 * k + 2:
        return np.zeros(n)
    hx = np.r_[x[k:] - x[:-k], np.zeros(k)]
    hz = np.r_[z[k:] - z[:-k], np.zeros(k)]
    # i の方向 = i から i+k への向き。中心を合わせるため i+k/2 の方向として扱う。
    head = np.unwrap(np.arctan2(hx, hz))
    w = np.gradient(head, t)
    w = np.r_[np.zeros(k // 2), w[: n - k // 2]]
    w[n - k:] = 0.0
    return w


def _yaw_rate(d, win_s=0.5):
    """位置から求めた進行方向の角速度 (rad/s)。win_s の間隔で方向を取り、1 サンプルのばらつきを避ける。
    位置の飛びをまたがないよう、飛びで切った区間ごとに計算する。"""
    w = np.zeros(len(d["t"]))
    for a, b in _segments(d):
        w[a:b] = _yaw_seg(d["t"][a:b], d["x"][a:b], d["z"][a:b], win_s)
    return w


def _moving_mask(d):
    """動き出して IGNORE_S 秒たった後の、走っている行。"""
    n = _first_moving(d)
    m = np.zeros(len(d["t"]), bool)
    if n >= len(m):
        return m
    m[d["t"] >= d["t"][n] + IGNORE_S] = True
    m &= d["kmh"] > MOVING_KMH
    for j in _jumps(d):                        # 走行中の位置の飛びの前後は使わない
        m[max(0, j - JUMP_MARGIN): j + JUMP_MARGIN] = False
    return m


def _max_lat_g(d):
    m = _moving_mask(d)
    if m.sum() < 5:
        return 0.0
    lat = np.abs(d["kmh"] / 3.6 * _yaw_rate(d))
    dt = float(np.median(np.diff(d["t"]))) or 0.1
    k = max(1, int(round(1.0 / dt)))
    sm = np.convolve(lat, np.ones(k) / k, mode="same")      # 1 秒の移動平均
    idx = np.nonzero(m)[0]
    idx = idx[k // 2: len(idx) - k // 2] if len(idx) > k else idx
    return float(sm[idx].max() / G) if len(idx) else 0.0


def _steady_run(d):
    """速度とヨー角速度がどちらも中央値の ±10 % に収まる最長の連続区間（STEADY_S 以上）。"""
    m = _moving_mask(d)
    if "steer_deg" in d:                       # 操舵を記録している csv は、最大舵角の 95 % 以上の行だけで探す（直進の加速区間を除く）
        smax = float(np.abs(d["steer_deg"]).max())
        if smax > 1.0:
            m = m & (np.abs(d["steer_deg"]) >= 0.95 * smax)
    w, v = _yaw_rate(d), d["kmh"] / 3.6
    if m.sum() < 5:
        return None
    sel = m.copy()
    for _ in range(2):
        mv, mw = np.median(v[sel]), np.median(w[sel])
        if abs(mw) < 0.02:
            return None
        ok = m & (np.abs(v - mv) <= 0.1 * abs(mv)) & (np.abs(w - mw) <= 0.1 * abs(mw))
        best, cur = (0, 0), None
        for i in range(len(ok)):
            if ok[i]:
                cur = i if cur is None else cur
                if i - cur + 1 > best[1] - best[0]:
                    best = (cur, i + 1)
            else:
                cur = None
        if best[1] - best[0] < 2:
            return None
        sel = np.zeros(len(ok), bool)
        sel[best[0]:best[1]] = True
    a, b = best
    if d["t"][b - 1] - d["t"][a] < STEADY_S:
        return None
    return a, b


def _circle(d):
    """定常旋回の区間の位置に円を当てはめる。戻り値は (CG の半径, 外側前輪の半径)。円にならなければ (None, None)。"""
    run = _steady_run(d)
    if run is None:
        return None, None
    a, b = run
    x, z = d["x"][a:b], d["z"][a:b]
    A = np.c_[2 * x, 2 * z, np.ones(len(x))]
    cx, cz, c = np.linalg.lstsq(A, x * x + z * z, rcond=None)[0]
    r2 = c + cx * cx + cz * cz
    if r2 <= 0:
        return None, None
    r = float(np.sqrt(r2))
    resid = float(np.sqrt(np.mean((np.hypot(x - cx, z - cz) - r) ** 2)))
    ang = np.unwrap(np.arctan2(z - cz, x - cx))
    if resid > 0.05 * r or abs(ang[-1] - ang[0]) < np.pi / 3:
        return None, None
    sp = _spec()
    d_rear = sp["cg_front"] * sp["wheelbase"]        # CG から後軸までの距離
    if r <= d_rear:
        return r, None
    rr = np.sqrt(r * r - d_rear * d_rear)
    return r, float(np.sqrt((rr + sp["track_f"] / 2) ** 2 + sp["wheelbase"] ** 2))


def summarize(csv) -> dict:
    d = _load(csv)
    if d is None:
        return dict(EMPTY, reason="no data rows")
    roll = float(np.abs(d["roll"]).max())
    r_cg, r_front = _circle(d)
    return {
        "settle_s": _settle(d),
        "max_rpm": float(d["rpm"].max()),
        "t_0_40": _t_0_40(d),
        "vmax": float(d["kmh"].max()),
        "max_roll_deg": roll,
        "flipped": bool(roll > FLIP_DEG),
        "turn_radius_cg_m": r_cg,
        "turn_radius_outer_front_m": r_front,
        "max_lat_g": _max_lat_g(d),
        "reason": None,
    }


def _gear_spec():
    s = json.loads((Path(__file__).resolve().parent.parent / "spec.json").read_text())
    g = {i: float(s[f"gear_{i}"]["v"]) for i in range(1, 7)}
    return g, float(s["final_drive"]["v"]), float(s["tyre_diameter"]["v"]) / 2


def drivetrain_diagnosis(csv, gears=None, final=None, radius=None):
    """ギアごとに: 後輪の表面速度 − 車速、エンジン回転から割り出した速度 / 車速、ブレーキ・クラッチの中央値。
    後輪が速い → 空転、回転由来の速度だけが速い → クラッチ滑り、ブレーキ中央値が大きい → ブレーキ。
    新形式（EXT 列あり）の csv が必要。無ければ None。"""
    d = _load(csv)
    if d is None or "w2_kmh" not in d:
        return None
    if gears is None:
        gears, final, radius = _gear_spec()
    out = {}
    for g in sorted(set(int(x) for x in d["gear"] if x >= 1)):
        m = (d["gear"] == g) & (d["kmh"] > 3.0)
        if m.sum() < 5 or g not in gears:
            continue
        rear = (d["w2_kmh"][m] + d["w3_kmh"][m]) / 2
        implied = d["rpm"][m] / (gears[g] * final) * 2 * np.pi * radius * 3.6 / 60
        out[g] = {
            "samples": int(m.sum()),
            "car_kmh": float(np.median(d["kmh"][m])),
            "rear_minus_car_kmh": float(np.median(rear - d["kmh"][m])),
            "rpm_implied_kmh": float(np.median(implied)),
            "implied_over_car": float(np.median(implied / d["kmh"][m])),
            "brake": float(np.median(d["brake"][m])),
            "clutch": float(np.median(d["clutch"][m])),
            "front_steer_deg": float(np.median(d["front_steer_deg"][m])),
        }
        o = out[g]
        o["verdict"] = ("brake" if o["brake"] > 0.1 else "wheel spin" if o["rear_minus_car_kmh"] > 3
                        else "clutch slip" if o["implied_over_car"] > 1.15 else "coupled")
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p)
        for k, v in summarize(Path(p)).items():
            print(f"  {k}: {v if v is None or isinstance(v, (bool, str)) else round(v, 3)}")
        dd = drivetrain_diagnosis(Path(p))
        if dd:
            print("  drivetrain diagnosis (gear: car / rear-car / rpm-implied / implied-over-car / brake / clutch / front steer -> verdict)")
            for g, o in dd.items():
                print(f"    gear {g}: {o['car_kmh']:.1f} / {o['rear_minus_car_kmh']:+.1f} / {o['rpm_implied_kmh']:.1f} / "
                      f"{o['implied_over_car']:.2f} / {o['brake']:.2f} / {o['clutch']:.2f} / {o['front_steer_deg']:+.1f} -> {o['verdict']}")
