"""運転手の kn5 のメッシュを、骨の姿勢（knh の座った姿勢・ksanim のコマ）で動かした世界座標を出す（AC と同じ計算）。

  posed_meshes(k, W) -> {メッシュ名: 頂点の世界座標 N x 3}
    k: kn5io.read の結果。W: 骨名 -> 世界行列（行ベクトル規約 4x4、driver_pose.fk の結果）。
    種類 3（骨で動く）: 頂点ごとに Σ 重み × 位置 @ 逆バインド行列（骨ごとの 64 バイト）@ 骨の世界行列。
    種類 2（固定）: 位置 @ 親の世界行列。親の種類 1 のうち骨は W、骨でない入れ物は自分の行列 @ 親の世界行列。
  seated_worlds(knh_path) / steer_worlds(ksanim_path, i): knh・ksanim から骨の世界行列を作る。
試験（姿勢を変えても頂点が動かないこと）と、目の位置（driver_eye.py）、確認用の描画に使う。
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import driver_pose as dp  # noqa: E402
import knh  # noqa: E402
import ksanim  # noqa: E402


def seated_worlds(knh_path):
    return dp.fk({n.name: np.array(n.matrix, dtype=float).reshape(4, 4) for n in knh.walk(knh.read(knh_path))})


def steer_worlds(tracks, i):
    """tracks: ksanim.read の結果（または同じ形の dict）。コマ i の骨の世界行列。"""
    return dp.fk({n: ksanim.to_matrix(f[i]) for n, f in tracks.items()})


def skin(node, W):
    """種類 3 のメッシュの頂点を骨の世界行列 W で動かす。"""
    V = np.frombuffer(node.vertices, "<f4").reshape(-1, 19).astype(float)
    names = [b for b, _ in node.bones]
    inv = [np.frombuffer(m, "<f4").reshape(4, 4).astype(float) for _, m in node.bones]
    P = np.c_[V[:, :3], np.ones(len(V))]
    acc = np.zeros((len(V), 3))
    for j in range(4):
        w, idx = V[:, 11 + j], V[:, 15 + j].astype(int)
        for bi in np.unique(idx[w > 0]):
            m = (idx == bi) & (w > 0)
            acc[m] += w[m, None] * (P[m] @ (inv[bi] @ np.asarray(W[names[bi]])))[:, :3]
    return acc


def posed_meshes(k, W):
    out = {}

    def go(n, parent):
        if n.cls == 1:
            M = np.asarray(W[n.name]) if n.name in W else np.array(n.matrix, dtype=float).reshape(4, 4) @ parent
            for c in n.children:
                go(c, M)
        elif n.cls == 2:
            v = np.frombuffer(n.vertices, "<f4").reshape(-1, 11)[:, :3].astype(float)
            out[n.name] = (np.c_[v, np.ones(len(v))] @ parent)[:, :3]
        elif n.cls == 3:
            out[n.name] = skin(n, W)
    go(k.root, np.eye(4))
    return out


def max_point_set_distance(a, b, chunk=256):
    """2 つの点の集合の、どちらの向きにも「いちばん近い点までの距離」の最大（頂点の並び・統合の違いに依らない比較）。"""
    def one_way(p, q):
        worst = 0.0
        for s in range(0, len(p), chunk):
            d = ((p[s:s + chunk, None, :] - q[None, :, :]) ** 2).sum(-1).min(1)
            worst = max(worst, float(np.sqrt(d.max())))
        return worst
    return max(one_way(a, b), one_way(b, a))
