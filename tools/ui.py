"""ui/ui_car.json・ui/badge.png・車フォルダの logo.png。絵は design/ui/ のもの。"""
import argparse
import json
import math
import shutil
from pathlib import Path

import paths
import physics
import spec

BHP = 227          # 169 kW
TORQUE = "773Nm"
WEIGHT = "9790kg"
TOPSPEED = "110km/h"
DESIGN_UI = paths.WORK / "design" / "ui"
DESCRIPTION = (
    "神奈川中央交通の路線バス（大型ノンステップ）。基準車種はいすゞ エルガ LV290 N 代（全長 10,430 mm・車両重量 9,790 kg、"
    "4HK1-TCH 169 kW・773 N·m、6 速 AT。いすゞ公式の主要諸元表による）。塗装は旧塗装（標準色、1949〜）と"
    "新塗装（2023〜、奥山清行氏デザイン。ニュースリリースによる）の 2 種。エンジン音は Pixabay の効果音から "
    "FMOD 1.08.12 で作った自作の音。最高速 110 km/h はギア比とリミッターからの計算値で、実測ではない。個人利用のみ・再配布不可。\n"
    "Kanachu city bus, large non-step type. Based on the Isuzu Erga LV290 N-size (10,430 mm, 9,790 kg curb weight, "
    "4HK1-TCH 169 kW / 773 N·m, 6-speed AT; official Isuzu spec sheet). Two liveries: the Kanachu standard livery "
    "(since 1949) and the new livery (since 2023, designed by Kiyoyuki (Ken) Okuyama per the press release). "
    "Top speed (110 km/h) is calculated from gearing and the limiter, not measured. Engine sound is built from Pixabay sound effects with FMOD 1.08.12. Personal use only, not for redistribution.")


def curves():
    """表示用のエンジン曲線 [rpm, Nm] / [rpm, bhp]。power.lut から駆動損失を除いたクランク値。"""
    lut = physics.make_power_lut(spec.load(), factor=1.0)
    torque = [[0.0, 0.0]] + [[float(r), float(nm)] for r, nm in lut]
    power = [[0.0, 0.0]] + [[float(r), round(nm * r * 2 * math.pi / 60 / 745.7, 1)] for r, nm in lut]
    return torque, power


# year 2019: 基準車の世代 2DG-LV290N3（ふ43 の写真が docs/research/erga_specs.md にある）
def card():
    torque, power = curves()
    return {
        "name": "Kanachu City Bus (Large Non-step)",
        "brand": "Kanachu",
        "description": DESCRIPTION,
        "tags": ["#bus", "city bus", "diesel", "rwd", "street"],
        "class": "street",
        "specs": {"bhp": "%dbhp" % BHP, "torque": TORQUE, "weight": WEIGHT, "topspeed": TOPSPEED,
                  "acceleration": "--s", "pwratio": "%.1fkg/HP" % (9790 / BHP)},
        "torqueCurve": torque, "powerCurve": power,
        "country": "Japan", "author": "ac_kanachu_bus", "version": "0.1", "year": 2019,
    }


def build(out=None):
    out = Path(out or paths.BUILD)
    d = out / "ui"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ui_car.json").write_text(json.dumps(card(), ensure_ascii=False, indent=2), encoding="utf8")
    shutil.copyfile(DESIGN_UI / "badge.png", d / "badge.png")
    shutil.copyfile(DESIGN_UI / "logo.png", out / "logo.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(paths.BUILD))
    build(ap.parse_args().out)
