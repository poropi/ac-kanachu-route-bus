"""座った姿勢を解いて driver_base_pos.knh を書く。

  python3 tools/driver_pose.py --kn5 build/driver/kanachu_driver.kn5 --cockpit design/driver/cockpit.json \
      --out build/driver/driver_base_pos.knh

入力: 運転手 kn5 の種類 1 のノード（骨名 -> 親からの相対行列。kn5 と同じ行ベクトル規約: 世界 = 自分 @ 親、
平行移動は 4 行目）、`cockpit.json`（kn5 座標）。出力: 骨名 -> 親からの相対行列 4x4（同じ規約）。

方法（体は骨の長さのまま、世界座標で解く。骨の向きには依存しない = 各骨の回転は「今の向きからの最小回転」で作る）:
 1. 体を「腰（RIG_Center）を原点に置いた体の座標」で作る。上半身（RIG_Cest 以下）を背もたれの角度だけ後ろへ倒し、
    頭は元の向き（正面）に戻す。目 = 頭の骨 + EYE_OFFSET（頭の骨から目までの、体の向きでの上・前の寸法）。
 2. 腰を座面の上 SEAT_CLEARANCE に置き、体全体の一様な拡大率 s と腰の位置 t を、目が DRIVER_EYE に一致するように決める
    （目の上下の高さは腰からの距離が s 倍になる）。s は RIG_Center の行列に入る（子の行列には入らない）。
    s が 1 から大きくずれるのは、モデルの大きさがこの運転席の目の高さに合っていないということ。
 3. 腕: リムの「真上から左右に grip_deg」の 2 点を、肩の位置が近い腕へ割り当てる（骨の名前の L/R は見ない）。
    手のひらの中心 = 手首の骨と中指の付け根の中点。リムの中心線の点に手のひらを置く。
    2 本の骨（上腕・前腕）の解析的 IK（余弦定理）、肘は下と外へ逃がす。手の向きは、指がリムの接線（運転手から遠ざかる向き）に沿うように。
 4. 脚: 腰の位置に近いペダルへ足を割り当て（アクセルは右足の側）、足の母指球（足先の骨）をペダルの踏面に置く。
    2 本の骨（腿・すね）の解析的 IK、膝は前と上へ逃がす。足首の骨は PEDAL_PITCH だけ爪先を下げる。
 5. 世界行列から親からの相対行列を作る（拡大率は RIG_Center だけが持つ）。
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
SEAT_CLEARANCE = 0.08                        # 腰の骨が座面の上にある高さ (m)
EYE_OFFSET = np.array([0.0, 0.06, 0.09])     # 頭の骨から目まで（体の座標: 上 +y、前 +z）(m)
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


def pos(M):
    return M[:3, 3].copy()


def side_bones(arm):
    """腕の骨 (Arm, ForeArm, Hand, Middle1)。arm は 'L' / 'R'。"""
    hand = P + "RIG_HAND_" + arm
    middle = next(c for c in CHILDREN[hand] if "Middle" in c)
    return P + "RIG_Arm_" + arm, P + "RIG_ForeArm_" + arm, hand, middle


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


def _two_bone_chain(B, b1, b2, end, target, pole):
    """b1（付け根）・b2（関節）の 2 本で、end の骨の原点を target に置く（B を書き換える）。"""
    S = pos(B[b1])
    u = np.linalg.norm(pos(B[b2]) - S)
    l = np.linalg.norm(pos(B[end]) - pos(B[b2]))
    E, T = two_bone(S, target, u, l, pole)
    _repose(B, b1, about(rot_between(pos(B[b2]) - S, E - S), S))
    _repose(B, b2, about(rot_between(pos(B[end]) - E, T - E), E))
    return float(np.linalg.norm(target - T))     # 届かなかった距離


# ---------- 本体 ----------
def rim_points(cockpit, grip_deg, sign=None):
    """リムの管の中心線上の、真上（面の中の上向き）から grip_deg の左右の 2 点。sign=±1 なら片側の 1 点だけ。"""
    c = np.array(cockpit["wheel_center"])
    n = unit(np.array(cockpit["wheel_axis"]))
    up = np.array([0.0, 1.0, 0.0])
    ip = up - np.dot(up, n) * n                  # リムの面の中の「真上」
    if np.linalg.norm(ip) < 1e-6:
        ip = np.array([0.0, 0.0, 1.0]) - n[2] * n
    ip = unit(ip)
    lat = np.cross(n, ip)
    g = np.radians(grip_deg)
    r = cockpit["rim_radius"]
    return [c + r * (np.cos(g) * ip + sg * np.sin(g) * lat) for sg in ((1.0, -1.0) if sign is None else (sign,))], n


def solve_seated(rest, cockpit, grip_deg=60.0, report=None):
    """report に dict を渡すと、拡大率 scale・手の実際の握り角 grip_deg・IK で届かなかった距離 arm_miss_m / leg_miss_m (m) を入れる。"""
    L0 = {n: np.asarray(rest[n], dtype=float).T for n, _ in BONES}
    W0 = world_of(L0)
    B = {n: M.copy() for n, M in W0.items()}
    shift = pos(B[CENTER])
    for n in B:
        B[n][:3, 3] -= shift
    # 1. 上半身を後ろへ倒し、頭は正面に戻す
    th = np.radians(cockpit["backrest_angle_deg"])
    Rl = rot_axis(np.array([1.0, 0.0, 0.0]), -th)
    _repose(B, CEST, about(Rl, pos(B[CEST])))
    _repose(B, HEAD, about(Rl.T, pos(B[HEAD])))
    eye_b = pos(B[HEAD]) + EYE_OFFSET
    # 2. 拡大率 s と腰の位置 t
    eye, seat = np.array(cockpit["eye"]), np.array(cockpit["seat_point"])
    hip_y = seat[1] + SEAT_CLEARANCE
    s = (eye[1] - hip_y) / eye_b[1]
    t = np.array([eye[0] - s * eye_b[0], hip_y, eye[2] - s * eye_b[2]])

    def body(p):
        return (np.asarray(p) - t) / s

    # 3. 腕
    c_b = body(cockpit["wheel_center"])
    axis = unit(np.array(cockpit["wheel_axis"]))
    sh = {a: pos(B[side_bones(a)[0]]) for a in "LR"}
    pts = [body(p) for p in rim_points(cockpit, grip_deg)[0]]
    straight = np.linalg.norm(sh["L"] - pts[0]) + np.linalg.norm(sh["R"] - pts[1])
    swapped = np.linalg.norm(sh["L"] - pts[1]) + np.linalg.norm(sh["R"] - pts[0])
    sign = {"L": 1.0, "R": -1.0} if straight <= swapped else {"L": -1.0, "R": 1.0}
    got = {}
    for a in "LR":
        arm, fore, hand, middle = side_bones(a)
        reach = np.linalg.norm(pos(B[fore]) - pos(B[arm])) + np.linalg.norm(pos(B[hand]) - pos(B[fore]))
        finger = pos(B[middle]) - pos(B[hand])
        palm0 = finger / 2
        pole = ARM_POLE * np.array([np.sign(sh[a][0] - c_b[0]) or 1.0, 1.0, 1.0])

        def at(g):
            """リムの g 度（真上から、sign の側）の点に手のひらを置くときの (点, 手の回転, 手首の目標)。"""
            pt = body(rim_points(cockpit, g, sign[a])[0][0])
            radial = unit(pt - c_b - np.dot(pt - c_b, axis) * axis)
            tang = np.cross(axis, radial)
            if np.dot(tang, pt - sh[a]) < 0:
                tang = -tang
            Rh = rot_between(finger, tang)               # 指をリムの接線へ
            return pt, Rh, pt - Rh @ palm0

        g = float(grip_deg)
        while g < 160 and np.linalg.norm(at(g)[2] - sh[a]) > reach - 0.01:
            g += 1.0          # 届かなければリムに沿って運転手に近い側へずらす
        got[a] = g
        pt, Rh, T = at(g)
        R_lean = B[hand][:3, :3].copy()
        miss = _two_bone_chain(B, arm, fore, hand, T, pole)
        _repose(B, hand, about(Rh @ R_lean @ B[hand][:3, :3].T, pos(B[hand])))   # 手の向きを絶対値で決める
        if report is not None:
            report.setdefault("arm_miss_m", {})[a] = miss * s
    if report is not None:
        report["grip_deg"] = got
    # 4. 脚
    pedals = {"accel": body(cockpit["pedal_accel"]), "brake": body(cockpit["pedal_brake"])}
    hips = {a: pos(B[P + "RIG_Leg_" + a]) for a in "LR"}
    d1 = np.linalg.norm(hips["L"] - pedals["accel"]) + np.linalg.norm(hips["R"] - pedals["brake"])
    d2 = np.linalg.norm(hips["L"] - pedals["brake"]) + np.linalg.norm(hips["R"] - pedals["accel"])
    ped = {"L": pedals["accel"], "R": pedals["brake"]} if d1 <= d2 else {"L": pedals["brake"], "R": pedals["accel"]}
    for a in "LR":
        leg, shin, hill, foot = (P + "RIG_Leg_" + a, P + "RIG_Shin_" + a, P + "RIG_Hill_" + a, P + "RIG_Foot_" + a)
        lat = np.array([1.0, 0.0, 0.0])
        Rp = rot_axis(lat, PEDAL_PITCH)                # +x まわりの正の回転は +z（前）側を下へ
        vec = Rp @ (pos(B[foot]) - pos(B[hill]))       # 足首 -> 母指球 を傾けた後の向き
        R_lean = B[hill][:3, :3].copy()
        miss = _two_bone_chain(B, leg, shin, hill, ped[a] - vec, KNEE_POLE)
        if report is not None:
            report.setdefault("leg_miss_m", {})[a] = miss * s
        _repose(B, hill, about(Rp @ R_lean @ B[hill][:3, :3].T, pos(B[hill])))
    if report is not None:
        report["scale"] = float(s)
    # 5. 世界行列 -> 親からの相対行列。拡大率と腰の位置は RIG_Center だけが持つ
    Wf = {}
    for n, _ in BONES:
        M = B[n].copy()
        M[:3, :3] *= s
        M[:3, 3] = t + s * B[n][:3, 3]
        Wf[n] = M
    Wf["DRIVER:DRIVER"] = W0["DRIVER:DRIVER"]
    out = {}
    for n, p in BONES:
        out[n] = (L0[n] if p is None else np.linalg.inv(Wf[p]) @ Wf[n]).T.copy()
    return out


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


def eye_position(local, rest):
    """解いた姿勢での目の世界位置。EYE_OFFSET は頭の骨の正面の向きで測る（rest の頭の骨の向きで頭の座標へ直す）。"""
    Wr = world_of({n: np.asarray(rest[n], dtype=float).T for n, _ in BONES})
    off_local = Wr[HEAD][:3, :3].T @ EYE_OFFSET
    Wp = world_of({n: np.asarray(local[n], dtype=float).T for n, _ in BONES})
    return (Wp[HEAD] @ np.append(off_local, 1.0))[:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kn5", required=True)
    ap.add_argument("--cockpit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--grip-deg", type=float, default=60.0)
    a = ap.parse_args()
    rest = rest_from_kn5(a.kn5)
    local = solve_seated(rest, json.load(open(a.cockpit, encoding="utf-8")), a.grip_deg)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    knhmod.write(to_knh(local), a.out)
    print("wrote", a.out, "scale %.3f" % np.linalg.norm(np.asarray(local[CENTER])[0, :3]))


if __name__ == "__main__":
    main()
