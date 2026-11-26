"""Build the LV290 exterior in metres. Run with Blender 5.2 in background mode."""
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import bpy
from mathutils import Vector

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))
import wheels
import fascias
import atlas
import coach_profile
import photo_views

FRONT, REAR = 4.950, -5.480
WIDTH = 1.2425
SHOULDER = 2.80
SILL, HEADER = 1.305, 2.530
FLOOR = .315
LEFT_DOORS = [(3.565, 4.695), (-1.395, -.260)]
LEFT_WINDOWS = [(2.115, 3.565), (.895, 2.115), (-.260, .895),
                (-3.255, -1.395), (-5.160, -3.255)]
RIGHT_WINDOWS = [(3.585, 4.675), (1.955, 3.585), (.610, 1.955),
                 (-.655, .610), (-1.835, -.655), (-3.585, -1.835),
                 (-4.295, -3.585), (-5.025, -4.295)]
# On fu43 the radiator screen has a narrow top inlet, the large field
# below, and a short centre extension visible beneath the large field.
INTAKE_FIELDS = ((-4.930, -4.414, 1.202, 1.259, 12, 3),
                 (-4.930, -4.395, .633, 1.122, 14, 23),
                 (-4.771, -4.553, .562, .633, 5, 4))
AXLES = [-2.65, 2.65]
ARCH = .581
MATS = {}
root = None


def make_materials():
    # All colours are scene-linear. The shared light/lens shaders use object colour.
    settings = {
        'paint': ((.81, .824, .792), .23, .20),
        'trim_black': ((.014, .017, .018), .38, .10),
        'chrome': ((.64, .69, .73), .19, .94),
        'glass': ((.033, .066, .072), .12, .30),
        'glass_light': ((.7, .74, .72), .16, .35),
        'light_emit': ((.8, .78, .65), .24, .12),
        'dest_led': ((.045, .070, .065), .48, .04),
        'tyre': ((.026, .028, .028), .66, .025),
        'rim': ((.54, .565, .56), .29, .70),
        'rubber': ((.029, .031, .030), .57, .02),
    }
    for name, (rgb, rough, metal) in settings.items():
        m = bpy.data.materials.new(name)
        m.diffuse_color = (*rgb, 1)
        tree = m.node_tree
        p = tree.nodes.get('Principled BSDF')
        p.inputs['Base Color'].default_value = (*rgb, 1)
        p.inputs['Roughness'].default_value = rough
        p.inputs['Metallic'].default_value = metal
        if name in ('trim_black','rubber','dest_led'):
            p.inputs['Specular IOR Level'].default_value=.20
        if name == 'paint':
            p.inputs['Coat Weight'].default_value = .33
            p.inputs['Coat Roughness'].default_value = .21
        if name == 'glass':
            p.inputs['Alpha'].default_value = .57
            p.inputs['Coat Weight'].default_value = .65
            p.inputs['Coat Roughness'].default_value = .07
            m.use_backface_culling = True
            m.surface_render_method = 'BLENDED'
            m.show_transparent_back = False
            m.diffuse_color = (*rgb, .48)
        if name in ('glass_light', 'light_emit'):
            attr = tree.nodes.new('ShaderNodeObjectInfo')
            tree.links.new(attr.outputs['Color'], p.inputs['Base Color'])
            if name == 'light_emit':
                tree.links.new(attr.outputs['Color'], p.inputs['Emission Color'])
                p.inputs['Emission Strength'].default_value = .32
            else:
                p.inputs['Alpha'].default_value = .38
                p.inputs['Coat Weight'].default_value = .6
        MATS[name] = m


def mesh(name, verts, faces, material, chart=None, coords=None, parent=None):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    o = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(o)
    o.parent = root if parent is None else parent
    data.materials.append(MATS[material])
    uv = data.uv_layers.new(name='UVMap')
    if chart:
        o['chart'] = chart
    for p in data.polygons:
        axis = max(range(3), key=lambda i: abs(p.normal[i]))
        uv_axes = [(1, 2), (0, 2), (0, 1)][axis]
        for li in p.loop_indices:
            vi = data.loops[li].vertex_index
            if coords is None:
                co = data.vertices[vi].co
                pair = tuple(co[a] for a in uv_axes)
            else:
                pair = coords[vi]
            uv.data[li].uv = pair
    if material in ('glass_light', 'light_emit'):
        o.color = (.72, .8, .85, 1)
    return o


def box(name, center, size, material, bevel=0, parent=None):
    x, y, z = center
    a, b, c = (i / 2 for i in size)
    verts = [(x+i*a, y+j*b, z+k*c) for k in (-1,1) for j in (-1,1) for i in (-1,1)]
    faces = [(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)]
    o = mesh(name, verts, faces, material, parent=parent)
    if bevel:
        mod = o.modifiers.new('Pressed edge', 'BEVEL')
        mod.width = bevel
        mod.segments = 3
        mod.harden_normals = True
        normal = o.modifiers.new('Face normals','WEIGHTED_NORMAL')
        normal.keep_sharp = True
    return o


def rod(name, points, radius, material, parent=None):
    # Parallel transport around a polyline, avoiding twists at changes of direction.
    verts, faces, prior = [], [], None
    pts = list(map(Vector, points))
    n = 10
    for j, p in enumerate(pts):
        tangent = (pts[min(j+1,len(pts)-1)] - pts[max(0,j-1)]).normalized()
        if prior is None:
            prior = Vector((0,0,1) if abs(tangent.z)<.85 else (1,0,0))
        u = (prior - tangent * prior.dot(tangent)).normalized()
        v = tangent.cross(u)
        prior = u
        for i in range(n):
            t = 2*math.pi*i/n
            verts.append(p + radius*(math.cos(t)*u + math.sin(t)*v))
        if j:
            for i in range(n):
                k = (i+1)%n
                faces.append(((j-1)*n+i,(j-1)*n+k,j*n+k,j*n+i))
    faces += [tuple(reversed(range(n))), tuple(range(len(verts)-n,len(verts)))]
    o = mesh(name, verts, faces, material, parent=parent)
    for p in o.data.polygons[:-2]: p.use_smooth = True
    return o


def tangent_height(distance, degrees):
    a = math.radians(degrees)
    return distance * math.tan(a) + .478*(1-1/math.cos(a))


def bottom(front):
    return tangent_height(FRONT-2.65 if front else -REAR-2.65, 9.6 if front else 8.4)


def end(front, x, z):
    # Mild rake of the windscreen and crown in plan; the bumper defines length.
    s = 1 if front else -1
    if front:
        inset=.045*(min(z,1.18)-bottom(True))+.081*max(0,z-1.18)
    else:
        belt=bottom(False)+.197
        inset=.034*min(1,(z-bottom(False))/.197)+.016*max(0,z-belt)
    # Carry the windscreen and the black lamp surrounds around the front corners.
    wrap=1+.052*max(0,min(1,(2.80-z)/.40))
    crown=.042*(x/1.12)**2
    if front:
        # The glass, bumper and lamp pockets curve into the boarding-side jamb.
        # The old almost planar front ended far ahead of that side tangent.
        t=max(0.,min(1.,(abs(x)-.58)/.54))
        crown += max(0.,.178-inset)*t*t
        wrap += .032*t*t
    return (x*wrap,(FRONT if front else REAR)-s*(inset+crown),z)


def front_developed_x(x,z):
    # Arc length along the pressed front panel at this height. Use the same
    # atlas coordinate on both sides of every joint and window aperture.
    stops=sorted({0,abs(x),min(.58,abs(x)),*(abs(x)*k/24 for k in range(1,24))})
    from coach_profile import shaped_point
    curve=[shaped_point(*end(True,station,z)) for station in stops]
    return math.copysign(sum(math.dist(a,b) for a,b in zip(curve,curve[1:])),x)


def outer_x(z):
    shoulder=max(0,min(1,(z-2.59)/.21))
    return WIDTH-.009-.013*max(0,1.10-z)-.078*(1-math.sqrt(1-.976*shoulder**2))


def side_point(sign, station, z, offset=0):
    return (sign*(outer_x(z)+offset), station, z)


def skirt(y):
    # The skirt steps up outside the wheel openings on both overhangs.
    # The measured lower edges of the entrance and engine bay are above
    # the chassis approach / departure tangents near the axles.
    overhang = max(0., min(1., (abs(y)-2.65)/.58))
    lower_edge = .228 + overhang*(.074 if y>0 else .082)
    return max(lower_edge, tangent_height(y-2.65,9.6), tangent_height(-y-2.65,8.4))


def arch_top(y):
    d = min(abs(y-a) for a in AXLES)
    if d >= ARCH-1e-7:
        return skirt(y)
    # Near-vertical ends lead into the flattened top of the pressed wheel opening.
    return .477 + .588*(max(0,1-(d/ARCH)**2.65)**(1/2.65))


class Patches:
    """Weld panel vertices when both their physical and developed positions agree."""
    def __init__(self):
        self.verts, self.faces, self.coords, self.index = [], [], [], {}

    def face(self, verts, coords, reverse=False):
        ids = []
        for pos, uv in zip(verts,coords):
            key = tuple(round(float(v),7) for v in (*pos,*uv))
            if key not in self.index:
                self.index[key] = len(self.verts)
                self.verts.append(pos)
                self.coords.append(uv)
            ids.append(self.index[key])
        self.faces.append(ids[::-1] if reverse else ids)

    def emit(self, name, material, chart=None, parent=None):
        return mesh(name,self.verts,self.faces,material,chart,self.coords,parent)


def corner(sign, front, t, z):
    # t=0 at the tangent to the long side, pi/2 at the tangent to the end.
    s = 1 if front else -1
    yc = (FRONT-.240) if front else (REAR+.235)
    xe, ye, _ = end(front,sign*1.12,z)
    return (xe+(sign*outer_x(z)-xe)*math.cos(t),
            yc+(ye-yc)*math.sin(t),z)


def corner_part(sign,front,patch):
    yc = FRONT-.240 if front else REAR+.235
    s = 1 if front else -1
    lo = bottom(front)
    zlevels = [0,.12,.27,.45,.70,.90,.94,.965,.98,.99,1.0]
    for i in range(12):
        a,b = [v*math.pi/24 for v in (i,i+1)]
        def point(t,f):
            h0 = skirt(yc)+(lo-skirt(yc))*math.sin(t)
            z = h0+(SHOULDER-h0)*f
            return corner(sign,front,t,z)
        def uv(t,z):
            # Develop the arc at belt-line height; shared side tangent stays aligned.
            length = 0
            last = corner(sign,front,0,1.3)
            for k in range(1,17):
                p=corner(sign,front,t*k/16,1.3)
                length += math.dist(p,last)
                last=p
            return (-yc-s*length,z)
        for f,g in zip(zlevels,zlevels[1:]):
            vs=[point(a,f),point(b,f),point(b,g),point(a,g)]
            uvs=[uv(t,p[2]) for t,p in zip((a,b,b,a),vs)]
            patch.face(vs,uvs,reverse=sign*s<0)


def rrect(low, high, z0, z1, radius, n=5):
    # Counterclockwise in the station/height plane.
    out=[]
    r = min(radius,(high-low)*.48,(z1-z0)*.48)
    for cy,cz,start in ((high-r,z0+r,-90),(high-r,z1-r,0),
                         (low+r,z1-r,90),(low+r,z0+r,180)):
        for j in range(n+1):
            t=math.radians(start+90*j/n)
            out.append((cy+r*math.cos(t),cz+r*math.sin(t)))
    return out


def side_surface(name,sign,outer,material,offset=0,inner=None,chart=None,parent=None):
    coords = outer if inner is None else outer+inner
    is_entry = name=='DOOR_FRONT' or (parent is not None and parent.name=='DOOR_FRONT')
    def positioned(y,z):
        if is_entry:
            z += max(0,skirt(y)+.008-.298)*max(0,min(1,(.70-z)/.402))
        return side_point(sign,y,z,offset)
    vs=[positioned(y,z) for y,z in coords]
    n=len(outer)
    if inner is None:
        faces=[tuple(range(n))]
    else:
        faces=[(i,(i+1)%n,n+(i+1)%n,n+i) for i in range(n)]
    if sign<0: faces=[f[::-1] for f in faces]
    return mesh(name,vs,faces,material,chart,[(-y,z) for y,z in coords],parent)


def bead(name,sign,y0,y1,z0,z1,material,offset=0,r=.006,parent=None):
    return side_surface(name,sign,rrect(y0,y1,z0,z1,r), material,offset,parent=parent)


def window(sign, a,b, idx, side):
    name=f'{side}_Window_{idx:02d}'
    out=rrect(a,b,SILL,HEADER,.003)
    inside=rrect(a+.030,b-.030,SILL+.041,HEADER-.038,.048)
    side_surface(name+'_Frit',sign,out,'trim_black',-.002,inside)
    glass=side_surface(name+'_Glass',sign,inside,'glass',-.005)
    # Hopper opening rail on the bays that show an upper ventilator in the reference.
    split = (sign<0 and idx in [1,4,5]) or (sign>0 and idx in [3,4,5,6])
    if split:
        z=2.050
        bead(name+'_Transom',sign,a+.021,b-.021,z-.018,z+.018,'trim_black',.000)
        bead(name+'_RailEdge',sign,a+.040,b-.040,z+.010,z+.016,'rubber',.002)
        bead(name+'_Latch',sign,(a+b)*.5-.058,(a+b)*.5+.058,z+.023,z+.038,'trim_black',.004)
    if sign>0 and idx==1:
        # Sliding driver's pane with a separate narrow forward sash.
        y=b-.56
        bead(name+'_SlidingSash',sign,y-.013,y+.013,SILL+.038,HEADER-.045,'trim_black',.001)
        bead(name+'_Grip',sign,y+.011,y+.024,1.82,1.93,'rubber',.005)
    if sign<0 and idx==5:
        y=a+.82
        bead(name+'_UpperDivider',sign,y-.013,y+.013,2.066,HEADER-.025,'trim_black',.001)
    if sign<0 and idx==1:
        cy=(a+b)*.5
        casing=rrect(cy-.61,cy+.61,2.085,2.495,.032)
        side_surface('Side_Sign_Cabinet',sign,casing,'trim_black',-.036)
        # Mounted just behind the pane, correctly visible from the kerb.
        side_surface('DEST_SIDE',sign,rrect(cy-.545,cy+.545,2.137,2.441,.014),'dest_led',-.032)
    return glass


def door_pane(sign,name,a,b,lo,hi,parent,sliding=False):
    outer=rrect(a,b,lo,hi,.009)
    if sliding:
        inside=rrect(a+.330,b-.067,lo+.145,hi-.207,.035)
    else:
        inside=rrect(a+.040,b-.040,lo+.084,hi-.058,.035)
    side_surface(name+'_Frame',sign,outer,'trim_black',-.002,inside,parent=parent)
    side_surface(name+'_Glass',sign,inside,'glass',-.006,parent=parent)


def door_hardware(leaf,a,b,parent):
    # Folding leaves carry their own pull rail and lower protective panel.
    center=(a+b)/2
    bead(leaf+'_KickPlate',-1,a+.036,b-.036,.365,.690,'trim_black',.001,parent=parent)
    for z in (.539,.561,.583):
        bead(leaf+'_KickRib',-1,a+.042,b-.042,z,z+.008,'rubber',.003,parent=parent)
    rod(leaf+'_Handrail',[(-1.203,a+.080,.855),(-1.177,a+.12,.851),
            (-1.174,b-.12,.793),(-1.201,b-.080,.790)],.010,'rim',parent)
    bead(leaf+'_PivotCap',-1,center-.025,center+.025,2.296,2.325,'rubber',.001,parent=parent)


def doors():
    for i,(a,b) in enumerate(LEFT_DOORS):
        sign=-1
        name=('DOOR_FRONT','DOOR_MID')[i]
        lo = .298 if i==0 else .275
        outer=rrect(a,b,lo,HEADER,.002)
        inner=rrect(a+.021,b-.021,lo+.025,HEADER-.025,.012)
        main=side_surface(name,sign,outer,'rubber',-.001,inner)
        for y in (a+.029,b-.029):
            bead(name+'_Jamb',sign,y-.009,y+.009,lo+.022,HEADER-.018,'trim_black',.000,parent=main)
        bead(name+'_StepNosing',sign,a+.03,b-.03,lo+.015,lo+.038,'chrome',.001,parent=main)
        a,b = a+.019,b-.019
        if i==0:
            mid=(a+b)*.5
            for j,(ya,yb) in enumerate(((a,mid),(mid,b))):
                door_pane(sign,f'Entrance_Leaf_{j+1}',ya,yb,lo+.027,2.302,main)
                door_hardware(f'Entrance_Leaf_{j+1}',ya,yb,main)
            for zh in (.62,1.75):
                bead('Entrance_Hinge',sign,mid-.009,mid+.009,zh,zh+.085,'rubber',.003,parent=main)
            bead('Entrance_Head',sign,a,b,2.301,HEADER-.019,'trim_black',-.002,parent=main)
        else:
            rail=SILL-.008
            door_pane(sign,'Sliding_Pane',a,b,rail,HEADER-.021,main,sliding=True)
            side_surface('Sliding_Painted_Apron',sign,rrect(a,b,lo+.038,rail,.004),
                         'paint',-.004,chart='LEFT',parent=main)
            bead('Sliding_TrailingGuide',sign,a+.148,a+.182,lo+.028,rail+.012,'trim_black',.001,parent=main)
            bead('Sliding_Grip',sign,a+.043,a+.063,.72,.84,'trim_black',.002,parent=main)
            bead('Sliding_Track',sign,a+.20,b-.20,2.404,2.435,'rubber',.001,parent=main)


def intake_screens():
    """Punch the three radiator screens in their original side paint chart."""
    grille=Patches()
    for idx,(a,b,lo,hi,cols,rows) in enumerate(INTAKE_FIELDS,1):
        # Outboard enamel web and the dark radiator recessed behind the holes.
        bead(f'Cooling_Intake_Core_{idx}',1,a,b,lo,hi,'trim_black',-.011,.001)
        dy,dz=(b-a)/cols,(hi-lo)/rows
        def strip(y0,y1,z0,z1):
            corners=[(y0,z0),(y1,z0),(y1,z1),(y0,z1)]
            grille.face([side_point(1,y,z) for y,z in corners],[(-y,z) for y,z in corners])
        for row in range(rows):
            bottom=lo+row*dz
            strip(a,b,bottom,bottom+.22*dz)
            for col in range(cols):
                edge=a+col*dy
                strip(edge,edge+.22*dy,bottom+.22*dz,bottom+dz)
            strip(b-.08*dy,b,bottom+.22*dz,bottom+dz)
    grille.emit('Cooling_Intake_PunchedSteel','paint','RIGHT')


def side_body(sign):
    left = sign < 0
    label = 'Left' if left else 'Right'
    chart = label.upper()
    windows = LEFT_WINDOWS if left else RIGHT_WINDOWS
    apertures = [(a,b,SILL) for a,b in windows]
    if left:
        apertures.extend((a,b,.298 if i==0 else .275) for i,(a,b) in enumerate(LEFT_DOORS))
    yc0,yc1=REAR+.235,FRONT-.240
    stations={yc0,yc1}
    for a,b,_ in apertures: stations.update([a,b])
    if not left:
        stations.update(y for a,b,*_ in INTAKE_FIELDS for y in (a,b))
    for axle in AXLES:
        for i in range(43):
            stations.add(round(axle+ARCH*math.cos(math.pi*i/42),8))
    # Include the kinks of the skirt and longitudinal service doors.
    stations.update([-4.243,-3.64,-2.04,-1.82,-.12,.64,1.965,3.36,4.039])
    ys=sorted(stations)
    sheet=Patches()
    for ya,yb in zip(ys,ys[1:]):
        ym=(ya+yb)*.5
        is_arch=any(abs(ym-axle)<ARCH for axle in AXLES)
        def lower(y):
            d=min(abs(y-a) for a in AXLES)
            if is_arch and abs(d-ARCH)<1e-6: return .477
            return arch_top(y) if is_arch else skirt(y)
        opening=next((low for a,b,low in apertures if a<ym<b),None)
        lowa,lowb=lower(ya),lower(yb)
        def strip(z0a,z0b,z1a,z1b):
            # Support the curved section between the arch lip and the sill.
            # In the narrow cells at either end of an arch, one tall quad
            # would twist across the break in the side-wall slope.
            rows=[(z0a,z0b)]
            for height in (.60,.72,.87,1.00,1.10,1.20,1.305):
                if max(z0a,z0b)+1e-5 < height < min(z1a,z1b)-1e-5:
                    rows.append((height,height))
            rows.append((z1a,z1b))
            for (a0,b0),(a1,b1) in zip(rows,rows[1:]):
                yz=[(ya,a0),(yb,b0),(yb,b1),(ya,a1)]
                sheet.face([side_point(sign,y,z) for y,z in yz],[(-y,z) for y,z in yz],reverse=left)
        if opening is None: strip(lowa,lowb,HEADER,HEADER)
        else:
            # Remove the door sill entirely where the sloping nose meets the entrance.
            if left and LEFT_DOORS[0][0]<ym<LEFT_DOORS[0][1]:
                strip(lowa,lowb,max(opening,lowa+.008),max(opening,lowb+.008))
            else:
                fields=sorted((lo,hi) for a,b,lo,hi,*_ in INTAKE_FIELDS if not left and a<ym<b)
                for lo,hi in fields:
                    if lo>lowa+1e-6: strip(lowa,lowb,lo,lo)
                    lowa=lowb=hi
                strip(lowa,lowb,opening,opening)
        for z,zz in zip((HEADER,2.64,2.70,2.755,2.785),(2.64,2.70,2.755,2.785,SHOULDER)):
            strip(z,z,zz,zz)
    for f in (False,True): corner_part(sign,f,sheet)
    sheet.emit(label+'_Coachwork','paint',chart)
    for i,(a,b) in enumerate(windows,1): window(sign,a,b,i,label)
    # Follow the tapered end pillars between the first and last bay. A
    # straight chord between those pillars would run under the central skin.
    start=windows[-1][0]
    finish=LEFT_DOORS[0][1] if left else windows[0][1]
    segments=math.ceil((finish-start)/.18)
    for offset,rad,z,material in ((.004,.005,HEADER+.016,'rubber'),(.004,.0065,HEADER+.033,'rim')):
        rod(label+'_DripRail',[(sign*(WIDTH-rad),start+(finish-start)*i/segments,z)
                               for i in range(segments+1)],rad,material)
    for axle in AXLES:
        path=[]
        for i in range(65):
            t=math.pi*i/64
            y=axle+ARCH*math.cos(t)
            top=.477+.588*max(0,1-abs(math.cos(t))**2.65)**(1/2.65)
            path.append((y,top))
        path=[(path[0][0],skirt(path[0][0]))]+path+[(path[-1][0],skirt(path[-1][0]))]
        vs = [(sign*x,y,z) for x in (outer_x(.7)-.0005,.675) for y,z in path]
        n=len(path)
        fs=[(i,i+1,n+i+1,n+i) for i in range(n-1)]
        if sign<0:fs=[f[::-1] for f in fs]
        mesh(label+'_WheelhouseReturn',vs,fs,'trim_black')
        # Fine rolled lip around the actual opening (no body panel behind the tyre).
        rod(label+'_ArchLip',[side_point(sign,y,z,.000) for y,z in path],.007,'rubber')
        if axle<0:
            # The short flap is visible behind the outside tyre in the left-front photograph.
            ya=axle-.545
            outline=[(.640,.585),(1.175,.585),(1.175,.165),(1.151,.150),(.640,.150)]
            verts=[(sign*x,ya+dy,z) for dy in (-.005,.005) for x,z in outline]
            faces=[(4,3,2,1,0),(5,6,7,8,9)]+[(i,(i+1)%5,5+(i+1)%5,5+i) for i in range(5)]
            mesh(label+'_DriveAxleMudflap',verts,faces if sign>0 else [f[::-1] for f in faces],'rubber')
    def joint(name, coords, r=.0028):
        rod(label+'_'+name,[side_point(sign,y,z,.0014) for y,z in coords],r,'rubber')
    # Gaps, hinge barrels and quarter turn fasteners on the inspection hatches.
    cuts=([-4.53,-3.37,-.30,.81] if left else [-4.95,-4.29,-3.61,-1.24,.90,3.70])
    for y in cuts:
        z0=arch_top(y)+.014
        if any(a<y<b for a,b,_ in apertures if _<1): continue
        upper=(1.277 if (left and y==-4.53) or (not left and y in (-4.95,-4.29,-3.61,3.70)) else .689)
        joint('ServiceJoint',[(y,z0),(y,max(upper,z0+.012))])
    lids=([(-4.53,-3.37,.688),(-4.53,-3.37,.718),(-.245,1.995,.689)] if left
          else [(-4.29,-3.61,.765),(-4.29,-3.61,.864),(-3.61,-3.25,.689),
                (-2.06,2.062,.677),(3.70,4.65,1.035)])
    for a,b,z in lids:
        joint('LockerLid',[(a,z),(b,z)])
    markers=((3.375,.599),(1.89,.599),(-2.00,.591)) if left else ((3.585,.581),(2.013,.575),(-1.931,.570))
    for y,z in markers:
        if any(a<y<b for a,b in LEFT_DOORS) and left:continue
        bead(label+'_RepeaterBoot',sign,y-.065,y+.065,z-.040,z+.040,'trim_black',.002,.016)
        m=bead(label+'_RepeaterLens',sign,y-.052,y+.052,z-.030,z+.030,'light_emit',.005,.013)
        m.color=(.68,.22,.027,1)
    # Recessed twist catches and butt hinges on the fleet-maintenance access lids.
    catches=([(3.33,.48),(1.01,.40),(-1.805,.73),(-2.115,.76),(-1.99,.41),
              (-3.96,.51)] if left else [(-4.23,.38),(-3.80,.47),(-1.93,.45),(1.10,.40),(3.42,.46)])
    for y,z in catches:
        bead(label+'_LockerEscutcheon',sign,y-.019,y+.019,z-.020,z+.020,'rubber',.002,.008)
        bead(label+'_KeySlot',sign,y-.009,y+.009,z-.002,z+.002,'trim_black',.003,.001)
    if not left:
        intake_screens()
        joint('RearQuarterServiceFlap',[(-5.24,1.36),(-5.035,1.36),(-5.035,1.69),
                                        (-5.24,1.69),(-5.24,1.36)])
        bead('RearQuarterServiceLatch',sign,-5.206,-5.173,1.465,1.501,'trim_black',.002,.006)
        bead('Fuel_Filler_Recess',sign,-4.00,-3.85,.99,1.20,'trim_black',.002,r=.044)
        bead('Fuel_Filler_Cap',sign,-3.971,-3.879,1.02,1.17,'rubber',.004,r=.024)


def make_roof():
    xmax=outer_x(SHOULDER)
    xs=sorted(set([0]+[s*x for s in (-1,1) for x in
                      (.25,.50,.75,1.0,1.10,1.12,1.135,1.15,1.157,1.162,xmax) if x<=xmax]))
    def height(x):
        u=abs(x)/xmax
        return .088*max(0,1-u*u)**.54
    def limit(x,front):
        # The fascia generator takes developed station X, while the roof is
        # sampled at physical X. Invert the wrap at the shared top seam.
        tangent = end(front,1.12,SHOULDER)[0]
        if abs(x)<=tangent:
            low,high = 0.,1.12
            for _ in range(35):
                mid = (low+high)/2
                if end(front,mid,SHOULDER)[0] < abs(x):
                    low = mid
                else:
                    high = mid
            return end(front,(low+high)/2,SHOULDER)[1]
        t=math.acos(min(1,(abs(x)-tangent)/(xmax-tangent)))
        return corner(1,front,t,SHOULDER)[1]
    developed=[0]
    for a,b in zip(xs,xs[1:]):developed.append(developed[-1]+math.hypot(b-a,height(b)-height(a)))
    patch=Patches()
    def point(i,j):
        x=xs[i]
        back,fore=limit(x,False),limit(x,True)
        y=[back,back+.035,back+.10,back+.22,-3,0,3,fore-.22,fore-.10,fore-.035,fore][j]
        f=[0,.51,.84,1,1,1,1,1,.84,.51,0][j]
        return (x,y,SHOULDER+height(x)*f)
    for i in range(len(xs)-1):
        for j in range(10):
            ij=((i,j),(i+1,j),(i+1,j+1),(i,j+1))
            vs=[point(a,b) for a,b in ij]
            patch.face(vs,[(-v[1],developed[a]) for v,(a,_) in zip(vs,ij)])
    o=patch.emit('Crowned_Roof','paint','ROOF')
    for p in o.data.polygons:p.use_smooth=True
    # Low condenser cover, with rounded shoulders and sloped end ramps.
    profile=[(-.88,2.874),(-.88,2.937),(-.864,2.982),(-.83,3.028),(-.77,3.071),
             (-.67,3.093),(-.49,3.102),(0,3.105),(.49,3.102),(.67,3.093),
             (.77,3.071),(.83,3.028),(.864,2.982),(.88,2.937),(.88,2.874)]
    profile=[(x*1.13 if x>0 else x,z) for x,z in profile]
    rings=[(-.91,.83,.18),(-.84,.91,.47),(-.74,.97,.76),(-.63,1,.94),
           (-.54,1,1),(2.58,1,1),(2.64,.995,.90),(2.72,.994,.57),
           (2.80,.993,.12),(3.14,.94,.10),(3.44,.85,.08)]
    # The rear-facing moulding has a recessed notch to the right of centre.
    profile += [(x,3.105-.003*x/.49) for x in (.12,.16,.36,.40)]
    profile.sort(key=lambda v:v[0])
    # Keep the vertical skirt points last on the positive flank.
    profile[-2:]=sorted(profile[-2:],key=lambda v:-v[1])
    width=[0]
    for a,b in zip(profile,profile[1:]):width.append(width[-1]+math.dist(a,b))
    def pod(i,j):
        y,w,f=rings[i];x,z=profile[j]
        notch=min(1,max(0,(x-.12)/.04),max(0,(.40-x)/.04))
        recess=.065*notch*max(0,min(1,(-.54-y)/.27))
        # The plain right cheek continues ahead of the steep louvred apron.
        if i>=6:
            cheek=max(0,min(1,(x-.24)/.45))
            f += ([1,.99,.98,.88,.24][i-6]-f)*cheek
            w += (.016 if i<10 else -.025)*cheek
        height=2.874+(z-2.874)*f-.0045-recess
        if i>=6:
            # The front elevation limits the height of the long offside cheek.
            # Grade it into the forward apron instead of leaving a second hump.
            crest=3.132-.126*(y-2.50)-.042*(abs(x*w)/.95)**2
            height=min(height,crest)
        return (x*w,y,height)
    patch=Patches()
    for i in range(len(rings)-1):
        for j in range(len(profile)-1):
            ids=[(i,j),(i,j+1),(i+1,j+1),(i+1,j)]
            vs=[pod(a,b) for a,b in ids]
            patch.face(vs,[(-p[1],width[b]) for p,(_,b) in zip(vs,ids)])
    o=patch.emit('HVAC_Moulded_Cover','paint','AUX_HVAC')
    for face in o.data.polygons:
        face.use_smooth = face.center.y>-.55 or not (.11<face.center.x<.42)
    for i in (0,len(rings)-1):
        vs=[pod(i,j) for j in range(len(profile))]
        mesh('HVAC_EndSeal',vs,[tuple(range(len(vs))) if i else tuple(reversed(range(len(vs))))],'rubber')
    # The horizontal return at the stepped rear opening is visible from behind.
    groove=[]
    for x in (.16,.36):
        j=next(k for k,(u,_) in enumerate(profile) if u==x)
        a,b=pod(2,j),pod(3,j)
        groove.append(tuple(.5*(u+v)+( .003 if k==2 else 0.) for k,(u,v) in enumerate(zip(a,b))))
    rod('HVAC_Notch_Reveal',groove,.004,'rubber')
    # The row of openings is on the forward ramp, across the vehicle.
    # Sample the very same cover sections so the slots sit flush with its crown.
    def ramp_point(x, i):
        for j in range(1,len(profile)):
            p0,p1=pod(i,j-1),pod(i,j)
            if p0[0] <= x < p1[0]:
                t=(x-p0[0])/(p1[0]-p0[0])
                return (x,p0[1]+.004,p0[2]+t*(p1[2]-p0[2])+.003)
        raise ValueError('HVAC louvre outside the cover')
    for j in range(17):
        x=-.784+j*.093
        verts=[ramp_point(x+dx-.039*(i-6), i) for i in (6,7,8)
               for dx in (0,.042)]
        mesh('HVAC_Discharge_Slot',verts,[(2*i,2*i+1,2*i+3,2*i+2) for i in range(2)],'trim_black')
    for sign,stations in ((1,(-.23,.41,1.65)),(-1,(-.35,-.02,1.24,1.57))):
        for y in stations:
            pts=[(x+sign*.0015,y,z-.003) for x,z in profile if x*sign>=0]
            rod('HVAC_ServiceSeam',pts,.003,'rubber')
    # A separate shallow dome appears over each destination display.
    # Both use the same pressed rim section; the forward cap is shallower.
    section=((2.869,.286,.278),(2.894,.325,.325),(2.918,.333,.341),
             (2.942,.326,.331),(2.964,.298,.292),(2.982,.222,.227),
             (2.991,.128,.13),(2.993,.035,.035))
    for name,cy,base,radius,rise in [('Roof_Extractor',-4.69,2.869,1.,1.),
                                     ('Roof_Vent_Front',3.96,2.857,.92,.795)]:
        vs=[]; faces=[]
        for z,rx,ry in section:
            for i in range(48):
                t=2*math.pi*i/48
                vs.append((radius*rx*math.cos(t),cy+radius*ry*math.sin(t),base+(z-2.869)*rise))
        for k in range(len(section)-1):
            for i in range(48):
                j=(i+1)%48
                faces.append((k*48+i,k*48+j,(k+1)*48+j,(k+1)*48+i))
        faces.append(tuple(range(48*(len(section)-1),48*len(section))))
        extractor=mesh(name,vs,faces,'rim')
        for face in extractor.data.polygons: face.use_smooth=True


def make_interior():
    # The exterior stops at the glass. A single removable inner liner shields the road.
    vertices,faces=[],[]
    def quad(p):
        i=len(vertices);vertices.extend([(x,y,max(z,tangent_height(y-2.65,9.6)+.004)) for x,y,z in p]);faces.append((i,i+1,i+2,i+3))
    def level(y):
        if y< -1.91:return .785
        if y< -1.58:return .53
        return FLOOR
    ys=sorted(set([-4.80,4.695,-1.91,-1.58]+[a+s*.61 for a in AXLES for s in (-1,1)]+
                  [v for pair in LEFT_DOORS for v in pair]))
    for a,b in zip(ys,ys[1:]):
        y=(a+b)/2;z=level(y)
        near=any(abs(y-k)<.61 for k in AXLES)
        half=.605 if near else 1.155
        quad([(-half,a,z),(half,a,z),(half,b,z),(-half,b,z)])
        if a!=ys[0] and level(a-.001)!=z:
            quad([(-half,a,z),(half,a,z),(half,a,level(a-.001)),(-half,a,level(a-.001))])
        for s in (-1,1):
            door = s==-1 and any(p<y<q for p,q in LEFT_DOORS)
            sillz=1.099 if near else z
            if near:
                quad([(s*half,a,z),(s*half,b,z),(s*half,b,sillz),(s*half,a,sillz)])
                quad([(s*half,a,sillz),(s*1.155,a,sillz),(s*1.155,b,sillz),(s*half,b,sillz)])
                for v in (a,b):
                    if any(abs(abs(v-k)-.61)<.0001 for k in AXLES):
                        quad([(s*half,v,z),(s*1.155,v,z),(s*1.155,v,sillz),(s*half,v,sillz)])
            if not door:
                quad([(s*1.155,a,sillz),(s*1.155,b,sillz),(s*1.155,b,SILL+.002),(s*1.155,a,SILL+.002)])
            else:
                quad([(s*1.155,a,z),(s*1.23,a,z),(s*1.23,b,z),(s*1.155,b,z)])
    ceiling=FLOOR+2.405
    # The inner roof and its upper side returns follow the tapered shell.
    # The full interior width and height are reached in the central bay.
    stations=[-4.8,-4.2,-3.7,-3.12,0,2.65,3.20,3.8,4.28,4.695]
    for ya,yb in zip(stations,stations[1:]):
        for xa,xb in ((-1.155,0),(0,1.155)):
            quad([coach_profile.shaped_point(x,y,ceiling) for x,y in
                  ((xa,ya),(xa,yb),(xb,yb),(xb,ya))])
        for sign in (-1,1):
            quad([coach_profile.shaped_point(sign*1.155,y,z) for y,z in
                  ((ya,HEADER),(yb,HEADER),(yb,ceiling),(ya,ceiling))])
    quad([(-1.155,-4.8,.785),(1.155,-4.8,.785),(1.155,-4.8,1.975),(-1.155,-4.8,1.975)])
    quad([(-1.155,4.695,FLOOR),(-1.155,4.695,1.175),(1.155,4.695,1.175),(1.155,4.695,FLOOR)])
    # Inward-facing surfaces of the lining. Orient each side return towards the aisle.
    o=mesh('INTERIOR_PLACEHOLDER',vertices,faces,'trim_black')
    for p in o.data.polygons:
        mid=p.center
        if abs(p.normal.x)>.8 and p.normal.x*mid.x>0:p.flip()
        elif p.normal.z<-.8 and mid.z<2.0:p.flip()
    o.data.update()
    # Wheel-arch wells and their backs are opaque; the floor does not cut the wheels.
    for s in (-1,1):
        for y in AXLES:
            box('Wheelhouse_Back',(s*.649,y,.632),(.050,1.24,.87),'trim_black',.022)
    box('Underfloor_Centre',(0,.04,.214),(1.20,6.21,.168),'trim_black',.046)
    for s in (-1,1):
        box('Sill_Undertray',(s*.86,.03,.244),(.63,3.77,.026),'trim_black',.010)
        # The wider rear guards are fitted to the double-wheel arches above.
        box('Mudflap',(s*.974,2.65-.595,.278),(.423,.028,.16),'rubber',.008)
    for front in (False,True):
        y=(FRONT-.240 if front else REAR+.235)
        s=1 if front else -1
        # Close the underside to the bumper, following the approach/departure line.
        ya=(3.30 if front else -3.31)
        xx=1.214
        q=[(-xx,ya,skirt(ya)),(xx,ya,skirt(ya)),(xx,y,skirt(y)),(-xx,y,skirt(y))]
        mesh('Overhang_Undertray',q,[(3,2,1,0) if front else (0,1,2,3)],'trim_black')
        cap=[end(front,x,bottom(front)) for x in [-1.12,-.84,-.56,-.28,0,.28,.56,.84,1.12]]
        cap+= [corner(1,front,t*math.pi/24,bottom(front)) for t in range(11,-1,-1)]
        cap+= [corner(-1,front,t*math.pi/24,bottom(front)) for t in range(12)]
        mesh('Bumper_Splashshield',cap,[tuple(range(len(cap))) if front else tuple(reversed(range(len(cap))))],'trim_black')
    return o


def set_route_artwork(material):
    tree = material.node_tree
    previous = next((node for node in tree.nodes if node.type == 'TEX_IMAGE'), None)
    with tempfile.TemporaryDirectory(dir=OUT) as td:
        path = Path(td) / 'Kanachu_dot_matrix.png'
        subprocess.run(['/usr/bin/python3', '-B', str(HERE/'route_display.py'), str(path)], check=True)
        image = bpy.data.images.load(str(path))
        image.pack()
        image.filepath = '//' + path.name

    texture = previous if previous is not None else tree.nodes.new('ShaderNodeTexImage')
    texture.image = image
    # Every mesh retains its original UVs. The object index selects one of
    # three equal-height strips in the packed texture (front/badges, side, rear).
    bpy.data.objects['DEST_SIDE'].pass_index = 1
    bpy.data.objects['DEST_REAR'].pass_index = 2
    index = tree.nodes.new('ShaderNodeObjectInfo').outputs['Object Index']
    offset = tree.nodes.new('ShaderNodeCombineXYZ')
    tree.links.new(index, offset.inputs['Y'])
    uv = tree.nodes.new('ShaderNodeTexCoord')
    add = tree.nodes.new('ShaderNodeVectorMath')
    add.operation = 'ADD'
    tree.links.new(uv.outputs['UV'], add.inputs[0])
    tree.links.new(offset.outputs[0], add.inputs[1])
    scale = tree.nodes.new('ShaderNodeVectorMath')
    scale.operation = 'MULTIPLY'
    tree.links.new(add.outputs[0], scale.inputs[0])
    scale.inputs[1].default_value = (1, 1/3, 1)
    tree.links.new(scale.outputs[0], texture.inputs['Vector'])

    shader = tree.nodes.get('Principled BSDF')
    tree.links.new(texture.outputs['Color'], shader.inputs['Base Color'])
    tree.links.new(texture.outputs['Color'], shader.inputs['Emission Color'])
    # The side and rear units sit behind tinted glazing.
    strength = tree.nodes.new('ShaderNodeMath')
    strength.operation = 'MULTIPLY_ADD'
    tree.links.new(index, strength.inputs[0])
    strength.inputs[1].default_value = .75
    strength.inputs[2].default_value = .62
    tree.links.new(strength.outputs[0], shader.inputs['Emission Strength'])
    for node, position in ((index.node,(-1020,-180)), (uv,(-1020,160)),
                           (offset,(-800,-100)), (add,(-600,140)),
                           (scale,(-400,140)), (texture,(-180,140)),
                           (strength,(-180,-180)), (shader,(120,140))):
        node.location = position
    tree.nodes.get('Material Output').location = (450,140)



def set_route():
    set_route_artwork(MATS['dest_led'])
    for tag,xc in [('Stroller',.805),('Wheelchair',-.805)]:
        patch=fascias.End(SimpleNamespace(end=end,mesh=mesh,bottom=bottom),True)
        patch.patch('Front_Sign_'+tag,(xc-.110,xc+.110,2.423,2.681),.008,'dest_led',.002)
    for name,axis,sign in [('Front_Sign_Stroller',0,-1),('Front_Sign_Wheelchair',0,-1),('DEST_FRONT',0,-1),('DEST_REAR',0,1),('DEST_SIDE',1,-1)]:
        o=bpy.data.objects[name]
        coords=[(v.co[axis]*sign,v.co.z) for v in o.data.vertices]
        x0,y0=map(min,zip(*coords));x1,y1=map(max,zip(*coords))
        uv=o.data.uv_layers.active
        for l in o.data.loops:
            x,y=coords[l.vertex_index]
            u,v=(x-x0)/(x1-x0),(y-y0)/(y1-y0)
            if name.startswith('Front_Sign_'):
                col=0 if name.endswith('Stroller') else 1
                uv.data[l.index].uv=((col*128+1+u*126)/864,(1+v*126)/300)
            else:
                uv.data[l.index].uv=(u,(132+168*v)/300)


def finish_glazing():
    # A 3 mm closed pane has distinct inside/outside normals, including in a
    # single-sided downstream renderer. Keep both surfaces in the same object.
    for o in list(root.children_recursive):
        if o.type!='MESH' or o.active_material!=MATS['glass']:continue
        m=o.data
        n=len(m.vertices)
        outer=[v.co.copy() for v in m.vertices]
        inner=[v.co-v.normal*.003 for v in m.vertices]
        # Both skins must use the same diagonals. A tapered side window is
        # slightly non-planar; tessellating the inner and outer n-gons
        # independently can put the nominal inner skin in front of the outer.
        m.calc_loop_triangles()
        outside=[tuple(t.vertices) for t in m.loop_triangles]
        counts={}
        for f in outside:
            for a,b in zip(f,f[1:]+f[:1]):
                key=tuple(sorted((a,b)))
                if key in counts:counts[key]=None
                else:counts[key]=(a,b)
        faces=outside+[tuple(n+i for i in reversed(f)) for f in outside]
        faces.extend((b,a,n+a,n+b) for edge in counts.values() if edge for a,b in (edge,))
        # Retaining the original object keeps door-child relationships intact.
        temp=mesh('Glazing tooling',outer+inner,faces,'glass')
        old=o.data
        o.data=temp.data
        bpy.data.objects.remove(temp,do_unlink=True)
        bpy.data.meshes.remove(old)
        o.data.name=o.name


def ready_geometry():
    # Limit export geometry to tris/quads so tangent-space calculation works
    # on lettering, rounded glass corners and small stamped covers as well.
    import bmesh
    for o in root.children_recursive:
        if o.type!='MESH' or not any(len(p.vertices)>4 for p in o.data.polygons):continue
        bm=bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.triangulate(bm,faces=[p for p in bm.faces if len(p.verts)>4],
                              quad_method='BEAUTY',ngon_method='EAR_CLIP')
        bm.to_mesh(o.data)
        bm.free()
        o.data.update()


def apply_modifiers():
    dg=bpy.context.evaluated_depsgraph_get()
    for o in list(root.children_recursive):
        if o.type=='MESH' and o.modifiers:
            data=bpy.data.meshes.new_from_object(o.evaluated_get(dg),depsgraph=dg,
                                                  preserve_all_data_layers=True)
            old=o.data
            o.modifiers.clear()
            o.data=data
            if old.users==0:bpy.data.meshes.remove(old)


def validate():
    from itertools import chain
    expected={'LIGHT_HEAD_L','LIGHT_HEAD_R','LIGHT_TAIL_L','LIGHT_TAIL_R','LIGHT_BRAKE_L',
              'LIGHT_BRAKE_R','LIGHT_IND_FL','LIGHT_IND_FR','LIGHT_IND_RL','LIGHT_IND_RR',
              'LIGHT_REVERSE_L','LIGHT_REVERSE_R','DOOR_FRONT','DOOR_MID','INTERIOR_PLACEHOLDER',
              'DEST_FRONT','DEST_SIDE','DEST_REAR'}
    objects=root.children_recursive
    assert expected.issubset({o.name for o in objects})
    assert {m.name for m in bpy.data.materials}==set(MATS)
    assert len(objects)+1==len(bpy.context.scene.objects)
    for prefix,stations in [('WHEEL',AXLES),('SUSP',AXLES)]:
        for s,k in ((-1,'L'),(1,'R')):
            for y,sub in zip(stations,['R','F']):
                o=bpy.data.objects[f'{prefix}_{k}{sub}']
                coord=(s*(.91 if y<0 else 1.0325),y,.478)
                assert o.type=='EMPTY' and (o.location-Vector(coord)).length<1e-6
                assert not any(o.rotation_euler) and o.parent==root
    bpy.context.view_layer.update()
    lo=[1e9]*3; hi=[-1e9]*3; tris=largest=0
    tires={}
    body_y_min, body_y_max = math.inf, -math.inf
    for o in objects:
        if o.type!='MESH':continue
        assert o.data.uv_layers.active,o.name
        o.data.calc_loop_triangles()
        tris+=len(o.data.loop_triangles)
        largest=max(largest,len(o.data.vertices))
        if o.name.startswith('Mirror'):continue
        coords=[o.matrix_world@v.co for v in o.data.vertices]
        if not o.name.startswith(('Wiper', 'FrontPlate', 'RearPlate', 'PlateLamp')):
            body_y_min = min(body_y_min, min(p.y for p in coords))
            body_y_max = max(body_y_max, max(p.y for p in coords))
        if o.active_material and o.active_material.name=='tyre':
            size=[max(v[k] for v in coords)-min(v[k] for v in coords) for k in range(3)]
            assert all(abs(x-y)<.001 for x,y in zip(size,(.275,.956,.956))), (o.name,size)
            tires[o.name]=size
        for k in range(3):
            lo[k]=min(lo[k],min(v[k] for v in coords));hi[k]=max(hi[k],max(v[k] for v in coords))
    allowed_names={f'{prefix}_{end}' for prefix in ('WHEEL','SUSP') for end in ('LF','RF','LR','RR')}
    for o in objects:
        if o.name.startswith(('WHEEL_','SUSP_','STEER_','ARROW_')):
            assert o.name in allowed_names,o.name
        if o.name.startswith('LIGHT_'):
            assert o.name in expected and o.active_material==MATS['light_emit'],o.name
        if o.name.startswith('DEST_'):
            assert o.name in expected and o.active_material==MATS['dest_led'],o.name
        if o.type=='MESH':
            o.data.calc_tangents()
    solids=[(o,v.co) for o in objects if o.type=='MESH' and not o.name.startswith('Mirror')
            and not o.parent.name.startswith('WHEEL_') for v in o.data.vertices]
    assert abs(min(p.z for _,p in solids)-.130)<.001
    for sign,degrees in [(1,9.6),(-1,8.4)]:
        angles=[]
        for o,p in solids:
            d=sign*p.y-2.65
            if d>.50 and p.z<.75:
                angles.append(math.degrees(math.atan2(p.z-.478,d)+math.asin(.478/math.hypot(d,p.z-.478))))
        assert abs(min(angles)-degrees)<.02, (sign,min(angles),degrees)
    assert len(tires)==6
    dims=[body_y_max-body_y_min,hi[0]-lo[0],hi[2]-lo[2]]
    assert all(abs(x-y)<=.020 for x,y in zip(dims,(10.430,2.485,3.105))),dims
    assert tris<=200000 and largest<=60000
    print(f'VERIFIED dimensions {dims}, envelope {lo} {hi}, triangles {tris}, largest mesh {largest}, {len(objects)} descendants',flush=True)


def save_model():
    scene=bpy.context.scene
    scene.unit_settings.system='METRIC'
    scene.unit_settings.length_unit='METERS'
    bpy.context.preferences.filepaths.save_version=0
    for f in list(bpy.data.fonts):
        if f.users==0 and f.name!='Bfont':bpy.data.fonts.remove(f)
    # Make the kerb-side three-quarter view the first view when opening the asset.
    q=(Vector((0,0,1.42))-Vector((-9,12,4.8))).to_track_quat('-Z','Y')
    for area in bpy.context.screen.areas:
        if area.type=='VIEW_3D':
            sp=area.spaces.active
            sp.region_3d.view_rotation=q
            sp.region_3d.view_distance=14.6
            sp.region_3d.view_location=(0,-.25,1.46)
            sp.overlay.show_overlays=False
            sp.shading.color_type='MATERIAL'
            sp.shading.type='MATERIAL'
            sp.shading.studiolight_rotate_z=1.15
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active=None
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'kanachu_exterior.blend'),compress=True)


def render(cameras, work):
    scene=bpy.context.scene
    scene.render.engine='BLENDER_EEVEE'
    scene.eevee.taa_render_samples=64
    scene.render.resolution_x=1600
    scene.render.resolution_y=900
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGB'
    scene.view_settings.view_transform='AgX'
    scene.view_settings.exposure=0
    scene.view_settings.look='AgX - Medium High Contrast'
    world=bpy.data.worlds.new('Photographic studio')
    scene.world=world
    tree=world.node_tree
    hdr=Path(bpy.utils.system_resource('DATAFILES',path='studiolights/world/courtyard.exr'))
    bg=tree.nodes.get('Background')
    if hdr.is_file():
        env=tree.nodes.new('ShaderNodeTexEnvironment')
        env.image=bpy.data.images.load(str(hdr))
        tree.links.new(env.outputs['Color'],bg.inputs[0])
    bg.inputs[1].default_value=.36
    camera_bg=tree.nodes.new('ShaderNodeBackground')
    camera_bg.inputs[0].default_value=(.46,.505,.53,1)
    rays=tree.nodes.new('ShaderNodeLightPath')
    mix=tree.nodes.new('ShaderNodeMixShader')
    tree.links.new(rays.outputs['Is Camera Ray'],mix.inputs[0])
    tree.links.new(bg.outputs[0],mix.inputs[1])
    tree.links.new(camera_bg.outputs[0],mix.inputs[2])
    tree.links.new(mix.outputs[0],tree.nodes.get('World Output').inputs['Surface'])
    # The stage is temporary and is set up only after the hand-off file is saved.
    g=bpy.data.meshes.new('Cyclorama')
    section=[(-250,-.002),(0,-.002),(9,-.002)]
    for i in range(1,33):
        t=i*math.pi/64
        section.append((9+4*math.sin(t),-.002+4*(1-math.cos(t))))
    section.append((13,60))
    g.from_pydata([(x,y,z) for y,z in section for x in (-100,100)],[],
                  [(2*i,2*i+1,2*i+3,2*i+2) for i in range(len(section)-1)])
    for polygon in g.polygons:polygon.use_smooth=True
    floor=bpy.data.objects.new('Studio sweep',g)
    bpy.context.collection.objects.link(floor)
    m=bpy.data.materials.new('Studio neutral')
    p=m.node_tree.nodes.get('Principled BSDF')
    p.inputs['Base Color'].default_value=(.205,.232,.246,1)
    p.inputs['Roughness'].default_value=.84
    # Gentle ambient lift on the backdrop, retaining the tyre contact shadows.
    p.inputs['Emission Color'].default_value=(.46,.50,.53,1)
    p.inputs['Emission Strength'].default_value=.76
    g.materials.append(m)
    def area(name,loc,target,watts,size,size_y,color):
        d=bpy.data.lights.new(name,'AREA')
        d.energy=watts;d.shape='RECTANGLE';d.size=size;d.size_y=size_y;d.color=color
        o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o)
        o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
    area('Large left softbox',(-6,3,9),(0,0,1),1800,10,6,(1,.955,.89))
    area('Right reflected strip',(6,-2,6),(0,0,1.7),1400,9,3,(.84,.92,1))
    area('Front fill',(1,9,5),(0,1,1),520,5,4,(1,.95,.87))
    area('Tail fill',(-2,-9,6),(0,-2,1.6),750,5,5,(.90,.95,1))
    d=bpy.data.cameras.new('Studio camera')
    cam=bpy.data.objects.new('Studio camera',d);bpy.context.collection.objects.link(cam)
    scene.camera=cam
    for key in ('front','side_left','rear','front34','rear34'):
        if key == 'side_left':
            target=Vector((0,-.16,1.62))
            cam.location=target+Vector((-170,0,3.6))
            cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
            d.type='ORTHO'
            d.ortho_scale=12.20
        else:
            matched=cameras[key]
            cam.matrix_world=matched.camera.matrix_world.copy()
            d.type='PERSP'
            d.sensor_fit='HORIZONTAL'
            d.sensor_width=36.
            # Expand just the canvas to 16:9. The equivalent focal length
            # keeps the complete original frame within the studio render.
            w,h=matched.render.resolution_x,matched.render.resolution_y
            d.lens=matched.camera.data.lens*min(1600/w,900/h)*w/1600
        d.clip_end=650
        direction=cam.rotation_euler.to_quaternion() @ Vector((0,0,-1))
        floor.rotation_euler.z=math.atan2(-direction.x,direction.y)
        scene.render.filepath=str(OUT/f'render_{key}.png')
        bpy.ops.render.render(write_still=True)

    for key, photo_scene in cameras.items():
        camera = photo_scene.camera
        scene.collection.objects.link(camera)
        scene.camera = camera
        direction = camera.matrix_world.to_quaternion() @ Vector((0,0,-1))
        floor.rotation_euler.z = math.atan2(-direction.x,direction.y)
        scene.render.resolution_x = photo_scene.render.resolution_x
        scene.render.resolution_y = photo_scene.render.resolution_y
        scene.render.filepath = str(work/(key+'-beauty.png'))
        bpy.ops.render.render(write_still=True)
        photo_views.render_ids(photo_scene, work, key)
        scene.collection.objects.unlink(camera)
    compare = OUT/'compare'
    compare.mkdir(exist_ok=True)
    subprocess.run(['/usr/bin/python3','-B',str(HERE/'photo_compare.py'),str(work),str(compare)],check=True)


def main():
    global root
    bpy.ops.wm.read_factory_settings(use_empty=True)
    root=bpy.data.objects.new('ROOT',None)
    bpy.context.collection.objects.link(root)
    root.empty_display_size=.18
    make_materials()
    api=SimpleNamespace(mesh=mesh,box=box,rod=rod,end=end,bottom=bottom,front_developed_x=front_developed_x,root=root)
    side_body(-1);side_body(1);doors();make_roof();make_interior()
    fascias.build(api)
    wheels.build(root,MATS)
    set_route()
    coach_profile.apply(root)
    finish_glazing()
    apply_modifiers()
    ready_geometry()
    print('ATLAS',atlas.finish(root,OUT),flush=True)
    validate()
    with tempfile.TemporaryDirectory(dir=OUT) as tmp:
        work = Path(tmp)
        subprocess.run(['/usr/bin/python3','-B',str(HERE/'photo_fit.py'),str(work)],check=True)
        cameras = photo_views.camera_scenes(work)
        save_model()
        render(cameras, work)


if __name__=='__main__':
    main()
