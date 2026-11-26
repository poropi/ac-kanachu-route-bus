"""灯火の設定。data/lights.ini（AC 本体）と extension/ext_config.ini（CSP）を作る。

ノード名は主 kn5 に実在するメッシュ名（tests が kn5 と突き合わせる）。座標は kn5 座標（x 左、y 上、z 前）。
書式は nix_suzuki_swift_sport_ht81s の lights.ini（VERSION=3）と extension/ext_config.ini に合わせた。
"""
import numpy as np

import kn5io

HEAD = ["LIGHT_HEAD_L", "LIGHT_HEAD_R"]
TAIL = ["LIGHT_TAIL_L", "LIGHT_TAIL_R"]
BRAKE = ["LIGHT_BRAKE_L", "LIGHT_BRAKE_R"]
IND = {"LEFT": {"FRONT": "LIGHT_IND_FL", "REAR": "LIGHT_IND_RL"},
       "RIGHT": {"FRONT": "LIGHT_IND_FR", "REAR": "LIGHT_IND_RR"}}
REVERSE = ["LIGHT_REVERSE_L", "LIGHT_REVERSE_R"]
DEST = ["DEST_FRONT", "DEST_SIDE", "DEST_REAR"]
ALL_NODES = HEAD + TAIL + BRAKE + [n for s in IND.values() for n in s.values()] + REVERSE + DEST


def lights_ini():
    """data/lights.ini。ヘッドライトとテールは点灯で光り、ブレーキ灯は踏むと明るくなる。
    ウインカーとバック灯は CSP の ext_config.ini 側。"""
    secs = ["[HEADER]\nVERSION=3\n"]
    for i, n in enumerate(HEAD + TAIL):
        secs.append("[LIGHT_%d]\nNAME=%s\nCOLOR=%s\n" % (i, n, "10,10,13" if n in HEAD else "6,0.4,0.3"))
    for i, n in enumerate(BRAKE):
        secs.append("[BRAKE_%d]\nNAME=%s\nCOLOR=%s\nOFF_COLOR=%s\n" % (i, n, "150,75,50", "30,10,5"))
    return "\n".join(secs)


def node_centers(kn5_path, names=ALL_NODES):
    """主 kn5 の各メッシュの頂点の中心（kn5 座標）。"""
    k = kn5io.read(str(kn5_path))
    out = {}

    def walk(n, M):
        if n.cls == 1 and n.matrix is not None:
            M = M @ np.array(n.matrix).reshape(4, 4).T
        if n.cls == 2 and n.name in names and n.name not in out:
            v = np.frombuffer(n.vertices, np.float32).reshape(-1, 11)[:, :3].astype(np.float64)
            out[n.name] = tuple(float(x) for x in ((M[:3, :3] @ v.T).T + M[:3, 3]).mean(0))
        for c in n.children:
            walk(c, M)
    walk(k.root, np.eye(4))
    return out


def _v(*xs):
    return ", ".join("%.4f" % x for x in xs)


def ext_config(pos):
    """CSP の設定本文。pos は ALL_NODES の名前 -> (x, y, z)。"""
    t = []
    a = t.append
    a("""; 神奈中バス CSP 設定。発光は NAME のメッシュ名に色を当てる（OFF_COLOR が消灯時）。
[BASIC]
; 乗用車と違いハイビームは持たない。ロービームだけ
IS_LOW_BEAM_AVAILABLE=1
HEADLIGHTS_ARE_HEADLIGHTS=1
TURNING_LIGHTS_REPEAT=1
HAZARD_LIGHTS_ENGINE_LIFE_THRESHOLD=0.001
LIGHT_DAMAGE_SPEED_MIN=80
LIGHT_DAMAGE_SPEED_MAX=120

[LIGHTING]
EMISSIVE_MULT=3
""")
    # ヘッドライトの光源。LIGHT_HEAD_L/R の中心から、レンズの少し前に置く
    for i, n in enumerate(HEAD):
        x, y, z = pos[n]
        a("""; ヘッドライトの光源（%s の位置から）
[LIGHT_HEADLIGHT_%d]
POSITION=%s
DIRECTION=0, -0.08, 1
COLOR=1, 0.85, 0.7, 3.5
RANGE=34
SPOT=80
SPOT_SHARPNESS=0.4
SPOT_EDGE=0.12, 0.12, 0.12
SPOT_EDGE_SHARPNESS=10
DIFFUSE_CONCENTRATION=0.88
LOWBEAM_RANGE_MAX=120
LOWBEAM_RANGE_MULT=1.0
LOWBEAM_RANGE_ONCOMING_MULT=1.2
FADE_AT=400
FADE_SMOOTH=50
AFFECTS_TRACK=1
NO_SELF_SPECULAR=1
""" % (n, i, _v(x, y, z + 0.05)))
    a("""; ヘッドライトのレンズの発光（ライト点灯で光る）
[EMISSIVE_LIGHT_0]
NAME=%s
COLOR=27,24,20, 3.5
OFF_COLOR=0,0,0
LAG=0.65
SIMULATE_HEATING=0.6
LOCATION=FRONT

; テールランプの発光（ライト点灯で光る）
[EMISSIVE_LIGHT_1]
NAME=%s
COLOR=40,1,0.5, 0.9
OFF_COLOR=0,0,0
LAG=0.7
SIMULATE_HEATING=0.6
LOCATION=REAR

; ブレーキ灯（踏むと明るくなる。ライト点灯中はテールの色のまま）
[EMISSIVE_BRAKE_0]
NAME=%s
COLOR=115,2,1, 1.5
FALLBACK_HEADLIGHTS_COLOR=12,0,0
OFF_COLOR=0,0,0
LAG=0.8
SIMULATE_HEATING=0.6
LOCATION=REAR
""" % (", ".join(HEAD), ", ".join(TAIL), ", ".join(BRAKE)))
    # 行先表示: 昼も薄く光り、ライト点灯（夜）で明るくする。物理は常時点灯の電光表示なので OFF_COLOR を 0 にしない
    a("""; 行先表示（前・側面・後）の発光。昼は OFF_COLOR で薄く、夜（ライト点灯）で明るく
[EMISSIVE_LIGHT_2]
NAME=%s
COLOR=2.5,2.5,2.5, 1.6
OFF_COLOR=0.9,0.9,0.9
LAG=0.1
SIMULATE_HEATING=0
LOCATION=NONE
""" % ", ".join(DEST))
    i = 0
    for side in ("LEFT", "RIGHT"):
        for loc, n in IND[side].items():
            a("""; ウインカー %s %s（非常点滅は左右とも点く）
[EMISSIVE_TURNSIGNAL_%s_%d]
NAME=%s
COLOR=125,25,0, 1.4
OFF_COLOR=0,0,0
LAG=0.82
SIMULATE_HEATING=0.65
LOCATION=%s
REPEAT_FREQENCY_HZ=1.4
CAST_LIGHT=1
""" % (side, loc, side, 0 if loc == "FRONT" else 1, n, loc))
    for side in ("LEFT", "RIGHT"):
        for j, (loc, n) in enumerate(IND[side].items()):
            x, y, z = pos[n]
            sx = 1 if x > 0 else -1
            a("""; ウインカーの光源 %s %s
[LIGHT_TURNSIGNAL_%s_%d]
AFFECTS_TRACK=1
COLOR=8,2.8,0, 0.75
POSITION=%s
DIRECTION=%s
SPOT=110
""" % (side, loc, side, j, _v(x, y, z + (0.03 if loc == "FRONT" else -0.03)),
       _v(0.33 * sx, 0.0, 1.0) if loc == "FRONT" else _v(0.025 * sx, 0.0, -1.0)))
    a("""; バック灯（リバースギアで光る）
[EMISSIVE_REVERSE_0]
NAME=%s
COLOR=65,55,35, 1.2
OFF_COLOR=0,0,0
LAG=0.7
SIMULATE_HEATING=0.3
LOCATION=REAR
CAST_LIGHT=1
""" % ", ".join(REVERSE))
    return "\n".join(t)


def write_ext_config(out, kn5_path):
    from pathlib import Path
    d = Path(out) / "extension"
    d.mkdir(parents=True, exist_ok=True)
    pos = node_centers(kn5_path)
    miss = [n for n in ALL_NODES if n not in pos]
    if miss:
        raise RuntimeError("主 kn5 に灯火のノードが無い: %s" % ", ".join(miss))
    import kn5_mirrors
    text = ext_config(pos) + "\n; バックミラー（CSP の本物の鏡。n は data/mirrors.ini の順）\n" + kn5_mirrors.real_mirrors_ext()
    (d / "ext_config.ini").write_text(text, encoding="utf8")
