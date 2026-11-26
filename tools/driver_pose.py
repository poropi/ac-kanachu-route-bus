"""座った姿勢を解いて driver_base_pos.knh を書く。

  python3 tools/driver_pose.py --kn5 build/driver/kanachu_driver.kn5 --cockpit design/driver/cockpit.json \
      --out build/driver/driver_base_pos.knh

入力: 運転手 kn5 の種類 1 のノード（骨名 -> 親からの相対行列。kn5 と同じ行ベクトル規約: 世界 = 自分 @ 親、
平行移動は 4 行目）、`cockpit.json`（kn5 座標）。出力: 骨名 -> 親からの相対行列 4x4（同じ規約、拡大なしの剛体）。

方法（世界座標で解く。骨の向きには依存しない = 各骨の回転は「今の向きからの最小回転」で作る）。2026-11-26 改訂:
 1. 体を腰（RIG_Center）を原点に置いた体の座標で作る。拡大はしない。上半身（RIG_Cest 以下）を前傾 phi（-6〜20°）させ、頭は正面のまま。
 2. 腰の骨は座面（seat_point の高さ）の上 SEAT_CLEARANCE、前後は seat_point から ±SEAT_HALF_DEPTH（座面の奥行の範囲）で動かす。
 3. 握り: リムの真上から grip_deg（60 = 10 時と 2 時）〜 GRIP_MAX_DEG の、左右対称の角度のうち、
    両腕が肘を MIN_ELBOW_BEND 以上曲げたまま届くいちばん上を選ぶ。そのうち前傾と前後のずれが小さい姿勢を取る
    （まず脚もペダルに届く姿勢から探し、無ければ脚を諦める）。どの角度も届かなければ、最大の前傾・前進・上限の角度で届く所まで。
    手のひらの中心 = 手首の骨と中指の付け根の中点。左右は骨名でなく肩の位置の近さで割り当てる。
    2026-11-26 改訂（握り）: 手のひらはリムの管の表面に置き、指は曲げて握る。
    - 手のひらの中心の目標は、管の中心線からリムの面の中で外へ (rim_tube_radius + PALM_HALF_THICKNESS) ずらした点
      （= 半径 rim_radius + rim_tube_radius + PALM_HALF_THICKNESS の「握りの円」の上）。
    - 手の向き: 小指の付け根から人差し指の付け根への向きをリムの接線（リムの上の向き）に、
      手のひらをハンドルの中心へ向け、そこから手の座標で GRIP_TILT_DEG だけ回す（曲げた指が管を包むように）。
    - 指の骨（RIG_HAND_L/R の子孫の HAND_*）は design/driver/grip_fingers.json の回転（.blend の握りのフレーム 2）で曲げる。
 4. 腕・脚は 2 本の骨の解析的 IK（余弦定理）。肘は下と外、膝は前と上へ逃がす。足の母指球（Foot）をペダルの踏面へ、爪先を PEDAL_PITCH 下げる。
 5. 世界行列から親からの相対行列を作る。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import knh as knhmod  # noqa: E402
from driver_skeleton import BONES  # noqa: E402

PARENT = dict(BONES)
CHILDREN = {}
for _n, _p in BONES:
    CHILDREN.setdefault(_p, []).append(_n)

P = "DRIVER:"
CENTER, CEST, HEAD = P + "RIG_Center", P + "RIG_Cest", P + "RIG_Head"
SEAT_CLEARANCE = 0.10                        # 腰の骨が座面の上にある高さ (m)
SEAT_HALF_DEPTH = 0.24                       # 座面の奥行 ≈ 0.48 m の半分。腰は seat_point から前後にこの範囲で動く
KNEE_MARGIN = 0.03                           # 膝とハンドルの柱の箱の間に空ける余裕 (m)
HAND_TOLERANCE = 0.02                        # 手のひらの中心と目標（握りの円の上の点）の距離の許容 (m)。超えたらエラー
PALM_HALF_THICKNESS = 0.0163                 # 手のひらの厚みの半分 (m)。GLOVES の手のひらの中心の 2 cm 四方の頂点の、手のひらの法線方向の幅 0.0325 の半分
# 手の向きの追加の回転（度、手の座標）: (指の付け根の並びのまわり, 手のひらの法線のまわり, 指の向きのまわり)。
# 手のひらを管に平らに当てただけ（全部 0）では、.blend の曲げた指は管の 1.5〜3 cm 前で輪になり、親指が管に 13 mm めり込む。
# 指の付け根の並びのまわりに倒して、指の付け根の側を管へ寄せると指が管を包む（値は GLOVES の頂点で、めり込みが最も浅い組を選んだ）。
GRIP_TILT_DEG = (-50.0, 10.0, -15.0)
GRIP_FINGERS_JSON = Path(__file__).resolve().parent.parent / "design" / "driver" / "grip_fingers.json"
MAX_LEAN = 20.0                              # 上体の前傾の上限 (度)
MIN_ELBOW_BEND = 16.0                        # 肘の曲げの下限 (度)。試験の 15° に余裕を持たせる
GRIP_MAX_DEG = 100                           # 握る角度の下限（真上から。60 が「10 時と 2 時」、大きいほど下）
PEDAL_PITCH = np.radians(20.0)               # 足を踏面に載せるときの爪先の下げ角
ARM_POLE = np.array([0.5, -1.0, 0.0])        # 肘の逃げ方向（下へ。外向きは肩の側で符号をそろえる）
KNEE_POLE = np.array([0.0, 1.0, 1.0])        # 膝の逃げ方向（前と上）


# ---------- 行列の基本（内部は列ベクトル規約: 世界 = 親 @ 自分、平行移動は 4 列目） ----------
def rot_between(a, b):
    """ベクトル a を b に回す最小回転（3x3）。"""
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if c < -1 + 1e-9:
        ax = np.cross(a, [1, 0, 0])
        if np.linalg.norm(ax) < 1e-6:
            ax = np.cross(a, [0, 1, 0])
        ax /= np.linalg.norm(ax)
        return 2 * np.outer(ax, ax) - np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c)


def rot_axis(axis, ang):
    axis = axis / np.linalg.norm(axis)
    K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + np.sin(ang) * K + (1 - np.cos(ang)) * K @ K


def about(R, p):
    """点 p のまわりの回転 R（4x4）。"""
    M = np.eye(4)
    M[:3, :3] = R
    M[:3, 3] = p - R @ p
    return M


def unit(v):
    return v / np.linalg.norm(v)


def world_of(local_col, names=None):
    W = {}
    for n, p in BONES:
        W[n] = local_col[n] if p is None else W[p] @ local_col[n]
    return W


def fk(local):
    """親からの相対行列（行ベクトル規約）-> 世界行列（同じ規約）。"""
    W = world_of({n: np.asarray(m).T for n, m in local.items()})
    return {n: m.T for n, m in W.items()}


def _desc(b):
    out = [b]
    for c in CHILDREN.get(b, []):
        out += _desc(c)
    return out


def _repose(B, b, delta):
    for d in _desc(b):
        B[d] = delta @ B[d]


class UnreachableError(RuntimeError):
    pass


def pos(M):
    return M[:3, 3].copy()


def side_bones(arm):
    """腕の骨 (Arm, ForeArm, Hand, Middle1)。arm は 'L' / 'R'。"""
    hand = P + "RIG_HAND_" + arm
    middle = next(c for c in CHILDREN[hand] if "Middle" in c)
    return P + "RIG_Arm_" + arm, P + "RIG_ForeArm_" + arm, hand, middle


def finger_bones(arm):
    """指の骨 = RIG_HAND_<arm> の子孫の HAND_* の骨（RIG_HAND 自身は含まない）。"""
    hand = P + "RIG_HAND_" + arm
    return [n for n in _desc(hand) if n != hand and n.startswith(P + "HAND_")]


def load_grip_fingers(path=None):
    """骨名 -> 3x3（行ベクトル規約の、親からの相対の回転の差。新しい 3x3 = delta @ レストの 3x3）。"""
    doc = json.loads(Path(path or GRIP_FINGERS_JSON).read_text(encoding="utf-8"))
    return {n: np.array(m, dtype=float) for n, m in doc["deltas"].items()}


def curl_fingers(local, deltas):
    """親からの相対行列（行ベクトル規約）の指の骨に、握りの回転を掛けたものを返す（骨の原点のまわり、平行移動はそのまま）。"""
    out = dict(local)
    want = set(finger_bones("L")) | set(finger_bones("R"))
    if set(deltas) != want:
        raise ValueError("grip_fingers.json の骨が指の骨と違う: %s" % sorted(set(deltas) ^ want))
    for n, d in deltas.items():
        M = np.array(local[n], dtype=float)
        M[:3, :3] = d @ M[:3, :3]
        out[n] = M
    return out


def hand_frame(B, arm):
    """手の座標（列ベクトル規約の世界行列 B から）: f = 手首→中指の付け根、l = 小指の付け根→人差し指の付け根（f に直交化）、
    palm = 手のひらの側（f, l に直交）。左手は f×l、右手は −f×l が手のひらの側（手の掌側・甲側の向きは左右で鏡）。"""
    _, _, hand, middle = side_bones(arm)
    kids = CHILDREN[hand]
    index = next(c for c in kids if "Index" in c)
    pinkie = next(c for c in kids if "Pinkie" in c)
    f = unit(pos(B[middle]) - pos(B[hand]))
    l = pos(B[index]) - pos(B[pinkie])
    l = unit(l - np.dot(l, f) * f)
    return f, l, np.cross(f, l) * (1.0 if arm == "L" else -1.0)


def grip_radius(cockpit):
    """握りの円の半径（リムの面の中）= 管の中心線の半径 + 管の半径 + 手のひらの厚みの半分。"""
    return cockpit["rim_radius"] + cockpit["rim_tube_radius"] + PALM_HALF_THICKNESS


def palm_center(W, arm):
    """手のひらの中心 = 手首の骨と中指の付け根の中点（W は世界行列、規約は行・列どちらでも）。"""
    _, _, hand, middle = side_bones(arm)
    return (pos_any(W[hand]) + pos_any(W[middle])) / 2


def pos_any(M):
    M = np.asarray(M)
    return M[3, :3].copy() if _is_row(M) else M[:3, 3].copy()


def _is_row(M):
    return abs(M[3, 3] - 1) < 1e-6 and np.allclose(M[:3, 3], 0) and not np.allclose(M[3, :3], 0)


def two_bone(S, T, u, l, pole):
    """肩 S・目標 T・長さ u, l・逃げ方向 pole から、関節の位置を余弦定理で求める。届かないときは T を手前に丸める。"""
    d = np.linalg.norm(T - S)
    d = float(np.clip(d, abs(u - l) + 1e-4, u + l - 1e-4))
    e = unit(T - S)
    a = (u * u - l * l + d * d) / (2 * d)
    h = np.sqrt(max(u * u - a * a, 0.0))
    pd = pole - np.dot(pole, e) * e
    if np.linalg.norm(pd) < 1e-6:
        pd = np.cross(e, [1.0, 0.0, 0.0])
    return S + a * e + h * unit(pd), S + d * e


def _two_bone_chain(B, b1, b2, end, target, pole, min_bend=0.0):
    """b1（付け根）・b2（関節）の 2 本で、end の骨の原点を target に置く（B を書き換える）。"""
    target0 = target
    S = pos(B[b1])
    u = np.linalg.norm(pos(B[b2]) - S)
    l = np.linalg.norm(pos(B[end]) - pos(B[b2]))
    if min_bend:     # 肘を伸ばしきらない: 届く距離を曲げ角 min_bend の分だけ短くする
        dmax = np.sqrt(u * u + l * l - 2 * u * l * np.cos(np.radians(180.0 - min_bend)))
        if np.linalg.norm(target - S) > dmax:
            target = S + unit(target - S) * dmax
    E, T = two_bone(S, target, u, l, pole)
    _repose(B, b1, about(rot_between(pos(B[b2]) - S, E - S), S))
    _repose(B, b2, about(rot_between(pos(B[end]) - E, T - E), E))
    return float(np.linalg.norm(target0 - T))    # 届かなかった距離


# ---------- 本体 ----------
def rim_points(cockpit, grip_deg, sign=None, radius=None):
    """リムの管の中心線上の、真上（面の中の上向き）から grip_deg の左右の 2 点。sign=±1 なら片側の 1 点だけ。
    radius を渡すと、中心線の代わりに同じ面・同じ中心のその半径の円の上の点（握りの円は grip_radius）。"""
    c = np.array(cockpit["wheel_center"])
    n = unit(np.array(cockpit["wheel_axis"]))
    up = np.array([0.0, 1.0, 0.0])
    ip = up - np.dot(up, n) * n                  # リムの面の中の「真上」
    if np.linalg.norm(ip) < 1e-6:
        ip = np.array([0.0, 0.0, 1.0]) - n[2] * n
    ip = unit(ip)
    lat = np.cross(n, ip)
    g = np.radians(grip_deg)
    r = cockpit["rim_radius"] if radius is None else radius
    return [c + r * (np.cos(g) * ip + sg * np.sin(g) * lat) for sg in ((1.0, -1.0) if sign is None else (sign,))], n


def solve_seated(rest, cockpit, grip_deg=60.0, report=None, fingers=None):
    """座った姿勢を解く。grip_deg は握りたいいちばん上の角度（真上から）。そこから GRIP_MAX_DEG まで、届くいちばん上を選ぶ。

    report に dict を渡すと、grip_deg（選んだ握り角）・lean_deg（上体の前傾、前が正）・pelvis_slide_m（座面の中心からの前後のずれ、前が正）・
    legs_on_pedals（脚がペダルに届く姿勢か）・elbow_bend_deg（L, R）・hand_miss_m（L, R）・leg_miss_m（L, R）を入れる。
    fingers: 指の握りの回転（load_grip_fingers の形）。None なら design/driver/grip_fingers.json を読む。
    """
    fingers = load_grip_fingers() if fingers is None else fingers
    L0 = {n: np.asarray(rest[n], dtype=float).T for n, _ in BONES}
    W0 = world_of(L0)
    B0 = {n: M.copy() for n, M in W0.items()}
    shift = pos(B0[CENTER])
    for n in B0:
        B0[n][:3, 3] -= shift                      # 腰（RIG_Center）を原点に
    seat = np.array(cockpit["seat_point"])
    c_w = np.array(cockpit["wheel_center"])
    axis = unit(np.array(cockpit["wheel_axis"]))
    hip_off = pos(B0[P + "RIG_Hips"])[1]
    ty = seat[1] + SEAT_CLEARANCE - hip_off        # 腰の骨が座面の上 SEAT_CLEARANCE
    ped_w = {"accel": np.array(cockpit["pedal_accel"]), "brake": np.array(cockpit["pedal_brake"])}

    cb = cockpit.get("column_box")
    col_box = None if cb is None else (np.array(cb["min"]) - KNEE_MARGIN, np.array(cb["max"]) + KNEE_MARGIN)

    def leaned(phi):
        B = {n: M.copy() for n, M in B0.items()}
        R = rot_axis(np.array([1.0, 0.0, 0.0]), np.radians(phi))      # +x まわりの正 = 上体が前へ
        _repose(B, CEST, about(R, pos(B[CEST])))
        _repose(B, HEAD, about(R.T, pos(B[HEAD])))                    # 頭は正面のまま
        return B

    r_grip = grip_radius(cockpit)
    top = rim_points(cockpit, 0.0, 1.0)[0][0] - c_w         # リムの面の中の「真上」

    def grip(B, t, a, sign, g):
        """握りの円の g 度の点に a 側の手のひらの中心を置くときの (点, 手の回転, 手首の目標)。体座標。"""
        arm, fore, hand, middle = side_bones(a)
        c_b = c_w - t
        pt = rim_points(cockpit, g, sign, r_grip)[0][0] - t
        radial = unit(pt - c_b - np.dot(pt - c_b, axis) * axis)
        tang = np.cross(axis, radial)
        if np.dot(tang, top) < 0:                      # 付け根の並びはリムの上の向き（人差し指が上）
            tang = -tang
        f0, l0, p0 = hand_frame(B, a)
        palm = -radial                                 # 手のひらをハンドルの中心（管）へ
        hs = 1.0 if a == "L" else -1.0                 # 右手は左手の鏡: 軸が鏡に映るので回す角度は逆
        f1 = np.cross(tang, palm) * hs
        tb, tn, tf = hs * np.radians(GRIP_TILT_DEG)
        Rt = rot_axis(f1, tf) @ rot_axis(palm, tn) @ rot_axis(tang, tb)
        Rh = Rt @ np.column_stack([f1, tang, palm]) @ np.column_stack([f0, l0, p0]).T
        return pt, Rh, pt - Rh @ ((pos(B[middle]) - pos(B[hand])) / 2)

    def arm_geom(B, a):
        arm, fore, hand, _ = side_bones(a)
        u, l = np.linalg.norm(pos(B[fore]) - pos(B[arm])), np.linalg.norm(pos(B[hand]) - pos(B[fore]))
        dmax = np.sqrt(u * u + l * l - 2 * u * l * np.cos(np.radians(180.0 - MIN_ELBOW_BEND)))
        return u, l, dmax

    def leg_targets(B, t):
        hips = {a: pos(B[P + "RIG_Leg_" + a]) for a in "LR"}
        pb = {k: v - t for k, v in ped_w.items()}
        d1 = np.linalg.norm(hips["L"] - pb["accel"]) + np.linalg.norm(hips["R"] - pb["brake"])
        d2 = np.linalg.norm(hips["L"] - pb["brake"]) + np.linalg.norm(hips["R"] - pb["accel"])
        ped = {"L": pb["accel"], "R": pb["brake"]} if d1 <= d2 else {"L": pb["brake"], "R": pb["accel"]}
        Rp = rot_axis(np.array([1.0, 0.0, 0.0]), PEDAL_PITCH)    # 爪先を下げる（+x まわりの正は +z 側が下）
        res = {}
        for a in "LR":
            leg, shin, hill, foot = (P + "RIG_Leg_" + a, P + "RIG_Shin_" + a, P + "RIG_Hill_" + a, P + "RIG_Foot_" + a)
            res[a] = (ped[a] - Rp @ (pos(B[foot]) - pos(B[hill])), Rp)
        return res

    def feasible(B, t, g, signs, with_legs):
        for a in "LR":
            arm = side_bones(a)[0]
            u, l, dmax = arm_geom(B, a)
            if np.linalg.norm(grip(B, t, a, signs[a], g)[2] - pos(B[arm])) > dmax:
                return False
        if with_legs:
            for a, (T, _) in leg_targets(B, t).items():
                leg, shin, hill = P + "RIG_Leg_" + a, P + "RIG_Shin_" + a, P + "RIG_Hill_" + a
                u = np.linalg.norm(pos(B[shin]) - pos(B[leg]))
                l = np.linalg.norm(pos(B[hill]) - pos(B[shin]))
                if np.linalg.norm(T - pos(B[leg])) > u + l - 0.005:
                    return False
                if col_box is not None:      # 膝がハンドルの柱の箱に入らない
                    knee = two_bone(pos(B[leg]), T, u, l, KNEE_POLE)[0] + t
                    if np.all(knee >= col_box[0]) and np.all(knee <= col_box[1]):
                        return False
        return True

    phis = np.arange(-6.0, MAX_LEAN + 0.01, 1.0)
    slides = np.arange(-SEAT_HALF_DEPTH, SEAT_HALF_DEPTH + 0.001, 0.02)
    cache = {float(p): leaned(p) for p in phis}
    best = None
    for g in np.arange(float(grip_deg), GRIP_MAX_DEG + 0.01, 1.0):       # 握りの高さが最優先
        for with_legs in (True, False):                                  # 同じ角度ならペダルに届く姿勢を先に
            cands = []
            for phi, B in cache.items():
                for d in slides:
                    t = np.array([seat[0], ty, seat[2] + d])
                    # 左右: 肩が近いほうの点へ
                    sh = {a: pos(B[side_bones(a)[0]]) + t for a in "LR"}
                    pl, pr = (rim_points(cockpit, g, sg, r_grip)[0][0] for sg in (1.0, -1.0))
                    sgn = {"L": 1.0, "R": -1.0} if (np.linalg.norm(sh["L"] - pl) + np.linalg.norm(sh["R"] - pr)
                                                   <= np.linalg.norm(sh["L"] - pr) + np.linalg.norm(sh["R"] - pl)) \
                        else {"L": -1.0, "R": 1.0}
                    if feasible(B, t, g, sgn, with_legs):
                        cands.append(((phi / MAX_LEAN) ** 2 + (d / SEAT_HALF_DEPTH) ** 2, phi, d, g, sgn, with_legs))
            if cands:
                best = min(cands, key=lambda c: c[0])
                break
        if best:
            break
    if best is None:
        raise UnreachableError("手がリムに届かない: 握り角 %g〜%g° のどれでも、前傾 %g° まで・腰の前後 ±%g m・肘の曲げ %g° 以上で、"
                               "両手がリムに届く姿勢が無い（ハンドルが遠い、または腕が短い）"
                               % (grip_deg, GRIP_MAX_DEG, MAX_LEAN, SEAT_HALF_DEPTH, MIN_ELBOW_BEND))
    _, phi, d, g, sgn, legs_ok = best
    t = np.array([seat[0], ty, seat[2] + d])
    B = {n: M.copy() for n, M in cache[float(phi)].items()}
    rep = {"grip_deg": float(g), "lean_deg": float(phi), "pelvis_slide_m": float(d), "legs_on_pedals": bool(legs_ok)}
    # 腕
    for a in "LR":
        arm, fore, hand, middle = side_bones(a)
        _, Rh, T = grip(B, t, a, sgn[a], g)
        pole = ARM_POLE * np.array([np.sign(pos(B[arm])[0] + t[0] - c_w[0]) or 1.0, 1.0, 1.0])
        R_lean = B[hand][:3, :3].copy()
        miss = _two_bone_chain(B, arm, fore, hand, T, pole, MIN_ELBOW_BEND)
        _repose(B, hand, about(Rh @ R_lean @ B[hand][:3, :3].T, pos(B[hand])))   # 手の向きを絶対値で決める
        rep.setdefault("hand_miss_m", {})[a] = float(miss)
        if miss > HAND_TOLERANCE:
            raise UnreachableError("手がリムに届かない: %s 側の手が %.3f m 外れた" % (a, miss))
    # 脚
    for a, (T, Rp) in leg_targets(B, t).items():
        leg, shin, hill = P + "RIG_Leg_" + a, P + "RIG_Shin_" + a, P + "RIG_Hill_" + a
        R_lean = B[hill][:3, :3].copy()
        miss = _two_bone_chain(B, leg, shin, hill, T, KNEE_POLE)
        _repose(B, hill, about(Rp @ R_lean @ B[hill][:3, :3].T, pos(B[hill])))
        rep.setdefault("leg_miss_m", {})[a] = float(miss)
    Wf = {}
    for n, _ in BONES:
        M = B[n].copy()
        M[:3, 3] += t                               # 剛体の動きだけ（拡大はしない）
        Wf[n] = M
    Wf["DRIVER:DRIVER"] = W0["DRIVER:DRIVER"]
    out = {}
    for n, p in BONES:
        out[n] = (L0[n] if p is None else np.linalg.inv(Wf[p]) @ Wf[n]).T.copy()
    out = curl_fingers(out, fingers)               # 指を曲げて握る（手首・中指の付け根の位置は変わらない）
    if report is not None:
        report.update(rep)
        report["elbow_bend_deg"] = elbow_bends(fk(out))
    return out


def elbow_bends(W):
    """肘の曲げ（伸ばしきりを 0° とする）。W は世界行列（行ベクトル規約）。"""
    res = {}
    for a in "LR":
        arm, fore, hand, _ = side_bones(a)
        v1, v2 = W[arm][3, :3] - W[fore][3, :3], W[hand][3, :3] - W[fore][3, :3]
        res[a] = 180.0 - float(np.degrees(np.arccos(np.clip(np.dot(v1, v2) / np.linalg.norm(v1) / np.linalg.norm(v2), -1, 1))))
    return res


def torso_lean_deg(W):
    """腰から首への向きの、鉛直からの前傾（前が正）。"""
    v = W[P + "RIG_Nek"][3, :3] - W[P + "RIG_Hips"][3, :3]
    return float(np.degrees(np.arctan2(v[2], v[1])))


def to_knh(local):
    """骨名 -> 親からの相対行列 から、BONES の木の形の KnhNode を作る。"""
    nodes = {n: knhmod.KnhNode(n, tuple(float(x) for x in np.asarray(local[n]).reshape(16))) for n, _ in BONES}
    root = None
    for n, p in BONES:
        if p is None:
            root = nodes[n]
        else:
            nodes[p].children.append(nodes[n])
    return root


def rest_from_kn5(path):
    import kn5io
    k = kn5io.read(path)
    got = {n.name: np.array(n.matrix, dtype=float).reshape(4, 4) for n in kn5io.walk(k.root) if n.cls == 1}
    return {n: got[n] for n, _ in BONES}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kn5", required=True)
    ap.add_argument("--cockpit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--grip-deg", type=float, default=60.0)
    a = ap.parse_args()
    rest = rest_from_kn5(a.kn5)
    rep = {}
    try:
        local = solve_seated(rest, json.load(open(a.cockpit, encoding="utf-8")), a.grip_deg, rep)
    except UnreachableError as e:
        sys.exit("driver_pose: " + str(e))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    knhmod.write(to_knh(local), a.out)
    print("wrote", a.out, json.dumps(rep, default=float))


if __name__ == "__main__":
    main()
