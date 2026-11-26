"""Lightweight mesh assembly. Coordinates and angular arguments use metres and degrees."""
import math
from contextlib import contextmanager

import bpy
from mathutils import Matrix, Vector


def tr(x=0, y=0, z=0):
    return Matrix.Translation((x, y, z))


def rot(axis, degrees):
    return Matrix.Rotation(math.radians(degrees), 4, axis)


def empty(name, parent=None, matrix=None):
    ob = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(ob)
    ob.parent = parent
    if matrix is not None:
        ob.matrix_basis = matrix
    ob.empty_display_size = .045
    return ob


def linear(v):
    s = v / 255
    return s / 12.92 if s <= .04045 else ((s + .055) / 1.055) ** 2.4


def material(name, color, rough=.48, metal=0, emission=0, image=None, alpha=1):
    mat = bpy.data.materials.new('interior_' + name)
    rgb = tuple(linear(int(color[i:i+2], 16)) for i in (0, 2, 4))
    mat.diffuse_color = (*rgb, alpha)
    bs = mat.node_tree.nodes.get('Principled BSDF')
    for key, val in [('Base Color', (*rgb, 1)), ('Metallic', metal), ('Roughness', rough),
                     ('Alpha', alpha), ('Emission Strength', emission), ('Emission Color', (*rgb, 1))]:
        bs.inputs[key].default_value = val
    if image:
        tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(image), check_existing=True)
        tex.image.pack()
        mat.node_tree.links.new(tex.outputs['Color'], bs.inputs['Base Color'])
        if emission:
            mat.node_tree.links.new(tex.outputs['Color'], bs.inputs['Emission Color'])
    return mat


class Part:
    def __init__(self, name, parent):
        self.name, self.parent = name, parent
        self.verts, self.faces, self.slots, self.indices = [], [], [], []
        self.uvs, self.smooth = [], []
        self.matrix = Matrix.Identity(4)

    @contextmanager
    def at(self, matrix):
        prev = self.matrix
        self.matrix = prev @ matrix
        try:
            yield self
        finally:
            self.matrix = prev

    def geom(self, pts, faces, mat, smooth=False, maps=None):
        base = len(self.verts)
        pts = [self.matrix @ Vector(p) for p in pts]
        self.verts.extend(pts)
        if mat not in self.slots:
            self.slots.append(mat)
        mi = self.slots.index(mat)
        for i, face in enumerate(faces):
            self.faces.append(tuple(base+k for k in face))
            self.indices.append(mi)
            self.smooth.append(smooth if isinstance(smooth, bool) else smooth[i])
            if maps:
                self.uvs.append(maps[i])
                continue
            # Per-face orthographic projection onto the face's own tangent frame.
            p, q, r = [pts[k] for k in face[:3]]
            n = (q-p).cross(r-p)
            if n.length < 1e-10:
                for k in face[3:]:
                    n = (q-p).cross(pts[k]-p)
                    if n.length > 1e-10:
                        break
            n.normalize()
            ref = Vector((0,1,0)) if abs(n.z) > .70 else Vector((0,0,1))
            u = ref.cross(n).normalized()
            v = n.cross(u)
            self.uvs.append([(pts[k].dot(u)*2, pts[k].dot(v)*2) for k in face])

    def finish(self):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.verts, [], self.faces)
        me.update()
        for mat in self.slots:
            me.materials.append(mat)
        uv = me.uv_layers.new(name='UVMap')
        for poly, index, sm, coords in zip(me.polygons, self.indices, self.smooth, self.uvs):
            poly.material_index = index
            poly.use_smooth = sm
            for loop, xy in zip(poly.loop_indices, coords):
                uv.data[loop].uv = xy
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.collection.objects.link(ob)
        ob.parent = self.parent
        return ob

    def box(self, center, size, mat, radius=.008, bevel=None):
        """Rounded injection-moulded block with tangent edge and corner bands."""
        x,y,z = center
        w,d,h = size
        r = min(radius,w*.48,d*.48)
        b = min(r*.48,h*.27) if bevel is None else min(bevel,r*.9,h*.48)
        if r <= 0:
            rings = [[(x+u*w/2,y+v*d/2,z+t*h/2) for u,v in
                      ((1,1),(-1,1),(-1,-1),(1,-1))] for t in (-1,1)]
        else:
            sections = [(-h/2,b),(-h/2+b*.32,b*.28),(-h/2+b,0),
                        (h/2-b,0),(h/2-b*.32,b*.28),(h/2,b)] if b else [(-h/2,0),(h/2,0)]
            rings=[]
            for height,inset in sections:
                ring=[]
                for cx,cy,start in ((1,1,0),(-1,1,90),(-1,-1,180),(1,-1,270)):
                    for j in range(4):
                        a=math.radians(start+30*j)
                        ring.append((x+cx*(w/2-r)+(r-inset)*math.cos(a),
                                     y+cy*(d/2-r)+(r-inset)*math.sin(a),z+height))
                rings.append(ring)
        self.loft(rings,mat,True)

    def loft(self,rings,mat,smooth=True,caps=True):
        n=len(rings[0])
        faces=[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i)
               for j in range(len(rings)-1) for i in range(n)]
        shading=[smooth]*len(faces)
        if caps:
            faces.extend([tuple(reversed(range(n))),tuple(range((len(rings)-1)*n,len(rings)*n))])
            shading.extend([False,False])
        if caps:
            # A mirrored or descending sweep still needs outward winding when
            # one-sided engine materials are used. Compare the inlet normal with travel.
            inlet=[Vector(p) for p in rings[0]]
            normal=sum((p.cross(inlet[(i+1)%n]) for i,p in enumerate(inlet)),Vector())
            advance=sum((Vector(b)-a for a,b in zip(inlet,rings[1])),Vector())
            if normal.dot(advance)<0:
                faces=[f[::-1] for f in faces]
        self.geom([p for ring in rings for p in ring],faces,mat,shading)

    def tube(self, pts, radius, mat, sides=10, bend=0, closed=False):
        pts=[Vector(p) for p in pts]
        if bend:
            out=[] if closed else [pts[0]]
            for i in (range(len(pts)) if closed else range(1,len(pts)-1)):
                p=pts[i]; a=pts[i-1]-p; b=pts[(i+1)%len(pts)]-p
                dist=min(bend,a.length*.44,b.length*.44)
                a=p+a.normalized()*dist; b=p+b.normalized()*dist
                for j in range(5):
                    t=j/4; out.append((1-t)**2*a+2*t*(1-t)*p+t*t*b)
            pts=out if closed else out+[pts[-1]]
        rings=[]
        last=None
        for i,p in enumerate(pts):
            pre=pts[i-1] if i or closed else p
            nxt=pts[(i+1)%len(pts)] if i<len(pts)-1 or closed else p
            tangent=((p-pre).normalized()+(nxt-p).normalized()).normalized()
            if last is None:
                ref=Vector((1,0,0)) if abs(tangent.x)<.8 else Vector((0,1,0))
            else:
                ref=last
            u=(ref-tangent*tangent.dot(ref)).normalized(); v=tangent.cross(u)
            last=u
            rings.append([p+radius*(u*math.cos(j*math.tau/sides)+v*math.sin(j*math.tau/sides)) for j in range(sides)])
        self.loft(rings+[rings[0]] if closed else rings,mat,True,not closed)

    def face(self, a,b,c,d,mat):
        self.geom([a,b,c,d],[(0,1,2,3)],mat,maps=[[(0,0),(1,0),(1,1),(0,1)]])

    def sticker(self,x,y,z,w,h,mat):
        self.face((x-w/2,y,z-h/2),(x+w/2,y,z-h/2),
                  (x+w/2,y,z+h/2),(x-w/2,y,z+h/2),mat)

    def disc(self,center,r,depth,mat,sides=32):
        x,y,z=center
        self.tube([(x,y,z-depth/2),(x,y,z+depth/2)],r,mat,sides)
