"""driver_base_pos.knh の読み書き。

形式（借り物を形式の確認にだけ読んだ）: ノード = 名前（int32 長さ + utf8）、行列 16 float32（kn5 と同じ並び。
平行移動は 12〜14 番目）、子の数 int32、子を順に。根は 1 つ。
"""
import struct
from dataclasses import dataclass, field


@dataclass
class KnhNode:
    name: str
    matrix: tuple
    children: list = field(default_factory=list)


def _read(b, p):
    n, = struct.unpack_from("<i", b, p); p += 4
    name = b[p:p + n].decode("utf8"); p += n
    m = struct.unpack_from("<16f", b, p); p += 64
    c, = struct.unpack_from("<i", b, p); p += 4
    node = KnhNode(name, tuple(m))
    for _ in range(c):
        ch, p = _read(b, p)
        node.children.append(ch)
    return node, p


def read(path):
    with open(path, "rb") as f:
        b = f.read()
    node, p = _read(b, 0)
    if p != len(b):
        raise ValueError("knh: 末尾に %d バイト余っている" % (len(b) - p))
    return node


def _write(node, out):
    s = node.name.encode("utf8")
    out += struct.pack("<i", len(s)) + s + struct.pack("<16f", *node.matrix) + struct.pack("<i", len(node.children))
    for c in node.children:
        _write(c, out)


def write(root, path):
    out = bytearray()
    _write(root, out)
    with open(path, "wb") as f:
        f.write(out)


def walk(node):
    yield node
    for c in node.children:
        yield from walk(c)
