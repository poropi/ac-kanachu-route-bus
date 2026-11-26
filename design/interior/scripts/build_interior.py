"""Build the stand-alone AC interior and its combined exterior/interior render set.
Usage: blender -b --factory-startup --python-exit-code 1 --python design/interior/scripts/build_interior.py
"""
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import bpy
from mathutils import Vector

HERE=Path(__file__).resolve().parent
OUT=HERE.parent
EXTERIOR=OUT.parent/'exterior'/'kanachu_exterior.blend'
sys.dont_write_bytecode=True
sys.path.insert(0,str(HERE))
from geometry import empty, material
import cabin
import cockpit
from studio import render_set

COLORS={
    'dash':('4c5055',.52), 'panel':('353b44',.45),'pad':('42464b',.58),
    'grip':('292d31',.61),'back':('5e656a',.52),'piping':('203f55',.66),
    'foot':('41494d',.55,.28),'seal':('2b3031',.72),'sill':('969da0',.43,.29),
    'headliner':('e8e8dd',.7),'sidewall':('d9dcd2',.57),'wheeltrim':('80878b',.65),
    'edge':('e7b739',.49),'orange':('f18c29',.40,.12),'joint':('666b6d',.39,.42),
    'metal':('b9bfc1',.26,.76),'strap':('b1aaa1',.78),'ivory':('f2eee2',.48),
    'buttoncream':('ebbd5e',.44),'stopred':('d34331',.38),'vent':('333a3a',.65),
    'ventblade':('686f6b',.51),'bezel':('585e61',.35,.41),'amber':('d7792d',.43),
    'needle':('fc6035',.41,0,.22),'lamp':('fff5dc',.32,0,2.1)
}
GRAPHICS={
    'speed':('25282a',.205),'rpm':('25282a',.205),'fare':('344053',.50),
    'telltales':('4a4d4e',.25),'cluster':('8c9d82',.33),'stop':('b4503e',.03),
    'moquette':('215c90',0),'priority':('23548e',0),'driver_cloth':('23539c',0),
    'floor':('4f5052',0),'priority_sign':('e8e3d1',0),'ticket':('ebe6d6',0),
    'ic':('2b5889',.09),'radio':('3c4246',.06),'rockers':('41464a',.08),'pay_screen':('344653',.36),'fare_slot':('ebe6d6',0),'exit_sign':('ebe6d6',0),
    'boarding':('ebe6d6',0),'notice':('ebe6d6',0),'partition_sign':('ebe6d6',0)
}

def read_body():
    bpy.ops.wm.open_mainfile(filepath=str(EXTERIOR))
    def coords(obj):
        return [obj.matrix_world @ v.co for v in obj.data.vertices]
    def bounds(obj):
        pts=coords(obj)
        return [tuple(fn(v[i] for v in pts) for i in range(3)) for fn in (min,max)]
    liner=bpy.data.objects['INTERIOR_PLACEHOLDER']
    pts=coords(liner)
    return {'liner':[[tuple(pts[i]) for i in p.vertices] for p in liner.data.polygons],
            'windows':{o.name:bounds(o) for o in bpy.data.objects if '_Window_' in o.name and o.name.endswith('_Glass')},
            'doors':{n:bounds(bpy.data.objects[n]) for n in ['DOOR_FRONT','DOOR_MID']}}

def build():
    ext=read_body()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version=0
    bpy.context.scene.unit_settings.system='METRIC'
    root=empty('COCKPIT_HR')
    root['passenger_seats']=27
    root['standing_capacity']=51
    mats={key:material(key,*vals) for key,vals in COLORS.items()}
    mats['guardglass']=material('guardglass','c7d9dc',.15,alpha=.095)
    with tempfile.TemporaryDirectory(dir=OUT) as folder:
        subprocess.run(['/usr/bin/python3',str(HERE/'graphics.py'),folder],check=True)
        for key,(color,glow) in GRAPHICS.items():
            name='linoleum' if key=='floor' else key
            rough=.87 if key in ('moquette','priority','driver_cloth','floor') else .52
            mats[key]=material(key,color,rough,emission=glow,image=Path(folder)/(name+'.png'))
            img=mats[key].node_tree.nodes.get('Image Texture').image
            img.filepath='//'+name+'.png'
        cabin.lining(root,mats,ext)
        cabin.seats(root,mats)
        cabin.fittings(root,mats)
        cabin.ceiling(root,mats)
        cockpit.operator(root,mats)
        cockpit.dashboard(root,mats)
        cockpit.steering(root,mats)
        cockpit.fare_equipment(root,mats)
        bpy.context.view_layer.update()
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type=='VIEW_3D':
                    space=area.spaces.active
                    space.region_3d.view_rotation=Vector((-.47,.85,-.24)).to_track_quat('-Z','Y')
                    space.region_3d.view_distance=7.65
                    space.region_3d.view_location=(0,0,1.3)
                    space.overlay.show_overlays=False
                    space.shading.color_type='MATERIAL'
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'kanachu_interior.blend'),compress=True)
    return bpy.context.scene

if __name__=='__main__':
    if '--render-only' in sys.argv:
        bpy.ops.wm.open_mainfile(filepath=str(OUT/'kanachu_interior.blend'))
    else:
        build()
    if '--model-only' not in sys.argv:
        shot=next((arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--shot=')),None)
        render_set(EXTERIOR,OUT/'renders',draft='--draft' in sys.argv,only=shot)
