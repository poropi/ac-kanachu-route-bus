# blender -b --python blender/m1_box_bus.py -- --out blender/m1_box.blend
# M1 の箱のバス。エクスポート経路と物理を実機で確かめるための仮の車体。Blender: Z 上, +Y 前, +X 右。
import bpy, sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import spec

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[argv.index("--out") + 1]
S = spec.load(); D = spec.derived(S)

W, H, CLR = S["width"], S["height"], S["ground_clearance"]
AXF, AXR = D["axle_z_front"], D["axle_z_rear"]          # Blender の y（前 +, 後 -）
Y_FRONT = AXF + S["overhang_f"]                          # 4.95
Y_REAR = AXR - S["overhang_r"]                           # -5.48
R, TW = 0.478, S["tyre_width"]
TF, TR = S["track_f"] / 2, S["track_r"] / 2
DUAL = 0.16                                              # 後輪ダブルの中心からのずれ

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

def empty(name, loc, parent=None, rot=(0, 0, 0)):
    o = bpy.data.objects.new(name, None)
    scene.collection.objects.link(o)
    o.location = loc; o.rotation_euler = rot
    o["kn5_name"] = name if parent else "kanachu_route_bus"
    o.parent = parent
    return o

def material(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    return m

def mesh_obj(name, kn5_name, mat, parent, loc=(0, 0, 0), rot=(0, 0, 0), kind="cube", dims=(1, 1, 1), bevel=0.0, cutters=()):
    if kind == "cube":
        bpy.ops.mesh.primitive_cube_add(size=1.0)
    else:
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.5, depth=1.0)
    o = bpy.context.active_object
    o.name = name
    o.dimensions = dims
    bpy.ops.object.transform_apply(scale=True)
    o.parent = parent
    o.location = loc; o.rotation_euler = rot
    o["kn5_name"] = kn5_name; o["kn5_material"] = mat
    o.data.materials.append(material(mat))
    for c in cutters:  # ブーリアンで穴を空け、カッターは削除（エクスポート対象の親なし物体を残さない）
        bm = o.modifiers.new("Cut", "BOOLEAN"); bm.operation = "DIFFERENCE"; bm.object = c; bm.solver = "EXACT"
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=bm.name)
    for c in cutters:
        bpy.data.objects.remove(c)
    if bevel:
        m = o.modifiers.new("Bevel", "BEVEL")
        m.width = bevel; m.segments = 1; m.limit_method = "ANGLE"
    o.modifiers.new("Tri", "TRIANGULATE")  # タンジェント計算は三角/四角面のみ（円柱の蓋・面取りの n 角形対策）
    return o

root = empty("ROOT", (0, 0, 0))

# ホイールアーチ: 各輪（後輪はダブル全体）のタイヤ外形から 0.08 m 空け、外側の壁を抜く。下は開放、車体内側は閉じたまま
ARCH_CLR = 0.08
def arch_cutters():
    out = []
    for sgn in (-1, 1):
        for bx, ay, half in ((TF, AXF, TW / 2), (TR, AXR, DUAL + TW / 2)):
            x_in = bx - half - ARCH_CLR; x_out = W / 2 + 0.2
            h = R + ARCH_CLR; z_top = R + h; z_bot = -0.2
            bpy.ops.mesh.primitive_cube_add(size=1.0)
            c = bpy.context.active_object
            c.dimensions = (x_out - x_in, 2 * h, z_top - z_bot)
            bpy.ops.object.transform_apply(scale=True)
            c.location = (sgn * (x_in + x_out) / 2, ay, (z_top + z_bot) / 2)
            out.append(c)
    return out

# 車体: 面取り 0.1 m の箱。窓板と黒帯は 1 mm だけ外へ出して z ファイトを避ける
yc = (Y_FRONT + Y_REAR) / 2; L = Y_FRONT - Y_REAR
mesh_obj("BODY", "BODY", "paint", root, (0, yc, (CLR + H) / 2), dims=(W, L, H - CLR), bevel=0.1, cutters=arch_cutters())
mesh_obj("WINDSHIELD", "WINDSHIELD", "glass", root, (0, Y_FRONT + 0.001, 2.1), dims=(2.2, 0.01, 1.5))
SK = 0.35
mesh_obj("SKIRT", "SKIRT", "trim_black", root, (0, yc, CLR + SK / 2), dims=(W + 0.002, L + 0.002, SK), cutters=arch_cutters())

# 車輪: WHEEL（空）+ タイヤ（円柱、軸は X）+ リム。後輪は 2 本
def wheel(side, axle, bx, by):
    sfx = side + axle
    w = empty("WHEEL_" + sfx, (bx, by, R), root)
    empty("SUSP_" + sfx, (bx, by, R), root)
    offs = [("", 0.0)] if axle == "F" else [("_IN", -DUAL), ("_OUT", DUAL)]
    for tag, dx in offs:
        mesh_obj("TYRE_" + sfx + tag, "TYRE_" + sfx + tag, "tyre", w, (dx, 0, 0),
                 rot=(0, math.radians(90), 0), kind="cyl", dims=(2 * R, 2 * R, TW))
        mesh_obj("RIM_" + sfx + tag, "RIM_" + sfx + tag, "rim", w, (dx, 0, 0),
                 rot=(0, math.radians(90), 0), kind="cyl", dims=(0.6, 0.6, TW + 0.002))
for side, sgn in (("L", -1), ("R", 1)):          # 左が -bx
    wheel(side, "F", sgn * TF, AXF)
    wheel(side, "R", sgn * TR, AXR)

# 運転席（右ハンドル）。ハンドル軸は後ろへ 20° 起こす
empty("STEER_HR", (0.75, 4.3, 1.75), root, rot=(math.radians(20), 0, 0))
empty("COCKPIT_HR", (0.75, 4.0, 1.4), root)

bpy.ops.wm.save_as_mainfile(filepath=OUT)
