"""Pack metre-based paint charts, validate the stored UVs and draw the paint guide.

The PNG subprocess uses the Pillow installation in the macOS system Python.
It reads its data from stdin, so building leaves only the requested PNG.
"""
from collections import defaultdict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import subprocess
import sys


WIDTH, HEIGHT = 4096, 2048
MAJOR = ("LEFT", "RIGHT", "ROOF", "FRONT", "REAR")
MARGIN, TOP, PAD, LABEL = 30, 84, 8, 28


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    def contains(self, other):
        return (self.x <= other.x and self.y <= other.y
                and self.right >= other.right and self.bottom >= other.bottom)


def _occupy(available, used):
    """Split free rectangles around a placed chart; trim redundant spaces."""
    spaces = []
    for slot in available:
        if (slot.right <= used.x or used.right <= slot.x
                or slot.bottom <= used.y or used.bottom <= slot.y):
            spaces.append(slot)
            continue
        if slot.x < used.x:
            spaces.append(Box(slot.x, slot.y, used.x - slot.x, slot.h))
        if used.right < slot.right:
            spaces.append(Box(used.right, slot.y, slot.right - used.right, slot.h))
        if slot.y < used.y:
            spaces.append(Box(slot.x, slot.y, slot.w, used.y - slot.y))
        if used.bottom < slot.bottom:
            spaces.append(Box(slot.x, used.bottom, slot.w, slot.bottom - used.bottom))
    spaces = list(dict.fromkeys(spaces))
    return [s for s in spaces if not any(t != s and t.contains(s) for t in spaces)]


def _pack(bounds, scale):
    sizes = {name: (math.ceil((b[2] - b[0]) * scale) + 2 * PAD,
                    math.ceil((b[3] - b[1]) * scale) + LABEL + 2 * PAD)
             for name, b in bounds.items()}
    for name, (w, h) in list(sizes.items()):
        if name.endswith("_CROWN"):
            sizes[name] = (max(94, w), h)
    canvas = Box(MARGIN, TOP, WIDTH - 2 * MARGIN, HEIGHT - TOP - MARGIN)
    spaces = [canvas]
    placed = {}
    y = TOP
    for chart in MAJOR[:3]:
        box = Box(MARGIN, y, *sizes[chart])
        if not canvas.contains(box):
            return None
        placed[chart] = box
        spaces = _occupy(spaces, box)
        y = box.bottom

    long_side_end = max(box.right for box in placed.values())
    # Try both end elevations across the top of the right column and stacked.
    # The alternatives accommodate different shapes of auxiliary equipment.
    auxiliary = sorted(set(bounds) - set(MAJOR))
    for arrangement in ("row", "stack"):
        ends, slots = dict(placed), spaces.copy()
        x, y = long_side_end, TOP
        for chart in MAJOR[3:]:
            box = Box(x, y, *sizes[chart])
            if not any(s.contains(box) for s in slots):
                break
            ends[chart] = box
            slots = _occupy(slots, box)
            if arrangement == "row":
                x = box.right
            else:
                y = box.bottom
        else:
            for order in (lambda k: sizes[k][0] * sizes[k][1],
                          lambda k: max(sizes[k]), lambda k: sizes[k][0]):
                layout, remaining = dict(ends), slots.copy()
                for chart in sorted(auxiliary, key=order, reverse=True):
                    w, h = sizes[chart]
                    candidates = [s for s in remaining if s.w >= w and s.h >= h]
                    if not candidates:
                        break
                    slot = min(candidates, key=lambda s: (min(s.w - w, s.h - h),
                                                          s.y, s.x))
                    box = Box(slot.x, slot.y, w, h)
                    layout[chart] = box
                    remaining = _occupy(remaining, box)
                else:
                    return layout
    return None


def _layout(bounds):
    # Both elevations use the same longitudinal and vertical datum.
    a, b = bounds["LEFT"], bounds["RIGHT"]
    bounds["LEFT"] = bounds["RIGHT"] = [min(a[0], b[0]), min(a[1], b[1]),
                                         max(a[2], b[2]), max(a[3], b[3])]
    low, high = 1, 900
    while low < high:
        trial = (low + high + 1) // 2
        if _pack(bounds, trial):
            low = trial
        else:
            high = trial - 1
    layout = _pack(bounds, low)
    if layout is None:
        raise ValueError("塗装UVの島を配置できません")
    return low, layout


def _paint_polygons(obj):
    paint_slots = {i for i, slot in enumerate(obj.material_slots)
                   if slot.material and slot.material.name == "paint"}
    if not paint_slots:
        return []
    return [face for face in obj.data.polygons if face.material_index in paint_slots]


def _turn(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _separated(a, b):
    # Both triangles are counterclockwise. A separating edge may touch the
    # other triangle. Only shared area, however small, is an overlap.
    for i in range(3):
        start, end = a[i - 1], a[i]
        if all(_turn(start, end, point) <= 0 for point in b):
            return True
    return False


def _validate(triangles):
    # UVMap stores IEEE binary32 coordinates. A common power-of-two
    # denominator converts all of them exactly into integers. This makes the
    # orientation and shared-edge tests independent of float epsilons.
    scalars = {v for _, points in triangles for pt in points for v in pt}
    denominator = max(v.as_integer_ratio()[1] for v in scalars)
    exact = {v: int(v * denominator) for v in scalars}
    bins = defaultdict(list)
    records = []
    mins, maxs = [1.0, 1.0], [0.0, 0.0]
    for name, points in triangles:
        for point in points:
            for i, val in enumerate(point):
                if not 0 <= val <= 1:
                    raise ValueError(f"塗装UV範囲外 {name} {point}")
                mins[i] = min(mins[i], val)
                maxs[i] = max(maxs[i], val)
        p = tuple((exact[u], exact[v]) for u, v in points)
        area = _turn(*p)
        if area == 0:
            raise ValueError(f"塗装UV面積ゼロ {name} {points}")
        if area < 0:
            p = (p[0], p[2], p[1])
        xx, yy = zip(*p)
        x0, y0, x1, y1 = min(xx), min(yy), max(xx), max(yy)
        cells = [(x, y) for x in range(x0 * 96 // denominator, x1 * 96 // denominator + 1)
                 for y in range(y0 * 48 // denominator, y1 * 48 // denominator + 1)]
        for index in {i for cell in cells for i in bins[cell]}:
            old_name, q, a, b, c, d = records[index]
            if x1 <= a or c <= x0 or y1 <= b or d <= y0:
                continue
            if not (_separated(p, q) or _separated(q, p)):
                raise ValueError(f"塗装UV重なり: {old_name} / {name}. UV {points}")
        for cell in cells:
            bins[cell].append(len(records))
        records.append((name, p, x0, y0, x1, y1))
    return mins, maxs


def _develop_ribbon(mesh, faces, bottom):
    """Unfold one short shoulder ribbon exactly by its measured triangle edges."""
    import numpy as np
    from collections import deque
    faces = {face.index for face in faces}
    tris = [tri for tri in mesh.loop_triangles if tri.polygon_index in faces]
    original = {}
    layer = mesh.uv_layers.active.data
    for tri in tris:
        for vi, li in zip(tri.vertices, tri.loops):
            original[vi] = np.asarray(tuple(layer[li].uv))
    xyz = {vi: np.asarray(tuple(mesh.vertices[vi].co)) for vi in original}
    edges = defaultdict(list)
    for i, tri in enumerate(tris):
        a,b,c = tri.vertices
        for v,w in ((a,b),(b,c),(c,a)):
            edges[tuple(sorted((v,w)))].append(i)
    a, b, _ = tris[0].vertices
    pos = {a: np.array([0.,0.]), b: np.array([np.linalg.norm(xyz[b]-xyz[a]),0.])}
    queue, seen = deque([0]), set()
    while queue:
        i = queue.popleft()
        if i in seen:
            continue
        seen.add(i)
        vertices = tris[i].vertices
        known = [v for v in vertices if v in pos]
        unknown = [v for v in vertices if v not in pos]
        if unknown:
            a,b = known
            c, = unknown
            d = xyz[b] - xyz[a]
            span = np.linalg.norm(d)
            along = np.dot(xyz[c]-xyz[a], d) / span
            across = np.linalg.norm(np.cross(d, xyz[c]-xyz[a])) / span
            e = (pos[b] - pos[a]) / span
            orientation = 1 if _turn(original[a],original[b],original[c]) > 0 else -1
            pos[c] = pos[a] + along*e + orientation*across*np.array([-e[1],e[0]])
        a,b,c = vertices
        for edge in ((a,b),(b,c),(c,a)):
            queue.extend(n for n in edges[tuple(sorted(edge))] if n not in seen)
    if len(seen) != len(tris):
        raise ValueError("上角のUV小帯が途中で切れています")
    # Align the developed piece to the station-height drawing, with no scale.
    keys = list(pos)
    source = np.array([pos[v] for v in keys])
    target = np.array([original[v] for v in keys])
    source -= source.mean(axis=0)
    target -= target.mean(axis=0)
    u,_,v = np.linalg.svd(source.T @ target)
    developed = source @ (u @ v)
    developed -= developed.min(axis=0)
    developed[:,1] += bottom
    coords = dict(zip(keys, developed))
    for tri in tris:
        for vi,li in zip(tri.vertices,tri.loops):
            layer[li].uv = coords[vi]
    return float(developed[:,1].max())


def _chart_sections(obj, chart, faces):
    """Keep the waist continuous; cut only the tight shoulder above the glazing."""
    if chart == "AUX_HVAC":
        # The long constant extrusion keeps one measurable continuous chart.
        # Unfold each cap lengthwise between adjacent ribs. The notch introduces
        # curvature in both directions, so the narrow pieces need relief cuts.
        mesh = obj.data
        mesh.calc_loop_triangles()
        layer = mesh.uv_layers.active.data
        stations = sorted({v.co.y for v in mesh.vertices})
        lo, hi = max(zip(stations, stations[1:]), key=lambda pair: pair[1]-pair[0])
        sections = {chart: []}
        caps = defaultdict(lambda: defaultdict(list))
        for face in faces:
            y = face.center.y
            if lo < y < hi:
                sections[chart].append(face)
            else:
                cap = "AUX_HVAC_FRONT" if y > hi else "AUX_HVAC_REAR"
                rib = min(layer[i].uv.y for i in face.loop_indices)
                caps[cap][rib].append(face)
        for cap, strips in caps.items():
            bottom = 0.
            sections[cap] = []
            for rib, strip in sorted(strips.items()):
                bottom = _develop_ribbon(mesh, strip, bottom) + .021
                sections[cap].extend(strip)
        return sections
    if chart not in ("LEFT","RIGHT"):
        return {chart: faces}
    mesh = obj.data
    layer = mesh.uv_layers.active.data
    body, corners = [], defaultdict(lambda: defaultdict(list))
    for face in faces:
        loops = face.loop_indices
        xyz = [mesh.vertices[mesh.loops[i].vertex_index].co for i in loops]
        station = [layer[i].uv.x for i in loops]
        curved = any(abs(u+p.y) > 2e-5 for p,u in zip(xyz,station))
        if not curved or min(layer[i].uv.y for i in loops) < 2.49:
            body.append(face)
            continue
        end = "FRONT" if xyz[0].y > 0 else "REAR"
        column = (round(min(station),5), round(max(station),5))
        corners[end][column].append(face)
    sections = {chart: body}
    mesh.calc_loop_triangles()
    for end, columns in corners.items():
        # Each angular column uses the same height sections. Corresponding
        # ranks form a single horizontal ribbon running around the corner.
        ordered = [sorted(items, key=lambda f: f.center.z) for items in columns.values()]
        if len({len(column) for column in ordered}) != 1:
            raise ValueError(f"上角の水平列を特定できません: {obj.name} {end}")
        bottom = 0.0
        cap = []
        for row in zip(*ordered):
            bottom = _develop_ribbon(mesh,row,bottom) + .030
            cap.extend(row)
        sections[f"AUX_{chart}_{end}_CROWN"] = cap
    return sections


def _unroll_curved_ends(obj, chart, faces):
    """Develop the rounded ends while locking the straight part of each chart.

    The input station/height coordinates preserve the painter's datum. On
    a tapered three-dimensional end, one longitudinal profile cannot describe
    all heights. Local/global ARAP fits the planar triangles to their actual
    edge lengths; straight side panels, their door cutouts and the constant
    central cross-sections stay pinned to the supplied metric coordinates.
    """
    if chart == "FRONT":
        # Developed width follows each curved row. The measured shoulder also
        # lowers the outer ends of those rows above the glazing.
        mesh = obj.data
        layer = mesh.uv_layers.active.data
        for face in faces:
            for i in face.loop_indices:
                vertex = mesh.vertices[mesh.loops[i].vertex_index]
                layer[i].uv.y = vertex.co.z + (.003 if obj.name=='FrontCantrail' else 0.)
        return
    if chart == "REAR":
        # The upper glazing is slightly narrower than the belt-line; apply
        # the physical width at each row, including all separate apertures.
        mesh = obj.data
        layer = mesh.uv_layers.active.data
        for face in faces:
            for i in face.loop_indices:
                vertex = mesh.vertices[mesh.loops[i].vertex_index]
                layer[i].uv = (vertex.co.x, vertex.co.z)
        return
    if chart not in ("LEFT", "RIGHT", "ROOF"):
        return
    import numpy as np
    mesh = obj.data
    layer = mesh.uv_layers.active.data
    mesh.calc_loop_triangles()
    face_ids = {f.index for f in faces}
    by_loop, by_corner, vertices, uv = {}, {}, [], []
    for face in faces:
        for i in face.loop_indices:
            vi = mesh.loops[i].vertex_index
            point = tuple(layer[i].uv)
            key = (vi, point)
            if key not in by_corner:
                by_corner[key] = len(uv)
                uv.append(point)
                vertices.append(tuple(mesh.vertices[vi].co))
            by_loop[i] = by_corner[key]
    xyz, xy = np.asarray(vertices), np.asarray(uv)
    if chart in ("LEFT", "RIGHT"):
        pin = np.abs(xyz[:, 1] + xy[:, 0]) < 2e-6
        # Develop the continuous gutter radius in height. The lower paint
        # band and windows retain their actual elevation and station datum.
        from build_exterior import outer_x
        from coach_profile import shaped_point
        # The upper side is more upright at midships. Develop the transverse
        # curve at each actual station, to keep a metre on the curved shoulder
        # a metre on the UV sheet even near the more tapered front and rear.
        sign = -1 if chart=='LEFT' else 1
        for station in np.unique(xyz[:,1]):
            ix = np.where((xyz[:,1]==station) & (xy[:,1]>2.53))[0]
            if not ix.size:
                continue
            heights = np.unique(np.r_[np.linspace(2.53,2.80,40),2.59,2.66,xy[ix,1]])
            profile = np.asarray([shaped_point(sign*outer_x(z), station, z) for z in heights])
            arc = heights[0]+np.r_[0.,np.cumsum(np.linalg.norm(np.diff(profile,axis=0),axis=1))]
            xy[ix,1] = np.interp(xy[ix,1],heights,arc)
    else:
        y = xyz[:, 1]
        length = np.ptp(y)
        pin = (y >= y.min() + .24 * length) & (y <= y.max() - .24 * length)
    if pin.all() or pin.sum() < 2:
        return
    tri = np.asarray([[by_loop[i] for i in t.loops] for t in mesh.loop_triangles
                      if t.polygon_index in face_ids])
    # Reduce the system to triangles touching an adjustable vertex.
    tri = tri[~pin[tri].all(axis=1)]
    edge = xyz[tri[:, 1:]] - xyz[tri[:, :1]]
    base = np.linalg.norm(edge[:, 0], axis=1)
    area2 = np.linalg.norm(np.cross(edge[:, 0], edge[:, 1]), axis=1)
    if (area2 < 1e-12).any():
        raise ValueError(f"展開できない立体面: {obj.name}")
    uv_edge = xy[tri[:, 1:]] - xy[tri[:, :1]]
    sign = np.sign(np.linalg.det(uv_edge))
    rest = np.zeros((len(tri), 2, 2))
    rest[:, 0, 0] = base
    rest[:, 1, 0] = np.sum(edge[:, 0] * edge[:, 1], axis=1) / base
    rest[:, 1, 1] = area2 / base * sign
    basis = np.linalg.inv(rest) @ np.array([[-1., 1., 0.], [-1., 0., 1.]])
    # Remap only participating vertices into the linear system. Body sheets
    # contain many fine wheel-arch segments whose UVs never move.
    active, index = np.unique(tri, return_inverse=True)
    t = index.reshape(tri.shape)
    fixed = pin[active]
    q = xy[active].copy()
    weights = np.ones(len(tri))
    best_score, best = math.inf, q.copy()
    for iteration in range(10):
        adjoint = basis.transpose(0, 2, 1) * (area2 * weights)[:, None, None]
        local = adjoint @ basis
        k = np.zeros((len(active), len(active)))
        np.add.at(k, (t[:, :, None], t[:, None, :]), local)
        inv = np.linalg.inv(k[~fixed][:, ~fixed])
        constraint = k[~fixed][:, fixed] @ q[fixed]
        for _ in range(120):
            jacobian = basis @ q[t]
            c = jacobian[:, 0, 0] + jacobian[:, 1, 1]
            s = jacobian[:, 1, 0] - jacobian[:, 0, 1]
            length = np.hypot(c, s)
            rotation = np.stack([c, -s, s, c], axis=1).reshape(-1, 2, 2) / length[:, None, None]
            rhs = np.zeros_like(q)
            np.add.at(rhs, t, adjoint @ rotation)
            updated = inv @ (rhs[~fixed] - constraint)
            delta = np.max(np.abs(updated - q[~fixed]))
            q[~fixed] = updated
            if delta < 1e-8:
                break
        singular = np.linalg.svd(basis @ q[t], compute_uv=False)
        strain = np.maximum(singular[:, 0], 1.0 / singular[:, 1]) - 1.0
        if strain.max() < best_score:
            best_score = float(strain.max())
            best = q.copy()
        # Weight the locally worst triangles more heavily on the next pass:
        # the very small pressed corners would disappear in an area average.
        weights *= 1 + np.minimum(strain / .025, 12)
        weights /= weights.mean()
    xy[active] = best
    for i, idx in by_loop.items():
        layer[i].uv = xy[idx]


def measure_distortion(root, scale):
    """Compare lengths in the stored UV map with the 3D surface, per triangle."""
    import numpy as np
    records = defaultdict(list)
    for obj in root.children_recursive:
        if obj.type != "MESH":
            continue
        face_ids = {p.index for p in _paint_polygons(obj)}
        if not face_ids:
            continue
        mesh = obj.data
        mesh.calc_loop_triangles()
        tris = [t for t in mesh.loop_triangles if t.polygon_index in face_ids]
        xyz = np.array([tuple(obj.matrix_world @ v.co) for v in mesh.vertices])
        uv = np.array([tuple(entry.uv) for entry in mesh.uv_layers.active.data])
        points = xyz[np.array([tuple(t.vertices) for t in tris])]
        tex = uv[np.array([tuple(t.loops) for t in tris])] * [WIDTH / scale, HEIGHT / scale]
        dp, dq = points[:, 1:] - points[:, :1], tex[:, 1:] - tex[:, :1]
        s = np.linalg.svd(np.linalg.solve(dq, dp), compute_uv=False)
        length_factor = np.maximum(s[:, 0], 1.0 / s[:, 1])
        area = np.linalg.norm(np.cross(dp[:, 0], dp[:, 1]), axis=1) * .5
        records[obj["chart"]].append(np.column_stack((length_factor, s[:, 0] / s[:, 1], area)))
    summary = {}
    for chart, entries in records.items():
        factors, aspect, area = np.concatenate(entries).T
        summary[chart] = {"max_length_factor": float(factors.max()),
                          "max_axes_ratio": float(aspect.max()),
                          "area_m2": float(area.sum()),
                          "area_over_5pct_m2": float(area[factors > 1.05].sum()),
                          "area_over_10pct_m2": float(area[factors > 1.10].sum())}
    return summary


def finish(root, outdir):
    """Normalise prepared paint UVs in place. Return verified atlas statistics."""
    bounds, groups = {}, {}
    for obj in sorted(root.children_recursive, key=lambda item: item.name):
        if obj.type != "MESH":
            continue
        faces = _paint_polygons(obj)
        if not faces:
            continue
        chart = obj.get("chart", "")
        if chart not in MAJOR and not chart.startswith("AUX"):
            raise ValueError(f"UV島の指定がありません: {obj.name} {chart!r}")
        uv = obj.data.uv_layers.active
        if uv is None:
            raise ValueError(f"UVがありません: {obj.name}")
        for chart, faces in _chart_sections(obj, chart, faces).items():
            _unroll_curved_ends(obj, chart, faces)
            box = bounds.setdefault(chart, [math.inf, math.inf, -math.inf, -math.inf])
            for face in faces:
                for idx in face.loop_indices:
                    x, y = uv.data[idx].uv
                    if not math.isfinite(x) or not math.isfinite(y):
                        raise ValueError(f"無効なUV座標 {obj.name} face {face.index}")
                    box[0], box[1] = min(box[0], x), min(box[1], y)
                    box[2], box[3] = max(box[2], x), max(box[3], y)
            groups[obj,chart] = {p.index for p in faces}
    missing = set(MAJOR) - bounds.keys()
    if missing:
        raise ValueError(f"主要な塗装島がありません: {sorted(missing)}")
    scale, layout = _layout(bounds)
    triangles, outlines = [], defaultdict(list)
    draw = {k: {"box": list(vars(v).values()), "triangles": []} for k, v in layout.items()}
    for (obj, chart), indices in groups.items():
        box, limits = layout[chart], bounds[chart]
        mesh = obj.data
        layer = mesh.uv_layers.active.data
        boundary = defaultdict(int)
        for index in indices:
            loop_ids = mesh.polygons[index].loop_indices
            for idx in loop_ids:
                x, y = layer[idx].uv
                pixel_x = box.x + PAD + (x - limits[0]) * scale
                pixel_y = box.y + LABEL + PAD + (limits[3] - y) * scale
                layer[idx].uv = (pixel_x / WIDTH, 1.0 - pixel_y / HEIGHT)
            for i, idx in enumerate(loop_ids):
                endpoints = tuple(sorted((tuple(layer[loop_ids[i - 1]].uv), tuple(layer[idx].uv))))
                boundary[endpoints] += 1
        for (a, b), count in boundary.items():
            if count == 1:
                outlines[chart].append([_pixels(a), _pixels(b)])
        mesh.calc_loop_triangles()
        for tri in mesh.loop_triangles:
            if tri.polygon_index not in indices:
                continue
            points = tuple(tuple(layer[idx].uv) for idx in tri.loops)
            triangles.append((f"{obj.name} face {tri.polygon_index}", points))
            draw[chart]["triangles"].append([_pixels(p) for p in points])
    minimum, maximum = _validate(triangles)
    for chart in draw:
        draw[chart]["edges"] = outlines[chart]
    payload = {"charts": draw, "scale": scale}
    subprocess.run(["/usr/bin/python3", __file__, "--draw", str(Path(outdir) / "uv_paint_layout.png")],
                   input=json.dumps(payload).encode(), check=True)
    return {"px_per_m": scale, "paint_faces": sum(map(len, groups.values())),
            "paint_triangles": len(triangles), "paint_charts": len(bounds),
            "uv_min": minimum, "uv_max": maximum, "distortion": measure_distortion(root, scale)}


def _pixels(point):
    return (round(point[0] * WIDTH, 4), round((1 - point[1]) * HEIGHT, 4))


def _draw_guide(path):
    import unicodedata
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    data = json.load(sys.stdin)
    base = Image.new("RGBA", (WIDTH, HEIGHT))
    canvas = ImageDraw.Draw(base)
    fonts = list(Path("/System/Library/Fonts").glob("*.ttc"))

    def font(weight, size):
        name = f"ヒラギノ角ゴシック W{weight}"
        source = next(p for p in fonts if unicodedata.normalize("NFC", p.stem) == name)
        return ImageFont.truetype(str(source), size)

    normal, bold, title = font(3, 18), font(6, 20), font(6, 31)
    ink = (31, 50, 58, 255)
    canvas.rectangle((0, 0, WIDTH, 62), fill=(240, 245, 244, 255))
    canvas.text((MARGIN, 27), "神奈中 エルガ N尺   ／   塗装 UV 配置図", font=title, fill=ink, anchor="lm")
    scale = data["scale"]
    x_end = WIDTH - MARGIN
    canvas.text((x_end - scale - 18, 30), f"1 m   ·   {scale} px", font=normal, anchor="rm", fill=ink)
    canvas.line((x_end - scale, 31, x_end, 31), fill=ink, width=2)
    for x in (x_end - scale, x_end):
        canvas.line((x, 23, x, 39), fill=ink, width=2)

    names = {"LEFT": "左側面・前", "RIGHT": "右側面・前", "FRONT": "前面",
             "REAR": "後面", "ROOF": "屋根・前", "AUX_HVAC": "冷房中央・前",
             "AUX_HVAC_FRONT": "冷房前端", "AUX_HVAC_REAR": "冷房後端"}
    for side, jp_side in (("LEFT","左"),("RIGHT","右")):
        for end, jp_end in (("FRONT","前"),("REAR","後")):
            names[f"AUX_{side}_{end}_CROWN"] = jp_side + jp_end + "肩"
    colors = {"LEFT": (55, 116, 135), "RIGHT": (56, 105, 119), "FRONT": (146, 94, 57),
              "REAR": (124, 82, 50), "ROOF": (94, 109, 76)}
    auxiliary = {key: i + 1 for i, key in enumerate(sorted(set(data["charts"]) - set(MAJOR)))}
    for chart, content in data["charts"].items():
        x, y, w, h = content["box"]
        # An oversampled local mask preserves holes and draws the outline
        # of the true islands without leaving triangle diagonals in the guide.
        factor = 2
        mask = Image.new("L", (w * factor, h * factor))
        painter = ImageDraw.Draw(mask)
        def local(point):
            return (round((point[0] - x) * factor), round((point[1] - y) * factor))
        for tri in content["triangles"]:
            painter.polygon([local(pt) for pt in tri], fill=255)
        rim = mask.filter(ImageFilter.MaxFilter(5))
        rgb = colors.get(chart, (97, 99, 106))
        outline = Image.new("RGBA", mask.size, (*rgb, 255))
        outline.putalpha(rim)
        fill = Image.new("RGBA", mask.size, tuple(round(.17 * v + .83 * 255) for v in rgb) + (255,))
        outline.paste(fill, mask=mask)
        pen = ImageDraw.Draw(outline)
        for a, b in content["edges"]:
            pen.line((local(a), local(b)), fill=(*rgb, 255), width=2)
        base.alpha_composite(outline.resize((w, h), Image.Resampling.LANCZOS), (x, y))

        label = names.get(chart)
        if not label:
            number = f"補助{auxiliary[chart]}"
            detail = chart[3:].strip(" _-").replace("_", " ")
            full_label = f"{number}  {detail}" if detail else number
            label = full_label if canvas.textlength(full_label, font=bold) + 16 <= w else number
            if canvas.textlength(label, font=bold) + 16 > w:
                continue

        def tag(at, text, right=False):
            width = math.ceil(canvas.textlength(text, font=bold))
            if right:
                at -= width + 16
            canvas.rounded_rectangle((at, y + 1, at + width + 15, y + LABEL),
                                     radius=4, fill=(*rgb, 255))
            canvas.text((at + 8, y + LABEL / 2 + 1), text, fill="white",
                        font=bold, anchor="lm")
        tag(x + PAD, label)
        if chart in ("LEFT", "RIGHT", "ROOF", "AUX_HVAC"):
            tag(x + w - PAD, "後", right=True)
    base.save(path, optimize=True)


if __name__ == "__main__" and sys.argv[1:2] == ["--draw"]:
    _draw_guide(sys.argv[2])
