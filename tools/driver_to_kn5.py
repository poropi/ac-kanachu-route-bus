# tools/driver_to_kn5.py
# 運転手の .blend（骨で動く体と、頭の骨に付いた固定メッシュ）を AC の kn5 にする（Blender の中で実行）。
#   blender -b X.blend --python tools/driver_to_kn5.py -- --out build/driver/kanachu_driver.kn5
#
# 構成（Kunos の運転手 driver.kn5 と同じ形）:
#   DRIVER:DRIVER（種類 1）→ 骨の階層（種類 1、行列は親からの相対）
#     RIG_Head の子 = HEAD_MESHES（種類 2、頂点は頭の骨のローカル座標）
#     根の直下に <名前>（種類 1、単位行列）→ その子に <名前>（種類 3、骨で動くメッシュ）。頂点は世界座標（バインド姿勢）
#
# Kunos の driver.kn5 を調べて分かったこと（データは写していない）:
#   - ノード行列は 16 個の float で、平行移動が 12〜14（行ベクトル規約）。世界行列 = 自分 @ 親（行ベクトル）。
#   - 種類 3 の骨ごとの 64 バイトは「その骨ノードの世界行列の逆行列」で、同じ並び。世界行列 @ これ = 単位行列（誤差 2e-7）。
#   - 頂点 76 バイト = 位置 3・法線 3・UV 2・接線 3・重み 4・骨番号 4（すべて float32）。骨番号は整数値で、
#     使わない枠は重み 0・骨番号 -1。これもそれに合わせる。
import bpy, bmesh, sys, os, struct, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kn5io
from driver_skeleton import BONES, HEAD_MESHES, SKINNED_MESHES
from textures import dds_from_rgba

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = lambda f, d=None: argv[argv.index(f) + 1] if f in argv else d

ARMATURE = "DRIVER:DRIVER"
HEAD_BONE = "DRIVER:RIG_Head"
MAX_INFLUENCE = 4
# 骨で動くメッシュのシェーダー。指定（ksPerPixel）どおり。Kunos の標準は ksSkinnedMesh_NMDetaill なので、
# ゲームで骨が効かなければ --skinned-shader ksSkinnedMesh を試す。
SKINNED_SHADER = opt("--skinned-shader", "ksPerPixel")
# Blender (bx,by,bz) -> kn5 (-bx, bz, by)。行列の共役に使う（自分自身の逆行列、向きは保つ）
C = np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], "f8")
def to_kn5(a): return np.c_[-a[:, 0], a[:, 2], a[:, 1]]
def row(m): return tuple(float(x) for x in np.asarray(m, "f8").T.ravel())   # 列ベクトル規約の行列 -> kn5 の並び
def row_bytes(m): return struct.pack("<16f", *row(m))

mats, mat_index, texs = [], {}, {}

def material_texture(m):
    """マテリアルの画像（Image Texture ノード）を DDS にする。画像が無ければ基本色の単色。"""
    img = None
    if m.use_nodes and m.node_tree:
        for nd in m.node_tree.nodes:
            if nd.type == "TEX_IMAGE" and nd.image is not None:
                img = nd.image; break
    if img is not None and img.size[0] > 0:
        w, h = img.size
        px = np.empty(w * h * 4, "f4"); img.pixels.foreach_get(px)
        arr = np.clip(px.reshape(h, w, 4)[::-1] * 255 + 0.5, 0, 255).astype(np.uint8)   # Blender は下から上
    else:
        arr = np.broadcast_to(np.clip(np.array(m.diffuse_color) * 255 + 0.5, 0, 255).astype(np.uint8), (4, 4, 4))
    return dds_from_rgba(arr)

def matid(ob, shader):
    m = ob.active_material
    if m is None: raise SystemExit("object %s has no material" % ob.name)
    key = (m.name, shader)
    if key not in mat_index:
        tname = m.name + ".dds"
        if tname not in texs: texs[tname] = kn5io.Tex(1, tname, material_texture(m))
        props = [("ksAmbient", 0.45), ("ksDiffuse", 0.5), ("ksSpecular", 0.0), ("ksSpecularEXP", 10.0),
                 ("ksEmissive", 0.0), ("ksAlphaRef", 0.0)]
        name = m.name if shader == "ksPerPixel" else m.name + "_skinned"
        mats.append(kn5io.Mat(name, shader, 0, 0, 0, [(p, v, bytes(36)) for p, v in props], [("txDiffuse", 0, tname)]))
        mat_index[key] = len(mats) - 1
    return mat_index[key]

def tri_mesh(ob):
    """三角化した一時メッシュ（頂点番号はそのまま）。calc_tangents が n 角形で落ちないように。"""
    me = ob.data.copy()
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me); bm.free()
    return me

def mesh_arrays(ob):
    """kn5 の世界座標で、ループごとの位置・法線・UV・接線と、三角形のループ番号を返す。"""
    if not ob.data.uv_layers: raise SystemExit("no UV on %s" % ob.name)
    me = tri_mesh(ob)
    try:
        me.calc_tangents(); me.calc_loop_triangles()
        nl = len(me.loops); nv = len(me.vertices)
        P = np.empty(nv * 3, "f4"); me.vertices.foreach_get("co", P); P = P.reshape(-1, 3).astype("f8")
        N = np.empty(nl * 3, "f4"); me.corner_normals.foreach_get("vector", N); N = N.reshape(-1, 3).astype("f8")
        T = np.empty(nl * 3, "f4"); me.loops.foreach_get("tangent", T); T = T.reshape(-1, 3).astype("f8")
        UV = np.empty(nl * 2, "f4"); me.uv_layers[0].data.foreach_get("uv", UV); UV = UV.reshape(-1, 2)
        LV = np.empty(nl, "i8"); me.loops.foreach_get("vertex_index", LV)
        tri = np.empty(len(me.loop_triangles) * 3, "i8"); me.loop_triangles.foreach_get("loops", tri)
    finally:
        bpy.data.meshes.remove(me)
    # オブジェクトの世界変換（Blender 座標）を焼き込む。法線は逆転置、接線は線形部分。鏡像なら巻き方向を戻す
    M = np.array(ob.matrix_world, "f8"); L = M[:3, :3]
    Pw = P[LV] @ L.T + M[:3, 3]
    Nw = N @ np.linalg.inv(L).T; Nw /= np.maximum(np.linalg.norm(Nw, axis=1, keepdims=True), 1e-12)
    Tw = T @ L.T
    if np.linalg.det(L) < 0: tri = tri.reshape(-1, 3)[:, ::-1].ravel()
    return Pw, Nw, UV, Tw, LV, tri

def weights_of(ob, bone_names):
    """頂点ごとに [(骨名, 重み)]（上位 4 本、合計 1 に正規化）。重みの無い頂点は SystemExit。"""
    gname = {g.index: g.name for g in ob.vertex_groups}
    out, bad = [], 0
    for v in ob.data.vertices:
        ws = sorted(((g.weight, gname[g.group]) for g in v.groups
                     if g.weight > 0 and gname[g.group] in bone_names), key=lambda x: (-x[0], x[1]))[:MAX_INFLUENCE]
        s = sum(w for w, _ in ws)
        if s <= 0: bad += 1; out.append([]); continue
        out.append([(n, w / s) for w, n in ws])
    if bad: raise SystemExit("%s has %d vertices with no bone weight" % (ob.name, bad))
    return out

def finish(n, rec, tri, key_extra=None):
    """ループごとのレコード rec と三角形から、同じ角を統合した頂点列と索引を n に入れる。"""
    R = rec[tri]; key = R.copy(); key[:, 3:6] = np.round(key[:, 3:6], 3)   # 法線は 1e-3 に丸めて統合（blend_to_kn5 と同じ）
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    uniq = R[first]
    if len(uniq) > 65535: raise SystemExit("%s has %d vertices > 65535 (u16 index)" % (n.name, len(uniq)))
    n.vertices = uniq.astype("<f4").tobytes(); n.indices = inv.ravel().tolist()
    return uniq

def common(Pk, Nk, UV, Tk):
    return [Pk, Nk, np.c_[UV[:, 0], 1 - UV[:, 1]], Tk]   # UV の v は反転（blend_to_kn5 と同じ）

def static_node(ob, name, bone_world_inv):
    """頭の骨に付く固定メッシュ（種類 2）。頂点は骨のローカル座標（kn5 空間）。"""
    Pw, Nw, UV, Tw, LV, tri = mesh_arrays(ob)
    Pk, Nk, Tk = to_kn5(Pw), to_kn5(Nw), to_kn5(Tw)
    Bi = bone_world_inv; Lb = Bi[:3, :3]                       # 世界 -> 骨ローカル（kn5、回転のみ）
    Pk = Pk @ Lb.T + Bi[:3, 3]; Nk = Nk @ Lb.T; Tk = Tk @ Lb.T
    rec = np.nan_to_num(np.column_stack(common(Pk, Nk, UV, Tk)).astype("<f4"))
    n = kn5io.Node(2, name, 1); n.matid = matid(ob, "ksPerPixel")
    n.cast = 1; n.visible = 1
    uniq = finish(n, rec, tri)
    c = uniq[:, :3].mean(0); rad = float(np.linalg.norm(uniq[:, :3] - c, axis=1).max())
    n.bsphere = (float(c[0]), float(c[1]), float(c[2]), rad)
    return n

def skinned_node(ob, name, bone_inv):
    """骨で動くメッシュ（種類 3）。頂点は kn5 の世界座標（バインド姿勢）。bone_inv: 骨名 -> 逆バインド行列（kn5 の並び）。"""
    Pw, Nw, UV, Tw, LV, tri = mesh_arrays(ob)
    W = weights_of(ob, set(bone_inv))
    used = [b for b, _ in BONES if any(b == bn for ws in W for bn, _ in ws)]
    index = {b: i for i, b in enumerate(used)}
    nv = len(W); WT = np.zeros((nv, 4), "f4"); WI = -np.ones((nv, 4), "f4")
    for i, ws in enumerate(W):
        for j, (bn, w) in enumerate(ws): WT[i, j] = w; WI[i, j] = index[bn]
    rec = np.nan_to_num(np.column_stack(common(to_kn5(Pw), to_kn5(Nw), UV, to_kn5(Tw)) + [WT[LV], WI[LV]]).astype("<f4"))
    n = kn5io.Node(3, name, 1); n.matid = matid(ob, SKINNED_SHADER)
    n.cast = 1; n.visible = 1
    finish(n, rec, tri)
    n.bones = [(b, bone_inv[b]) for b in used]
    return n

def main():
    OUT = opt("--out")
    if not OUT: raise SystemExit("--out is required")
    bpy.context.view_layer.update()
    arm = bpy.data.objects.get(ARMATURE)
    if arm is None or arm.type != "ARMATURE": raise SystemExit("armature %s not found" % ARMATURE)
    want = dict(BONES)
    have = {b.name: b for b in arm.data.bones}
    if set(have) != set(want): raise SystemExit("bones differ from driver_skeleton: %s" % sorted(set(have) ^ set(want)))
    AW = np.array(arm.matrix_world, "f8")
    K = {n: C @ AW @ np.array(have[n].matrix_local, "f8") @ C for n, _ in BONES}   # kn5 空間の世界行列（列ベクトル規約）
    nodes = {}
    for name, parent in BONES:
        rel = np.linalg.inv(K[parent]) @ K[name] if parent else K[name]
        nodes[name] = kn5io.Node(1, name, 1, matrix=row(rel))
        if parent: nodes[parent].children.append(nodes[name])
    root = nodes[ARMATURE]
    bone_inv = {n: row_bytes(np.linalg.inv(K[n])) for n, _ in BONES}   # 世界行列の逆行列を、ノード行列と同じ並びで 64 バイトに
    for n in HEAD_MESHES:
        ob = bpy.data.objects.get(n)
        if ob is None or ob.type != "MESH": raise SystemExit("mesh %s not found" % n)
        if ob.parent != arm or ob.parent_type != "BONE" or ob.parent_bone != HEAD_BONE:
            raise SystemExit("%s is not bone-parented to %s" % (n, HEAD_BONE))
        nodes[HEAD_BONE].children.append(static_node(ob, n, np.linalg.inv(K[HEAD_BONE])))
    for n in SKINNED_MESHES:
        ob = bpy.data.objects.get(n)
        if ob is None or ob.type != "MESH": raise SystemExit("mesh %s not found" % n)
        dummy = kn5io.Node(1, n, 1, matrix=row(np.linalg.inv(K[ARMATURE])))   # 頂点は世界座標なので、根の変換を打ち消して世界で単位にする
        dummy.children = [skinned_node(ob, n, bone_inv)]
        root.children.append(dummy)
    k = kn5io.Kn5(5, None, list(texs.values()), mats, root)
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
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
