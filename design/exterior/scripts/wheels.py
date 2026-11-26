"""LV290 road wheels. All positions below are local to an unrotated axle empty."""

from math import cos, hypot, pi, sin, tau

import bmesh
import bpy


class WheelPart:
    """Collect closed turned/pressed components into a single drawable mesh."""

    def __init__(self, side):
        self.side = side
        self.points = []
        self.lookup = {}
        self.faces = []
        self.smooth = []

    def vertex(self, point):
        # Rotating a right wheel through 180 degrees preserves its winding on the left.
        x, y, z = point
        key = (round(self.side * x, 8), round(self.side * y, 8), round(z, 8))
        if key not in self.lookup:
            self.lookup[key] = len(self.points)
            self.points.append(key)
        return self.lookup[key]

    def face(self, indices, smooth=True):
        self.faces.append(indices)
        self.smooth.append(smooth)

    def tube(self, profile, sectors=64, center=(0, 0), smooth=True):
        """Revolve a closed (outboard offset, radius) section. Zero radius closes an end."""
        y0, z0 = center
        rings = []
        for x, radius in profile:
            rings.append([self.vertex((x, y0 + radius * cos(tau * i / sectors),
                                       z0 + radius * sin(tau * i / sectors)))
                          for i in range(sectors)])
        for i, a in enumerate(rings):
            b = rings[(i + 1) % len(rings)]
            for k in range(sectors):
                n = (k + 1) % sectors
                indices = tuple(dict.fromkeys((a[k], a[n], b[n], b[k])))
                if len(indices) >= 3:
                    self.face(indices, smooth)

    def finish(self, name, parent, material, offset=0):
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(self.points, [], self.faces)
        mesh.update()
        for face, smooth in zip(mesh.polygons, self.smooth):
            face.use_smooth = smooth
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        bm.free()
        mesh.update()
        mesh.set_sharp_from_angle(angle=pi / 4)
        uv = mesh.uv_layers.new(name='UVMap')
        for face in mesh.polygons:
            # A per-face projection also maps the walls of the hand holes and nut bevels.
            axis = max(range(3), key=lambda i: abs(face.normal[i]))
            u_axis, v_axis = ((1, 2), (2, 0), (0, 1))[axis]
            for loop_id in face.loop_indices:
                co = mesh.vertices[mesh.loops[loop_id].vertex_index].co
                uv.data[loop_id].uv = (.5 + co[u_axis], .5 + co[v_axis])
        obj = bpy.data.objects.new(name, mesh)
        parent.users_collection[0].objects.link(obj)
        obj.parent = parent
        obj.location.x = self.side * offset
        mesh.materials.append(material)
        return obj


def build_tyre(side, parent, material, suffix, offset):
    tyre = WheelPart(side)
    # Four circumferential channels in the road-contact surface, with rounded shoulders
    # and a shallow molded rib on each sidewall. Diameter and width are the outer extrema.
    half_section = [
        (0, .478), (.023, .478), (.026, .470), (.031, .470), (.034, .478),
        (.067, .477), (.070, .469), (.075, .469), (.078, .476),
        (.099, .474), (.117, .462), (.130, .435),
        (.1367, .395), (.1375, .373), (.1360, .368), (.1373, .365),
        (.131, .339), (.108, .286)
    ]
    profile = [(-x, r) for x, r in reversed(half_section[1:])] + half_section
    tyre.tube(profile, sectors=48)
    return tyre.finish('Tyre_' + suffix, parent, material, offset)


def hand_hole_plate(part, front):
    """Stamp ten actual through-holes in an annular disc, including the rolled edges."""
    inner_radius, outer_radius = .169, .264
    half_sector = pi / 10
    middle_radius = (inner_radius + outer_radius) / 2
    radial_extent = (outer_radius - inner_radius) / 2

    def surface(radius):
        t = max(0, min(1, (radius - inner_radius) / (outer_radius - inner_radius)))
        # Convex front disc and inverted rear disc of a dished commercial wheel.
        return (.098 - .124 * t ** 1.35) if front else (-.137 + .065 * t ** 1.55)

    def vertex(angle, radius, depth):
        return part.vertex((surface(radius) + depth, radius*cos(angle), radius*sin(angle)))

    # Perimeter of one radial sector in (angle, radius), with regular samples
    # along the inner and outer arcs and identical boundaries at adjacent sectors.
    boundary = []
    for i in range(6):
        boundary.append((-1 + i / 3, -1))
    for i in range(4):
        boundary.append((1, -1 + i / 2))
    for i in range(6):
        boundary.append((1 - i / 3, 1))
    for i in range(4):
        boundary.append((-1, 1 - i / 2))

    for index in range(10):
        center = tau * index / 10 + half_sector
        rings = [[] for _ in range(5)]
        for a, b in boundary:
            length = hypot(a, b)
            angle = center + a * half_sector
            radius = middle_radius + b * radial_extent
            hole_angle = center + .142 * a / length
            hole_radius = middle_radius + .030 * b / length
            rings[0].append(vertex(angle, radius, 0))
            rings[1].append(vertex(center + .151 * a / length,
                                   middle_radius + .0325 * b / length, -.0008))
            rings[2].append(vertex(hole_angle, hole_radius, -.004))
            rings[3].append(vertex(hole_angle, hole_radius, -.010))
            rings[4].append(vertex(angle, radius, -.010))
        for i, (a, b) in enumerate(boundary):
            j = (i + 1) % len(boundary)
            for outer, inner in zip(rings, rings[1:]):
                part.face((outer[i], outer[j], inner[j], inner[i]))
            if abs(b) == 1 and b == boundary[j][1]:
                part.face((rings[4][i], rings[4][j], rings[0][j], rings[0][i]))


def build_rim(side, parent, mats, suffix, offset, front, nuts):
    wheel = WheelPart(side)
    # Inboard and outboard bead flanges and the drop centre of the steel rim.
    rim_profile = [
        (-.115, .288), (-.113, .299), (-.108, .303), (-.101, .300),
        (-.100, .289), (-.070, .283), (-.045, .268), (.018, .268),
        (.046, .281), (.099, .287), (.104, .299), (.110, .303),
        (.116, .300), (.116, .289), (.111, .286), (.102, .280),
        (.052, .275), (.023, .259), (-.052, .259), (-.077, .276),
        (-.109, .282)
    ]
    wheel.tube(rim_profile, sectors=40 if not nuts else 48)
    if nuts:
        hand_hole_plate(wheel, front)
        if not front:
            wheel.tube([(-.083,.261),(-.071,.261),(-.065,.277),(-.078,.278)],sectors=48)
    else:
        # Inboard twin rim: its mounting face is concealed between the two wheels.
        wheel.tube([(.137, .164), (.137, .173), (.015, .241), (-.025, .264),
                    (-.033, .264), (.006, .239), (.126, .168)], sectors=40)
    dish = .098 if front and nuts else (.137 if front else -.137)
    wheel.tube([(dish-.014, .080), (dish-.014, .168), (dish-.008, .174),
                (dish+.002, .173), (dish+.006, .161), (dish+.006, .088)],
               sectors=50)
    if nuts:
        for i in range(10):
            angle = tau*i/10 + pi/10
            center = (.137 * cos(angle), .137 * sin(angle))
            # A flanged hex nut with a small chamfer catching light at oblique angles.
            wheel.tube([(dish+.005, 0), (dish+.005, .0190), (dish+.011, .0190),
                        (dish+.013, .0165), (dish+.027, .0165),
                        (dish+.030, .0135), (dish+.030, 0)],
                       sectors=6, center=center, smooth=False)
    wheel.finish('Steel_rim_' + suffix, parent, mats['rim'], offset)
    if nuts:
        hub = WheelPart(side)
        # Photo fu43 shows a dark hub and a distinctly narrower raised bearing cap.
        end = dish + (.075 if front else .071)
        hub.tube([(dish-.020, 0), (dish-.020, .104), (dish+.001, .108),
                  (dish+.012, .106), (dish+.026, .100), (dish+.033, .097),
                  (dish+.040, .078), (end-.010, .065), (end-.003, .056),
                  (end, .044), (end, 0)], sectors=40)
        # The drum is visible in shadow through the real apertures in the steel disc.
        back = -.130 if front else -.162
        hub.tube([(back-.016, 0), (back-.016, .240), (back-.010, .249),
                  (back, .246), (back, 0)], sectors=40)
        hub.finish('Axle_cap_' + suffix, parent, mats['trim_black'], offset)


def build(root, mats):
    """Create four X-axis wheel pivots and four coincident suspension references."""
    for side_name, side in (('L', -1), ('R', 1)):
        for axle_name, front in (('F', True), ('R', False)):
            station = side_name + axle_name
            location = (side*(1.0325 if front else .910), 2.65 if front else -2.65, .478)
            for prefix in ('SUSP_', 'WHEEL_'):
                empty = bpy.data.objects.new(prefix + station, None)
                root.users_collection[0].objects.link(empty)
                empty.parent = root
                empty.location = location
                empty.empty_display_size = .09
            wheel_parent = empty
            pairs = [('', 0)] if front else [('_outer', .147), ('_inner', -.147)]
            for qualifier, offset in pairs:
                suffix = station + qualifier
                build_tyre(side, wheel_parent, mats['tyre'], suffix, offset)
                build_rim(side, wheel_parent, mats, suffix, offset,
                          front or qualifier == '_inner', qualifier != '_inner')
