"""Temporary daylight test stand. Saved vehicle contains no stage or camera objects."""
import math
import bpy
from mathutils import Vector


def area(name,pos,target,power,size,size_y,color):
    data=bpy.data.lights.new(name,'AREA')
    data.shape='RECTANGLE';data.energy=power;data.size=size;data.size_y=size_y;data.color=color
    ob=bpy.data.objects.new(name,data);bpy.context.collection.objects.link(ob)
    ob.location=pos;ob.rotation_euler=(Vector(target)-Vector(pos)).to_track_quat('-Z','Y').to_euler()


def stage():
    scene=bpy.context.scene
    world=bpy.data.worlds.new('Daylight')
    scene.world=world
    bg=world.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value=(.65,.77,.90,1)
    bg.inputs['Strength'].default_value=.85
    def rectangle(name,x,y,z,w,h,color):
        mesh=bpy.data.meshes.new(name)
        mesh.from_pydata([(x-w/2,y-h/2,z),(x+w/2,y-h/2,z),(x+w/2,y+h/2,z),(x-w/2,y+h/2,z)],[],[(0,1,2,3)])
        mat=bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(*color,1)
        mesh.materials.append(mat)
        bpy.context.collection.objects.link(bpy.data.objects.new(name,mesh))
    rectangle('Test surface',0,0,-.009,350,350,(.22,.247,.258))
    for s in (-1,1):
        rectangle('Edge stripe',s*3.2,25,-.006,.095,125,(.71,.71,.65))
        for i in range(18):rectangle('Road marking',s*1.77,-13+5*i,-.005,.09,1.85,(.76,.77,.73))
    area('Daylight port',(-4,2,5),(0,0,1.2),720,7,6,(1,.93,.83))
    area('Daylight starboard',(4,-1,4),(0,0,1.4),640,8,5,(.83,.90,1))
    area('Windshield daylight',(0,8,4),(0,3,1),430,4,3,(.91,.96,1))
    for k,y in enumerate([-3.75,-1.6,.65,3.12]):
        area('Cabin practical',(.05,y,2.52),(0,y,1),22 if k<3 else 17,.86,1.15,(1,.94,.83))


def render_set(exterior,folder,draft=False,only=None):
    folder.mkdir(exist_ok=True)
    with bpy.data.libraries.load(str(exterior),link=False) as (src,dst):
        dst.objects=[n for n in src.objects if n!='INTERIOR_PLACEHOLDER']
    for obj in dst.objects:
        bpy.context.collection.objects.link(obj)
    stage()
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.samples=6 if draft else 36
    scene.cycles.use_denoising=True
    scene.cycles.transparent_max_bounces=12
    prefs=bpy.context.preferences.addons['cycles'].preferences
    try:
        prefs.compute_device_type='METAL'
        prefs.get_devices()
        devices=[d for d in prefs.devices if d.type=='METAL']
        if devices:
            for dev in prefs.devices:dev.use=dev in devices
            scene.cycles.device='GPU'
    except (TypeError,RuntimeError):
        pass
    scene.view_settings.view_transform='AgX'
    scene.view_settings.exposure=.32
    # The exterior is authored for single-sided realtime glass. Cycles otherwise
    # stacks its preview opacity at both sides of every 3 mm pane. Only the
    # appended studio copy uses this daylight transmission; a control retains the original.
    pane=bpy.data.materials['glass'].node_tree.nodes.get('Principled BSDF')
    original_alpha=pane.inputs['Alpha'].default_value
    pane.inputs['Alpha'].default_value=.115
    scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGB'
    scene.render.resolution_percentage=35 if draft else 100
    data=bpy.data.cameras.new('Review lens');data.sensor_fit='HORIZONTAL';data.clip_start=.025
    camera=bpy.data.objects.new('Review lens',data);bpy.context.collection.objects.link(camera);scene.camera=camera
    eye=bpy.data.objects['DRIVER_EYE'].matrix_world.translation
    shots=[('01_driver_eye',eye,(eye.x,eye.y+1,eye.z-.515),60,1280,1376),
           ('02_saloon_to_front',(-.08,-4.35,1.97),(.02,1.67,1.47),81,1440,960),
           ('03_saloon_to_rear',(-.49,3.47,1.74),(.04,-1.42,1.59),82,1440,960),
           ('04_through_glazing',(3.28,1.96,1.95),(-.61,.57,1.53),63,1440,960),
           ('05_driver_station',(-.92,3.22,2.08),(.43,3.98,1.35),77,1440,960),
           ('06_exterior_glass_original',(3.35,4.96,2.18),(.03,3.84,1.59),65,1440,960),
           ('07_driver_eye_wide',eye,(eye.x,eye.y+1,eye.z-.515),
            math.degrees(2*math.atan(math.tan(math.radians(30))*16/9)),1600,900)]
    for name,pos,target,angle,w,h in shots:
        if only and name != only:
            continue
        pane.inputs['Alpha'].default_value=original_alpha if name.startswith('06') else .115
        camera.location=pos
        camera.rotation_euler=(Vector(target)-Vector(pos)).to_track_quat('-Z','Y').to_euler()
        data.angle=math.radians(angle)
        scene.render.resolution_x=w;scene.render.resolution_y=h
        scene.render.filepath=str(folder/(name+'.png'))
        bpy.ops.render.render(write_still=True)
