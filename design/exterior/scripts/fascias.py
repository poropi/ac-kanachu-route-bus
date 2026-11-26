"""Front and rear coachwork for the LV290. All distances are in metres.

Construction takes place on the end-cap surface provided by the body builder.
Glazing is fitted into openings, so a view from inside sees the same reveal.
"""

from math import ceil, cos, hypot, pi, sin, sqrt

from mathutils import Vector


HALF_FACE = 1.12
TOP = 2.80


def arc_levels(lo, hi, radius, divisions=6):
    """Horizontal sections through both corner arcs of a rounded rectangle."""
    if not radius:
        return [lo, hi]
    offsets = [radius * (1 - cos(i * pi / (2 * divisions))) for i in range(divisions + 1)]
    return sorted({*(lo + value for value in offsets), *(hi - value for value in offsets)})


def rounded_span(bounds, radius, z):
    left, right, lo, hi = bounds
    distance = max(lo + radius - z, z - hi + radius, 0)
    inset = radius - sqrt(max(radius * radius - distance * distance, 0))
    return left + inset, right - inset


class End:
    def __init__(self, api, front):
        self.api = api
        self.front = front
        self.chart = 'FRONT' if front else 'REAR'
        self.sign = 1 if front else -1
        self.lo = api.bottom(front)

    def position(self, x, z, offset=0):
        point = Vector(self.api.end(self.front, x, z))
        point.y += self.sign * offset
        return tuple(point)

    def strips(self, name, levels, bounds_at, material, offset=0, columns=12):
        """Tessellate each scanline to follow the windscreen and bumper curvature."""
        vertices, coords, faces = [], [], []
        levels = sorted({round(z, 8) for z in levels})
        for z in levels:
            left, right = bounds_at(z)
            for col in range(columns + 1):
                x = left + (right - left) * col / columns
                dy = offset(x, z) if callable(offset) else offset
                vertices.append(self.position(x, z, dy))
                coords.append((self.api.front_developed_x(x,z) if self.front and material=='paint' else x, z))
        for row in range(len(levels) - 1):
            for col in range(columns):
                i = row * (columns + 1) + col
                face = (i, i + 1, i + columns + 2, i + columns + 1)
                faces.append(face[::-1] if self.front else face)
        if material == 'paint':
            return self.api.mesh(name, vertices, faces, material, self.chart, coords)
        return self.api.mesh(name, vertices, faces, material)

    def patch(self, name, bounds, radius, material, offset=0, columns=10):
        return self.strips(name, arc_levels(bounds[2], bounds[3], radius),
                           lambda z: rounded_span(bounds, radius, z), material, offset, columns)

    def rectangle(self, name, lo, hi, material, offset=0, left=-HALF_FACE, right=HALF_FACE):
        return self.strips(name, [lo, (lo+hi)/2, hi], lambda z: (left, right), material, offset)

    def glazing_band(self, prefix, bounds, radius, material, gasket, offset):
        """Separate the painted jamb and the glazing by a solid black lip."""
        levels = arc_levels(bounds[2], bounds[3], radius)
        left, right, lo, hi = bounds
        for sign in [-1, 1]:
            def outside(z, sign=sign):
                a, b = rounded_span(bounds, radius, z)
                return (-HALF_FACE, a) if sign < 0 else (b, HALF_FACE)
            self.strips(prefix + ('_PortPillar' if sign < 0 else '_StarboardPillar'),
                        levels, outside, 'paint', columns=3)
        inner = (left + gasket, right - gasket, lo + gasket, hi - gasket)
        inner_radius = max(radius - gasket, .002)
        self.patch(prefix + '_LowerSeal', (left + radius, right - radius, lo, lo + gasket),
                   0, 'trim_black', .001)
        self.patch(prefix + '_UpperSeal', (left + radius, right - radius, hi - gasket, hi),
                   0, 'trim_black', .001)
        # Ring strips have an exact shared contour on all four sides.
        low = [lo, *[v for v in levels if lo < v < lo + gasket], lo + gasket]
        high = [hi - gasket, *[v for v in levels if hi - gasket < v < hi], hi]
        for label, end_levels in [('Lower', low), ('Upper', high)]:
            for sign in [-1, 1]:
                def corner(z, sign=sign):
                    a, b = rounded_span(bounds, radius, z)
                    return (a, left+radius) if sign < 0 else (right-radius, b)
                # At each tangent the first/last row collapses to a point.
                self.corner_strip(prefix + '_' + label + 'Corner' + str(sign), end_levels, corner)
        middle = sorted({*[v for v in levels if inner[2] < v < inner[3]],
                         *arc_levels(inner[2], inner[3], inner_radius)})
        for sign in [-1, 1]:
            def seal(z, sign=sign):
                a, b = rounded_span(bounds, radius, z)
                c, d = rounded_span(inner, inner_radius, z)
                return (a, c) if sign < 0 else (d, b)
            self.strips(prefix + '_SideSeal' + str(sign), middle, seal, 'trim_black', .001, 1)
        self.patch(prefix, inner, inner_radius, material, offset, 18)

    def corner_strip(self, name, levels, bounds_at):
        verts, faces, rows = [], [], []
        for z in levels:
            left, right = bounds_at(z)
            rows.append([len(verts)])
            verts.append(self.position(left, z, .001))
            if right - left > 1e-8:
                rows[-1].append(len(verts))
                verts.append(self.position(right, z, .001))
        for a, b in zip(rows, rows[1:]):
            face = a + list(reversed(b))
            if len(face) >= 3:
                faces.append(face[::-1] if self.front else face)
        if faces:
            self.api.mesh(name, verts, faces, 'trim_black')

    def line(self, name, xz, depth, radius=.005, material='trim_black'):
        points = [self.position(*xz[0], depth)]
        for (x0, z0), (x1, z1) in zip(xz, xz[1:]):
            steps = max(1, ceil(hypot(x1-x0, z1-z0)/.10))
            for i in range(1, steps+1):
                t = i/steps
                points.append(self.position(x0+(x1-x0)*t, z0+(z1-z0)*t, depth))
        return self.api.rod(name, points, radius, material)


def mirror_mesh(api, name, center, normal, width, height, thickness, radius, material, face_material, roll=0):
    """A pressed housing with a rounded rim and a lightly convex mirror insert."""
    n = Vector(normal).normalized()
    axis = Vector((0, 0, 1)).cross(n)
    if axis.length < .05:
        axis = Vector((1, 0, 0))
    axis.normalize()
    up = n.cross(axis).normalized()
    axis, up = axis*cos(roll) + up*sin(roll), up*cos(roll) - axis*sin(roll)
    center = Vector(center)
    ring = []
    for sx, sy, start in [(1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)]:
        for i in range(6):
            angle = (start + 90*i/5) * pi/180
            ring.append((sx*(width/2-radius)+radius*cos(angle),
                         sy*(height/2-radius)+radius*sin(angle)))
    rows = [(.79, -thickness*.54), (.94, -thickness*.45), (1, -.24*thickness),
            (1, thickness*.36), (.96, thickness*.5), (.86, thickness*.51)]
    count = len(ring)
    verts = [tuple(center + axis*(u*s) + up*(v*s) + n*d)
             for s, d in rows for u, v in ring]
    faces = [tuple(reversed(range(count)))]
    for level in range(len(rows)-1):
        for i in range(count):
            j = (i+1) % count
            a, b = level*count, (level+1)*count
            faces.append((a+i, a+j, b+j, b+i))
    api.mesh(name, verts, faces, material)
    glass = verts[-count:] + [tuple(center + n*(thickness*.51+.0045))]
    api.mesh(name + '_Surface', glass, [(i, (i+1)%count, count) for i in range(count)], face_material)
    if name in ('Mirror_Port_Long','Mirror_Starboard_Main'):
        # The long mirrors have a pressed rear cover and central pivot socket.
        rib=[tuple(center+axis*(u*sx)+up*(v*sy)-n*(thickness*depth))
             for sx,sy,depth in ((.745,.795,.535),(.72,.77,.596),(.69,.74,.596),(.665,.715,.535))
             for u,v in ring]
        quads=[]
        for row in range(3):
            a=row*count
            for i in range(count):
                j=(i+1)%count
                quads.append((a+i,a+count+i,a+count+j,a+j))
        api.mesh(name+'_PressedBack',rib,quads,material)



def under_mirror(api, name, center, normal):
    """Circular convex under-view mirror with a rolled rim and a domed back."""
    n=Vector(normal).normalized()
    h=Vector((0,0,1)).cross(n).normalized()
    v=n.cross(h).normalized()
    c=Vector(center)
    count=40
    # Two poles avoid collapsed rings and degenerate UV triangles.
    rings=[(.027,-.025),(.077,-.016),(.099,-.004),(.101,.003),(.095,.008)]
    verts=[tuple(c-n*.027)]
    for radius,depth in rings:
        for i in range(count):
            angle=2*pi*i/count
            verts.append(tuple(c+n*depth+radius*(cos(angle)*h+sin(angle)*v)))
    faces=[(0,1+(i+1)%count,1+i) for i in range(count)]
    for j in range(len(rings)-1):
        a=1+j*count
        faces += [(a+i,a+(i+1)%count,a+count+(i+1)%count,a+count+i) for i in range(count)]
    api.mesh(name,verts,faces,'trim_black')
    surface=verts[-count:]+[tuple(c+n*.024)]
    api.mesh(name+'_Surface',surface,[(i,(i+1)%count,count) for i in range(count)],'chrome')


def mirrors(e):
    a=e.api
    # Positions measured with the fixed head-on and three-quarter cameras.
    # The two attachment lugs stay on the corner, behind the forward elbow.
    a.box('Mirror_Port_Foot',(-1.181,4.592,2.575),(.062,.114,.151),'trim_black',.014)
    a.rod('Mirror_Port_MainBoom',[(-1.1974,4.6115,2.624),(-1.208,4.680,2.620),
          (-1.239,5.044,2.608),(-1.242,5.064,2.604),(-1.244,5.082,2.594),
          (-1.246,5.094,2.576),(-1.248,5.100,2.548),(-1.257,5.158,2.210),
          (-1.262,5.169,2.171)],.020,'rim')
    a.rod('Mirror_Port_BoomBrace',[(-1.198,4.610,2.530),(-1.205,4.680,2.532),
          (-1.240,5.060,2.532),(-1.248,5.100,2.548)],.014,'rim')
    # Shallow pressed web between the hems of the upper folding arm.
    sections = [(-1.202,4.640,2.531,2.623),(-1.239,5.055,2.532,2.604)]
    web = [(x+dx,y,z) for x,y,low,high in sections
           for dx,z in ((-.012,low),(-.012,high),(.012,high),(.012,low))]
    a.mesh('Mirror_Port_BoomWeb',web,[(3,2,1,0),(4,5,6,7),(0,1,5,4),
           (1,2,6,5),(2,3,7,6),(3,0,4,7)],'rim')
    a.rod('Mirror_Port_Spindle',[(-1.262,5.169,2.176),(-1.271,5.184,2.016)],
          .011,'rim')
    mirror_mesh(a,'Mirror_Port_Long',(-1.2759,5.1535,2.0031),(.3784,-.9061,-.1891),
                .173,.314,.064,.041,'rim','chrome',roll=-.0069)
    a.rod('Mirror_Port_Pivot',[(-1.271,5.184,2.016),(-1.284,5.182,2.005)],.022,'trim_black')
    mirror_mesh(a,'Mirror_Port_Upper',(-1.243,5.0394,2.2734),(.35,-.93,-.14),
                .226,.119,.055,.031,'trim_black','chrome')
    a.rod('Mirror_Port_UpperClamp',[(-1.255,5.148,2.273),(-1.270,5.123,2.279),
          (-1.271,5.090,2.280),(-1.254,5.063,2.276)],.013,'rim')
    a.rod('Mirror_Port_CrossviewArm',[(-1.258,5.158,2.210),(-1.103,5.195,2.205),
          (-1.083,5.199,2.199),(-1.074,5.203,2.185),(-1.069,5.210,2.149),
          (-1.063,5.212,2.120)],.011,'rim')
    under_mirror(a,'Mirror_Port_Crossview',(-1.0347,5.2135,2.1055),(.582,-.422,-1.0))
    # The driver's long mirror folds back along the side. The separate
    # cross-view stalk turns in the opposite direction, towards the windscreen.
    a.box('Mirror_Starboard_Foot',(1.200,4.682,1.979),(.047,.132,.108),'trim_black',.012)
    a.rod('Mirror_Starboard_Boom',[(1.206,4.670,1.978),(1.231,4.654,2.067),
          (1.245,4.645,2.115),(1.259,4.634,2.129),(1.318,4.593,2.136),
          (1.333,4.581,2.126),(1.337,4.578,2.107),(1.345,4.571,2.031)],.014,'trim_black')
    mirror_mesh(a,'Mirror_Starboard_Main',(1.3366,4.5394,2.0297),(-.30,-.95,.04),
                .173,.302,.065,.042,'trim_black','chrome',roll=.095)
    a.rod('Mirror_Starboard_CrossviewArm',[(1.206,4.673,1.978),(1.183,4.800,2.097),
          (1.161,4.866,2.123),(1.139,4.905,2.133),(1.001,4.971,2.127),
          (.979,4.984,2.118),(.973,4.986,2.085)],.012,'rim')
    under_mirror(a,'Mirror_Starboard_Crossview',(.9719,4.9766,2.0684),(-.20,-.47,-.86))


def light(e, name, x, z, width, height, tint, depth=.008, grid=False):
    """A tinted lens return, an emissive face, and a separate moulded reflector."""
    def bounds(w, h):
        return x-w/2, x+w/2, z-h/2, z+h/2
    r = min(.012,height*.15)
    e.patch(name.replace('LIGHT_','Gasket_'), bounds(width+.012,height+.012),r+.004,'rubber',depth-.002,4)
    lens=e.patch(name.replace('LIGHT_','Lens_'),bounds(width,height),r,'glass_light',depth,4)
    lens.color=tint
    emitting=e.patch(name,bounds(width-.012,height-.010),r*.72,'light_emit',depth+.0016,4)
    emitting.color=tint
    if grid:
        # Fine ribs break up the highlights on the vehicle's unlit signal lenses.
        for i in range(1,5):
            u=x-width*.46+i*width*.18
            l=e.line(name.replace('LIGHT_','Prism_')+str(i),[(u,z-height*.43),(u,z+height*.43)],
                     depth+.0027,.0008,'glass_light')
            if l is not None:
                l.color=tint
    return emitting


def headlamps(e, s, tag, bumper_top):
    def sign_interval(a, b):
        return (a, b) if s > 0 else (-b, -a)
    def pocket(z):
        # The mask has a diagonal inner edge to match the removable nose panel.
        t=(z-(bumper_top+.008))/.321
        # Compound corner at the outside foot of the black lamp pocket.
        edge=.061*max(0,1-min(1,t/.22))**2
        return sign_interval(.685+.055*t+.012*max(0,1-t/.13),1.119-edge)
    e.strips('HeadlampBlackBezel_'+tag,[bumper_top+.008,bumper_top+.025,
              bumper_top+.060,bumper_top+.245,bumper_top+.321],pocket,'trim_black',.0015,6)
    x=.942*s
    z=bumper_top+.159
    e.patch('HeadlampReflector_'+tag,(x-.118,x+.118,z-.094,z+.094),.028,'chrome',.004,8)
    # A terraced optical bowl surrounds the small central projector.
    e.patch('HeadlampDarkOptic_'+tag,(x-.092,x+.092,z-.063,z+.079),.044,'trim_black',.006,8)
    # Individual radial facets catch grazing light around the small projector optic.
    count = 24
    levels = [(1.0,.009),(.87,.015),(.77,.012),(.42,.0068)]
    verts = []
    for scale,depth in levels:
        for i in range(count):
            angle = 2*pi*i/count
            verts.append(e.position(x+.088*scale*cos(angle), z+.009+.062*scale*sin(angle), depth))
    faces = []
    for row in range(len(levels)-1):
        for i in range(count):
            j = (i+1)%count
            faces.append((row*count+i,(row+1)*count+i,(row+1)*count+j,row*count+j))
    e.api.mesh('HeadlampSteppedReflector_'+tag,verts,faces,'chrome')
    light(e,'LIGHT_HEAD_'+tag,x,z+.010,.077,.054,(.84,.91,.98,1.),.009)
    e.line('HeadlampUpperCutoff_'+tag,[(x-.074,z+.047),(x-.050,z+.053),(x+.054,z+.053),
           (x+.073,z+.046)],.016,.005,'trim_black')
    for i in range(6):
        u=x-.077+.030*i
        e.line('HeadlampReflectorFlute_'+tag+str(i),[(u,z-.047),(u+.006,z-.080)],
               .007,.0018,'chrome')
    e.line('HeadlampCrescent_'+tag,[(x-.087,z+.034),(x-.076,z-.027),(x-.049,z-.050),
           (x+.047,z-.050),(x+.077,z-.027),(x+.086,z+.027)],.012,.006,'chrome')
    # A slightly domed clear lens covers the chromed bowl and cut-off shield.
    ring=[]
    for cx,cz,start in ((.083,.061,0),(-.083,.061,90),(-.083,-.061,180),(.083,-.061,270)):
        for k in range(5):
            phi=(start+90*k/4)*pi/180
            ring.append((cx+.025*cos(phi),cz+.025*sin(phi)))
    vs=[e.position(x+u,z+v,.014) for u,v in ring]
    vs.extend(e.position(x+u*.63,z+v*.63,.018) for u,v in ring)
    n=len(ring)
    fs=[(j,(j+1)%n,n+(j+1)%n,n+j) for j in range(n)]
    fs.append(tuple(range(n,2*n)))
    cover=e.api.mesh('Headlamp_Cover_'+tag,vs,[f[::-1] for f in fs],'glass_light')
    cover.color=(.63,.72,.76,1)
    e.line('Headlamp_Shield_'+tag,[(x-.069,z+.033),(x-.044,z+.040),(x+.047,z+.040),
                                  (x+.073,z+.026)],.012,.005,'trim_black')
    # The shared assembly in the lower bumper has an inner clear lamp and outer blinker.
    z=(e.lo+bumper_top)*.5
    e.patch('LowerLampHousing_'+tag,(*sign_interval(.741,1.028),z-.049,z+.049),.025,'trim_black',.004,6)
    light(e,'LIGHT_IND_F'+tag,.966*s,z,.103,.062,(.9,.237,.015,1.),.008,True)
    e.patch('FrontFogReflector_'+tag,(*sign_interval(.755,.905),z-.033,z+.034),.011,'chrome',.008,4)
    e.patch('FrontFogLens_'+tag,(*sign_interval(.764,.896),z-.026,z+.028),.009,'glass_light',.010,4)
    # The square corner marker is a separate clear lens on the bumper return.
    e.patch('CornerMarkerSeal_'+tag,(*sign_interval(1.061,1.118),z-.055,z+.055),
            .020,'trim_black',.006,6)
    marker=e.patch('CornerMarkerLens_'+tag,(*sign_interval(1.067,1.114),z-.047,z+.047),
                   .016,'glass_light',.009,6)
    marker.color=(.86,.90,.88,1)


def numberplate(e, z):
    # Leave the mounting blank for the livery author. Two bright fixing screws remain.
    half_height=.109 if e.front else .111
    e.patch('FrontPlateMount' if e.front else 'RearPlateMount',(-.225,.225,z-half_height,z+half_height),
            .012,'trim_black',.004)
    e.patch('FrontPlateBlank' if e.front else 'RearPlateBlank',(-.214,.214,z-half_height+.005,z+half_height-.005),
            .008,'rim',.006)
    for x in [-.165,.165]:
        e.patch(('Front' if e.front else 'Rear')+'PlateScrew'+str(x),
                (x-.006,x+.006,z+.047,z+.057),.0045,'chrome',.008,2)


def nose(api):
    e=End(api,True)
    bumper_top=e.lo+.215
    e.rectangle('FrontBumper',e.lo,bumper_top,'paint')
    e.rectangle('NosePanel',bumper_top,1.18,'paint')
    e.glazing_band('Windshield',(-1.114,1.114,1.18,2.323),.062,'glass',.025,-.003)
    e.rectangle('FrontBrow',2.323,2.366,'paint')
    e.glazing_band('DestinationMaskFront',(-1.071,1.071,2.366,2.753),.090,'trim_black',.013,-.001)
    e.rectangle('FrontCantrail',2.753,TOP,'paint')
    e.patch('DEST_FRONT',(-.672,.672,2.419,2.705),.016,'dest_led',.001,18)
    # Black ceramic frit and the wiper pivots occupy the narrow strip at sill height.
    e.patch('WindshieldFrit',(-1.106,1.106,1.185,1.314),.031,'trim_black',.002,24)
    e.line('Windshield_Frit_RaisedLip',[(-1.079,1.294),(-.85,1.301),(0,1.303),
           (.85,1.301),(1.079,1.294)],.006,.007,'rubber')
    for s,tag in [(-1,'L'),(1,'R')]:
        e.line('WiperServiceCover_'+tag,[(s*.194,1.221),(s*.212,1.219),(s*.471,1.220)],
               .008,.016,'rubber')
        headlamps(e,s,tag,bumper_top)
        e.line('FrontBonnetJoint_'+tag,[(s*.774,1.18),(s*.756,1.065),(s*.696,bumper_top+.083),
               (s*.685,bumper_top+.059),(s*.660,bumper_top+.047)],.002,.0045)
        for x,z in [(.544,bumper_top+.118),(.61,1.12)]:
            e.line('FrontInspectionLatch_'+tag+str(z),[(s*x,z),(s*(x+.05),z+.004)],
                   .004,.004,'chrome')
        # Two parallel arms and a long, near-vertical blade are distinctive Erga features.
        e.line('WiperBase_'+tag,[(s*.586,1.22),(s*.523,1.22)],.016,.024)
        e.line('WiperArmOuter_'+tag,[(s*.578,1.226),(s*.449,1.361),(s*.169,1.666),
               (s*.128,1.711),(s*.071,1.704)],.023,.010)
        e.line('WiperArmInner_'+tag,[(s*.526,1.226),(s*.426,1.340),(s*.182,1.607),
               (s*.136,1.682),(s*.076,1.693)],.025,.007)
        e.line('WiperBlade_'+tag,[(s*.071,1.389),(s*.068,1.714),(s*.062,2.025)],
               .027,.009,'rubber')
        e.line('WiperBladeSpine_'+tag,[(s*.072,1.523),(s*.078,1.701),(s*.064,1.877)],
               .032,.005)
        e.line('BrowCatch_'+tag,[(s*.398,2.325),(s*.417,2.336),(s*.519,2.336),
               (s*.539,2.326)],.004,.009)
        e.line('BumperJointFront_'+tag,[(s*.57,e.lo+.005),(s*.57,bumper_top-.006)],.002,.004)
    e.line('NoseLowerJoint',[(-.660,bumper_top+.047),(-.35,bumper_top+.043),(0,bumper_top+.043),
                             (.35,bumper_top+.043),(.660,bumper_top+.047)],.002,.0045)
    for s,tag in [(-1,'L'),(1,'R')]:
        a,b=sorted((s*.222,s*.566))
        e.patch('FrontBumperRubStrip_'+tag,(a,b,bumper_top-.020,bumper_top+.004),
                .006,'rubber',.004,8)
    numberplate(e,e.lo+.109)
    e.patch('FrontTowRecess',(.282,.453,e.lo+.055,e.lo+.164),.016,'trim_black',.002)
    e.line('FrontTowLatch',[(-.446,e.lo+.158),(-.303,e.lo+.158),(-.29,e.lo+.143),
                            (-.29,e.lo+.055),(-.444,e.lo+.055),(-.45,e.lo+.148)],.002,.003)
    mirrors(e)


class RearWindowEnd(End):
    """The upper glass edge follows the crown; the lower hinge line is level."""
    def position(self, x, z, offset=0):
        amplitude = max(0, min(1, (z-2.43)/.318, (TOP-z)/.052))
        return super().position(x, z-.032*(x/HALF_FACE)**2*amplitude, offset)

    def strips(self, *args, **kwargs):
        obj = super().strips(*args, **kwargs)
        if obj.get('chart') == 'REAR':
            for loop in obj.data.loops:
                obj.data.uv_layers.active.data[loop.index].uv.y = obj.data.vertices[loop.vertex_index].co.z
        return obj


def rear_bumper(e, top):
    # The lower lip steps up around the outlet on the vehicle's right.
    section=[(-HALF_FACE,0),(-.8,0),(-.6,0),(-.4,0),(-.2,0),(0,0),(.25,0),
             (.444,0),(.458,.028),(.472,.039),(.489,.044),(.626,.044),
             (.644,.039),(.657,.028),(.668,0),(.83,0),(1.02,0),(HALF_FACE,0)]
    coords=[(x,z) for x,h in section for z in (e.lo+h,(e.lo+top)/2,top)]
    vs=[e.position(x,z) for x,z in coords]
    fs=[(3*i+j,3*i+3+j,3*i+4+j,3*i+j+1)
        for i in range(len(section)-1) for j in (0,1)]
    e.api.mesh('RearBumper',vs,fs,'paint','REAR',coords)
    rim=section[7:15]
    verts=[e.position(x,e.lo+h,d) for x,h in rim for d in (-.035,0)]
    e.api.mesh('RearOutlet_Return',verts,[(2*i,2*i+1,2*i+3,2*i+2) for i in range(len(rim)-1)],'trim_black')


def plate_lamp(e, x, tag):
    """Domed plate illumination hood on a diamond-shaped mounting flange."""
    z=.932
    diamond=[(x-.062,z),(x,z-.044),(x+.062,z),(x,z+.044)]
    e.api.mesh('PlateLampFlange_'+tag,[e.position(u,v,.010) for u,v in diamond],
               [(0,1,2,3)],'rubber')
    rings=[(.046,.041,.012),(.043,.040,.027),(.031,.030,.036),(.012,.013,.042)]
    verts=[e.position(x+rx*cos(2*pi*i/24),z+rz*sin(2*pi*i/24),depth)
           for rx,rz,depth in rings for i in range(24)]
    faces=[(24*j+i,24*j+(i+1)%24,24*(j+1)+(i+1)%24,24*(j+1)+i)
           for j in range(3) for i in range(24)]
    faces.append(tuple(range(72,96)))
    hood=e.api.mesh('PlateLampHood_'+tag,verts,faces,'trim_black')
    for face in hood.data.polygons: face.use_smooth=True


def rear_view_lens(e):
    # Clear wide-angle reversing lens on the inside of the rear window.
    # Rounded square perimeter, with the optical centre raised above mid-height.
    verts=[]
    for rx,rz,rounding,zc,depth in ((.170,.140,.031,2.210,-.014),
            (.164,.134,.034,2.210,-.015),(.145,.109,.087,2.223,-.019),
            (.129,.097,.090,2.232,-.027),(.107,.078,.076,2.237,-.032),
            (.073,.053,.052,2.240,-.035),(.029,.021,.020,2.243,-.039)):
        for sx,sz,start in ((1,1,0),(-1,1,90),(-1,-1,180),(1,-1,270)):
            for k in range(9):
                a=(start+90*k/8)*pi/180
                x=sx*(rx-rounding)+rounding*cos(a)
                z=zc+sz*(rz-rounding)+rounding*sin(a)
                verts.append(e.position(x,z,depth))
    n=36
    faces=[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i)
           for j in range(len(verts)//n-1) for i in range(n)]
    faces.append(tuple(range(len(verts)-n,len(verts))))
    lens=e.api.mesh('Rear_Window_WideAngleLens',verts,faces,'glass_light')
    lens.color=(.54,.65,.67,1.0)


def tail(api):
    e=End(api,False)
    bumper_top=e.lo+.197
    rear_bumper(e, bumper_top)
    e.rectangle('EngineCoverPanel',bumper_top,2.008,'paint')
    crown=RearWindowEnd(api,False)
    crown.glazing_band('RearWindow',(-1.088,1.088,2.008,2.748),.058,'glass',.030,-.003)
    # Use the upper jamb vertices on the adjoining cantrail edge as well;
    # the curved boundary must have the very same chords on both sides.
    boundary_left,boundary_right=rounded_span((-1.088,1.088,2.008,2.748),.058,2.748)
    spans=[(-HALF_FACE,boundary_left,3,'Port'),(boundary_left,boundary_right,18,'Centre'),
           (boundary_right,HALF_FACE,3,'Starboard')]
    for left,right,n,label in spans:
        crown.strips('RearCantrail_'+label,[2.748,2.774,TOP],lambda z,l=left,r=right:(l,r),
                     'paint',columns=n)
    rear_view_lens(e)
    e.patch('RearDestinationHousing',(-.582,.582,2.402,2.69),.012,'trim_black',-.039)
    e.patch('DEST_REAR',(-.463,.463,2.461,2.653),.006,'dest_led',-.036,16)
    # The removable cover steps up between the left and right combination lamps.
    line=[(-1.050,1.222),(-.705,1.222),(-.685,1.238),(-.685,1.453),(-.673,1.465),
          (.673,1.465),(.685,1.453),(.685,1.238),(.705,1.222),(1.050,1.222)]
    e.line('EngineHatchJoint',line,.002,.0045)
    e.line('EngineHatchLowerSeal',[(-1.050,bumper_top),(-.6,bumper_top),(0,bumper_top),
                                   (.6,bumper_top),(1.050,bumper_top)],.001,.006)
    for s,tag in [(-1,'L'),(1,'R')]:
        def interval(a,b):
            return tuple(sorted((s*a,s*b)))
        e.line('RearPanelEdge_'+tag,[(s*1.050,bumper_top),(s*1.050,1.221),
                                     (s*1.060,1.225),(s*1.060,2.008)],.002,.005)
        e.patch('TailLampHousing_'+tag,(*interval(.710,1.031),1.251,1.467),
                .008,'trim_black',.003,8)
        xr=.795*s
        # Upper/lower functions share a continuous red lens, alongside a split amber lens.
        light(e,'LIGHT_TAIL_'+tag,xr,1.309,.148,.102,(.39,.012,.012,1),.007)
        light(e,'LIGHT_BRAKE_'+tag,xr,1.412,.148,.102,(.66,.013,.018,1),.007)
        light(e,'LIGHT_IND_R'+tag,.954*s,1.361,.146,.203,(.68,.175,.015,1),.007)
        e.line('IndicatorLensRib_'+tag,[(s*.888,1.354),(s*1.023,1.354)],.011,.0025,'rubber')
        z=e.lo+.103
        e.patch('ReverseHousing_'+tag,(*interval(.707,.943),z-.047,z+.047),
                .014,'trim_black',.003,6)
        light(e,'LIGHT_REVERSE_'+tag,.792*s,z,.139,.072,(.72,.87,1.,1),.006)
        r=e.patch('RearRetroreflector_'+tag,(*interval(.872,.924),z-.033,z+.033),
                  .005,'glass_light',.006,3)
        r.color=(.56,.006,.009,1)
        e.line('EngineHatchHandle_'+tag,[(s*.338,.706),(s*.360,.710),
               (s*.493,.710),(s*.515,.706)],.012,.012)
        e.line('RearBumperSplit_'+tag,[(s*.973,e.lo+.002),(s*.973,bumper_top-.004)],.002,.004)
        plate_lamp(e,s*.108,tag)
    e.patch('BoardingIndicatorSurround',(-1.016,-.849,.659,1.179),.026,'rim',.007,6)
    e.patch('BoardingIndicatorRecess',(-.997,-.868,.681,1.158),.011,'trim_black',.011,6)
    # Uprights are pressed channels on a raised, open advertising carrier.
    for i,x in enumerate([-.486,-.297,-.006,.281,.434,.481]):
        w=.010 if i in (4,5) else .018
        e.patch('AdvertCarrierUpright_'+str(i),(x-w,x+w,.997,1.454),.002,'rim',.034,2)
        e.line('AdvertCarrierFold_'+str(i),[(x-w,1.001),(x-w,1.454)],.028,.006,'chrome')
    for label,z in [('Base',.992),('Top',1.459)]:
        e.patch('AdvertCarrier_'+label,(-.502,.498,z-.012,z+.012),.003,'rim',.038,14)
        for x in (-.476,.473):
            e.api.box('AdvertCarrier_Bracket_'+label,e.position(x,z,.019),(.048,.034,.021),'rim',.003)
            e.patch('AdvertCarrier_Fastener_'+label,(x-.005,x+.005,z-.005,z+.005),.0048,'chrome',.040,2)
    numberplate(e,.761)


def build(api):
    nose(api)
    tail(api)
    for front in (False,True):
        e=End(api,front)
        stamped_plate(e)
        z=e.lo+(.215 if front else .197)
        # Narrow flange between the moulded bumper and the surrounding panels.
        e.line(('Front' if front else 'Rear')+'_Bumper_Flange',
               [(i*HALF_FACE/20,z+.0005) for i in range(-20,21)],.0015,.0035)
        if not front:
            # Each rear combination unit has individual LED cells behind the lens.
            for s,tag in ((-1,'L'),(1,'R')):
                vs=[];faces=[]
                for level in (1.309,1.412):
                    for col in range(5):
                        for row in range(3):
                            x=s*.795+(col-2)*.025
                            z=level+(row-1)*.023
                            k=len(vs)
                            for a in range(12):
                                t=2*pi*a/12
                                vs.append(e.position(x+.008*cos(t),z+.008*sin(t),.0115))
                            faces.append(tuple(range(k,k+12)))
                obj=api.mesh('Tail_DiodeOptics_'+tag,vs,faces,'glass_light')
                obj.color=(.93,.065,.042,1)



def stamped_plate(e):
    """Raised, original registration lettering. Project local glyphs onto the plate."""
    import bpy
    import unicodedata
    from pathlib import Path
    prefix='Front' if e.front else 'Rear'
    # Straight plate, with letters kept parallel to its face.
    plate=bpy.data.objects[prefix+'PlateBlank']
    plate.data.materials[0]=bpy.data.materials['trim_black']
    src=next(p for p in Path('/System/Library/Fonts').glob('*.ttc')
             if unicodedata.normalize('NFC',p.stem)=='ヒラギノ角ゴシック W6')
    font=next((f for f in bpy.data.fonts if f.filepath==str(src)),None) or bpy.data.fonts.load(str(src))
    platez=e.lo+.109 if e.front else .761
    for j,(word,w,h,dx,dz) in enumerate([('湘南200',.163,.034,0,.048),('か',.031,.033,-.167,-.025),
                                          ('22-88',.244,.073,.020,-.020)]):
        data=bpy.data.curves.new('Press tool','FONT')
        data.font=font
        data.body=word
        data.resolution_u=3
        temp=bpy.data.objects.new('Press tool',data)
        bpy.context.collection.objects.link(temp)
        dg=bpy.context.evaluated_depsgraph_get()
        ev=temp.evaluated_get(dg)
        outline=ev.to_mesh()
        xy=[(v.co.x,v.co.y) for v in outline.vertices]
        x0,y0=map(min,zip(*xy));x1,y1=map(max,zip(*xy))
        vs=[]
        for x,y in xy:
            px=((x-(x0+x1)/2)*w/(x1-x0)+dx)*(-e.sign)
            pz=(y-(y0+y1)/2)*h/(y1-y0)+platez+dz
            vs.append(e.position(px,pz,.009))
        # Blender can generate duplicate, reversed back faces at zero thickness.
        fs=[tuple(p.vertices) for p in outline.polygons if p.normal.z>.5 and p.area>1e-13]
        e.api.mesh(f'{prefix}Plate_Type_{j}',vs,fs,'rim')
        ev.to_mesh_clear()
        bpy.data.objects.remove(temp,do_unlink=True)
        bpy.data.curves.remove(data)
