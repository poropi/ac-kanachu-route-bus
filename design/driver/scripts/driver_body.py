"""Tailored jacket, trousers and loafers, built in measured drawing coordinates."""
import math
from pathlib import Path
import subprocess
import tempfile

import bpy

SCALE = .00115
SCRIPT = Path(__file__).resolve().parent
PALETTE = "white ink silver rim shine navy blue skin sole shoe band thread welt shirt_shadow".split()
TAU = math.tau


def clamp(t):
    return min(1., max(0.,t))


def smooth(x, a, b):
    t = clamp((x-a)/(b-a))
    return t*t*(3.-2.*t)


def mix(a, b, t):
    out = {k: v*(1.-t) for k,v in a.items()}
    for k,v in b.items():
        out[k] = out.get(k,0)+v*t
    return {k:v for k,v in out.items() if v>0.000001}


def bone(name):
    return {"DRIVER:RIG_"+name:1.}


def interp(rows, v):
    if v <= rows[0][0]:
        return rows[0][1:]
    for a,b in zip(rows,rows[1:]):
        if v <= b[0]:
            t = (v-a[0])/(b[0]-a[0])
            return tuple(i+(j-i)*t for i,j in zip(a[1:],b[1:]))
    return rows[-1][1:]


def tex(x,y):
    return (x/2048,1.-y/1536)


def swatch(name, point):
    # Continuous planar UVs inside each tiny constant-colour island retain shared KN5 corners.
    x,y,p=point
    return tex(18+12*PALETTE.index(name)+.004*x+.009*y,44+.003*(p-700)-.004*y)


def materials():
    with tempfile.NamedTemporaryFile(prefix="driver_body_",suffix=".png",dir=SCRIPT) as f:
        subprocess.run(["/usr/bin/python3",str(SCRIPT/"driver_body_paint.py")],stdout=f,check=True)
        f.flush()
        img = bpy.data.images.load(f.name, check_existing=False)
        img.name = "driver_uniform_albedo.png"
        img.pack()
        img.filepath = "//driver_uniform_albedo.png"
    mats=[]
    for label,rough,metal in [("uniform",.87,0),("shoes",.25,.06),("hardware",.32,.3),("neck",.78,0)]:
        mat = bpy.data.materials.new("driver_"+label)
        mat.use_nodes = True
        bs = mat.node_tree.nodes.get("Principled BSDF")
        bs.inputs["Roughness"].default_value=rough
        bs.inputs["Metallic"].default_value=metal
        if label=="uniform":
            bs.inputs["Specular IOR Level"].default_value=.23
        im=mat.node_tree.nodes.new("ShaderNodeTexImage")
        im.image=img
        im.location=(-320,260)
        mat.node_tree.nodes.active=im
        mat.node_tree.links.new(im.outputs["Color"],bs.inputs["Base Color"])
        mats.append(mat)
    return mats


class Cloth:
    def __init__(self):
        self.coords=[]
        self.weights=[]
        self.faces=[]
        self.uv=[]
        self.slots=[]

    def vertex(self, point, weights):
        self.coords.append(point)
        self.weights.append(weights)
        return len(self.coords)-1

    def face(self, ids, mat=0, color=None, uv=None):
        self.faces.append(tuple(ids))
        if color:
            self.uv.append([swatch(color,self.coords[i]) for i in ids])
        else:
            self.uv.append(uv)
        self.slots.append(mat)

    def loft(self, rows, n, point_fn, uv_fn=None, *, mat=0, color=None, ends=True, flip=False):
        rings=[]
        for i,row in enumerate(rows):
            ring=[]
            for j in range(n):
                pos,w = point_fn(row,TAU*j/n)
                ring.append(self.vertex(pos,w))
            rings.append(ring)
        for i,(r,s) in enumerate(zip(rings,rings[1:])):
            for j in range(n):
                k=(j+1)%n
                ids=[r[j],r[k],s[k],s[j]]
                uv=uv_fn(ids,i,j,n) if uv_fn else None
                if flip:
                    ids.reverse()
                    if uv is not None:
                        uv.reverse()
                self.face(ids,mat,color,uv)
        if ends:
            for k,rev in [(0,not flip),(-1,flip)]:
                ring=rings[k]
                ids=ring[::-1] if rev else ring
                self.face(ids,mat,color or "ink")
        return rings

    def projection(self,ids,i,j,n):
        # Shared drawing-space UV on the front and separate cloth seam work on the back.
        ofs = 0 if math.cos(TAU*(j+.5)/n)>=0 else 1024
        return [tex(512+self.coords[q][0]+ofs,self.coords[q][2]) for q in ids]

    def finish(self,mats):
        # Positive drawing x is screen-right in the front elevation, i.e. world -X.
        verts=[(-x*SCALE,y*SCALE,(1487-py)*SCALE) for x,y,py in self.coords]
        mesh=bpy.data.meshes.new("Tailoring, shirt, trousers and leather")
        mesh.from_pydata(verts,[],[face[::-1] for face in self.faces])
        for m in mats:
            mesh.materials.append(m)
        mesh.update()
        uv=mesh.uv_layers.new(name="Uniform UV")
        for face,coords,slot in zip(mesh.polygons,self.uv,self.slots):
            face.material_index=slot
            face.use_smooth=len(face.vertices)<=4
            for k,c in zip(face.loop_indices,reversed(coords)):
                uv.data[k].uv=c
        ob=bpy.data.objects.new("DRIVER:BODY",mesh)
        bpy.context.collection.objects.link(ob)
        groups={}
        for index,ws in enumerate(self.weights):
            for n,w in ws.items():
                if n not in groups:
                    groups[n]=ob.vertex_groups.new(name=n)
                groups[n].add([index],w,"REPLACE")
        return ob


# row (height in the drawing, half width, center on sagittal axis, front and back radii)
JACKET=[
    (307,35,7,34,35),(315,41,7,36,37),(323,53,6,41,46),
    (331,66,5,51,52),(340,96,4,60,56),(348,121,4,70,57),
    (363,128,5,83,61),(385,124,9,96,67),(407,115,16,109,74),
    (434,108,24,113,77),(456,102,30,108,84),(478,98,32,101,84),
    (500,91,32,97,82),(525,84,33,97,81),(546,82,34,97,79),
    (566,88,31,100,83),(586,99,26,105,89),(611,110,23,109,98),
    (638,120,21,115,105),(670,130,21,116,112),(704,141,21,117,114),
    (725,147,21,118,115),(732,148,21,117,115)
]


def torso_weights(x,y,p):
    ws=mix(bone("Cest"),bone("Hips"),smooth(p,491,632))
    # The coat skirt follows the thigh while the waist remains anchored at the pelvis.
    if p>661:
        ws=mix(ws,bone("Leg_"+("L" if x>=0 else "R")),
               smooth(p,661,752)*(.24+.16*smooth(y,-30,95)))
    if p<396 and abs(x)>57:
        side="L" if x>=0 else "R"
        ws=mix(ws,bone("Clave_"+side),smooth(abs(x),57,121)*(1-smooth(p,338,398))*.73)
    return ws


def torso_point(py,t,offset=0):
    rx,cy,rf,rb=interp(JACKET,py)
    si,co=math.sin(t),math.cos(t)
    x=rx*si
    depth=rf if co>=0 else rb
    y=cy+depth*math.copysign(abs(co)**.82,co)
    # Two subtle bust volumes divided by the shirt and center opening.
    y+=5*math.exp(-((py-436)/45)**2)*(math.sin(2*t)**2)*max(co,0)
    # Slightly raised tails, front opening and side vents at the flared hem.
    p=py
    if py<327:
        p+=12*(1.-smooth(py,307,327))*max(co,0)**2
    if py>694:
        f=smooth(py,694,732)
        p+=f*(10*abs(co)-21*math.exp(-(x/10)**2)*max(co,0)-4*si*si)
    return (x+offset*si,y+offset*co,p)


def face_depth(x,py):
    rx,*_=interp(JACKET,py)
    return torso_point(py,math.asin(max(-.999,min(.999,x/rx))))[1]


def add_button(cloth, center, radius, wts, axes=None):
    # Face, raised steel rim and small inset. Axes are expressed in drawing coordinates.
    x,y,p=center
    ax,ay=(1,0) if axes is None else axes
    nx,ny=-ay,ax
    rows=[(0,.82,"rim"),(.8,1,"rim"),(2,1,"silver"),(3.2,.82,"shine"),(3.45,.57,"silver")]
    old=None
    for depth,ratio,col in rows:
        ids=[]
        for i in range(12):
            a=TAU*i/12
            dx=math.sin(a)*radius*ratio
            dp=math.cos(a)*radius*ratio
            ids.append(cloth.vertex((x+ax*dx+nx*depth,y+ay*dx+ny*depth,p+dp),wts))
        if old:
            for j in range(12):
                k=(j+1)%12
                cloth.face([old[j],old[k],ids[k],ids[j]],2,col)
        old=ids
    cloth.face(ids[::-1],2,"silver")


def jacket(cloth):
    def profile(row,t):
        pt=torso_point(row[0],t)
        return pt,torso_weights(*pt)
    cloth.loft(JACKET,32,profile,cloth.projection)
    # Three-dimensional breast and pocket flaps track the curvature of the tailored front.
    def overlay(outline, lift):
        from mathutils import Vector
        from mathutils.geometry import tessellate_polygon
        loop=[Vector((x,p,0)) for x,p in outline]
        shared={}
        for tri in tessellate_polygon([loop]):
            points=[outline[i] for i in tri]
            div=3
            grid={}
            for i in range(div+1):
                for j in range(div+1-i):
                    u,v=i/div,j/div
                    x,p=(points[0][c]*(1-u-v)+points[1][c]*u+points[2][c]*v for c in (0,1))
                    y=face_depth(x,p)+lift
                    key=(round(x,4),round(p,4))
                    if key not in shared:
                        shared[key]=cloth.vertex((x,y,p),torso_weights(x,y,p))
                    grid[i,j]=shared[key]
            for i in range(div):
                for j in range(div-i):
                    triangles=[[grid[i,j],grid[i+1,j],grid[i,j+1]]]
                    if i+j<div-1:
                        triangles.append([grid[i+1,j],grid[i+1,j+1],grid[i,j+1]])
                    for ids in triangles:
                        a,b,c=[cloth.coords[q] for q in ids]
                        if (b[0]-a[0])*(c[2]-a[2])-(c[0]-a[0])*(b[2]-a[2])<0:
                            ids.reverse()
                        cloth.face(ids,uv=[tex(512+cloth.coords[k][0],cloth.coords[k][2]) for k in ids])
    for sign in (-1,1):
        overlay([(sign*x+(.18*max(0,p-419)),p) for x,p in [(36,313),(57,325),(71,354),(57,357),(74,368),
                                            (50,406),(9,468),(32,376),(39,348)]],1.35)
        overlay([(sign*x,p) for x,p in [(47,596),(106,594),(116,622),(57,627),(53,622)]],1.6)
    for p in (496,563,629):
        add_button(cloth,(-2,face_depth(-2,p)+1,p),8,torso_weights(-2,100,p))

    def collar(row,t):
        p,rx,cy,ry=row
        return (math.sin(t)*rx,cy+ry*math.cos(t),p+max(0,math.cos(t))**1.5*16),bone("Cest")
    # The shirt neckband and blue-edged collar stand are visible in the rear view.
    cloth.loft([(299,27,6,28),(302,32,6,29),(312,38,6,32),(321,42,6,35)],
               24,collar,color="white")
    for start,end,col in [(307,324,"navy"),(323,327,"blue")]:
        def back_collar(row,t):
            # The lower edge of the collar sits on the shoulder slope. Register
            # its back centre with the horizontal blue seam at reference row 327.
            point=torso_point(row + 13*(1+math.cos(t)),t,2.3)
            return point,torso_weights(*point)
        # Draw the jacket collar only around the nape. Open edges meet the printed lapels.
        rings=[]
        for row in (start,end):
            rings.append([cloth.vertex(*back_collar(row,math.radians(61+238*j/24))) for j in range(25)])
        for j in range(24):
            cloth.face([rings[0][j],rings[0][j+1],rings[1][j+1],rings[1][j]],0,col)
    def neck(row,t):
        p,rx,cy,ry=row
        return (rx*math.sin(t),cy+ry*math.cos(t),p),mix(bone("Nek"),bone("Cest"),smooth(p,302,328)*.6)
    cloth.loft([(268,33,8,37),(277,31,9,34),(287,29,8,31),(301,28,7,28),
                (314,30,7,29),(321,32,7,31)],24,neck,mat=3,color="skin")


def sleeve(cloth,sgn):
    side="L" if sgn>0 else "R"
    rows=[
        (345,109,3,7,12),(349,115,1,16,31),(357,120,0,22,45),
        (370,124,-1,26,50),(386,131,-1,29,49),(405,138,-2,30,47),
        (427,147,-4,32,44),(453,160,-7,32,41),(481,172,-10,30,38),
        (505,183,-14,29,36),(520,189,-16,30,35),(532,194,-17,31,36),
        (544,198,-16,30,36),(560,204,-15,29,35),(584,214,-13,28,34),
        (609,225,-11,29,34),(637,236,-9,29,34),(661,246,-8,29,33),
        (685,256,-6,29,34),(713,266,-5,29,33)]
    # The flared cuff is centred on the wrist line; the upper arm has extra loops at the elbow.
    # Inner and outer edges, registered at the shoulder seam, elbow and cuff.
    # At row 496, for instance, the sleeve runs from columns 619 to 692.
    contour = [(345,15,0),(360,21,0),(390,25,1),(430,30,3),(465,32,4),
               (500,31,4),(530,28,4),(560,22,4),(590,16,3),(620,13,3),
               (650,10,3),(690,4,1),(713,0,0)]
    sections = []
    for p, x, cy, radius, depth in rows:
        inward, fullness = interp(contour, p)
        taper = max(0, (p - 384) / (713 - 384)) * 16
        sections.append((p, x - taper - inward, cy, radius + fullness, depth))
    rows = sections
    def weights(p):
        if p<392:
            return mix(bone("Clave_"+side),bone("Arm_"+side),.31+.69*smooth(p,344,393))
        return mix(bone("Arm_"+side),bone("ForeArm_"+side),smooth(p,493,566))
    def profile(row,a):
        p,x,cy,r,d=row
        # Parametrize around the arm, starting underneath where the longitudinal seam falls.
        co,si=math.cos(a),math.sin(a)
        dx=-r*co
        return (sgn*(x+dx*.928),cy+d*si,p-dx*.371),weights(p)
    def uv(ids,i,j,n):
        uv=[]
        for ring,seg in ((i,j),(i,j+1),(i+1,j+1),(i+1,j)):
            p=rows[ring][0]
            uv.append(tex(17+254*seg/n,299+(p-345)/(713-345)*400))
        return uv
    cloth.loft(rows,16,profile,uv,flip=sgn<0)
    # A narrow shirt cuff between the dark jacket and wrist of the glove.
    cloth.loft([(710,249,-5,24,28),(717,252,-5,24,27),(724,254,-5,24,25),
                (727,255,-5,22,24)],16,profile,color="white",flip=sgn<0)
    # Rear-facing pair of cuff buttons, down the trailing outer seam.
    for p in (688,704):
        x,cy,r,d=interp(rows,p)
        angle=math.radians(226)
        pt,w=profile((p,x,cy,r,d),angle)
        tangent=(-.68,.735*sgn)
        add_button(cloth,pt,4.25,w,tangent)


PANTS=[
    (710,67,72,24,102),(730,69,73,23,105),(749,70,73,19,103),
    (766,70,73,18,98),(781,70,73,16,95),(796,70,71,17,91),
    (820,69,68,17,88),(851,68,65,18,83),(892,65,60,19,76),
    (931,63,55,20,69),(966,62,50,19,61),(989,62,46,19,56),
    (1004,62,45,18,56),(1018,63,46,16,57),(1034,64,47,12,58),
    (1050,65,46,9,57),(1068,67,45,7,56),(1092,69,47,5,55),
    (1121,70,48,2,55),(1153,71,48,0,55),(1191,72,47,-2,53),
    (1230,73,45,-4,51),(1274,73,42,-6,49),(1309,72,39,-6,47),
    (1330,71,38,-5,46),(1349,71,39,-3,48),(1368,70,38,-2,49),
    (1386,70,36,-2,49),(1399,70,36,-1,50),(1405,70,35,-1,48)]


def trousers(cloth,sgn):
    side="L" if sgn>0 else "R"
    def profile(row,a):
        p,cx,r,cy,depth=row
        co,si=math.cos(a),math.sin(a)
        x=cx+si*r
        y=cy+depth*co
        # At the crotch the inner wall of the tube tapers into a half-pelvis instead of overlapping the other leg.
        merge=1-smooth(p,745,810)
        if merge>0:
            lateral=(1+si)/2
            hipx=2*cx*(lateral**1.14)
            hipy=cy+math.copysign(depth*((1-(hipx/(2*cx))**2)**.5),co)
            if si<-.92:
                hipy=cy+(hipy-cy)*clamp((1+si)/.08)
            x=x*(1-merge)+hipx*merge
            y=y*(1-merge)+hipy*merge
        hem=smooth(p,1382,1405)
        pp=p+hem*(3*math.cos(a)-2*math.sin(a))
        # Pressed crease is modelled into the front and rear cross-sections.
        y+=math.copysign((abs(co)**15)*2.5,co)
        if p<833:
            w=mix(bone("Hips"),bone("Leg_"+side),.32+.68*smooth(p,730,831))
        else:
            w=mix(bone("Leg_"+side),bone("Shin_"+side),smooth(p,966,1075))
        return (sgn*x,y,pp),w
    cloth.loft(PANTS,18,profile,cloth.projection,flip=sgn<0)


# Shoe profiles measured from rear heel to toe, in drawing units. The heel block is separate
# from the raised arch. Its vamp, saddle and apron sit on the leather upper.
SHOE=[
    (-52,8,47),(-50,24,61),(-43,30,77),(-27,32,88),(-11,32,93),
    (4,31,87),(15,30,74),(28,31,62),(42,32,51),(60,33,42),
    (78,35,34),(95,35,31),(114,33,28),(125,29,25),(132,22,24),(135,12,21),(136.5,5,19),(137,.6,16.5)]


def loafer(cloth,sgn):
    side="L" if sgn>0 else "R"
    cx=70*sgn
    def weight(y):
        return mix(bone("Hill_"+side),bone("Foot_"+side),smooth(y,-6,53))
    def sole_height(y):
        return 12+3*(1-smooth(y,-14,86))
    def upper_pos(y,t):
        rw,h=interp(SHOE,y)
        base=sole_height(y)
        co,si=math.cos(t),math.sin(t)
        x=1.1*(rw-1)*math.copysign(abs(si)**.84,si)
        z=base-1+(h-base)*max(0,co)**.93
        if co<0:
            z-=2*abs(co)
        return (cx+x,y,1487-z)
    def upper(row,t):
        y=row[0]
        return upper_pos(y,t),weight(y)
    def leather_uv(ids,i,j,n):
        a=TAU*j/n
        if TAU*(j+.5)/n>math.pi:
            a-=TAU
        corners=((a,i),(a+TAU/n,i),(a+TAU/n,i+1),(a,i+1))
        return [tex(520+70*angle,65+(SHOE[k][0]+52)*177/189) for angle,k in corners]
    cloth.loft(SHOE,16,upper,leather_uv,mat=1)
    def sole(row,t):
        y,r,_=row
        co,si=math.cos(t),math.sin(t)
        arch=8*(1-smooth(y,2,64))
        bottom=1.6+arch+2.6*smooth(y,95,137)
        h=sole_height(y)+1.5
        x=1.1*(r+1.4)*math.copysign(abs(si)**.50,si)
        z=(bottom+h)*.5+(h-bottom)*.5*math.copysign(abs(co)**.35,co)
        return (cx+x,y,1487-z),weight(y)
    sole_sections=[row for i,row in enumerate(SHOE) if i not in (3,5,7,9,11,14)]
    cloth.loft(sole_sections,12,sole,mat=1,color="sole")
    def heel(row,t):
        y,w=row
        co,si=math.cos(t),math.sin(t)
        return (cx+1.1*w*math.copysign(abs(si)**.46,si),y,
                1487-6.5-6.5*math.copysign(abs(co)**.35,co)),weight(y)
    cloth.loft([(-52,9),(-50,21),(-43,29),(-31,29),(-16,29),(-2,26),(1,19)],
               10,heel,mat=1,color="sole")
    # Cross-vamp strap wraps continuously from near the sole, over the instep, to its far side.
    rings=[]
    for y in (23,25,30,47,50):
        ids=[]
        for j in range(19):
            a=-1.32+2.64*j/18
            yy=y+4*math.cos(a)
            x,_,p=upper_pos(yy,a)
            ids.append(cloth.vertex((x+math.sin(a)*1.45,yy,p-math.cos(a)*1.9),weight(yy)))
        rings.append(ids)
    for i,(first,second) in enumerate(zip(rings,rings[1:])):
        for j in range(18):
            cloth.face([first[j],first[j+1],second[j+1],second[j]],1,
                       "thread" if i in (0,3) else "band")
    # Raised U-shaped apron seam tracing the toe.
    for sign in (-1,1):
        rows=[(33,.93),(50,.97),(70,1.00),(90,1.0),(107,.94),(117,.81),(123,.60),(127,.30),(128,0)]
        prev=None
        for y,angle in rows:
            pair=[]
            for delta in (-.035,.035):
                a=sign*angle+delta
                x,_,p=upper_pos(y,a)
                pair.append(cloth.vertex((x+math.sin(a)*.8,y,p-1.3),weight(y)))
            if prev:
                cloth.face([prev[0],prev[1],pair[1],pair[0]],1,"thread")
            prev=pair


def build_body():
    cloth=Cloth()
    jacket(cloth)
    for s in (-1,1):
        sleeve(cloth,s)
        trousers(cloth,s)
        loafer(cloth,s)
    return cloth.finish(materials())
