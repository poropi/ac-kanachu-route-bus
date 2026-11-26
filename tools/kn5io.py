# 出典: ~/Documents/develop/ac_swift_zc32s/tools/kn5io.py (verbatim copy)
"""kn5 の無損失な読み書き。フィールド順は tools/kn5.py（AcTools Kn5Reader 準拠、9ファイルで終端一致を確認済み）と同じ。"""
import struct
from dataclasses import dataclass, field

@dataclass
class Tex:
    active: int; name: str; data: bytes

@dataclass
class Mat:
    name: str; shader: str; blend: int; alpha_tested: int; depth_mode: object
    props: list = field(default_factory=list); tex: list = field(default_factory=list)

@dataclass
class Node:
    cls: int; name: str; active: int; children: list = field(default_factory=list)
    matrix: tuple = None
    cast: int = 1; visible: int = 1; transparent: int = 0; bones: list = field(default_factory=list)
    vertices: bytes = b""; indices: list = field(default_factory=list)
    matid: int = 0; layer: int = 0; lod_in: float = 0.0; lod_out: float = 0.0
    bsphere: tuple = (0.0, 0.0, 0.0, 0.0); renderable: int = 1

@dataclass
class Kn5:
    version: int; extra: object; textures: list; materials: list; root: Node

class _R:
    def __init__(s, b): s.b = b; s.p = 0
    def u(s, fmt):
        v = struct.unpack_from("<" + fmt, s.b, s.p); s.p += struct.calcsize("<" + fmt)
        return v if len(v) > 1 else v[0]
    def s(s):
        n = s.u("i"); v = s.b[s.p:s.p + n].decode("utf8"); s.p += n; return v
    def raw(s, n):
        v = s.b[s.p:s.p + n]; s.p += n; return v

def read(path):
    with open(path, "rb") as fh:
        r = _R(fh.read())
    if r.raw(6) != b"sc6969": raise ValueError("not kn5: " + path)
    ver = r.u("i"); extra = r.u("i") if ver > 5 else None
    texs = [Tex(r.u("i"), r.s(), r.raw(r.u("i"))) for _ in range(r.u("i"))]
    mats = []
    for _ in range(r.u("i")):
        m = Mat(r.s(), r.s(), r.u("B"), r.u("B"), None)
        if ver > 4: m.depth_mode = r.u("i")
        m.props = [(r.s(), r.u("f"), r.raw(36)) for _ in range(r.u("i"))]
        m.tex = [(r.s(), r.u("i"), r.s()) for _ in range(r.u("i"))]
        mats.append(m)
    def node():
        cls = r.u("i"); name = r.s(); cc = r.u("i"); act = r.u("B")
        n = Node(cls, name, act)
        if cls == 1:
            n.matrix = r.u("16f")
        elif cls in (2, 3):
            n.cast, n.visible = r.u("B"), r.u("B")
            if ver > 4: n.transparent = r.u("B")
            if cls == 3:
                n.bones = [(r.s(), r.raw(64)) for _ in range(r.u("i"))]
            vc = r.u("i"); n.vertices = r.raw(vc * (44 if cls == 2 else 76))
            ic = r.u("i"); n.indices = list(struct.unpack_from("<%dH" % ic, r.b, r.p)); r.p += 2 * ic
            n.matid, n.layer, n.lod_in, n.lod_out = r.u("i"), r.u("i"), r.u("f"), r.u("f")
            if cls == 2:                       # 骨で動くメッシュ（3）は外接球と描画フラグを持たない（AC の driver.kn5 で確認）
                n.bsphere = r.u("4f")
                if ver > 4: n.renderable = r.u("B")
        else:
            raise ValueError("bad node class %d at %d" % (cls, r.p))
        n.children = [node() for _ in range(cc)]
        return n
    root = node()
    if r.p != len(r.b): raise ValueError("trailing bytes: %d/%d" % (r.p, len(r.b)))
    return Kn5(ver, extra, texs, mats, root)

def _s(x):
    b = x.encode("utf8"); return struct.pack("<i", len(b)) + b

def write(k, path):
    o = [b"sc6969", struct.pack("<i", k.version)]
    if k.version > 5: o.append(struct.pack("<i", k.extra))
    o.append(struct.pack("<i", len(k.textures)))
    for t in k.textures: o += [struct.pack("<i", t.active), _s(t.name), struct.pack("<i", len(t.data)), t.data]
    o.append(struct.pack("<i", len(k.materials)))
    for m in k.materials:
        o += [_s(m.name), _s(m.shader), struct.pack("<BB", m.blend, m.alpha_tested)]
        if k.version > 4: o.append(struct.pack("<i", m.depth_mode))
        o.append(struct.pack("<i", len(m.props)))
        for pn, v, ex in m.props: o += [_s(pn), struct.pack("<f", v), ex]
        o.append(struct.pack("<i", len(m.tex)))
        for sn, slot, tn in m.tex: o += [_s(sn), struct.pack("<i", slot), _s(tn)]
    def node(n):
        o.extend([struct.pack("<i", n.cls), _s(n.name), struct.pack("<iB", len(n.children), n.active)])
        if n.cls == 1:
            o.append(struct.pack("<16f", *n.matrix))
        else:
            if max(n.indices, default=0) > 65535: raise ValueError("u16 index overflow in " + n.name)
            o.append(struct.pack("<BB", n.cast, n.visible))
            if k.version > 4: o.append(struct.pack("<B", n.transparent))
            if n.cls == 3:
                o.append(struct.pack("<i", len(n.bones)))
                for bn, bm in n.bones: o.extend([_s(bn), bm])
            stride = 44 if n.cls == 2 else 76
            o.extend([struct.pack("<i", len(n.vertices) // stride), n.vertices,
                      struct.pack("<i", len(n.indices)), struct.pack("<%dH" % len(n.indices), *n.indices),
                      struct.pack("<iiff", n.matid, n.layer, n.lod_in, n.lod_out)])
            if n.cls == 2:
                o.append(struct.pack("<4f", *n.bsphere))
                if k.version > 4: o.append(struct.pack("<B", n.renderable))
        for c in n.children: node(c)
    node(k.root)
    with open(path, "wb") as fh:
        fh.write(b"".join(o))

def walk(n):
    yield n
    for c in n.children: yield from walk(c)
