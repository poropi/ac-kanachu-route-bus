# tools/driver_to_kn5.py
# 運転手の .blend（骨で動く体と、頭の骨に付いた固定メッシュ）を AC の kn5 にする（Blender の中で実行）。
#   blender -b X.blend --python tools/driver_to_kn5.py -- --out build/driver/kanachu_driver.kn5
#
# 構成（Kunos の運転手 driver.kn5 と同じ形）:
#   DRIVER:DRIVER（種類 1）→ 骨の階層（種類 1、行列は親からの相対）
#     RIG_Head の子 = HEAD_MESHES（種類 2、頂点は頭の骨のローカル座標）と、首の肌 NECK_MESH（DRIVER:BODY の driver_neck* の面。
#       2026-11-26: 骨で動くメッシュは HIDE_OBJECT で隠れないので、頭と同じ固定メッシュにする。BODY からは外す）
#     根の直下に <名前>（種類 1、単位行列）→ その子に <名前>（種類 3、骨で動くメッシュ）。頂点は世界座標（バインド姿勢）
#   メッシュは面が使うマテリアルごとに分ける（使わない枠は飛ばす）。Kunos の DRIVER:HELMET（種類 1）→
#   DRIVER:HELMET_SUB0 / _SUB1（種類 2）と同じ形:
#     頭のメッシュ: 1 マテリアルなら <名前>（種類 2）のまま。複数なら <名前>（種類 1、単位行列）の子に
#       <名前>_SUB0, _SUB1, …（種類 2、マテリアルの枠の順）。driver3d.ini の HIDE_OBJECT は <名前> のまま効く
#     骨で動くメッシュ: <名前>（種類 1）の子に、1 マテリアルなら <名前>、複数なら <名前>_SUB0, _SUB1, …（種類 3）。
#       骨リストと骨番号は部分ごとに、その部分の頂点が使う骨だけで振り直す
#
# Kunos の driver.kn5 を調べて分かったこと（データは写していない）:
#   - ノード行列は 16 個の float で、平行移動が 12〜14（行ベクトル規約）。世界行列 = 自分 @ 親（行ベクトル）。
#   - 種類 3 の骨ごとの 64 バイトは「その骨ノードの世界行列の逆行列」で、同じ並び。世界行列 @ これ = 単位行列（誤差 2e-7）。
#   - 頂点 76 バイト = 位置 3・法線 3・UV 2・接線 3・重み 4・骨番号 4（すべて float32）。骨番号は整数値で、
#     使わない枠は重み 0・骨番号 -1。これもそれに合わせる。
import bpy, bmesh, sys, os, struct, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kn5io
from driver_skeleton import AC_AXES_BONES, BONES, HEAD_MESHES, NECK_MATERIAL_PREFIX, NECK_MESH, NECK_SOURCE, SKINNED_MESHES
from textures import dds_from_rgba

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = lambda f, d=None: argv[argv.index(f) + 1] if f in argv else d

ARMATURE = "DRIVER:DRIVER"
HEAD_BONE = "DRIVER:RIG_Head"
MAX_INFLUENCE = 4
# 骨で動くメッシュ（種類 3）のシェーダー。ksPerPixel では骨が効かないので ksSkinnedMesh を既定にする
# （Kunos は ksSkinnedMesh_NMDetaill）。--skinned-shader で変えられる。頭の固定メッシュ（種類 2）は ksPerPixel。
SKINNED_SHADER = opt("--skinned-shader", "ksSkinnedMesh")
# Blender (bx,by,bz) -> kn5 (-bx, bz, by)。行列の共役に使う（自分自身の逆行列、向きは保つ）
C = np.array([[-1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], "f8")
def to_kn5(a): return np.c_[-a[:, 0], a[:, 2], a[:, 1]]
def row(m): return tuple(float(x) for x in np.asarray(m, "f8").T.ravel())   # 列ベクトル規約の行列 -> kn5 の並び
def row_bytes(m): return struct.pack("<16f", *row(m))

mats, mat_index, texs, tex_by_src = [], {}, {}, {}   # tex_by_src: ("image", 画像名) / ("color", マテリアル名) -> テクスチャ名

def material_image(m):
    """マテリアルの画像（最初の Image Texture ノード）。無ければ None。"""
    if m.use_nodes and m.node_tree:
        for nd in m.node_tree.nodes:
            if nd.type == "TEX_IMAGE" and nd.image is not None and nd.image.size[0] > 0:
                return nd.image
    return None

def material_texture_name(m):
    """kn5 のテクスチャ名。マテリアル名 + .dds。ただし同じ画像を使うマテリアルどうしは、その画像を最初に使った
    マテリアルの名前の 1 枚を共有する（実モデルでは制服・靴・金具・首の 4 マテリアルが 2048x1536 の 1 枚を使う）。"""
    img = material_image(m)
    key = ("image", img.name) if img is not None else ("color", m.name)
    if key not in tex_by_src: tex_by_src[key] = m.name + ".dds"
    return tex_by_src[key]

def material_texture(m):
    """マテリアルの画像（Image Texture ノード）を DDS にする。画像が無ければ基本色の単色。"""
    img = material_image(m)
    if img is not None:
        w, h = img.size
        px = np.empty(w * h * 4, "f4"); img.pixels.foreach_get(px)
        arr = np.clip(px.reshape(h, w, 4)[::-1] * 255 + 0.5, 0, 255).astype(np.uint8)   # Blender は下から上
    else:
        arr = np.broadcast_to(np.clip(np.array(m.diffuse_color) * 255 + 0.5, 0, 255).astype(np.uint8), (4, 4, 4))
    return dds_from_rgba(arr)

# 骨で動くマテリアル（ksSkinnedMesh）が使う共有テクスチャ（kn5 に 1 回ずつ埋める）。
# txMaps は Kunos の服（2016_Suit_MAP）の値の範囲（R 約 70、G 約 7、B 約 35。どれも低い）に合わせた、つや消し・非金属の単色。
SHARED = {"driver_flat_nm.dds": (128, 128, 255, 255), "driver_maps.dds": (64, 8, 32, 255),
          "driver_detail.dds": (255, 255, 255, 255)}
# 骨で動くマテリアルの props。ksSkinnedMesh の定義（cbBones・cbMaterial・cbCarPaint）の全部。Kunos の骨で動くマテリアルにも bones がある
SKINNED_PROPS = [("bones", 0.0), ("ksAmbient", 0.45), ("ksDiffuse", 0.5), ("ksSpecular", 0.0), ("ksSpecularEXP", 10.0),
                 ("ksEmissive", 0.0), ("ksAlphaRef", 0.0), ("fresnelC", 0.0), ("fresnelEXP", 1.0), ("fresnelMaxLevel", 0.0),
                 ("nmObjectSpace", 0.0), ("isAdditive", 0.0), ("useDetail", 0.0), ("detailUVMultiplier", 1.0), ("boh", 0.0)]

def shared_texture(name):
    if name not in texs:
        texs[name] = kn5io.Tex(1, name, dds_from_rgba(np.broadcast_to(np.array(SHARED[name], np.uint8), (4, 4, 4))))
    return name

def matid(m, shader):
    """Blender のマテリアル m を kn5 のマテリアル番号にする。同じ (マテリアル, シェーダー) は 1 回だけ書く。"""
    key = (m.name, shader)
    if key not in mat_index:
        tname = material_texture_name(m)
        if tname not in texs: texs[tname] = kn5io.Tex(1, tname, material_texture(m))
        if shader == "ksPerPixel":
            props = [("ksAmbient", 0.45), ("ksDiffuse", 0.5), ("ksSpecular", 0.0), ("ksSpecularEXP", 10.0),
                     ("ksEmissive", 0.0), ("ksAlphaRef", 0.0)]
            tex = [("txDiffuse", 0, tname)]
        else:
            props = SKINNED_PROPS
            tex = [("txDiffuse", 0, tname), ("txNormal", 1, shared_texture("driver_flat_nm.dds")),
                   ("txMaps", 2, shared_texture("driver_maps.dds")), ("txDetail", 3, shared_texture("driver_detail.dds"))]
        name = m.name if shader == "ksPerPixel" else m.name + "_skinned"
        mats.append(kn5io.Mat(name, shader, 0, 0, 0, [(p, v, bytes(36)) for p, v in props], tex))
        mat_index[key] = len(mats) - 1
    return mat_index[key]

def tri_mesh(ob):
    """モディファイア（Mirror など）を評価し、三角化した一時メッシュにする。calc_tangents が n 角形で落ちないように。
    Armature モディファイアだけは外す（骨の変形は頂点に焼かない。骨で動くのは AC 側）。重み（deform 層）は残す。"""
    arms = [m for m in ob.modifiers if m.type == "ARMATURE"]
    saved = [m.show_viewport for m in arms]
    for m in arms: m.show_viewport = False
    try:
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    finally:
        for m, v in zip(arms, saved): m.show_viewport = v
    bm = bmesh.new(); bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.to_mesh(me); bm.free()
    return me

def mesh_arrays(ob, bone_names=None):
    """kn5 の世界座標で、ループごとの位置・法線・UV・接線と、三角形のループ番号、（bone_names があれば）頂点ごとの重みを返す。"""
    if not ob.data.uv_layers: raise SystemExit("no UV on %s" % ob.name)
    me = tri_mesh(ob)
    W = None
    try:
        if bone_names is not None: W = weights_of(ob, me, bone_names)
        me.calc_tangents(); me.calc_loop_triangles()
        nl = len(me.loops); nv = len(me.vertices)
        P = np.empty(nv * 3, "f4"); me.vertices.foreach_get("co", P); P = P.reshape(-1, 3).astype("f8")
        N = np.empty(nl * 3, "f4"); me.corner_normals.foreach_get("vector", N); N = N.reshape(-1, 3).astype("f8")
        T = np.empty(nl * 3, "f4"); me.loops.foreach_get("tangent", T); T = T.reshape(-1, 3).astype("f8")
        UV = np.empty(nl * 2, "f4"); me.uv_layers[0].data.foreach_get("uv", UV); UV = UV.reshape(-1, 2)
        LV = np.empty(nl, "i8"); me.loops.foreach_get("vertex_index", LV)
        tri = np.empty(len(me.loop_triangles) * 3, "i8"); me.loop_triangles.foreach_get("loops", tri)
        FM = np.empty(len(me.loop_triangles), "i8"); me.loop_triangles.foreach_get("material_index", FM)
    finally:
        bpy.data.meshes.remove(me)
    # オブジェクトの世界変換（Blender 座標）を焼き込む。法線は逆転置、接線は線形部分。鏡像なら巻き方向を戻す
    M = np.array(ob.matrix_world, "f8"); L = M[:3, :3]
    Pw = P[LV] @ L.T + M[:3, 3]
    Nw = N @ np.linalg.inv(L).T; Nw /= np.maximum(np.linalg.norm(Nw, axis=1, keepdims=True), 1e-12)
    Tw = T @ L.T
    if np.linalg.det(L) < 0: tri = tri.reshape(-1, 3)[:, ::-1].ravel()
    return Pw, Nw, UV, Tw, LV, tri, W, material_groups(ob, FM, tri)

def material_groups(ob, FM, tri):
    """三角形を、使うマテリアルごとに [(マテリアル, その三角形のループ番号)] に分ける。並びはマテリアルの枠の順。
    面が使わない枠は飛ばす。同じマテリアルが 2 つの枠にあれば 1 つにまとめる。"""
    slots = ob.material_slots
    if not slots: raise SystemExit("object %s has no material" % ob.name)
    FM = np.clip(FM, 0, len(slots) - 1)   # 枠より大きい番号は最後の枠（Blender の描画と同じ）
    T = tri.reshape(-1, 3)
    groups = {}
    for i in sorted(set(FM.tolist())):
        m = slots[i].material
        if m is None: raise SystemExit("object %s material slot %d is empty" % (ob.name, i))
        groups.setdefault(m.name, [m, np.zeros(len(FM), bool)])[1] |= FM == i
    return [(m, T[mask].ravel()) for m, mask in groups.values()]

def sub_names(name, groups):
    """1 マテリアルなら <名前>、複数なら <名前>_SUB0, _SUB1, …（Kunos の DRIVER:HELMET_SUB0 と同じ付け方）。"""
    return [name] if len(groups) == 1 else ["%s_SUB%d" % (name, i) for i in range(len(groups))]

def weights_of(ob, me, bone_names):
    """頂点ごとに [(骨名, 重み)]（上位 4 本、合計 1 に正規化）。重みの無い頂点は SystemExit。"""
    gname = {g.index: g.name for g in ob.vertex_groups}
    out, bad = [], 0
    for v in me.vertices:
        ws = sorted(((g.weight, gname[g.group]) for g in v.groups
                     if g.weight > 0 and gname[g.group] in bone_names), key=lambda x: (-x[0], x[1]))[:MAX_INFLUENCE]
        s = sum(w for w, _ in ws)
        if s <= 0: bad += 1; out.append([]); continue
        out.append([(n, w / s) for w, n in ws])
    if bad: raise SystemExit("%s has %d vertices with no bone weight" % (ob.name, bad))
    return out

MAX_VERTICES = 60000   # 1 メッシュの頂点数の上限（Global Constraint。u16 索引の 65535 より小さい）

def finish(n, rec, tri, key_extra=None):
    """ループごとのレコード rec と三角形から、同じ角を統合した頂点列と索引を n に入れる。"""
    R = rec[tri]; key = R.copy(); key[:, 3:6] = np.round(key[:, 3:6], 3)   # 法線は 1e-3 に丸めて統合（blend_to_kn5 と同じ）
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    uniq = R[first]
    if len(uniq) > MAX_VERTICES: raise SystemExit("%s has %d vertices > %d (Global Constraint)" % (n.name, len(uniq), MAX_VERTICES))
    n.vertices = uniq.astype("<f4").tobytes(); n.indices = inv.ravel().tolist()
    return uniq

def common(Pk, Nk, UV, Tk):
    return [Pk, Nk, np.c_[UV[:, 0], 1 - UV[:, 1]], Tk]   # UV の v は反転（blend_to_kn5 と同じ）

def is_neck(m): return m.name.startswith(NECK_MATERIAL_PREFIX)

def static_node(ob, name, bone_world_inv, keep=None):
    """頭の骨に付く固定メッシュ（種類 2）。頂点は骨のローカル座標（kn5 空間）。
    複数マテリアルなら、単位行列の <名前>（種類 1）の子に <名前>_SUBi（種類 2）を並べたものを返す。
    keep（マテリアル -> bool）を渡すと、その面だけを書く（無ければ None）。"""
    Pw, Nw, UV, Tw, LV, tri, _, groups = mesh_arrays(ob)
    if keep is not None: groups = [g for g in groups if keep(g[0])]
    if not groups: return None
    Pk, Nk, Tk = to_kn5(Pw), to_kn5(Nw), to_kn5(Tw)
    Bi = bone_world_inv; Lb = Bi[:3, :3]                       # 世界 -> 骨ローカル（kn5、回転のみ）
    Pk = Pk @ Lb.T + Bi[:3, 3]; Nk = Nk @ Lb.T; Tk = Tk @ Lb.T
    rec = np.nan_to_num(np.column_stack(common(Pk, Nk, UV, Tk)).astype("<f4"))
    out = []
    for nm, (m, t) in zip(sub_names(name, groups), groups):
        n = kn5io.Node(2, nm, 1); n.matid = matid(m, "ksPerPixel")
        n.cast = 1; n.visible = 1
        uniq = finish(n, rec, t)
        c = uniq[:, :3].mean(0); rad = float(np.linalg.norm(uniq[:, :3] - c, axis=1).max())
        n.bsphere = (float(c[0]), float(c[1]), float(c[2]), rad)
        out.append(n)
    if len(out) == 1: return out[0]
    return kn5io.Node(1, name, 1, children=out, matrix=row(np.eye(4)))   # 単位行列なので世界での位置は変わらない

def skinned_nodes(ob, name, bone_inv, keep=None):
    """骨で動くメッシュ（種類 3）をマテリアルごとに返す。頂点は kn5 の世界座標（バインド姿勢）。
    bone_inv: 骨名 -> 逆バインド行列（kn5 の並び）。骨リストはその部分の頂点が使う骨だけ（BONES の順）。
    keep（マテリアル -> bool）を渡すと、その面だけを書く。"""
    Pw, Nw, UV, Tw, LV, tri, W, groups = mesh_arrays(ob, set(bone_inv))
    if keep is not None: groups = [g for g in groups if keep(g[0])]
    base = np.column_stack(common(to_kn5(Pw), to_kn5(Nw), UV, to_kn5(Tw)))
    out = []
    for nm, (m, t) in zip(sub_names(name, groups), groups):
        verts = np.unique(LV[t])
        names = {bn for i in verts for bn, _ in W[i]}
        used = [b for b, _ in BONES if b in names]
        index = {b: i for i, b in enumerate(used)}
        nv = len(W); WT = np.zeros((nv, 4), "f4"); WI = -np.ones((nv, 4), "f4")
        for i in verts:
            for j, (bn, w) in enumerate(W[i]): WT[i, j] = w; WI[i, j] = index[bn]
        rec = np.nan_to_num(np.column_stack([base, WT[LV], WI[LV]]).astype("<f4"))
        n = kn5io.Node(3, nm, 1); n.matid = matid(m, SKINNED_SHADER)
        n.cast = 1; n.visible = 1
        finish(n, rec, t)
        n.bones = [(b, bone_inv[b]) for b in used]
        out.append(n)
    return out

def main():
    OUT = opt("--out")
    if not OUT: raise SystemExit("--out is required")
    arm = bpy.data.objects.get(ARMATURE)
    if arm is None or arm.type != "ARMATURE": raise SystemExit("armature %s not found" % ARMATURE)
    arm.data.pose_position = "REST"   # ポーズが付いた .blend でも同じ kn5 になるように、骨をレスト位置にして評価する（保存はしない）
    bpy.context.view_layer.update()
    want = dict(BONES)
    have = {b.name: b for b in arm.data.bones}
    if set(have) != set(want): raise SystemExit("bones differ from driver_skeleton: %s" % sorted(set(have) ^ set(want)))
    AW = np.array(arm.matrix_world, "f8")
    K = {n: C @ AW @ np.array(have[n].matrix_local, "f8") @ C for n, _ in BONES}   # kn5 空間の世界行列（列ベクトル規約）
    for n in AC_AXES_BONES:
        K[n][:3, :3] = np.eye(3)   # AC の首・頭の軸（driver_skeleton.AC_AXES_BONES、位置はそのまま）。以下の行列はすべてこの K から作る
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
        dummy.children = skinned_nodes(ob, n, bone_inv, keep=(lambda m: not is_neck(m)) if n == NECK_SOURCE else None)
        root.children.append(dummy)
    # 首の肌: BODY の driver_neck* の面を頭の骨の固定メッシュにする（骨で動くメッシュの後に書くので、マテリアル・テクスチャの番号と名前は前のまま）
    neck = static_node(bpy.data.objects[NECK_SOURCE], NECK_MESH, np.linalg.inv(K[HEAD_BONE]), keep=is_neck)
    if neck is not None: nodes[HEAD_BONE].children.append(neck)
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
