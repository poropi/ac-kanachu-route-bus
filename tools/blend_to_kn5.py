# tools/blend_to_kn5.py  (blender -b in.blend --python this -- --materials m.json --tex-dir D --out o.kn5 [--root NAME])
import bpy, sys, os, json, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kn5io, kn5_axes, kn5_mirrors
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = lambda f, d=None: argv[argv.index(f) + 1] if f in argv else d
# Blender(bx,by,bz) -> kn5(x,y,z) = (-bx, bz, by)
def to_kn5(a): return np.c_[-a[:, 0], a[:, 2], a[:, 1]]

def init():
    global mats, mat_index, defs
    mats = []; mat_index = {}
    path = opt("--materials")
    if not path: raise SystemExit("--materials is required")
    defs = json.load(open(path))

def interior_def(name):
    """materials.json に無い interior_* は、prepare_blend.py が入れた kn5_tex・kn5_alpha・kn5_emissive から作る（ksPerPixel）。"""
    m = bpy.data.materials.get(name)
    if m is None or not name.startswith("interior_") or "kn5_tex" not in m: return None
    clear = float(m.get("kn5_alpha", 1.0)) < 0.999
    return {"shader": "ksPerPixel", "blend": 1 if clear else 0, "alpha_tested": 0, "depth_mode": 0,
            "props": [["ksAmbient", 0.45], ["ksDiffuse", 0.5], ["ksSpecular", 0.0], ["ksSpecularEXP", 10.0],
                      ["ksEmissive", float(m.get("kn5_emissive", 0.0))], ["ksAlphaRef", 0.0]],
            "tex": [["txDiffuse", 0, str(m["kn5_tex"])]]}

def matid(name):
    if name not in mat_index:
        e = defs.get(name) or interior_def(name)
        if e is None: raise SystemExit("material %s not in materials.json" % name)
        mats.append(kn5io.Mat(name, e["shader"], e.get("blend", 0), e.get("alpha_tested", 0), e.get("depth_mode", 0),
                              [(p[0], p[1], bytes(36)) for p in e["props"]], [tuple(t) for t in e["tex"]]))
        mat_index[name] = len(mats) - 1
    return mat_index[name]

def collect_textures(tex_dir):
    """マテリアルが参照する順（重複なし）で Tex(1, name, bytes) を作る。無ければエラー。"""
    out, seen = [], set()
    for m in mats:
        for _slot, _idx, tname in m.tex:
            if tname in seen: continue
            seen.add(tname)
            p = os.path.join(tex_dir, tname)
            if not os.path.isfile(p): raise SystemExit("texture %s (material %s) not found in %s" % (tname, m.name, tex_dir))
            with open(p, "rb") as fh: out.append(kn5io.Tex(1, tname, fh.read()))
    return out

def set_attrs(n, ob):
    n.cast = int(ob.get("kn5_cast", ob.visible_shadow)); n.visible = int(ob.get("kn5_visible", 1))
    n.transparent = int(ob.get("kn5_transparent", 0)); n.layer = int(ob.get("kn5_layer", 0))
    n.lod_in = float(ob.get("kn5_lod_in", 0.0)); n.lod_out = float(ob.get("kn5_lod_out", 0.0))
    n.renderable = int(ob.get("kn5_renderable", 1))

def mesh_node(ob, name, bake=True):
    n = kn5io.Node(2, name, int(ob.get("kn5_active", 1)))
    set_attrs(n, ob)
    mname = ob.get("kn5_material") or (ob.active_material.name if ob.type == "MESH" and ob.active_material else None)
    if mname is None: raise SystemExit("object %s has no kn5_material" % ob.name)
    n.matid = matid(mname)
    if ob.type != "MESH":  # 頂点なしの mesh ノード
        n.bsphere = tuple(float(x) for x in ob.get("kn5_bsphere", (0, 0, 0, 0))); return n
    dg = bpy.context.evaluated_depsgraph_get(); eob = ob.evaluated_get(dg); me = eob.to_mesh()
    if not me.uv_layers: raise SystemExit("no UV on %s" % name)
    me.calc_loop_triangles()
    nl = len(me.loops); nv = len(me.vertices)
    P = np.empty(nv * 3, "f4"); me.vertices.foreach_get("co", P); P = P.reshape(-1, 3)
    N = np.empty(nl * 3, "f4"); me.corner_normals.foreach_get("vector", N); N = N.reshape(-1, 3)
    UV = np.empty(nl * 2, "f4"); me.uv_layers[0].data.foreach_get("uv", UV); UV = UV.reshape(-1, 2)
    LV = np.empty(nl, "i8"); me.loops.foreach_get("vertex_index", LV)
    if "kn5_tangent" in me.attributes and len(me.attributes["kn5_tangent"].data) == nv:
        T = np.empty(nv * 3, "f4"); me.attributes["kn5_tangent"].data.foreach_get("vector", T); T = T.reshape(-1, 3)[LV]
    else:  # 新規メッシュ等: UV から計算
        me.calc_tangents(); T = np.empty(nl * 3, "f4"); me.loops.foreach_get("tangent", T); T = T.reshape(-1, 3)
    tri = np.empty(len(me.loop_triangles) * 3, "i8"); me.loop_triangles.foreach_get("loops", tri)
    # オブジェクト自身の変換（親逆行列を含む matrix_local）を頂点に焼き込む。法線は逆転置、tangent は線形部分
    ML = np.array(ob.matrix_local, "f8") if bake else np.eye(4); L = ML[:3, :3]   # bake=False: 変換は dummy に持たせ、頂点はローカルのまま
    P = P.astype("f8")[LV] @ L.T + ML[:3, 3]
    if not np.allclose(ML, np.eye(4), atol=1e-7):
        Ln = np.linalg.inv(L).T
        N = N.astype("f8") @ Ln.T; N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
        T = T.astype("f8") @ L.T
        if np.linalg.det(L) < 0: tri = tri.reshape(-1, 3)[:, ::-1].ravel()  # 鏡像で巻き方向が反転する分を戻す
    rec = np.c_[to_kn5(P), to_kn5(N), UV[:, 0], 1 - UV[:, 1], to_kn5(T)].astype("<f4")
    rec = np.nan_to_num(rec)  # 元 kn5 に NaN の tangent があり、np.unique が NaN 行を統合できないため 0 に置換
    # 統合のキーは法線を 1e-3 に丸める（Blender の corner_normals は loop ごとの座標系で量子化され、同じ頂点でも 1e-4 程度ずれるため）
    R = rec[tri]; key = R.copy(); key[:, 3:6] = np.round(key[:, 3:6], 3)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    uniq = R[first]
    if len(uniq) > 65535: raise SystemExit("%s has %d vertices > 65535 (u16 index)" % (name, len(uniq)))
    c = uniq[:, :3].mean(0); rad = float(np.linalg.norm(uniq[:, :3] - c, axis=1).max())
    eob.to_mesh_clear()
    n.vertices = uniq.tobytes(); n.indices = inv.ravel().tolist()
    n.bsphere = (float(c[0]), float(c[1]), float(c[2]), rad)
    return n

C = np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], "f8")
def build(ob, keep=None, prune=None):
    """lods.py 用のフック。keep(ob)->False の子はノードを作らず捨てる。prune(ob, node)->True の子は作ったあとで捨てる（空になったラッパー用）。"""
    name = ob.get("kn5_name")
    if not name: raise SystemExit("object %s has no kn5_name" % ob.name)
    kids = sorted(ob.children, key=lambda c: c.get("kn5_order", 1 << 30))
    if keep is not None: kids = [c for c in kids if keep(c)]
    is_mesh = ob.type == "MESH" or ob.get("kn5_class") == 2
    if is_mesh and not kids:
        n = mesh_node(ob, name)
        n.children = []
        return n
    # メッシュに子があると CSP が落ちる（Kunos の kn5 はメッシュが葉だけ）。dummy に名前と変換を持たせ、メッシュは <名前>_GEO として最初の子にする
    n = kn5io.Node(1, name, int(ob.get("kn5_active", 1)))
    M = C @ np.array(ob.matrix_local) @ C   # C は自分自身の逆行列
    n.matrix = tuple(float(x) for x in M.T.ravel())
    n.children = [mesh_node(ob, name + "_GEO", bake=False)] if is_mesh else []
    for c in kids:
        x = build(c, keep, prune)
        if prune is None or not prune(c, x): n.children.append(x)
    return n

def main():
    OUT = opt("--out"); tex_dir = opt("--tex-dir")
    if not OUT or not tex_dir: raise SystemExit("--materials, --tex-dir and --out are required")
    init()
    root_name = opt("--root")
    roots = [o for o in bpy.data.objects if o.parent is None and (root_name is None or o.name == root_name)]
    if len(roots) != 1: raise SystemExit("need exactly one root, got %s" % [o.name for o in roots])
    root = build(roots[0])
    kn5_axes.reorient(root)   # 針・ハンドルのローカル Z を回転軸（運転手から遠ざかる向き）にする
    if any(n.name in kn5_mirrors.NAMES for n in kn5io.walk(root)):   # 外装モデルだけ（M1 の箱には鏡が無い）
        miss = kn5_mirrors.apply(root, matid(kn5_mirrors.MATERIAL))   # 鏡面のマテリアルを mirror にし、UV を 0〜1 に貼り直す
        if miss: raise SystemExit("mirror meshes not found: %s" % miss)
    k = kn5io.Kn5(5, None, collect_textures(tex_dir), mats, root)
    tmp = OUT + ".tmp"
    try:
        kn5io.write(k, tmp); os.replace(tmp, OUT)
    finally:
        if os.path.exists(tmp): os.remove(tmp)
    print("WROTE", OUT)

if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(1)
