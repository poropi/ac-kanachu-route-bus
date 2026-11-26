"""Reusable Blender cameras, visibility passes, and exact reprojection checks."""
import json
import math
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Matrix, Vector


HERE = Path(__file__).resolve().parent
VIEWS = ('front34','rear34','front','rear')


def camera_scenes(directory):
    """Link the same vehicle meshes in four independent camera scenes."""
    asset = bpy.data.objects['ROOT']
    models = bpy.data.collections.new('Exterior · shared geometry')
    for obj in (asset, *asset.children_recursive):
        models.objects.link(obj)
    result = {}
    for key in VIEWS:
        fit = json.loads((Path(directory)/(key+'.json')).read_text())
        sc = bpy.data.scenes.new('Photo · '+key)
        sc.collection.children.link(models)
        sc.collection['reference'] = fit['photo']
        lens = bpy.data.cameras.new('PhotoLens_'+key)
        lens.sensor_fit = 'HORIZONTAL'
        lens.sensor_width = 36
        lens.lens = fit['lens_mm']
        lens.clip_end = 500
        cam = bpy.data.objects.new('PHOTO_'+key,lens)
        sc.collection.objects.link(cam)
        cam.matrix_world = Matrix(fit['world'])
        sc.camera = cam
        sc.render.resolution_x, sc.render.resolution_y = fit['size']
        sc.render.resolution_percentage = 100
        sc.unit_settings.system = 'METRIC'
        sc.render.engine = 'BLENDER_WORKBENCH'
        sc.display.shading.color_type = 'MATERIAL'
        sc.display.shading.background_type = 'VIEWPORT'
        sc.display.shading.background_color = (.16,.17,.18)
        sc.display.shading.show_shadows = True
        sc.view_layers[0].update()
        measurements = []
        w, h = fit['size']
        for name, xyz, uv in fit['points']:
            p = world_to_camera_view(sc,cam,Vector(xyz))
            measurements.append([w*p.x-uv[0],h*(1-p.y)-uv[1]])
        if max(math.dist(got,want) for got,want in zip(measurements, fit['delta_px'])) > .02:
            raise RuntimeError(f'{key}: Blenderのカメラと採寸時の投影が一致しません')
        cam['source_photo'] = fit['photo']
        cam['landmarks'] = json.dumps(fit['points'],ensure_ascii=False)
        cam['residual_xy_px'] = json.dumps(measurements)
        cam['rms_px'] = math.sqrt(sum(x*x+y*y for x,y in measurements)/len(measurements))
        result[key] = sc
    return result


def render_ids(sc, directory, key):
    # Visible surface regions are rasterised by Blender's depth buffer, including
    # through-window occlusions. Give continuous paint and rubber a common ID.
    colors = {'paint':(.75,.75,.75),'glass':(.0,.35,.35),'trim_black':(.28,0,0),
              'rubber':(.28,0,0),'rim':(.25,.65,0),'chrome':(.6,.18,.4),
              'tyre':(.03,.03,.08),'glass_light':(.58,.2,.0),
              'light_emit':(.58,.2,.0),'dest_led':(.30,.15,.65)}
    sc.render.engine = 'BLENDER_WORKBENCH'
    shading = sc.display.shading
    shading.light = 'FLAT'
    shading.color_type = 'OBJECT'
    shading.show_shadows = shading.show_cavity = shading.show_specular_highlight = False
    shading.show_object_outline = False
    shading.background_type = 'WORLD'
    sc.display.render_aa = 'OFF'
    sc.view_settings.view_transform = 'Standard'
    sc.render.dither_intensity = 0
    sc.render.film_transparent = True
    sc.render.image_settings.color_mode = 'RGBA'
    original = []
    for obj in sc.objects:
        if obj.type != 'MESH':
            continue
        original.append((obj, tuple(obj.color), obj.hide_render))
        if 'Plate_Type_' in obj.name or obj.name.startswith('Prism_'):
            obj.hide_render = True
        group = obj.active_material.name
        if obj.name.startswith('Cooling_Intake_'):
            group = 'trim_black'
        obj.color = (*colors[group],1)
    sc.render.filepath = str(directory/(key+'-id.png'))
    try:
        bpy.ops.render.render(scene=sc.name, write_still=True)
        # Trace the equipment seen through a pane. Other objects still occlude
        # it; ordinary edges of the cabin and of far-side windows stay hidden.
        inside = (('RearDestinationHousing','DEST_REAR','Rear_Window_WideAngleLens')
                  if key.startswith('rear') else ('Side_Sign_Cabinet','DEST_SIDE'))
        for obj, _, _ in original:
            obj.hide_render |= obj.active_material.name == 'glass'
            sign = obj.name.startswith(inside)
            value = (.36 if obj.name.startswith(('RearDestinationHousing','Side_Sign_Cabinet')) else 1.) if sign else 0.
            obj.color = (value,value,value,1)
        sc.render.filepath = str(directory/(key+'-inside.png'))
        bpy.ops.render.render(scene=sc.name, write_still=True)
    finally:
        for obj, color, hidden in original:
            obj.color = color
            obj.hide_render = hidden


def diagnostic(directory, cameras):
    for key, sc in cameras.items():
        sc.render.engine = 'BLENDER_WORKBENCH'
        sc.display.shading.color_type = 'MATERIAL'
        sc.display.shading.light = 'STUDIO'
        sc.display.shading.show_shadows = True
        sc.render.filepath = str(directory/(key+'-beauty.png'))
        bpy.ops.render.render(scene=sc.name, write_still=True)
        render_ids(sc,directory,key)


if __name__ == '__main__':
    import sys
    folder = Path(sys.argv[-1]).resolve()
    diagnostic(folder,camera_scenes(folder))
