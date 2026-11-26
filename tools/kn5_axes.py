"""kn5 のノードのローカル軸を回し直す（子の世界位置は変えない）。

AC は ARROW_*（針）と STEER_HR（ハンドル）を、そのノードの「ローカル Z」まわりに回す。HT81S ではこの Z が運転手から遠ざかる向き。
Blender の空は回転軸を Z に作ってあるが、kn5 に直すと座標変換 (-x, z, y) で軸の対応が入れ替わるので、書き出した後の kn5 で軸を決め直す。
"""
import numpy as np

# 新しい軸 = 古い軸 @ R（R の列が、新しい X・Y・Z を古いローカル座標で表したもの。どれも det +1 の回転）
# 針: 新 Z = -古い Y（文字盤の法線の向き＝運転手側の逆）、新 Y = 古い Z、新 X = 古い X
NEEDLE = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], "f8")
# ハンドル: 回転軸（コラム）は古い Y（Blender のローカル Z）。新 Z = 古い Y、新 X = 古い X、新 Y = 新 Z × 新 X = -古い Z
STEER = NEEDLE.T.copy()
AXES = {"ARROW_SPEED": NEEDLE, "ARROW_RPM": NEEDLE, "STEER_HR": STEER}


def _mat(n):
    return np.array(n.matrix, "f8").reshape(4, 4).T


def _set(n, M):
    n.matrix = tuple(float(x) for x in M.T.ravel())


def _counter_rotate(child, Ri):
    """親の軸が R で回ったぶん、子を R^-1 で戻す（世界は不変）。ダミーは行列、メッシュは頂点・法線・接線。"""
    if child.cls == 1 and child.matrix is not None:
        M = _mat(child)
        T = np.eye(4); T[:3, :3] = Ri
        _set(child, T @ M)
    elif child.cls == 2 and len(child.vertices):
        v = np.frombuffer(child.vertices, "<f4").reshape(-1, 11).astype("f8").copy()
        for a, b in ((0, 3), (3, 6), (8, 11)):
            v[:, a:b] = v[:, a:b] @ Ri.T
        child.vertices = v.astype("<f4").tobytes()
        if len(v):
            c = v[:, :3].mean(0); child.bsphere = (float(c[0]), float(c[1]), float(c[2]),
                                                   float(np.linalg.norm(v[:, :3] - c, axis=1).max()))


def reorient(root, axes=None):
    """AXES にある名前のダミーを回し、直下の子を打ち消す。回したノード名のリストを返す。"""
    axes = AXES if axes is None else axes
    done = []

    def walk(n):
        if n.cls == 1 and n.name in axes and n.matrix is not None:
            R = axes[n.name]
            M = _mat(n)
            T = np.eye(4); T[:3, :3] = R
            _set(n, M @ T)
            for c in n.children:
                _counter_rotate(c, R.T)
            done.append(n.name)
        for c in n.children:
            walk(c)
    walk(root)
    return done
