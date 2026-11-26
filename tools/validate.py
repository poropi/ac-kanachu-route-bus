#!/usr/bin/env python3
"""成果物フォルダの検査。validate(car_dir) -> 問題のリスト（空なら合格）。

使い方: python3 tools/validate.py [<car_dir>] [--box]（運転手の kn5 は <car_dir>/../driver/kanachu_driver.kn5）
"""
import json
import sys
import tempfile
from pathlib import Path

import driver_skeleton
import kn5io
import knh
import ksanim
import paths
import physics

MAIN = paths.CAR_NAME + ".kn5"
NODES = ("WHEEL_LF", "WHEEL_RF", "WHEEL_LR", "WHEEL_RR", "SUSP_LF", "SUSP_RF", "SUSP_LR", "SUSP_RR",
         "STEER_HR", "COCKPIT_HR")
# COCKPIT_HR（運転席まわり）がある主 kn5 に必須の名前。kn5 に入る名前は Blender の ARROW_SPEED・ARROW_RPM・DRIVER_EYE（空オブジェクト）
COCKPIT_NODES = ("ARROW_SPEED", "ARROW_RPM", "DRIVER_EYE")
# 無いと CSP が落ちる運転手の 3 ファイル（空でないことも見る）
DRIVER_FILES = ("driver_base_pos.knh", "animations/steer.ksanim", "data/driver3d.ini")
# 必須ファイルは「動く 3 台すべてにあるもの」から決めた（計画書ではなく実物）。3 台:
#   ks_toyota_ae86（Kunos、data.acd）、tky_bus_jetset（バス MOD、data/ 展開）、nix_suzuki_swift_sport_ht81s（data.acd）。
# data.acd は data/ と同等とみなし、data/*.ini の名前で比べた（ae86 は tools/acd.read_acd、HT81S は展開済みの data）。
# skins/ は別途検査する。車名入りのファイル（主 kn5・sfx/<車名>.bank）は車名だけ置き換えて必須。
COMMON_FILES = ["collider.kn5", "driver_base_pos.knh", "animations/steer.ksanim", "body_shadow.png",
                "tyre_0_shadow.png", "tyre_1_shadow.png", "tyre_2_shadow.png", "tyre_3_shadow.png",
                "logo.png", "ui/ui_car.json", "ui/badge.png"]
COMMON_DATA = ("aero.ini ai.ini ambient_shadows.ini brakes.ini cameras.ini car.ini colliders.ini damage.ini "
               "dash_cam.ini digital_instruments.ini driver3d.ini drivetrain.ini electronics.ini engine.ini "
               "escmode.ini lights.ini lods.ini mirrors.ini power.lut proview_nodes.ini setup.ini sounds.ini "
               "suspension_graphics.ini suspensions.ini throttle.lut tyres.ini wing_animations.ini "
               "wing_body_AOA_CD.lut wing_body_AOA_CL.lut wing_front_AOA_CD.lut wing_front_AOA_CL.lut "
               "wing_rear_AOA_CD.lut wing_rear_AOA_CL.lut").split()
# 3 台に共通だが M1 では未実装のもの。実機で M1 がこれ無しで動いたので外す（M2 以降で足す）。
# driver3d.ini / driver_base_pos.knh / steer.ksanim は無いと落ちるので、ここに入れない。
M1_ABSENT = {"data/digital_instruments.ini", "data/escmode.ini", "data/proview_nodes.ini",
             "data/suspension_graphics.ini", "data/throttle.lut", "data/wing_animations.ini",
             "data/wing_front_AOA_CD.lut", "data/wing_front_AOA_CL.lut", "data/wing_rear_AOA_CD.lut",
             "data/wing_rear_AOA_CL.lut"}
# 3 台の共通ではないが、この MOD 自身が使う（バス MOD と HT81S は固有の GUIDs.txt を持つ）
OWN_FILES = ["sfx/GUIDs.txt", "data/analog_instruments.ini"]   # 針（ARROW_SPEED・ARROW_RPM）を回す
COMMON_ALL = COMMON_FILES + ["data/" + n for n in COMMON_DATA]   # 3 台すべてにある物（車名入りを除く）
FIXED = [MAIN, "sfx/%s.bank" % paths.CAR_NAME] + OWN_FILES + [f for f in COMMON_ALL if f not in M1_ABSENT]
SKIN_FILES = ("ui_skin.json", "livery.png", "preview.jpg")
MAX_VERTS = 65535


def data_files():
    with tempfile.TemporaryDirectory() as t:
        return physics.build(t)


def mesh_children_problems(root):
    """Kunos の kn5 はメッシュが葉だけ。メッシュに子があると CSP が Node::Node で落ちた。"""
    return ["メッシュ %s に子ノードがある（dummy の下に <名前>_GEO として置く）" % n.name
            for n in kn5io.walk(root) if n.cls == 2 and n.children]


def axis_problems(root):
    """針とハンドルは AC がローカル Z まわりに回す。(1) 子メッシュはローカル Z 方向にいちばん薄い（文字盤・リム面の法線）、
    (2) 世界のローカル Z は運転手の目から回転中心へ向かう方向と同じ向き（遠ざかる向き。HT81S と同じ）。
    目は DRIVER_EYE ノード。針・ハンドル（ARROW_SPEED・ARROW_RPM・STEER_HR）のどれも無いビルドは対象外。STEER_HR だけでも検査する。"""
    import numpy as np
    world = {}

    def walk(n, M):
        if n.cls == 1 and n.matrix is not None:
            M = M @ np.array(n.matrix).reshape(4, 4).T
        if n.cls == 1:
            world[n.name] = (n, M)
        for c in n.children:
            walk(c, M)
    walk(root, np.eye(4))
    if not any(n in world for n in ("ARROW_SPEED", "ARROW_RPM", "STEER_HR")):
        return []
    if "DRIVER_EYE" not in world:
        return ["DRIVER_EYE が無い"]
    eye = world["DRIVER_EYE"][1][:3, 3]
    bad = []

    def local_points(n, M, out):
        for c in n.children:
            Mc = M
            if c.cls == 1 and c.matrix is not None:
                Mc = M @ np.array(c.matrix).reshape(4, 4).T
            if c.cls == 2 and len(c.vertices):
                v = np.frombuffer(c.vertices, "<f4").reshape(-1, 11)[:, :3].astype("f8")
                out.append(v @ Mc[:3, :3].T + Mc[:3, 3])
            local_points(c, Mc, out)
    for name in ("ARROW_SPEED", "ARROW_RPM", "STEER_HR"):
        if name not in world:
            continue
        n, M = world[name]
        z = M[:3, 2] / np.linalg.norm(M[:3, 2])
        if float(z @ (M[:3, 3] - eye)) <= 0:
            bad.append("%s のローカル Z が運転手の方を向いている（目から回転中心への向きと逆）" % name)
        pts = []
        local_points(n, np.eye(4), pts)
        if not pts:
            bad.append("%s の下にメッシュが無い" % name)
            continue
        ext = np.vstack(pts).max(0) - np.vstack(pts).min(0)
        if not (ext[2] < ext[0] and ext[2] < ext[1]):
            bad.append("%s の子メッシュがローカル Z 方向に薄くない（範囲 %s）" % (name, tuple(round(float(x), 3) for x in ext)))
    return bad


def collider_problems(root):
    """AC は root -> mesh の 2 階層だと initPhysics で落ちる。mesh の親は root ではない dummy でなければならない。"""
    bad = []

    def walk(n, parent):
        if n.cls == 2 and (parent is None or parent.cls != 1 or parent is root):
            bad.append("collider.kn5 の mesh %s の親が root か dummy でない（root -> dummy -> mesh が要る）" % n.name)
        for c in n.children:
            walk(c, n)
    walk(root, None)
    return bad


def mirror_problems(k, mirrors_ini):
    """data/mirrors.ini の NAME が主 kn5 のメッシュで、マテリアル mirror・UV が u 0〜1／v −1〜0 の範囲いっぱいか。"""
    import re
    import numpy as np
    names = re.findall(r"(?m)^NAME=(.+?)\s*$", mirrors_ini)
    meshes = {n.name: n for n in kn5io.walk(k.root) if n.cls == 2}
    bad = []
    for nm in names:
        n = meshes.get(nm)
        if n is None:
            bad.append("mirrors.ini の %s が主 kn5 に無い" % nm); continue
        if k.materials[n.matid].name != "mirror":
            bad.append("鏡 %s のマテリアルが mirror でない（%s）" % (nm, k.materials[n.matid].name))
        uv = np.frombuffer(n.vertices, "<f4").reshape(-1, 11)[:, 6:8]
        if not (abs(uv[:, 0].min()) < 0.01 and abs(uv[:, 0].max() - 1) < 0.01 and abs(uv[:, 1].min() + 1) < 0.01 and abs(uv[:, 1].max()) < 0.01):
            bad.append("鏡 %s の UV が 0〜1 いっぱいでない" % nm)
    return bad


def driver_problems(car, driver_kn5):
    """運転手の検査。種類 1 のノードに driver_skeleton.BONES の骨が全部ある（欠けは問題。骨でも、メッシュの入れ物（SKINNED_MESHES・HEAD_MESHES）でもない余分な名前も問題）、knh に全骨、ksanim の軌跡が骨の数、
    driver3d.ini の MODEL NAME が運転手の kn5 のファイル名（拡張子なし）と同じ。"""
    car, driver_kn5 = Path(car), Path(driver_kn5)
    want = [n for n, _ in driver_skeleton.BONES]
    bad = []
    if not driver_kn5.is_file() or driver_kn5.stat().st_size == 0:
        bad.append("運転手の kn5 が無い／空: %s" % driver_kn5)
    else:
        try:
            got = {n.name for n in kn5io.walk(kn5io.read(driver_kn5).root) if n.cls == 1}
        except Exception as e:
            got = None
            bad.append("%s を読めない: %s" % (driver_kn5.name, e))
        if got is not None:
            bad += ["%s に骨 %s が無い" % (driver_kn5.name, n) for n in want if n not in got]
            okay = set(want) | set(driver_skeleton.SKINNED_MESHES) | set(driver_skeleton.HEAD_MESHES)   # メッシュの入れ物も種類 1
            bad += ["%s に余分な種類 1 のノード %s がある" % (driver_kn5.name, n) for n in sorted(got - okay)]
    f = car / "driver_base_pos.knh"
    if f.is_file() and f.stat().st_size:
        try:
            have = {n.name for n in knh.walk(knh.read(f))}
            bad += ["driver_base_pos.knh に骨 %s が無い" % n for n in want if n not in have]
        except Exception as e:
            bad.append("driver_base_pos.knh を読めない: %s" % e)
    f = car / "animations" / "steer.ksanim"
    if f.is_file() and f.stat().st_size:
        try:
            if len(ksanim.read(f)) != len(want):
                bad.append("steer.ksanim の軌跡が %d 本（骨は %d 本）" % (len(ksanim.read(f)), len(want)))
        except Exception as e:
            bad.append("steer.ksanim を読めない: %s" % e)
    f = car / "data" / "driver3d.ini"
    if f.is_file() and f.stat().st_size:
        try:
            name = physics.read_ini(f).get("MODEL", {}).get("NAME")
        except Exception as e:
            name = None
            bad.append("driver3d.ini を読めない: %s" % e)
        else:
            if name != driver_kn5.stem:
                bad.append("driver3d.ini の MODEL NAME=%s が運転手の kn5 の名前 %s と違う" % (name, driver_kn5.stem))
    return bad


def validate(car_dir, warnings=None, cockpit=True, driver_kn5=None):
    """問題のリストを返す。cockpit=False は M1 の箱（針・目のノードが無い）用で、COCKPIT_NODES を必須にしない。driver_kn5（運転手の kn5 のパス）を渡すと運転手の中身も検査する（None なら車のフォルダの運転手のファイルが空でないことだけ）。warnings（list）を渡すと、M1_ABSENT のうち無いものを 1 行で追記する（合否には影響しない）。"""
    car = Path(car_dir)
    bad = []
    if not car.is_dir():
        return ["フォルダが無い: %s" % car]
    for f in FIXED + ["data/" + n for n in data_files()]:
        if not (car / f).is_file():
            bad.append("無い: " + f)
    for f in DRIVER_FILES:
        if (car / f).is_file() and (car / f).stat().st_size == 0:
            bad.append("空: " + f)
    if warnings is not None:
        gone = sorted(f for f in M1_ABSENT if not (car / f).is_file())
        if gone:
            warnings.append("3 台の動く車に共通だがこのビルドには無い: " + ", ".join(gone))
    if (car / "data.acd").exists():
        bad.append("data.acd がある（M1 は展開した data/ を使う）")
    for kn in (MAIN, "collider.kn5"):
        if (car / kn).is_file():
            try:
                k = kn5io.read(car / kn)
            except Exception as e:
                bad.append("%s を読めない: %s" % (kn, e))
                continue
            nodes = list(kn5io.walk(k.root))
            if kn == MAIN:
                names = {n.name for n in nodes}
                need = NODES + (COCKPIT_NODES if cockpit and "COCKPIT_HR" in names else ())
                bad += ["%s に %s が無い" % (kn, n) for n in dict.fromkeys(need) if n not in names]
                if "DRIVER_EYE" in names:          # 無いときは上で指摘済み
                    bad += axis_problems(k.root)
                mi = car / "data" / "mirrors.ini"
                if mi.is_file() and "Mirror_Starboard_Main_Surface" in names:   # 外装モデル（M1 の箱には鏡が無い）
                    bad += mirror_problems(k, mi.read_text(encoding="utf8"))
            bad += ["%s: %s" % (kn, p) for p in mesh_children_problems(k.root)]
            if kn == "collider.kn5":
                bad += collider_problems(k.root)
            for n in nodes:
                nv = len(n.vertices) // 44
                if n.cls == 2 and nv > MAX_VERTS:
                    bad.append("%s の %s が頂点 %d > %d" % (kn, n.name, nv, MAX_VERTS))
    if driver_kn5 is not None:
        bad += driver_problems(car, driver_kn5)
    skins = [d for d in (car / "skins").iterdir() if d.is_dir()] if (car / "skins").is_dir() else []
    if not skins:
        bad.append("skins/ にスキンが 1 つも無い")
    for s in skins:
        bad += ["無い: skins/%s/%s" % (s.name, f) for f in SKIN_FILES if not (s / f).is_file()]
    ui = car / "ui" / "ui_car.json"
    if ui.is_file():
        try:
            json.loads(ui.read_text(encoding="utf8"))
        except Exception as e:
            bad.append("ui_car.json が JSON でない: %s" % e)
    return bad


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--box"]      # --box: M1 の箱のビルド
    d = args[0] if args else str(paths.BUILD)
    warns = []
    problems = validate(d, warns, cockpit="--box" not in sys.argv, driver_kn5=Path(d).parent / "driver" / "kanachu_driver.kn5")
    for w in warns:
        print("WARN: " + w)
    if problems:
        print("\n".join("NG " + p for p in problems))
        sys.exit(1)
    print("OK")
