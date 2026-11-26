"""ハンドルを回すときの腕の動き（steer.ksanim）を作る。

  python3 tools/driver_steer.py --kn5 build/driver/kanachu_driver.kn5 --cockpit design/driver/cockpit.json \
      --lock 90 --out build/driver/steer.ksanim

座った姿勢（driver_pose.solve_seated）を土台に、コマごとにハンドルの回転角 θ（運転手から見て時計回りが正 = 右へ切る）を決め、
座った姿勢で握っている手を、ハンドルの軸（wheel_center を通り wheel_axis の向き）まわりに θ 回した位置・向きへ置く。
腕は driver_pose の 2 本骨 IK（肘は座った姿勢と同じ逃げ方向）で、毎コマ座った姿勢から解く（前のコマに依存しないので解が飛ばない）。
腕・手・指（RIG_Arm_* の子孫）以外の骨は全コマで座った姿勢のまま。

コマ i の角度: 借り物の steer.ksanim を読んだ結果、コマが増えると手は運転手から見て反時計回りに回っていた
（右手が 3 時から上へ）ので、θ_i = +lock − 2·lock·i/(frames−1)（lock = 片側の角度。コマ 0 = 時計回りいっぱい、最後 = 反時計回りいっぱい）。ゲームでの向きは Task 8 で確かめる。
手ごとに、座った握り点を回して届く（手首の取り残し STOP_MISS = 0.002 m 以内、肘の曲げ 15° 以上）区間を 1° 刻みで調べ、
θ がその外に出たら、その手は届く端のリムの上で止まる（リムの上を滑る。手は常にリムの上）。胴・鎖骨は動かさない。
座った姿勢の握り（手のひらは管の表面の外側、指は grip_fingers.json の曲げ）は、手から先を剛体のまま回すので全コマで保たれる。
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import driver_pose as dp  # noqa: E402
import ksanim  # noqa: E402
from driver_skeleton import BONES  # noqa: E402

FRAME0_SIGN = +1            # コマ 0 の向き: +1 = 時計回り（右）いっぱい。ゲームで逆なら -1 にする
MIN_BEND = 15.5             # 握りを続けられる肘の曲げの下限（度。試験の 15° に余裕を持たせる）
# 握りを続けられる手の取り残し（m）の上限。2026-11-26 改訂: 指を曲げて管を包む握りでは、手が目標から外れると
# 指と手のひらが管にめり込む（第 2 回の握りで、端のコマのめり込みは判定 0.02 m で 14.7 mm、0.005 m で 7.0 mm、0.002 m で 3.8 mm）。
# 外れ始める前に止めて滑らせる（試験の上限は 6 mm のめり込み。0.002 m で外側の手が一緒に回るのは 1°、0.02 m でも 10°）。
STOP_MISS = 0.002


def _ctx(seated, cockpit):
    c = np.array(cockpit["wheel_center"], dtype=float)
    axis = dp.unit(np.array(cockpit["wheel_axis"], dtype=float))
    W0 = {n: np.asarray(m).T for n, m in dp.fk(seated).items()}          # 列ベクトル規約の世界行列
    arms = {}
    for a in "LR":
        arm, fore, hand, _ = dp.side_bones(a)
        shoulder_x = dp.pos(W0[arm])[0] - c[0]
        arms[a] = (arm, fore, hand, dp.ARM_POLE * np.array([np.sign(shoulder_x) or 1.0, 1.0, 1.0]))
    return c, axis, W0, arms


def _solve_hand(c, axis, W0, spec, phi_deg, B=None):
    """握り点を座った姿勢の位置から軸まわりに phi 度回した所へ手を置く。B（世界行列）を書き換え、(取り残し m, 肘の曲げ度) を返す。"""
    arm, fore, hand, pole = spec
    B = {n: M.copy() for n, M in W0.items()} if B is None else B
    R = dp.rot_axis(axis, np.radians(phi_deg))
    target = c + R @ (dp.pos(W0[hand]) - c)                              # 手首も握り点と同じ円の上を回る
    miss = dp._two_bone_chain(B, arm, fore, hand, target, pole, MIN_BEND)
    dp._repose(B, hand, dp.about(R @ W0[hand][:3, :3] @ B[hand][:3, :3].T, dp.pos(B[hand])))   # 手の向きもハンドルと一緒に回る（指の曲げはそのまま）
    v1, v2 = dp.pos(B[arm]) - dp.pos(B[fore]), dp.pos(B[hand]) - dp.pos(B[fore])
    bend = 180.0 - float(np.degrees(np.arccos(np.clip(np.dot(v1, v2) / np.linalg.norm(v1) / np.linalg.norm(v2), -1, 1))))
    return float(miss), bend, B


def grip_arcs(seated, cockpit, step=1.0):
    """手ごとに、座った握り点から回して届く（取り残し ≤ STOP_MISS、肘の曲げ ≥ MIN_BEND）リムの角度の連続区間 (最小, 最大)。"""
    c, axis, W0, arms = _ctx(seated, cockpit)
    res = {}
    for a, spec in arms.items():
        def ok(phi):
            miss, bend, _ = _solve_hand(c, axis, W0, spec, phi)
            return miss <= STOP_MISS and bend >= MIN_BEND - 1e-6
        if not ok(0.0):
            raise dp.UnreachableError("手がリムに届かない: 座った握り点に %s 側の手が届かない" % a)
        lim = []
        for sg in (-1.0, 1.0):
            phi = 0.0
            while abs(phi) < 360.0 and ok(phi + sg * step):
                phi += sg * step
            lim.append(phi)
        res[a] = tuple(lim)
    return res


def grip_angles(seated, cockpit, lock_deg=90.0, frames=101):
    """手 -> コマごとの握り角（座った握り点から軸まわりに回した度、時計回り正）。届く区間の端で止まる（リムの上を滑る）。"""
    arcs = grip_arcs(seated, cockpit)
    out = {a: [] for a in "LR"}
    for i in range(frames):
        theta = FRAME0_SIGN * (lock_deg - 2 * lock_deg * i / (frames - 1))
        for a in "LR":
            out[a].append(float(np.clip(theta, *arcs[a])))
    return out


def build_steer(seated, rest, cockpit, lock_deg=90.0, frames=101):
    """骨名 -> コマ列（ksanim.Frame）。BONES の 56 本すべてを入れる。rest は互換のため受ける（使わない）。"""
    if frames < 2:
        raise ValueError("コマ数は 2 以上")
    c, axis, W0, arms = _ctx(seated, cockpit)
    moving = []
    for spec in arms.values():
        moving += [n for n in dp._desc(spec[0]) if n not in moving]
    phis = grip_angles(seated, cockpit, lock_deg, frames)
    tracks = {n: [] for n, _ in BONES}
    for i in range(frames):
        B = {n: M.copy() for n, M in W0.items()}
        for a, spec in arms.items():
            _solve_hand(c, axis, W0, spec, phis[a][i], B)
        for n, p in BONES:
            local = (np.linalg.inv(B[p]) @ B[n]).T if n in moving else np.asarray(seated[n])
            tracks[n].append(ksanim.from_matrix(local))
    return tracks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kn5", required=True)
    ap.add_argument("--cockpit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lock", type=float, default=90.0, help="片側の角度（度）。driver3d.ini の LOCK と同じ値。コマ 0〜最後が −lock〜+lock")
    ap.add_argument("--frames", type=int, default=101)
    ap.add_argument("--grip-deg", type=float, default=60.0)
    a = ap.parse_args()
    rest = dp.rest_from_kn5(a.kn5)
    cockpit = json.load(open(a.cockpit, encoding="utf-8"))
    try:
        seated = dp.solve_seated(rest, cockpit, a.grip_deg)
        tracks = build_steer(seated, rest, cockpit, a.lock, a.frames)
    except dp.UnreachableError as e:
        sys.exit("driver_steer: " + str(e))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    ksanim.write(tracks, a.out)
    print("wrote", a.out, "bones", len(tracks), "frames", a.frames, "lock", a.lock)


if __name__ == "__main__":
    main()
