"""神奈中塗装の実写・公式図比較。python3 compare_livery.py [旧新・方向のキー ...]"""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
LIVERY = HERE.parent
DESIGN = LIVERY.parent
MODEL = DESIGN / 'exterior' / 'kanachu_exterior.blend'
PHOTOS = DESIGN.parent / 'refs' / 'photos'
OUT = LIVERY / 'compare'
BLENDER = '/opt/homebrew/bin/blender'
DRAWING = 'new_202310311010_2.jpg'
# (元図の切り出し枠, 車体中心の横画素, タイヤ接地点の縦画素, px/m)
DRAWINGS = {
    'front': ((8, 7, 128, 139), 69.1, 129.0, 35.5),
    'left': ((131, 7, 540, 139), 336.0, 129.0, 36.3),
    'rear': ((8, 150, 128, 282), 68.5, 272.5, 35.5),
    'right': ((131, 150, 540, 282), 336.5, 273.0, 36.3),
}
VIEWS = {
    'standard_front34': ('standard', 'front34', 'ふ43　左斜め前'),
    'standard_rear34': ('standard', 'rear34', 'ふ43　右斜め後'),
    'new2023_front': ('new2023', 'front', 'な39　正面'),
    'new2023_rear': ('new2023', 'rear', 'ち85　後面'),
    'new2023_photo02': ('new2023', 'photo02', '実車02　乗降側・前方から'),
    'new2023_photo03': ('new2023', 'photo03', '実車03　乗降側・後方から'),
    **{f'new2023_drawing_{key}': ('new2023', key, label) for key, label in
       [('front', '正面'), ('left', '左側面'), ('rear', '後面'), ('right', '右側面')]},
}
PHOTO_NAMES = {
    'front34': '2019103001-fu43.jpg', 'rear34': '2019103002-fu43r.jpg',
    'front': '2024-05-16-03-na39ff.jpg', 'rear': '2024-05-01-13-chi85rr.jpg',
    'photo02': 'new_kncb_nwclr2yrs_02.jpg', 'photo03': 'new_kncb_nwclr2yrs_03.jpg',
}

# 各写真の左右の車体端、乗降側の前後輪中心、屋根肩・裾を使って
# 1200 × 800 px の透視投影を近似した。縦ラインはカメラの採寸点に含めない。
# 36 mm センサー換算の焦点距離、位置 (m)、Blender の XYZ 回転 (rad)。
SIDE_CAMERAS = {
    'photo02': (42.503631, (-5.345283, 10.882022, 1.635208), (1.577058, .040090, -2.605905)),
    'photo03': (29.364346, (-3.551023, -9.370792, 1.400067), (1.660456, .010896, -.530211)),
}


def side_camera(scene, key):
    import bpy

    focal, location, rotation = SIDE_CAMERAS[key]
    lens = bpy.data.cameras.new(key)
    lens.sensor_fit = 'HORIZONTAL'
    lens.sensor_width = 36
    lens.lens = focal
    cam = bpy.data.objects.new(key, lens)
    scene.collection.objects.link(cam)
    cam.location, cam.rotation_euler = location, rotation
    scene.render.resolution_x, scene.render.resolution_y = 1200, 800
    return cam


def drawing_camera(scene, key):
    import bpy
    from mathutils import Vector

    (x0, y0, x1, y1), centre_x, ground_y, ppm = DRAWINGS[key]
    w, h = x1 - x0, y1 - y0
    outward = Vector({'front': (0, 1, 0), 'left': (-1, 0, 0),
                      'rear': (0, -1, 0), 'right': (1, 0, 0)}[key])
    up = Vector((0, 0, 1))
    screen_right = (-outward).cross(up)
    target = Vector((0, -.265, 0)) + screen_right * ((x0 + w / 2 - centre_x) / ppm)
    target.z = (ground_y - y0 - h / 2) / ppm
    lens = bpy.data.cameras.new('図面・平行投影')
    lens.type = 'ORTHO'
    lens.sensor_fit = 'HORIZONTAL'
    lens.ortho_scale = w / ppm
    cam = bpy.data.objects.new('図面・' + key, lens)
    scene.collection.objects.link(cam)
    cam.location = target + outward * 25
    cam.rotation_euler = (-outward).to_track_quat('-Z', 'Y').to_euler()
    # 公式図の縦横比を保ち、両パネルを同じ寸法で比較する。
    scene.render.resolution_x, scene.render.resolution_y = w * 3, h * 3
    return cam


def lighting(scene):
    import bpy
    from mathutils import Vector

    # 均一な全天光に弱い斜光を加え、車体の曲面と膨らみを残す。
    world = bpy.data.worlds.new('塗装比較・白色照明')
    scene.world = world
    background = world.node_tree.nodes.get('Background')
    background.inputs['Color'].default_value = (1, 1, 1, 1)
    # 白い全天光を鏡面にもそのまま映すと、飽和した赤が均一に白っぽくなる。
    # 拡散用の白い照明と、クリア塗装に映り込むスタジオ壁の明るさを分ける。
    rays = world.node_tree.nodes.new('ShaderNodeLightPath')
    wall = world.node_tree.nodes.new('ShaderNodeBackground')
    wall.inputs['Color'].default_value = (.065, .065, .065, 1)
    background.inputs['Strength'].default_value = 1.20
    mix = world.node_tree.nodes.new('ShaderNodeMixShader')
    world.node_tree.links.new(rays.outputs['Is Glossy Ray'], mix.inputs[0])
    world.node_tree.links.new(background.outputs[0], mix.inputs[1])
    world.node_tree.links.new(wall.outputs[0], mix.inputs[2])
    output = world.node_tree.nodes.get('World Output')
    world.node_tree.links.new(mix.outputs[0], output.inputs['Surface'])
    light = bpy.data.lights.new('軟らかい斜光', 'SUN')
    light.energy = .56
    light.angle = .34
    obj = bpy.data.objects.new(light.name, light)
    scene.collection.objects.link(obj)
    obj.rotation_euler = Vector((.45, -.32, -1)).to_track_quat('-Z', 'Y').to_euler()
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    if 'METAL' in {group[0] for group in prefs.get_device_types(bpy.context)}:
        prefs.compute_device_type = 'METAL'
        prefs.refresh_devices()
        for device in prefs.devices:
            device.use = device.type == 'METAL'
        if any(device.use for device in prefs.devices):
            scene.cycles.device = 'GPU'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.cycles.transparent_max_bounces = 12
    scene.render.film_transparent = True
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1


def render(work, views):
    import bpy

    scene = bpy.data.scenes['Scene']
    lighting(scene)
    tree = bpy.data.materials['paint'].node_tree
    texture = tree.nodes.new('ShaderNodeTexImage')
    tree.links.new(texture.outputs['Color'], tree.nodes.get('Principled BSDF').inputs['Base Color'])
    for name in views:
        skin, key, _ = VIEWS[name]
        texture.image = bpy.data.images.load(str(LIVERY / f'paint_{skin}.png'), check_existing=True)
        texture.image.colorspace_settings.name = 'sRGB'
        if '_drawing_' in name:
            camera = drawing_camera(scene, key)
        elif key in SIDE_CAMERAS:
            camera = side_camera(scene, key)
        else:
            photo = bpy.data.scenes['Photo · ' + key]
            camera = photo.camera
            if camera.name not in scene.objects:
                scene.collection.objects.link(camera)
            if camera['source_photo'] != PHOTO_NAMES[key]:
                raise ValueError((camera.name, camera['source_photo'], PHOTO_NAMES[key]))
            scene.render.resolution_x = photo.render.resolution_x
            scene.render.resolution_y = photo.render.resolution_y
        scene.camera = camera
        scene.render.filepath = str(work / (name + '.png'))
        bpy.ops.render.render(scene=scene.name, write_still=True)


def compare(work, name):
    from PIL import Image, ImageDraw, ImageFont
    import unicodedata

    skin, key, direction = VIEWS[name]
    diagram = '_drawing_' in name
    shot = Image.open(work / (name + '.png')).convert('RGBA')
    if diagram:
        original = Image.open(PHOTOS / DRAWING).convert('RGB').crop(DRAWINGS[key][0])
        original = original.resize(shot.size, Image.Resampling.LANCZOS)
        ref_label = '公式側面図' if key in ('left', 'right') else '別車種の公式図（参考）'
    else:
        original = Image.open(PHOTOS / PHOTO_NAMES[key]).convert('RGB')
        assert original.size == shot.size
        ref_label = '実車写真'
    plate = Image.new('RGB', shot.size, '#FFFFFF' if diagram else '#DCE0E2')
    plate.paste(shot, mask=shot.getchannel('A'))
    w, h = original.size
    gutter, margin = 8, 14
    bar = 40 if w < 450 else 50
    pair = Image.new('RGB', (w * 2 + gutter, h + bar), '#253239')
    pair.paste(original, (0, bar))
    pair.paste(plate, (w + gutter, bar))
    draw = ImageDraw.Draw(pair)
    font_path = next(p for p in Path('/System/Library/Fonts').glob('*.ttc')
                     if unicodedata.normalize('NFC', p.stem) == 'ヒラギノ角ゴシック W5')
    font = ImageFont.truetype(str(font_path), 17 if w < 450 else 23)
    paint_label = '旧塗装' if skin == 'standard' else '新塗装'
    for offset, caption in [(0, f'{ref_label}　{direction}'),
                            (w + gutter, f'{paint_label}　{direction}')]:
        draw.text((offset + margin, bar / 2), caption, font=font, fill='#FFFFFF', anchor='lm')
    pair.save(OUT / (name + '.png'))


def main():
    args = sys.argv[1:]
    if '--' in args:
        args = args[args.index('--') + 1:]
        if args[0] == '--render':
            render(Path(args[1]), args[2:])
            return
    views = args or list(VIEWS)
    for name in views:
        if name not in VIEWS:
            raise SystemExit('方向を指定してください。 ' + ' '.join(VIEWS))
    OUT.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=OUT, prefix='.render-') as folder:
        work = Path(folder)
        env = {**os.environ, 'TMPDIR': folder, 'PYTHONDONTWRITEBYTECODE': '1'}
        subprocess.run([BLENDER, '-b', '--factory-startup', '--disable-autoexec', str(MODEL),
                        '--python-exit-code', '1', '--python', str(Path(__file__).resolve()),
                        '--', '--render', folder, *views], check=True, env=env)
        for name in views:
            compare(work, name)


if __name__ == '__main__':
    main()
