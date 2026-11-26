"""運転士のモデルの目の位置（座った姿勢、kn5 = 車の座標）を出す。car.ini の DRIVEREYES（tools/spec.json の eye_x/y/z）にする値。

  python3 tools/driver_eye.py --kn5 build/driver/kanachu_driver.kn5 --knh build/kanachu_route_bus/driver_base_pos.knh

方法（2026-11-26、ユーザー判断で運転席の視点を運転士の頭の中へ移すため）:
 1. 顔のメッシュ（頭の骨の子 DRIVER:GEO_Driver_FACE* のうちマテリアル FACE_MATERIAL のもの）のテクスチャ（kn5 に埋めた DDS）で、
    瞳の画素（青 − 緑 > IRIS_BLUE_MINUS_GREEN。肌・眉・口・頬は青 ≤ 緑、瞳の紫だけが青 > 緑）を選び、画像の左半分・右半分ごとの重心を
    その目の UV にする（kn5 の UV は v が反転済みなので、画素 (x, y) = (u·幅, v·高さ)）。
 2. その UV を含む顔の三角形を探し、重心座標で頭の骨のローカルの 3 次元の点にする（頂点の平均でなく面の上の点。頂点は目の絵の
    範囲に数個しかない）。顔のテクスチャは頭の後ろ側の面にも同じ UV で貼られていて（本物のモデルでは片目ごとに 2 つの三角形に当たる）、
    頭の前（ローカル +Z）へいちばん出ている点を取る。
 3. 両目の中点を座った姿勢の頭の骨で世界へ移し、頭の後ろ向き（頭の骨のローカル −Z。AC の軸、driver_skeleton.AC_AXES_BONES）へ
    EYE_BACK だけ下げる（顔の表面の上でなく頭の中）。
"""
import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import driver_posed  # noqa: E402
import kn5io  # noqa: E402

HEAD_BONE = "DRIVER:RIG_Head"
FACE_MESH = "DRIVER:GEO_Driver_FACE"
FACE_MATERIAL = "driver_face"
IRIS_BLUE_MINUS_GREEN = 20          # 瞳の画素の判定（0〜255）。瞳の紫は 25〜40、肌・眉・口・頬は 0 以下
MIN_IRIS_PIXELS = 100               # 片目の瞳の画素がこれより少なければ失敗にする
EYE_BACK = 0.03                     # 両目の中点から頭の中へ下げる距離（m）


def rgba_from_dds(data):
    """tools/textures.dds_from_rgba が書く無圧縮 A8R8G8B8 の DDS の、いちばん大きいミップを (高さ, 幅, 4) の RGBA（上が 0 行）にする。"""
    if data[:4] != b"DDS ":
        raise ValueError("DDS ではない")
    h, w = struct.unpack_from("<2I", data, 12)
    bits, rm, gm, bm, am = struct.unpack_from("<5I", data, 88)
    if (bits, rm, gm, bm, am) != (32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000):
        raise ValueError("無圧縮 A8R8G8B8 の DDS ではない")
    bgra = np.frombuffer(data, np.uint8, w * h * 4, 128).reshape(h, w, 4)
    return bgra[..., [2, 1, 0, 3]]


def iris_uvs(rgba):
    """瞳の画素の、画像の左半分・右半分ごとの重心の UV（kn5 の UV。v は画像の上が 0）。[(u, v) 左, (u, v) 右]。"""
    h, w = rgba.shape[:2]
    c = rgba.astype(int)
    ys, xs = np.nonzero(c[..., 2] - c[..., 1] > IRIS_BLUE_MINUS_GREEN)
    out = []
    for side in (xs < w / 2, xs >= w / 2):
        if side.sum() < MIN_IRIS_PIXELS:
            raise ValueError("顔のテクスチャに瞳が見つからない（画素 %d）" % side.sum())
        out.append(((xs[side].mean() + 0.5) / w, (ys[side].mean() + 0.5) / h))
    return out


def surface_point(node, uv):
    """種類 2 のメッシュ node の、UV が uv の面の上の点（node のローカル座標）と、当たった三角形の数。"""
    v = np.frombuffer(node.vertices, "<f4").reshape(-1, 11).astype(float)
    T = np.array(node.indices, dtype=int).reshape(-1, 3)
    a, b, c = (v[T[:, i], 6:8] for i in range(3))
    e1, e2, q = b - a, c - a, np.asarray(uv, dtype=float) - a
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    ok = np.abs(det) > 1e-12
    s = np.where(ok, (q[:, 0] * e2[:, 1] - q[:, 1] * e2[:, 0]) / np.where(ok, det, 1), -1)
    t = np.where(ok, (e1[:, 0] * q[:, 1] - e1[:, 1] * q[:, 0]) / np.where(ok, det, 1), -1)
    hit = ok & (s >= -1e-9) & (t >= -1e-9) & (s + t <= 1 + 1e-9)
    if not hit.any():
        raise ValueError("UV %s を含む顔の三角形が無い" % (tuple(uv),))
    P = [(1 - s[i] - t[i]) * v[T[i, 0], :3] + s[i] * v[T[i, 1], :3] + t[i] * v[T[i, 2], :3] for i in np.nonzero(hit)[0]]
    return max(P, key=lambda p: p[2]), int(hit.sum())


def face_node(k):
    head = next(n for n in kn5io.walk(k.root) if n.name == HEAD_BONE)
    for n in kn5io.walk(head):
        if n.cls == 2 and n.name.startswith(FACE_MESH) and k.materials[n.matid].name == FACE_MATERIAL:
            return n
    raise ValueError("顔のメッシュ（%s*、マテリアル %s）が頭の骨の下に無い" % (FACE_MESH, FACE_MATERIAL))


def model_eye(k, W, report=None):
    """k: 運転手の kn5（kn5io.read）。W: 骨の世界行列（行ベクトル規約、driver_posed.seated_worlds）。目の位置（kn5 座標）。"""
    face = face_node(k)
    mat = k.materials[face.matid]
    tname = next(t[2] for t in mat.tex if t[0] == "txDiffuse")
    rgba = rgba_from_dds(next(t.data for t in k.textures if t.name == tname))
    uvs = iris_uvs(rgba)
    pts = [surface_point(face, uv) for uv in uvs]
    Wh = np.asarray(W[HEAD_BONE])
    mid = (pts[0][0] + pts[1][0]) / 2
    fwd = Wh[2, :3] / np.linalg.norm(Wh[2, :3])            # 頭の骨のローカル +Z（前）の世界の向き
    eye = (np.r_[mid, 1.0] @ Wh)[:3] - EYE_BACK * fwd
    if report is not None:
        report.update(iris_uv=[list(map(float, uv)) for uv in uvs], hits=[h for _, h in pts],
                      eyes_world=[(np.r_[p, 1.0] @ Wh)[:3].tolist() for p, _ in pts], head_forward=fwd.tolist())
    return eye


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kn5", required=True)
    ap.add_argument("--knh", required=True)
    a = ap.parse_args()
    rep = {}
    eye = model_eye(kn5io.read(a.kn5), driver_posed.seated_worlds(a.knh), rep)
    print(json.dumps({"eye": [round(float(x), 4) for x in eye], **rep}, ensure_ascii=False))


if __name__ == "__main__":
    main()
