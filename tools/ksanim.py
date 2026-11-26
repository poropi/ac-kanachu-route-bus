"""steer.ksanim（版 2）の読み書き。

形式（借り物を形式の確認にだけ読んだ）: int 版=2、int 骨の数、骨ごとに 名前（int 長さ + utf8）・int コマ数・
コマごとに 10 float32（四元数 x y z w、位置 3、大きさ 3）。コマの値は骨の「親からの相対」変換。
四元数の成分順は x y z w。標準の回転行列（列ベクトル規約）に直したものの転置が、knh / kn5 の行ベクトル規約の 3x3 になる。
"""
import struct
from typing import NamedTuple

import numpy as np

VERSION = 2


class Frame(NamedTuple):
    rot: tuple      # (x, y, z, w)
    pos: tuple      # (x, y, z)
    scale: tuple    # (x, y, z)


def read(path):
    with open(path, "rb") as f:
        b = f.read()
    ver, n = struct.unpack_from("<ii", b, 0)
    if ver != VERSION:
        raise ValueError("ksanim: 版 %d は読めない（版 %d のみ）" % (ver, VERSION))
    p = 8
    tracks = {}
    for _ in range(n):
        ln, = struct.unpack_from("<i", b, p); p += 4
        name = b[p:p + ln].decode("utf8"); p += ln
        cnt, = struct.unpack_from("<i", b, p); p += 4
        frames = []
        for _ in range(cnt):
            v = struct.unpack_from("<10f", b, p); p += 40
            frames.append(Frame(tuple(v[0:4]), tuple(v[4:7]), tuple(v[7:10])))
        tracks[name] = frames
    if p != len(b):
        raise ValueError("ksanim: 末尾に %d バイト余っている" % (len(b) - p))
    return tracks


def write(tracks, path):
    out = bytearray(struct.pack("<ii", VERSION, len(tracks)))
    for name, frames in tracks.items():
        s = name.encode("utf8")
        out += struct.pack("<i", len(s)) + s + struct.pack("<i", len(frames))
        prev = None
        for fr in frames:
            rot = fr.rot
            if prev is not None and sum(a * b for a, b in zip(rot, prev)) < 0:
                rot = tuple(-x for x in rot)         # 隣のコマと同じ半球へ（補間で手が回らないように）
            prev = rot
            out += struct.pack("<10f", *rot, *fr.pos, *fr.scale)
    with open(path, "wb") as f:
        f.write(out)


def _quat(R):
    """回転行列（列ベクトル規約、3x3）-> 四元数 (x, y, z, w)。w >= 0 に正規化。"""
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        q = [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, 0.25 * s]
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        q = [0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s, (R[2, 1] - R[1, 2]) / s]
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        q = [(R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s, (R[0, 2] - R[2, 0]) / s]
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        q = [(R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s, (R[1, 0] - R[0, 1]) / s]
    q = np.array(q) / np.linalg.norm(q)
    return tuple(float(x) for x in (q if q[3] >= 0 else -q))


def _matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def from_matrix(M):
    """親からの相対行列（行ベクトル規約 4x4、平行移動は 4 行目）-> Frame。大きさは各行の長さ。"""
    M = np.asarray(M, dtype=float)
    sc = np.linalg.norm(M[:3, :3], axis=1)
    R = (M[:3, :3] / sc[:, None]).T
    return Frame(_quat(R), tuple(float(x) for x in M[3, :3]), tuple(float(x) for x in sc))


def to_matrix(fr):
    """Frame -> 親からの相対行列（行ベクトル規約 4x4）。"""
    M = np.eye(4)
    M[:3, :3] = _matrix(fr.rot).T * np.asarray(fr.scale)[:, None]
    M[3, :3] = fr.pos
    return M
