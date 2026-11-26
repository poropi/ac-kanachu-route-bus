"""Blender で外装に塗装 PNG を貼り、斜め前（左前 3/4）から 1022x575 の preview.jpg を描く（AC のスキン一覧用）。

使い方: blender -b design/exterior/kanachu_exterior.blend --python tools/render_skin_preview.py -- --paint X.png --out Y.jpg
.blend は保存しない（開いた状態で貼り替えて描くだけ）。スタジオの空・床・照明は design/exterior/scripts/build_exterior.py の render() と同じ。
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
paint = out = None
samples = 64
for i, a in enumerate(argv):
    if a == "--paint":
        paint = argv[i + 1]
    elif a == "--out":
        out = argv[i + 1]
    elif a == "--samples":
        samples = int(argv[i + 1])

scene = bpy.context.scene
mat = bpy.data.materials["paint"]
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load(paint)
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = samples
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1022, 575, 100
scene.render.image_settings.file_format = "JPEG"
scene.render.image_settings.quality = 90
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"

world = bpy.data.worlds.new("Studio")
scene.world = world
world.use_nodes = True
tree = world.node_tree
bg = tree.nodes.get("Background") or tree.nodes.new("ShaderNodeBackground")
hdr = Path(bpy.utils.system_resource("DATAFILES", path="studiolights/world/courtyard.exr"))
if hdr.is_file():
    env = tree.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(hdr))
    tree.links.new(env.outputs["Color"], bg.inputs[0])
bg.inputs[1].default_value = .36
cbg = tree.nodes.new("ShaderNodeBackground")
cbg.inputs[0].default_value = (.46, .505, .53, 1)
rays = tree.nodes.new("ShaderNodeLightPath")
mix = tree.nodes.new("ShaderNodeMixShader")
tree.links.new(rays.outputs["Is Camera Ray"], mix.inputs[0])
tree.links.new(bg.outputs[0], mix.inputs[1])
tree.links.new(cbg.outputs[0], mix.inputs[2])
out_node = tree.nodes.get("World Output") or tree.nodes.new("ShaderNodeOutputWorld")
tree.links.new(mix.outputs[0], out_node.inputs["Surface"])

section = [(-250, -.002), (0, -.002), (9, -.002)]
for i in range(1, 33):
    t = i * math.pi / 64
    section.append((9 + 4 * math.sin(t), -.002 + 4 * (1 - math.cos(t))))
section.append((13, 60))
g = bpy.data.meshes.new("Cyclorama")
g.from_pydata([(x, y, z) for y, z in section for x in (-100, 100)], [],
              [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(section) - 1)])
for p in g.polygons:
    p.use_smooth = True
floor = bpy.data.objects.new("Studio sweep", g)
bpy.context.collection.objects.link(floor)
m = bpy.data.materials.new("Studio neutral")
m.use_nodes = True
p = m.node_tree.nodes.get("Principled BSDF")
if p is None:
    p = m.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    o = m.node_tree.nodes.get("Material Output") or m.node_tree.nodes.new("ShaderNodeOutputMaterial")
    m.node_tree.links.new(p.outputs[0], o.inputs["Surface"])
p.inputs["Base Color"].default_value = (.205, .232, .246, 1)
p.inputs["Roughness"].default_value = .84
p.inputs["Emission Color"].default_value = (.46, .50, .53, 1)
p.inputs["Emission Strength"].default_value = .76
g.materials.append(m)


def area(name, loc, target, watts, w, h, color):
    d = bpy.data.lights.new(name, "AREA")
    d.energy, d.shape, d.size, d.size_y, d.color = watts, "RECTANGLE", w, h, color
    o = bpy.data.objects.new(name, d)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - o.location).to_track_quat("-Z", "Y").to_euler()


area("Large left softbox", (-6, 3, 9), (0, 0, 1), 1800, 10, 6, (1, .955, .89))
area("Right reflected strip", (6, -2, 6), (0, 0, 1.7), 1400, 9, 3, (.84, .92, 1))
area("Front fill", (1, 9, 5), (0, 1, 1), 520, 5, 4, (1, .95, .87))
area("Tail fill", (-2, -9, 6), (0, -2, 1.6), 750, 5, 5, (.90, .95, 1))

# 前左 3/4: 写真合わせ用のカメラ PHOTO_front34 は車の前（+y）の左（-x）にある。そのレンズと位置をそのまま使い、16:9 に広げる
src = bpy.data.objects["PHOTO_front34"]
cd = bpy.data.cameras.new("Preview camera")
cam = bpy.data.objects.new("Preview camera", cd)
bpy.context.collection.objects.link(cam)
cam.location, cam.rotation_euler = src.location.copy(), src.rotation_euler.copy()   # 他のシーンのカメラの matrix_world は更新されていない
cd.sensor_fit, cd.sensor_width, cd.lens, cd.clip_end = "HORIZONTAL", 36.0, src.data.lens, 650
scene.camera = cam
d = cam.rotation_euler.to_quaternion() @ Vector((0, 0, -1))
floor.rotation_euler.z = math.atan2(-d.x, d.y)
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
