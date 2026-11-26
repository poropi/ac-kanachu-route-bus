"""外装 .blend から、kn5 書き出し用の一時 .blend を作る（Blender の中で実行）。

blender -b design/exterior/kanachu_exterior.blend --python tools/prepare_blend.py -- --out X.blend --tex-dir DIR
- 全オブジェクトに kn5_name＝オブジェクト名、メッシュには kn5_material＝マテリアル名を入れる（ROOT の kn5_name は車名）。
- モディファイアは適用する。ROOT の外にある物（撮影用カメラなど）と、メッシュ以外の飾り（カメラ・ライト）は消す。
- 内装 design/interior/kanachu_interior.blend のオブジェクト（COCKPIT_HR 以下）を ROOT の下に取り込む。
  外装の INTERIOR_PLACEHOLDER は消す。複数マテリアルのメッシュは、マテリアルごとに別オブジェクトへ分ける（kn5 のメッシュは 1 マテリアル）。
- interior_* マテリアルには kn5_tex（txDiffuse の DDS 名）を入れる。画像があればその DDS、無ければ基本色の単色 DDS（<マテリアル名>.dds）。
- パックされた画像を DDS（ミップマップ付き）にして DIR に書く。ファイル名は画像名の拡張子を .dds に替えたもの。
"""
import os
import sys

import bmesh
import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textures

CAR_NAME = "kanachu_route_bus"
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = lambda f, d=None: argv[argv.index(f) + 1] if f in argv else d


def dds_name(image):
    return os.path.splitext(image.name)[0] + ".dds"


def export_images(tex_dir):
    """使われているパック済み画像を DDS で書く。書いたファイル名のリストを返す。"""
    os.makedirs(tex_dir, exist_ok=True)
    out = []
    for im in bpy.data.images:
        if im.users == 0 or im.size[0] == 0 or not im.packed_file:
            continue
        w, h = im.size
        px = np.empty(w * h * 4, "f4")
        im.pixels.foreach_get(px)
        # Blender は下の行から並ぶ。DDS は上の行から
        a = np.clip(px.reshape(h, w, 4)[::-1] * 255.0 + 0.5, 0, 255).astype(np.uint8)
        name = dds_name(im)
        with open(os.path.join(tex_dir, name), "wb") as fh:
            fh.write(textures.dds_from_rgba(a))
        out.append(name)
    return out


def tag_interior_materials(tex_dir):
    """使われている interior_* マテリアルに kn5_tex（txDiffuse の DDS 名）・kn5_emissive・kn5_alpha を入れる。
    テクスチャの無いマテリアルは基本色（と透明度）の単色 DDS を書く。書いた単色 DDS の名前を返す。"""
    out = []
    used = {s.material.name for ob in bpy.data.objects if ob.type == "MESH" for s in ob.material_slots if s.material}
    for name in sorted(used):
        if not name.startswith("interior_"):
            continue
        m = bpy.data.materials[name]
        nodes = m.node_tree.nodes if m.node_tree else []
        img = next((n.image for n in nodes if n.type == "TEX_IMAGE" and n.image and n.image.packed_file), None)
        bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
        alpha = float(bsdf.inputs["Alpha"].default_value) if bsdf else 1.0
        if alpha < 0.999:
            alpha = GLASS_ALPHA
        if img is not None:
            m["kn5_tex"] = dds_name(img)
        else:
            rgb = bsdf.inputs["Base Color"].default_value if bsdf else (0.5, 0.5, 0.5, 1.0)
            px = [srgb_byte(rgb[0]), srgb_byte(rgb[1]), srgb_byte(rgb[2]), int(min(max(alpha, 0.0), 1.0) * 255 + 0.5)]
            fn = name + ".dds"
            with open(os.path.join(tex_dir, fn), "wb") as fh:
                fh.write(textures.dds_bytes(4, px))
            m["kn5_tex"] = fn
            out.append(fn)
        m["kn5_alpha"] = alpha
        m["kn5_emissive"] = EMISSIVE.get(name, 0.0)
    return out


def apply_modifiers():
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in list(bpy.data.objects):
        if ob.type == "MESH" and ob.modifiers:
            new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
            old = ob.data
            ob.modifiers.clear()
            ob.data = new
            if old.users == 0:
                bpy.data.meshes.remove(old)


INTERIOR_BLEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "design", "interior",
                              "kanachu_interior.blend")
INTERIOR_NODES = ("COCKPIT_HR", "STEER_HR", "ARROW_SPEED", "ARROW_RPM", "DRIVER_EYE")
# 材質 glass のうち、薄い着色のまま残す物（風防・運転席の窓・前扉のガラス）。それ以外の glass は濃い着色の glass_tint にする
LIGHT_GLASS = {"Windshield", "Right_Window_01_Glass", "Entrance_Leaf_1_Glass", "Entrance_Leaf_2_Glass"}
GLASS_ALPHA = 0.25   # 透過する内装材（保護板）のテクスチャの不透明度。.blend の値（0.095）は Cycles 用で、ゲームでは見えなくなりすぎる
EMISSIVE = {"interior_lamp": 1.0}   # 天井灯


def srgb_byte(c):
    """リニアの 0〜1 を sRGB の 0〜255 に。"""
    c = min(max(c, 0.0), 1.0)
    v = c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return int(v * 255 + 0.5)


def append_interior(root, path):
    """外装の仮の内装・運転台の空を消し、内装の全オブジェクトを ROOT の下に取り込む。取り込んだオブジェクトのリストを返す。"""
    for name in ("INTERIOR_PLACEHOLDER",) + INTERIOR_NODES:
        o = bpy.data.objects.get(name)
        if o is not None:
            bpy.data.objects.remove(o)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
        wanted = list(src.objects)
    objs = list(dst.objects)
    renamed = [(w, o.name) for w, o in zip(wanted, objs) if w != o.name]
    if renamed:
        raise SystemExit("内装の名前が外装とぶつかった: %s" % renamed)
    for o in objs:
        o["kn5_interior"] = 1   # 複製（マテリアルで分けた部品）にも引き継がれる
        bpy.context.scene.collection.objects.link(o)
    top = bpy.data.objects["COCKPIT_HR"]
    top.parent = root
    top.matrix_parent_inverse.identity()
    for n in INTERIOR_NODES:
        if n not in bpy.data.objects:
            raise SystemExit("内装に %s が無い" % n)
    return objs


def split_by_material(ob):
    """複数マテリアルのメッシュをマテリアルごとの別オブジェクト（同じ親・同じ配置）に分ける。名前は <元の名前>.<マテリアル名から interior_ を除いたもの>。"""
    used = sorted({p.material_index for p in ob.data.polygons})
    if len(used) <= 1:
        return
    base = ob.name
    if ob.data.users > 1:
        ob.data = ob.data.copy()
    before = set(bpy.data.objects)
    ob.hide_set(False)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.separate(type="MATERIAL")
    bpy.ops.object.mode_set(mode="OBJECT")
    for o in [ob] + sorted(set(bpy.data.objects) - before, key=lambda x: x.name):
        if not len(o.data.polygons):
            raise SystemExit("分けた結果が空: " + o.name)
        mat = o.material_slots[o.data.polygons[0].material_index].material
        o["kn5_material"] = mat.name
        o.name = "%s.%s" % (base, mat.name.replace("interior_", "", 1))


def triangulate_ngons(ob):
    """5 角以上の面を三角形にする（接線の計算が三角面・四角面だけなので）。"""
    me = ob.data
    if not any(len(p.vertices) > 4 for p in me.polygons):
        return
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bm.to_mesh(me)
    bm.free()


def mesh_material(ob):
    """メッシュが使っている（唯一の）マテリアル。複数なら分け忘れ。"""
    used = {p.material_index for p in ob.data.polygons}
    if len(used) > 1:
        raise SystemExit("複数マテリアルのメッシュ: " + ob.name)
    if used:
        i = used.pop()
        if i < len(ob.material_slots) and ob.material_slots[i].material:
            return ob.material_slots[i].material
    return ob.active_material


def main():
    out, tex_dir = opt("--out"), opt("--tex-dir")
    if not out or not tex_dir:
        raise SystemExit("--out and --tex-dir are required")
    root = bpy.data.objects.get("ROOT")
    if root is None:
        raise SystemExit("ROOT がありません")
    apply_modifiers()
    # ROOT の子孫以外を消す（カメラ・ライトなど）
    keep = set()
    stack = [root]
    while stack:
        o = stack.pop(); keep.add(o); stack.extend(o.children)
    for ob in list(bpy.data.objects):
        if ob not in keep:
            bpy.data.objects.remove(ob)
    interior = append_interior(root, opt("--interior", INTERIOR_BLEND))
    for ob in interior:
        if ob.type == "MESH":
            split_by_material(ob)
    for ob in bpy.data.objects:   # 分けた後の部品も含めて、内装のメッシュだけ
        if ob.type == "MESH" and ob.get("kn5_interior"):
            triangulate_ngons(ob)
    for ob in bpy.data.objects:
        ob["kn5_name"] = CAR_NAME if ob is root else ob.name
        if ob.type == "MESH":
            mat = mesh_material(ob)
            if not mat:
                raise SystemExit("マテリアルが無い: " + ob.name)
            ob["kn5_material"] = "glass_tint" if mat.name == "glass" and ob.name not in LIGHT_GLASS else mat.name
    names = export_images(tex_dir)
    names += tag_interior_materials(tex_dir)
    bpy.ops.wm.save_as_mainfile(filepath=out)
    print("PREPARED", out, "textures:", names)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(1)
