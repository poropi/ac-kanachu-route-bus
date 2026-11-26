"""運転席の寸法を内装 .blend から測って JSON にする（Blender の中で動く）。

  blender -b design/interior/kanachu_interior.blend --python tools/cockpit_geometry.py -- \
      --blend design/interior/kanachu_interior.blend --out design/driver/cockpit.json

JSON の値はすべて kn5 座標（m）。Blender (bx, by, bz) → kn5 (-bx, bz, by)（blend_to_kn5.to_kn5 と同じ）。
一度測って design/driver/cockpit.json を git に入れる。座った姿勢の計算（driver_pose.py）は JSON だけ読む。
"""
import argparse
import json
import sys

import numpy as np

EYE, STEER = "DRIVER_EYE", "STEER_HR"
RIM, COLUMN, SEAT, DASH = "Steering_Rim", "Steering_Column_and_Stalks", "Drivers_Seat", "Cab_Dash_and_Driving_Controls"


def to_kn5(p):
    p = np.asarray(p, dtype=float)
    return np.stack([-p[..., 0], p[..., 2], p[..., 1]], axis=-1)


def rim_circle(rim, center, eye):
    """リムの頂点（Blender 座標）から、最小二乗の平面の法線と管の中心線の半径を求める。
    法線は運転手から遠ざかる向き（dot(axis, center - eye) > 0）にそろえる。"""
    c = rim.mean(0)
    n = np.linalg.svd(rim - c)[2][2]
    if np.dot(n, center - eye) < 0:
        n = -n
    d = rim - center
    inplane = np.linalg.norm(d - np.outer(d @ n, n), axis=1)
    return n, float((inplane.min() + inplane.max()) / 2)


def measure(verts, empties):
    """verts: オブジェクト名 -> 頂点 (N,3)（Blender ワールド座標）、empties: 名前 -> 位置。"""
    eye, center = np.asarray(empties[EYE]), np.asarray(empties[STEER])
    axis, rim_r = rim_circle(verts[RIM], center, eye)

    s = verts[SEAT]
    # 座面: 背もたれより前（y が大きい側）で、床から約 0.45 m の高さの頂点。上面の高さは中央値で取る
    cush = s[(s[:, 2] > 1.05) & (s[:, 2] < 1.20) & (s[:, 1] > 3.40)]
    seat = np.array([(cush[:, 0].min() + cush[:, 0].max()) / 2, (cush[:, 1].min() + cush[:, 1].max()) / 2,
                     float(np.median(cush[:, 2]))])
    # 背もたれ: 座面より高い頂点を、高さ z に対する前後 y の直線で当てはめる。後ろへ倒れた角度（垂直から）
    back = s[s[:, 2] > 1.25]
    slope = np.polyfit(back[:, 2], back[:, 1], 1)[0]     # dy/dz。正なら上ほど前
    back_angle = float(np.degrees(np.arctan(-slope)))    # 上ほど後ろなら正

    d = verts[DASH]
    floor_z = float(np.median(d[(d[:, 2] > 0.60) & (d[:, 2] < 0.70) & (d[:, 1] > 3.9) & (d[:, 1] < 4.6)][:, 2]))
    # ペダル: ハンドルの真下で、床より少し上に浮いた床下前方の小さな塊（x 方向に隙間のある 2 つ）
    reg = d[(d[:, 1] > 4.20) & (d[:, 1] < 4.34) & (d[:, 2] > floor_z + 0.01) & (d[:, 2] < 0.85)
            & (np.abs(d[:, 0] - center[0]) < 0.25)]
    xs = np.sort(reg[:, 0])
    cut = (xs[:-1] + xs[1:])[np.argmax(np.diff(xs))] / 2     # 一番広い x の隙間で 2 つに分ける
    brake_v, accel_v = reg[reg[:, 0] < cut], reg[reg[:, 0] >= cut]

    def pad(v):   # 塊の x・y の中央、高さは上端（足の母指球が乗る面）
        return np.array([(v[:, 0].min() + v[:, 0].max()) / 2, (v[:, 1].min() + v[:, 1].max()) / 2, v[:, 2].max()])

    col = verts[COLUMN]
    box = to_kn5(np.stack([col.min(0), col.max(0)]))
    notes = (
        "全値 kn5 座標 (m)。eye=DRIVER_EYE、wheel_center=STEER_HR。wheel_axis は Steering_Rim の頂点の最小二乗平面の法線で、"
        "dot(axis, center-eye)>0 になる向き（運転手から遠ざかる）。rim_radius は管の中心線の半径 = 平面内の頂点の中心からの距離の"
        "最小と最大の平均。seat_point は Drivers_Seat の座面（z 1.05-1.20、背もたれより前 y>3.40 の頂点）の x・y の中央と上面の高さ（中央値）。"
        "backrest_angle_deg は z>1.25 の頂点の y-z 直線当てはめから、垂直から後ろへ倒れた角度。"
        "ペダルは別オブジェクトが無く Cab_Dash_and_Driving_Controls の一部。ハンドルの真下 (|x-wheel_x|<0.25)・y 4.20-4.34・床 (floor_height) より"
        "上 0.85 以下の頂点を x の一番広い隙間で 2 つに分け、右（blender +X、kn5 の -x）をアクセル、左をブレーキとして、"
        "各塊の x・y の中央と上端の高さを踏面の位置に推定した（推定値。実測の部品ではない）。"
        "column_box は Steering_Column_and_Stalks の外接箱（脚の干渉の確認用）。"
    )
    out = {
        "eye": to_kn5(eye), "wheel_center": to_kn5(center), "wheel_axis": to_kn5(axis), "seat_point": to_kn5(seat),
        "pedal_accel": to_kn5(pad(accel_v)), "pedal_brake": to_kn5(pad(brake_v)),
    }
    out = {k: [round(float(x), 4) for x in v] for k, v in out.items()}
    out["rim_radius"] = round(rim_r, 4)
    out["backrest_angle_deg"] = round(back_angle, 2)
    out["floor_height"] = round(floor_z, 4)
    out["column_box"] = {"min": [round(float(x), 4) for x in box.min(0)], "max": [round(float(x), 4) for x in box.max(0)]}
    out["notes"] = notes
    return out


def main():
    import bpy
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(a)
    if args.blend:
        bpy.ops.wm.open_mainfile(filepath=args.blend)
    bpy.context.view_layer.update()

    def world(n):
        o = bpy.data.objects[n]
        M = np.array(o.matrix_world)
        co = np.array([v.co[:] for v in o.data.vertices])
        return co @ M[:3, :3].T + M[:3, 3]

    verts = {n: world(n) for n in (RIM, COLUMN, SEAT, DASH)}
    empties = {n: np.array(bpy.data.objects[n].matrix_world.translation) for n in (EYE, STEER)}
    res = measure(verts, empties)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
