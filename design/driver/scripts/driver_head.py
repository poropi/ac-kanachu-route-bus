"""Three rigid head parts. All coordinates are drafted in the reference views' pixels."""
from math import sin, cos, pi, sqrt, exp
from shutil import which
import subprocess

import bpy
from mathutils import Vector

SCALE = .00115
TAU = 2 * pi


def world(p):
    x, depth, row = p
    return ((x - 512) * SCALE, (505 - depth) * SCALE, (1487 - row) * SCALE)


def svg_material(name, width, height, view, body, roughness=.78):
    """Rasterise original vector artwork directly to a packed PNG, without scratch files."""
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{view}" preserveAspectRatio="none">{body}</svg>'
    png = subprocess.check_output([which("rsvg-convert") or "/opt/homebrew/bin/rsvg-convert"],
                                  input=svg.encode())
    im = bpy.data.images.new(name + ".png", width, height)
    im.source = 'FILE'
    im.filepath_raw = "//" + im.name
    im.pack(data=png, data_len=len(png))
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    bs = nt.nodes.get('Principled BSDF')
    bs.inputs['Roughness'].default_value = roughness
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = im
    tex.extension = 'EXTEND'
    nt.links.new(tex.outputs['Color'], bs.inputs['Base Color'])
    return mat


# Original facial artwork. Paths are defined in front-view landmarks so they wrap with the face.
EYE = '''
<path d="M453 209 Q467 201 483 205" fill="none" stroke="#d79886" stroke-width="1.1"/>
<path d="M453 211 Q463 204 475 204 Q485 205 492 219 Q486 233 477 236 Q465 237 459 231 Q455 224 456 216Z" fill="#fff6ec"/>
<path d="M456 215 Q467 206 478 208 Q486 209 490 218 Q473 212 457 219Z" fill="#e0ced7"/>
<g clip-path="url(#eyeclip)">
 <ellipse cx="476" cy="219.7" rx="11.9" ry="15.7" fill="#3c2b46"/>
 <ellipse cx="476" cy="220.2" rx="10.1" ry="14.2" fill="url(#iris)"/>
 <ellipse cx="476" cy="218" rx="5" ry="8.1" fill="#352038"/>
 <path d="M467 228 q4 6 9 5 q7 0 9-8 q-5 7-10 6 q-5 0-8-3" fill="#e6a0bc"/>
 <path d="M470 231 q4 3 8 2" fill="none" stroke="#ffd1cc" stroke-width="1.4"/>
 <circle cx="471.1" cy="214" r="3.4" fill="#fffaf6"/><circle cx="481" cy="222" r="1.5" fill="#fcf1f8"/>
</g>
<path d="M450 209 Q454 213 457 211 L453 205 Q457 209 461 208 Q471 200 482 205 Q489 208 493 221 Q487 211 480 209 Q467 206 460 215 Q456 221 460 229 Q455 225 454 216Z" fill="#392b38"/>
<path d="M460 230 Q463 235 469 236 M484 233 Q489 230 490 226" fill="none" stroke="#a16869" stroke-width="1" stroke-linecap="round"/>
<path d="M451 189 Q465 176 486 183 Q489 184 491 187 Q470 181 452 191Z" fill="#7b5049"/>
'''


def head_materials():
    face = '''<defs>
    <linearGradient id="skin" x2=".14" y2="1" gradientUnits="objectBoundingBox"><stop stop-color="#f2bd9f"/><stop offset=".52" stop-color="#ffe3c9"/><stop offset="1" stop-color="#ffdcc2"/></linearGradient>
    <radialGradient id="blush"><stop stop-color="#ed9b99" stop-opacity=".48"/><stop offset="1" stop-color="#f2a59c" stop-opacity="0"/></radialGradient>
    <linearGradient id="iris" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#40314e"/><stop offset=".45" stop-color="#624064"/><stop offset=".78" stop-color="#b16991"/><stop offset="1" stop-color="#f3adc3"/></linearGradient>
    <clipPath id="eyeclip"><path d="M454 217 Q458 205 475 205 Q485 206 492 219 Q485 235 477 236 Q460 238 455 223Z"/></clipPath></defs>
    <rect x="410" y="78" width="206" height="239" fill="url(#skin)"/>
    <ellipse cx="459" cy="242" rx="22" ry="12" fill="url(#blush)"/><ellipse cx="565" cy="242" rx="22" ry="12" fill="url(#blush)"/>
    '''
    face += EYE + '<g transform="translate(1024 0) scale(-1 1)">' + EYE + '</g>'
    face += '''<ellipse cx="512" cy="243" rx="8" ry="7" fill="url(#blush)"/>
    <path d="M509 243 q2-6 5-3 q3 3-3 5Z" fill="#fff4dc"/>
    <path d="M515 246 q0.4 2.4-1.7 3" fill="none" stroke="#dc9f8a" stroke-width="1"/>
    <path d="M499 267 Q504 270 512 270 Q520 270 527 265 Q523 271 514 272 Q505 272 499 268Z" fill="#b57171"/>
    <path d="M506 274 q7 1.8 12-1.2" fill="none" stroke="#fff1df" stroke-width="1.5" stroke-linecap="round"/>'''
    mats = {'face': svg_material('driver_face', 768, 896, '410 78 206 239', face)}
    # Small pieces use horizontal bands of a shared palette.
    colors = ['#373447', '#252331', '#161621', '#302d3c', '#494559',
              '#786374', '#a9a4ab', '#e9e1dd', '#bc9670', '#a780cf',
              '#cebbea', '#e5d7ff', '#b79ad8', '#f1bc9f', '#dc9684',
              '#f4ccba', '#8d584c', '#533730', '#a66f61', '#68423c']
    strips = ''.join(f'<rect x="{i}" width="1" height="1" fill="{c}"/>' for i,c in enumerate(colors))
    mats['trim'] = svg_material('driver_head_trim', 400, 16, f'0 0 {len(colors)} 1', strips)
    hair = '''<defs><linearGradient id="h"><stop stop-color="#563c39"/><stop offset=".12" stop-color="#714b44"/><stop offset=".34" stop-color="#895e53"/><stop offset=".51" stop-color="#916455"/><stop offset=".73" stop-color="#805247"/><stop offset="1" stop-color="#503731"/></linearGradient></defs>
    <rect width="100" height="200" fill="url(#h)"/>
    <path d="M21 -6 Q48 41 24 112 Q40 44 17 -6Z" fill="#ad7966" opacity=".8"/>
    <path d="M34 -4 Q56 38 46 61 Q49 43 41 31 Q37 23 34 -4Z M46 72 Q51 80 37 115 Q43 88 46 72Z" fill="#d1987e" opacity=".7"/>
    <path d="M64 8 Q86 61 53 187 Q79 63 64 8Z" fill="#633e38"/>
    <path d="M82 30 Q94 83 73 137 Q90 80 82 30Z" fill="#ad7765" opacity=".65"/>'''
    mats['hair'] = svg_material('driver_hair', 256, 512, '0 0 100 200', hair, .72)
    # Near-symmetrical elliptical border and two-colour stitched wordmark.
    badge = '''<rect width="100" height="56" fill="#303248"/>
    <ellipse cx="50" cy="28" rx="49" ry="27" fill="#c6a366"/>
    <ellipse cx="50" cy="28" rx="46" ry="24" fill="#f6d98e"/>
    <ellipse cx="50" cy="28" rx="43" ry="21" fill="#22314d"/>
    <path d="M17 25 q27-22 65-8 q-34-5-65 12Z" fill="#72a7dd"/>
    <text x="50" y="36" text-anchor="middle" font-family="Arial,sans-serif" font-style="italic" font-weight="bold" font-size="17" letter-spacing="-1" fill="#fff5df">Kanachu</text>'''
    mats['badge'] = svg_material('driver_cap_badge', 384, 216, '0 0 100 56', badge)
    return mats


class Part:
    def __init__(self, materials):
        self.materials = materials
        self.v, self.f, self.attrs = [], [], []

    def point(self, p):
        self.v.append(world(p))
        return len(self.v)-1

    def face(self, indices, material, uv):
        self.f.append(list(reversed(indices)))
        self.attrs.append((material, list(reversed(uv))))

    def grid(self, rows, n, fun, material, uvfun, wrap=True, flip=False):
        cols = n if wrap else n + 1
        ids = [[self.point(fun(i/rows,j/n)) for j in range(cols)] for i in range(rows+1)]
        for i in range(rows):
            for j in range(n):
                k=(j+1)%cols
                corners=((i,j),(i+1,j),(i+1,j+1),(i,j+1))
                indices=[ids[i][j],ids[i+1][j],ids[i+1][k],ids[i][k]]
                uvs=[uvfun(a/rows,b/n) for a,b in corners]
                if flip:
                    indices.reverse()
                    uvs.reverse()
                self.face(indices, material, uvs)

    def finish(self, name):
        if name == "DRIVER:HAIR":
            # Under the cap band, compress the buried roots toward the scalp.
            # This leaves the curved visor and band uninterrupted in profile.
            coords=[]
            for x,y,z in self.v:
                row=1487-z/SCALE
                root=min(max((157-row)/22,0),1)
                sink=min(max((118-row)/26,0),1)
                coords.append((x*(1-.12*root),y*(1-.25*root),z-.027*sink))
            self.v=coords
        me=bpy.data.meshes.new(name)
        me.from_pydata(self.v, [], self.f)
        me.update()
        ob=bpy.data.objects.new(name, me)
        bpy.context.collection.objects.link(ob)
        slots=list(dict.fromkeys(m for m, uv in self.attrs))
        for m in slots:
            me.materials.append(self.materials[m])
        layer=me.uv_layers.new(name="UVMap")
        for p,(m,uv) in zip(me.polygons,self.attrs):
            p.material_index=slots.index(m)
            p.use_smooth=True
            for loop,co in zip(p.loop_indices,uv):
                layer.data[loop].uv=co
        # All surfaces are closed, apart from the badge and the overlapping hair scalp.
        return ob


def uvstrip(i):
    return lambda t,s: ((i+.5)/20, .5)


def interp(seq,t):
    t=min(max(t,0),1)*(len(seq)-1)
    i=min(int(t),len(seq)-2)
    return [a+(b-a)*(t-i) for a,b in zip(seq[i],seq[i+1])]


def ellipsoid(part, center, radii, band, rows=6,n=12):
    def coord(t,s):
        a=pi*(.001+.998*t)
        b=TAU*s
        return (center[0]+radii[0]*sin(a)*sin(b),center[1]-radii[1]*sin(a)*cos(b),center[2]-radii[2]*cos(a))
    part.grid(rows,n,coord,'trim',uvstrip(band))


# row, half width, foremost and rearmost side-view pixels.
FACE_ROWS = [(91,4,490,500),(100,39,453,543),(114,62,430,557),(134,79,411,567),
             (156,83,404,575),(177,82,402,579),(192,80,405,579),(207,77,410,575),
             (218,74,414,570),(228,72,416,566),(237,69,415,560),(244,66,415,556),
             (250,63,414,553),(258,59,413,551),(265,55,411,548),(271,50,415,544),
             (278,43,417,540),(286,32,420,534),(292,20,424,520),(298,2,438,444)]


def skin_surface(t,s):
    row,rx,f,b=interp(FACE_ROWS,t)
    angle=TAU*s
    x=512 + rx*sin(angle)
    d=(b+f)/2-(b-f)/2*cos(angle)
    if cos(angle)>0:
        # Build nose bridge, tip and philtrum into the face's own rows.
        dx=x-512
        d-= (14*exp(-((row-238)/8)**2)+6*exp(-((row-222)/16)**2))*exp(-(dx/10)**2)
        d-=2.8*exp(-((row-264)/5)**2-(dx/19)**2)
    # The jaw rises from the chin toward the ears in profile.
    jaw=max(0, min(1,(row-222)/68))
    row-=jaw*min(max((d-440)/85,0),1)*33
    conceal=min(max((173-row)/32,0),1)
    return 512+(x-512)*(1-.19*conceal),505+(d-505)*(1-.39*conceal),row


def build_face(mats):
    p=Part(mats)
    def uv(t,s):
        x,d,h=skin_surface(t,s)
        if cos(TAU*s)<0:
            x=410 if sin(TAU*s)<0 else 616
        return ((x-410)/206,(317-h)/239)
    p.grid(len(FACE_ROWS)-1,32,skin_surface,'face',uv)
    # The lower jaw blends into the neck behind the mandibular angle. Its
    # lowest ring sits inside the top of the independently skinned body neck.
    neck=[(237,24,502,30),(247,32,503,39),(258,34,501,40),
          (268,32,497,37),(277,30,496,32),(287,27,497,29)]
    def upper_neck(t,s):
        row,w,center,depth=interp(neck,t)
        return 512+w*sin(TAU*s),center-depth*cos(TAU*s),row
    p.grid(len(neck)-1,20,upper_neck,'trim',uvstrip(15))
    for sign in (-1,1):
        ear_x=512+sign*75
        ellipsoid(p,(ear_x,504,232),(9,14,19),13)
        ellipsoid(p,(ear_x+sign*6.1,503,231),(3.0,8,12),14,4,10)
        ellipsoid(p,(ear_x+sign*8.1,501,234),(1.8,4.3,7.7),13,4,8)
    return p.finish("DRIVER:GEO_Driver_FACE")


def spline(points,t):
    """Catmull–Rom through profile points, including lock widths and thicknesses."""
    z=t*(len(points)-1)
    k=min(int(z),len(points)-2)
    f=z-k
    a,b,c,d=[points[min(max(j,0),len(points)-1)] for j in (k-1,k,k+1,k+2)]
    return [(.5*((2*v)+(-u+w)*f+(2*u-5*v+4*w-q)*f*f+(-u+3*v-3*w+q)*f**3))
            for u,v,w,q in zip(a,b,c,d)]


def lock(p, points, depth_axis=(0,-1,0), rows=10,n=8):
    # The shallow convex front and the dark perimeter read as a single drawn hair clump.
    def geom(t,s):
        cx,cd,ch,w,r=spline(points,t)
        before=spline(points,max(t-.005,0))
        after=spline(points,min(t+.005,1))
        tangent=(Vector(after[:3])-Vector(before[:3])).normalized()
        ax=Vector(depth_axis)
        across=tangent.cross(ax).normalized()
        normal=across.cross(tangent).normalized()
        return Vector((cx,cd,ch))+across*cos(TAU*s)*max(w,.09)+normal*sin(TAU*s)*max(r,.09)
    p.grid(rows,n,geom,'hair',lambda t,s: ((1+cos(TAU*s))*.5,1-t),flip=True)


def build_hair(mats):
    p=Part(mats)
    def scalp(t,s):
        a=TAU*s
        # Behind the ears the hair gathers into a low V at the nape.
        end=1.48+1.10*(1-cos(a))*.5
        polar=.03+(end-.03)*t
        gather=t**4*max(-cos(a),0)
        return (512+89*sin(polar)*sin(a)*(1-.19*gather),495-98*sin(polar)*cos(a)-11*gather,183-110*cos(polar)+10*gather)
    p.grid(8,32,scalp,'hair',lambda t,s: ((s*14)%1,1-t))
    # Tapering swept sections over the cap of hair, converging toward the tied side.
    for sign in (-1,1):
        for i in range(5):
            angle0=.98+i*.22
            pts=[]
            for j in range(5):
                f=j/4
                angle=angle0+(2.54-angle0)*f
                if sign<0: angle+=.25*f
                t=.46+.12*i + (.30-.06*i)*f
                x,d,h=scalp(min(.994,t),sign*angle/TAU)
                pts.append((x,d,h, (4.4+2*sin(pi*f)) if j<4 else .4, 2.1 if j<4 else .3))
            lock(p,pts,(sign*.75,.85,0),4,6)
    # Bangs fan from beneath the band. X coordinates follow the irregular fringe of the front plate.
    bangs=[
        [(448,437,118,13,4),(443,429,158,15,4),(437,429,181,10,3),(434,434,210,.3,.2)],
        [(460,428,117,16,4),(456,417,158,16,5),(449,414,185,8,4),(447,419,203,.3,.2)],
        [(478,415,115,16,4),(474,405,160,17,5),(470,401,185,10,4),(464,407,207,.4,.3)],
        [(493,411,114,14,3),(490,398,162,14,4),(490,397,187,10,4),(498,405,210,.3,.2)],
        [(513,408,124,14,3),(510,396,160,15,5),(514,393,193,10,4),(507,400,217,.3,.2)],
        [(528,410,125,11,4),(528,395,156,13,5),(527,393,186,8,4),(520,402,209,.4,.2)],
        [(545,414,116,16,4),(547,403,159,13,4),(547,400,182,9,4),(553,407,201,.4,.2)],
        [(561,417,119,14,4),(566,409,159,11,4),(569,412,185,8,4),(577,420,207,.4,.2)]]
    # On a curved forehead the outer bangs turn back toward the temples.
    for path in bangs:
        pts=[(x,d+.0078*(x-512)**2,h,w,r) for x,d,h,w,r in path]
        lock(p,pts)
    for sign in (-1,1):
        def h(x,d,y,w,r): return (512+sign*x,d,y,w,r)
        lock(p,[h(66,445,137,11,5),h(78,440,175,14,6),h(77,445,220,11,5),
                h(77,450,270,7,4),h(61,461,306,.3,.2)],(sign*.6,-1,0),13)
        lock(p,[h(77,462,132,10,4),h(88,455,169,10,4),h(91,454,221,8,3),
                h(85,459,253,4,2),h(75,472,278,.25,.2)],(sign*.7,-1,0))
        lock(p,[h(86,461,143,2,1.5),h(101,452,190,2,1.3),h(107,458,234,1.4,.9),
                h(98,466,255,.18,.1)],(sign*.5,-1,0),9,6)
    # A crest and two alternating bends run through the ponytail. Locks have
    # staggered phases, so their broad sections overlap in the side elevation.
    spine=[(597,570,165),(620,594,178),(638,610,207),(647,608,239),
           (644,604,268),(625,613,301),(616,624,331),(624,609,362),
           (617,593,386),(604,597,407),(610,610,422),(623,603,419)]
    strands=[(-8,-20, .2,-20),(-5,-7,1.4,5),(7,18,2.5,14),
             (12,22,4.8,-24),(-9,12,5.8,12),(-18,-18,3.6,-31),
             (10,-8,3.1,-4),(5,2,.3,18),(15,29,2.1,-42)]
    widths=[4,9,14,15,14,12,11,8.5,6,4,1.8,.15]
    depths=[4,9,14,15,14,12,11,8,5.5,3.8,1.6,.15]
    def wave(i):
        offx,offd,phase,length=strands[i]
        pts=[]
        for j,(x,d,h) in enumerate(spine):
            t=j/(len(spine)-1)
            spread=min(1,t*4)
            curl=t*t
            x+=spread*(offx+(5+7*t)*sin(TAU*t*1.8+phase))
            d+=spread*(offd+(5+10*t)*cos(TAU*t*2+phase))
            flick=max(0,(t-.74)/.26)**1.5
            x+=13*sin(phase)*flick
            d+=18*cos(phase)*flick
            h+=length*curl-7*abs(sin(phase))*flick
            pts.append((x,d,h,widths[j],depths[j]))
        return pts
    for i in range(len(strands)):
        lock(p,wave(i),(.2*(-1)**i,-1,.12),17,8)
    for i in (0,2,6):
        pts=[(x+5,d+6,h-4,max(.15,w*.14),max(.14,r*.13)) for x,d,h,w,r in wave(i)]
        lock(p,pts,(.2,-1,.1),15,5)
    # Fold the satin into shallow, solid strips. The notched ends and the
    # rear-facing tail remain legible when the ponytail is seen from behind.
    def ribbon(points,widths,axis,notch=False):
        ids=[]
        vx,vd=axis
        for j,((x,d,y),w) in enumerate(zip(points,widths)):
            fold=-8 if notch and j==len(points)-1 else -1.8
            face=[(x-vx*w,d-vd*w,y),(x+vd*2,d-vx*2,y+fold),(x+vx*w,d+vd*w,y-2)]
            ids.append([p.point(q) for q in face]+[p.point((a-vd*1.8,b+vx*1.8,c)) for a,b,c in face])
        edges=[(0,1,11),(1,2,10),(2,5,9),(5,4,10),(4,3,11),(3,0,9)]
        for a,b,band in edges:
            for u,v in zip(ids,ids[1:]):
                p.face([u[a],v[a],v[b],u[b]],'trim',[uvstrip(band)(0,0)]*4)
        for end in (ids[0],ids[-1]):
            p.face(end[:3]+end[3:][::-1],'trim',[uvstrip(10)(0,0)]*6)
    ribbon([(607,570,174),(617,564,188),(625,555,204),(630,550,219),(633,553,234)],
           [4,8,10,12,12],(.76,.65),True)
    ribbon([(607,575,174),(613,582,190),(610,576,211),(605,564,235),(600,561,257),(598,561,274)],
           [4,7,9,10,11,10],(.64,.77),True)
    ribbon([(608,571,176),(608,564,166),(599,552,157),(598,553,164),(605,566,178)],
           [3,7,9,7,3],(.64,-.77))
    ribbon([(609,573,176),(617,580,167),(621,584,153),(617,580,156),(608,572,173)],
           [3,8,10,6,3],(.76,-.65))
    ellipsoid(p,(608,572,174),(7.5,8,8),10,6,12)
    return p.finish("DRIVER:HAIR")


def build_cap(mats):
    p=Part(mats)
    # Full peaked crown. The top is higher above the forehead than above the nape.
    rings=[(2,2,76,.38),(47,48,76,.38),(85,77,80,.39),(104,93,90,.40),
           (110,96,100,.40),(109,97,104,.37),(102,96,116,.29),(94,97,125,.23),
           (93,97,128,.22),(92,98,139,.21),(91,98,142,.20),(90,98,144,.19)]
    def crown(t,s):
        w,d,h,slope=interp(rings,t)
        off=-d*cos(TAU*s)
        return (508+w*sin(TAU*s),506+off,h+off*slope-2*min(1,max(0,(.58-t)/.19)))
    ids=[[p.point(crown(i/(len(rings)-1), j/32)) for j in range(32)] for i in range(len(rings))]
    p.face(ids[0], 'trim', [uvstrip(0)(0,0)]*32)
    for i,band in enumerate([0,0,0,4,0,0,0,3,1,2,1]):
        for j in range(32):
            k=(j+1)%32
            p.face([ids[i][j],ids[i+1][j],ids[i+1][k],ids[i][k]],'trim',[uvstrip(band)(0,0)]*4)
    # A strong, curved visor projects beyond the front band only.
    def visor(t,s):
        ang=(s-.5)*pi*1.14
        a=cos(ang)
        d=506-(98+47*t*max(a,0))*a
        return (508+(91+3*t)*sin(ang),d,142+20*t*max(a,0)-17*a+2*(1-a))
    p.grid(4,24,visor,'trim',uvstrip(2),False)
    p.grid(1,24,lambda t,s:(lambda q:(q[0],q[1],q[2]+2.9*t))(visor(1,s)),'trim',uvstrip(3),False)
    p.grid(3,24,lambda t,s:(lambda q:(q[0],q[1],q[2]+3))(visor(t,s)),'trim',uvstrip(1),False,True)
    for side in (-1,1):
        ellipsoid(p,(508+side*88,484,133),(2.6,4.7,4.7),6,5,10)
    # Convex cloth emblem. UV orientation follows our front-view drawing convention.
    def badge(t,s):
        r=.002+.998*t
        x=34*r*cos(TAU*s)
        h=20*r*sin(TAU*s)
        return (509+x,407+.0055*x*x-1.2*(1-r*r),88+h)
    p.grid(3,28,badge,'badge',lambda t,s:(.5+.49*t*cos(TAU*s),.5-.49*t*sin(TAU*s)),flip=True)
    return p.finish("DRIVER:CAP")


def build_head():
    mats=head_materials()
    return build_face(mats),build_hair(mats),build_cap(mats)
