#!/usr/bin/env python3
"""運転手の一式を作る入口。

  driver.build(out_car, out_driver_dir)
    out_driver_dir/kanachu_driver.kn5       … design/driver/kanachu_driver.blend から（Blender、tools/driver_to_kn5.py）
    out_car/driver_base_pos.knh             … 座った姿勢（tools/driver_pose.py。届かなければ失敗する）
    out_car/animations/steer.ksanim         … ハンドルを回す腕（tools/driver_steer.py）
    out_car/data/driver3d.ini               … driver3d_ini() の文字列

使い方: python3 tools/driver.py --car build/kanachu_route_bus --driver-dir build/driver
"""
import argparse
import subprocess
import sys
from pathlib import Path

import paths

ROOT = paths.WORK
BLEND = ROOT / "design" / "driver" / "kanachu_driver.blend"
COCKPIT = ROOT / "design" / "driver" / "cockpit.json"
DRIVER_NAME = "kanachu_driver"
LOCK_DEG = 90    # ハンドルの片側の角度（度）。AC は steer.ksanim のコマ 0〜最後を −LOCK〜+LOCK に割り当てる。driver_steer.py の --lock と driver3d.ini の LOCK は同じ値にする

# 自動変速の路線バス用の変速の手の動き（レーシングカーの値は使わない）。
# 変速は自動で、運転手の手は変速レバーをゆっくり動かす程度にする（時間はミリ秒）。
#   PRELOAD_RPM=2100 … 変速点（tools/spec.json の shift_up_rpm 2300 rpm）の少し手前から動き出す。回転は 2,600 rpm まで。
#   POSITIVE_TIME / NEGATIVE_TIME=250 … 押す・戻すを、レースの 100〜150 より遅くする。
#   BLEND_TIME=150 … 手の動きの切り替えをなめらかに。STATIC_TIME=10 は最小限の保持。
#   INVERT_SHIFTING_HANDS=0 … 右手でレバーを扱う標準の向き。
SHIFT = (("BLEND_TIME", 150), ("POSITIVE_TIME", 250), ("STATIC_TIME", 10), ("NEGATIVE_TIME", 250),
         ("PRELOAD_RPM", 2100), ("INVERT_SHIFTING_HANDS", 0))
HIDE = ("DRIVER:GEO_Driver_FACE", "DRIVER:HAIR", "DRIVER:CAP", "DRIVER:NECK")
# 運転席の視点で顔・髪・帽子・首の肌が目に入らないよう隠す（2026-11-26 ユーザー判断で首も隠す）。
# 首の肌は前は骨で動くメッシュ DRIVER:BODY_SUB3 で、HIDE_OBJECT で隠れなかった（試走のユーザーの画面）ので、
# 書き出しで頭の骨の固定メッシュ DRIVER:NECK にした（tools/driver_to_kn5.py、driver_skeleton.NECK_MESH）


# 運転士の頭の G による動き（AC 本体が driver3d.ini の [HEAD_MOVEMENT] を読む。書かないと既定の値で首が左右に傾く）。
# ユーザー判断（2026-11-26）: 首の左右の傾き（ROLL）とうなずき（PITCH）は止め、カーブの方へ顔を向ける動き（YAW）だけ少し残す。
#   角度は MAX_G の G で最大になり、それより小さい G では比例して小さくなる。路線バスの横 G は 0.3 G 前後なので、
#   MAX_G=0.3 で YAW 5° にする（普通のカーブで 5° ほど顔を向ける）。FILTER は G のならし（0 は不可）。
HEAD = (("FILTER", 0.15), ("MAX_G", 0.3), ("ROLL_MAX_DEG", 0), ("PITCH_MAX_DEG", 0), ("YAW_MAX_DEG", 5))


def driver3d_ini(lock_deg: float = LOCK_DEG) -> str:
    lock = ("%g" % lock_deg)
    lines = ["[MODEL]", "NAME=" + DRIVER_NAME, "POSITION=0,0,0", "",
             "[STEER_ANIMATION]", "NAME=steer.ksanim", "LOCK=" + lock, "",
             "[SHIFT_ANIMATION]"] + ["%s=%s" % kv for kv in SHIFT] + [""]
    lines += ["[HEAD_MOVEMENT]"] + ["%s=%g" % kv for kv in HEAD] + [""]
    for i, n in enumerate(HIDE):
        lines += ["[HIDE_OBJECT_%d]" % i, "NAME=" + n, ""]
    return "\n".join(lines)


def _run(cmd, what):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("運転手: %s に失敗\n%s%s" % (what, r.stdout[-800:], r.stderr[-800:]))
    return r


def build(out_car: Path, out_driver_dir: Path) -> None:
    out_car, out_driver_dir = Path(out_car), Path(out_driver_dir)
    kn5 = out_driver_dir / (DRIVER_NAME + ".kn5")
    out_driver_dir.mkdir(parents=True, exist_ok=True)
    kn5.unlink(missing_ok=True)
    _run([paths.BLENDER, "-b", BLEND, "--python", ROOT / "tools/driver_to_kn5.py", "--", "--out", kn5], "kn5 の書き出し")
    if not kn5.is_file():
        raise RuntimeError("運転手: kn5 ができていない: %s" % kn5)
    (out_car / "animations").mkdir(parents=True, exist_ok=True)
    (out_car / "data").mkdir(parents=True, exist_ok=True)
    _run([sys.executable, ROOT / "tools/driver_pose.py", "--kn5", kn5, "--cockpit", COCKPIT,
          "--out", out_car / "driver_base_pos.knh"], "座った姿勢（届かない可能性）")
    _run([sys.executable, ROOT / "tools/driver_steer.py", "--kn5", kn5, "--cockpit", COCKPIT, "--lock", LOCK_DEG,
          "--out", out_car / "animations" / "steer.ksanim"], "ハンドルの動き")
    (out_car / "data" / "driver3d.ini").write_text(driver3d_ini(LOCK_DEG), encoding="utf8", newline="\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--car", default=str(paths.BUILD))
    ap.add_argument("--driver-dir", default=str(paths.BUILD.parent / "driver"))
    a = ap.parse_args()
    build(Path(a.car), Path(a.driver_dir))
    print("WROTE", a.car, a.driver_dir)
