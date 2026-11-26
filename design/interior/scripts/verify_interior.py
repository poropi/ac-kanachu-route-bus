"""Blender background verifier; neither input scene is saved.

blender -b --factory-startup --python-exit-code 1 --python verify_interior.py
Append -- --self-test for an in-memory check of the geometric tests.
"""
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

OUT = Path(__file__).resolve().parent.parent
INTERIOR = OUT / "kanachu_interior.blend"
EXTERIOR = OUT.parent / "exterior" / "kanachu_exterior.blend"
COPLANAR_TOL = 0.000001  # 0.001 mm plane separation
TOL = 0.00001  # 0.01 mm, for point-side/containment queries only
ANIM = ("STEER_HR", "ARROW_SPEED", "ARROW_RPM")
RESERVED = ("WHEEL_", "SUSP_", "STEER_", "ARROW_")


@dataclass
class Surface:
    name: str
    points: np.ndarray
    triangles: np.ndarray
    tree: BVHTree
    lo: np.ndarray
    hi: np.ndarray
    closed: bool

    @classmethod
    def create(cls, name, points, triangles):
        points = np.asarray(points, dtype=float)
        triangles = np.asarray(triangles, dtype=int)
        # Account for split UV seams / face corners when identifying closed solids.
        _, welded = np.unique(points.round(7), axis=0, return_inverse=True)
        tri = welded[triangles]
        edges = np.concatenate([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
        _, counts = np.unique(np.sort(edges, axis=1), axis=0, return_counts=True)
        tree = BVHTree.FromPolygons(points.tolist(), triangles.tolist(), all_triangles=True)
        return cls(name, points, triangles, tree, points.min(0), points.max(0), bool(np.all(counts == 2)))

    @classmethod
    def from_object(cls, obj, depsgraph):
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            return cls.create(obj.name, [evaluated.matrix_world @ v.co for v in mesh.vertices],
                              [t.vertices[:] for t in mesh.loop_triangles])
        finally:
            evaluated.to_mesh_clear()


def envelope_surface(exterior):
    # Major shell only. Trim, mirrors, seats and underfloor auxiliaries cannot
    # masquerade as the boundary. Door frames cover the holes around the glass.
    prefixes = ("Left_Coachwork", "Right_Coachwork", "Left_Window_", "Right_Window_",
                "Windshield", "RearWindow", "FrontBrow", "FrontCantrail", "RearCantrail",
                "DestinationMaskFront", "DOOR_", "Entrance_", "Sliding_", "FrontBumper",
                "RearBumper", "NosePanel", "EngineCoverPanel", "Crowned_Roof")
    pieces = [p for p in exterior if p.name.startswith(prefixes)]
    return pieces


def union_tree(pieces):
    points, triangles = [], []
    for piece in pieces:
        triangles.extend((piece.triangles + len(points)).tolist())
        points.extend(piece.points.tolist())
    return BVHTree.FromPolygons(points, triangles, all_triangles=True)


def hull_check(interior, shell):
    """A globally bounded test also covers detached parts beyond every ray."""
    vertices = np.unique(np.concatenate([s.points for s in shell]).round(7), axis=0)
    bm = bmesh.new()
    try:
        verts = [bm.verts.new(co) for co in vertices]
        hull = bmesh.ops.convex_hull(bm, input=verts)
        bm.normal_update()
        center = vertices.mean(0)
        boundaries = []
        for face in hull["geom"]:
            if not isinstance(face, bmesh.types.BMFace):
                continue
            n, point = np.array(face.normal), np.array(face.verts[0].co)
            if np.dot(n, center - point) > 0:
                n = -n
            # Use the actual support of the contributing shell vertices. Tiny
            # near-coplanar triangles can otherwise tilt a hull plane in float32.
            boundaries.append(n)
    finally:
        bm.free()
    normals = np.unique(np.round(boundaries, 6), axis=0)
    support = np.array([np.max(vertices @ n) for n in normals])
    outside = []
    for part in interior:
        worst, where = 0, None
        for start in range(0, len(part.points), 1024):
            points = part.points[start:start+1024]
            excess = points @ normals.T - support
            row, col = np.unravel_index(excess.argmax(), excess.shape)
            if excess[row,col] > worst:
                worst, where = float(excess[row,col]), points[row].tolist()
        if worst > TOL:
            outside.append({"mesh":part.name,"point":where,"outside_m":worst})
    return {"shell_normal_directions":len(normals),"outside":outside}


def envelope_check(interior, skin, bottom):
    """At every distinct mesh vertex, compare against the shell along 4 axes."""
    misses = Counter()
    tested = Counter()
    minimum = {}
    failures = {}
    for piece in interior:
        for x, y, z in np.unique(piece.points, axis=0):
            sx, sy = (1 if x >= 0 else -1), (1 if y >= 0 else -1)
            # Rays start outside, to avoid taking an air gap for an escape.
            rays = (("side", skin, (3*sx, y, z), (-sx, 0, 0), 0, sx),
                    ("end", skin, (x, 8*sy, z), (0, -sy, 0), 1, sy),
                    ("roof", skin, (x, y, 5), (0, 0, -1), 2, 1),
                    ("underside", bottom, (x, y, -2), (0, 0, 1), 2, -1))
            pos = (x, y, z)
            for label, tree, origin, direction, axis, sign in rays:
                hit = tree.ray_cast(origin, direction)[0]
                # Reject a hit on the *opposite* side through an unclosed gap.
                if hit is None or (axis in (0, 1) and hit[axis]*sign <= 0):
                    misses[label] += 1
                    continue
                tested[label] += 1
                distance = (hit[axis] - pos[axis]) * sign
                if label not in minimum or distance < minimum[label]["distance_m"]:
                    minimum[label] = {"distance_m": float(distance), "mesh": piece.name,
                                      "point": list(pos)}
                if distance < -TOL:
                    key = (piece.name, label)
                    if key not in failures or distance < failures[key]["distance_m"]:
                        failures[key] = {"mesh": piece.name, "side": label,
                                         "distance_m": float(distance), "point": list(pos)}
    return {"rays_with_boundary": dict(tested), "rays_without_boundary": dict(misses),
            "minimum_axis_clearance": minimum, "outside": list(failures.values())}


def inside(tree, point):
    """Majority parity in 3 oblique directions, excluding numerical skin contact."""
    if tree.find_nearest(point, TOL)[0] is not None:
        return False
    votes = 0
    for delta in ((.83, .47, .3), (-.39, .87, -.29), (.41, -.51, .75)):
        direction = Vector(delta).normalized()
        origin = Vector(point)
        hits = 0
        while True:
            loc = tree.ray_cast(origin, direction)[0]
            if loc is None:
                break
            hits += 1
            origin = loc + direction * (TOL / 4)
        votes += hits % 2
    return votes >= 2


def contained_point(candidate, solid):
    if not solid.closed:
        return None
    mask = ((candidate.points > solid.lo + TOL) & (candidate.points < solid.hi - TOL)).all(axis=1)
    for point in candidate.points[mask]:
        if inside(solid.tree, point):
            return point.tolist()
    return None


def coplanar_overlap(a, b):
    """BVHTree.overlap ignores coplanar triangles; test projected area separately."""
    lo = np.maximum(a.lo, b.lo) - COPLANAR_TOL
    hi = np.minimum(a.hi, b.hi) + COPLANAR_TOL

    def candidates(surface):
        tri = surface.points[surface.triangles]
        selected = np.flatnonzero(((tri.max(1) >= lo) & (tri.min(1) <= hi)).all(1))
        return selected,tri[selected]

    ia, first = candidates(a)
    ib, second = candidates(b)
    if not len(ia) or not len(ib):
        return None
    low, high = second.min(1), second.max(1)
    for index, tri in zip(ia, first):
        mask = ((low <= tri.max(0) + COPLANAR_TOL) & (high >= tri.min(0) - COPLANAR_TOL)).all(1)
        if not mask.any():
            continue
        normal = np.cross(tri[1]-tri[0],tri[2]-tri[0])
        length = np.linalg.norm(normal)
        if length < 1e-14:
            continue
        normal /= length
        ids = np.flatnonzero(mask)
        # Check every vertex, not just coincident pair(s) along a shared edge.
        distance = np.max(np.abs((second[ids]-tri[0]) @ normal),axis=1)
        for j in ids[distance <= COPLANAR_TOL]:
            other = second[j]
            other_n = np.cross(other[1]-other[0],other[2]-other[0])
            if abs(np.dot(normal,other_n)) < np.linalg.norm(other_n)*(1-1e-8):
                continue
            axis = np.argmax(np.abs(normal))
            t,u = np.delete(tri,axis,axis=1),np.delete(other,axis,axis=1)
            edges = np.concatenate((np.roll(t,-1,axis=0)-t, np.roll(u,-1,axis=0)-u))
            separating = np.column_stack((-edges[:,1],edges[:,0]))
            p,q = t @ separating.T,u @ separating.T
            common = np.minimum(p.max(0),q.max(0)) - np.maximum(p.min(0),q.min(0))
            if np.all(common > 1e-9*np.linalg.norm(separating,axis=1)):
                return {"interior":a.name,"exterior":b.name,"interior_triangle":int(index),
                        "exterior_triangle":int(ib[j]),"first_interior_triangle_m":tri.tolist(),
                        "first_exterior_triangle_m":other.tolist()}
    return None


def collision_check(interior, exterior):
    crossings, coplanar, containment = [], [], []
    candidates = 0
    for a in interior:
        for b in exterior:
            if np.any(a.hi + COPLANAR_TOL < b.lo) or np.any(b.hi + COPLANAR_TOL < a.lo):
                continue
            candidates += 1
            hits = a.tree.overlap(b.tree)
            if hits:
                ia, ib = hits[0]
                crossings.append({"interior": a.name, "exterior": b.name, "triangle_pairs": len(hits),
                                  "first_interior_triangle_m": a.points[a.triangles[ia]].tolist(),
                                  "first_exterior_triangle_m": b.points[b.triangles[ib]].tolist()})
                continue
            flat = coplanar_overlap(a,b)
            if flat is not None:
                coplanar.append(flat)
                continue
            for part, solid in ((a, b), (b, a)):
                point = contained_point(part, solid)
                if point is not None:
                    containment.append({"mesh": part.name, "inside_closed_mesh": solid.name, "point": point})
    return {"interior_meshes": len(interior), "exterior_meshes": len(exterior),
            "all_object_pairs": len(interior)*len(exterior), "aabb_candidates": candidates,
            "crossing_pairs": crossings, "coplanar_pairs": coplanar, "contained_pairs": containment}


def gauge_frames(mesh, surface):
    """Find the actual dial origin and its U/right, V/up basis in the saved UVs."""
    if not mesh.uv_layers.active:
        return {}
    slots = {}
    for i, material in enumerate(mesh.materials):
        if not material or not material.node_tree:
            continue
        for node in material.node_tree.nodes:
            image = getattr(node, "image", None)
            if not image:
                continue
            stem = Path(image.filepath).stem.lower()
            if stem in ("speed", "rpm"):
                slots[i] = "ARROW_" + stem.upper()
    if not slots:
        return {}
    result = {}
    uv = mesh.uv_layers.active.data
    for i, tri in enumerate(mesh.loop_triangles):
        name = slots.get(tri.material_index)
        if not name or name in result:
            continue
        st = np.array([uv[loop].uv[:] for loop in tri.loops])
        delta = st[1:] - st[0]
        if abs(np.linalg.det(delta)) < 1e-12:
            continue
        weights = np.linalg.solve(delta.T,[.5-st[0,0], .5-st[0,1]])
        if min(weights) < -1e-5 or sum(weights) > 1+1e-5:
            continue
        xyz = surface.points[surface.triangles[i]]
        tangents = np.linalg.solve(delta,xyz[1:]-xyz[0])
        u,v = [d/np.linalg.norm(d) for d in tangents]
        n = np.cross(u,v)
        result[name] = (xyz[0] + weights @ (xyz[1:]-xyz[0]), u,v,n/np.linalg.norm(n))
    return result


def read_interior():
    bpy.ops.wm.open_mainfile(filepath=str(INTERIOR))
    objects = list(bpy.context.scene.objects)
    named = {o.name: o for o in objects}
    root = named.get("COCKPIT_HR")
    errors = []
    if root is None or root.type != "EMPTY" or root.parent or not np.allclose(root.matrix_world, np.identity(4), atol=1e-6):
        errors.append("COCKPIT_HR の種別・親・世界変換")
    members = set(root.children_recursive) if root else set()
    for obj in objects:
        if obj is not root and obj not in members:
            errors.append(f"COCKPIT_HR 階層外 {obj.name}")
        if obj.name.startswith(RESERVED) and obj.name not in ANIM:
            errors.append(f"予約名 {obj.name}")
    empties = {}
    for name in (*ANIM, "DRIVER_EYE"):
        obj = named.get(name)
        if not obj or obj.type != "EMPTY":
            errors.append(f"空オブジェクト不足 {name}")
            continue
        axis = (obj.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized()
        empties[name] = {"origin": list(obj.matrix_world.translation), "local_z_world": list(axis)}
        if name in ANIM:
            if not any(o.type == "MESH" for o in obj.children):
                errors.append(f"直下に可動メッシュなし {name}")
            if not np.allclose(obj.matrix_world.to_3x3().to_scale(), (1,1,1), atol=1e-5):
                errors.append(f"回転親の非単位スケール {name}")
    if "DRIVER_EYE" in empties and "STEER_HR" in empties:
        steer, eye = empties["STEER_HR"], np.array(empties["DRIVER_EYE"]["origin"])
        away = np.array(steer["origin"]) - eye
        if np.dot(away, steer["local_z_world"]) <= 0 or steer["local_z_world"][1] <= 0:
            errors.append("STEER_HR ローカルZの方向")
    graph = bpy.context.evaluated_depsgraph_get()
    meshes = [o for o in objects if o.type == "MESH"]
    surfaces = [Surface.from_object(o,graph) for o in meshes]
    by_name = {p.name:p for p in surfaces}
    for name in ANIM:
        if name not in empties:
            continue
        parts = [by_name[o.name].points for o in named[name].children_recursive if o.name in by_name]
        if not parts:
            continue
        points = np.concatenate(parts) - empties[name]["origin"]
        rotation = np.asarray(named[name].matrix_world.to_3x3().normalized())
        local = points @ rotation
        radii = np.linalg.norm(local[:,:2],axis=1)
        if name == "STEER_HR":
            rim = local[radii > radii.max()*.92]
            centre_xy = (rim[:,:2].min(0)+rim[:,:2].max(0))*.5
            normal = np.linalg.svd(rim-rim.mean(0), full_matrices=False)[2][-1]
            tilt = math.degrees(math.acos(min(1,abs(normal[2]))))
            empties[name].update(radius_m=float(radii.max()), rim_axis_error_deg=tilt,
                                  rim_box_center_offset_m=float(np.linalg.norm(centre_xy)))
            if tilt > 5 or np.linalg.norm(centre_xy) > radii.max()*.06:
                errors.append("リムの中心または面とSTEER_HRの軸が不一致")
        else:
            tip = local[radii > radii.max()-.0001].mean(0)
            normal = np.linalg.svd(local-local.mean(0), full_matrices=False)[2][-1]
            empties[name].update(radius_m=float(radii.max()),
                                local_tip_angle_deg_ccw_from_x=math.degrees(math.atan2(tip[1],tip[0])),
                                local_z_extent_m=float(np.ptp(local[:,2])),
                                best_fit_axis_delta_deg=math.degrees(math.acos(min(1,abs(normal[2])))))
            # The pointer must rotate in XY; hub detail may legitimately be thicker than its tip.
            if np.ptp(local[:,2]) >= radii.max()*.5:
                errors.append(f"針の面と親軸の不一致 {name}")
    uv_zero, spatial_zero, frames = {}, {}, {}
    for o, part in zip(meshes, surfaces):
        obj = o.evaluated_get(graph)
        mesh = obj.to_mesh()
        try:
            uv = mesh.uv_layers.active
            if uv is None:
                errors.append(f"UV なし {o.name}")
                continue
            mesh.calc_loop_triangles()
            frames.update(gauge_frames(mesh,part))
            uv_points = np.array([d.uv[:] for d in uv.data])
            uv_triangles = np.array([t.loops[:] for t in mesh.loop_triangles])
            if not np.isfinite(uv_points).all():
                errors.append(f"無限・未定義 UV {o.name}")
            f = uv_points[uv_triangles]
            a, b = f[:,1]-f[:,0],f[:,2]-f[:,0]
            n = int(np.count_nonzero(np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0]) < 1e-14))
            if n:
                uv_zero[o.name] = n
            f = part.points[part.triangles]
            n = int(np.count_nonzero(np.linalg.norm(np.cross(f[:,1]-f[:,0], f[:,2]-f[:,0]),axis=1)<1e-14))
            if n:
                spatial_zero[o.name] = n
            if not mesh.materials or any(m is None or not m.name.startswith("interior_") for m in mesh.materials):
                errors.append(f"材質割当 {o.name}")
        finally:
            obj.to_mesh_clear()
    for name in ("ARROW_SPEED","ARROW_RPM"):
        if name not in frames or name not in empties:
            continue
        center,u,v,normal = frames[name]
        pivot = empties[name]
        shift = np.array(pivot["origin"]) - center
        radial = np.hypot(shift@u, shift@v)
        axis_error = math.degrees(math.acos(min(1,abs(normal @ pivot["local_z_world"]))))
        piv = np.array(pivot["origin"])
        pts = np.concatenate([by_name[o.name].points for o in named[name].children_recursive
                              if o.name in by_name]) - piv
        planar = np.column_stack((pts @ u,pts @ v))
        lengths = np.linalg.norm(planar,axis=1)
        tip = planar[lengths > lengths.max()-.0001].mean(0)
        pivot.update(dial_center_world=center.tolist(), dial_center_offset_m=float(radial),
                     pointer_clearance_to_face_m=float(shift @ normal), axis_to_dial_normal_deg=axis_error,
                     pointer_angle_deg_clockwise_from_12=math.degrees(math.atan2(tip[0],tip[1])))
        if "DRIVER_EYE" in empties:
            eye = Vector(empties["DRIVER_EYE"]["origin"])
            samples = []
            for angle in range(0,360,45):
                tangent = u*math.cos(math.radians(angle)) + v*math.sin(math.radians(angle))
                point = Vector(center + tangent * .04)
                hit, loc, _, polygon, obj, _ = bpy.context.scene.ray_cast(graph, eye, (point-eye).normalized())
                material = (obj.data.materials[obj.data.polygons[polygon].material_index]
                            if hit and 0 <= polygon < len(obj.data.polygons) else None)
                nodes = material.node_tree.nodes if material and material.node_tree else []
                visible = any(Path(node.image.filepath).stem.lower() == name.removeprefix("ARROW_").lower()
                              for node in nodes if getattr(node,"image",None))
                samples.append({"angle":angle, "face_visible":visible, "first_surface":obj.name if hit else None,
                                "first_material":material.name if material else None})
            pivot["dial_view_from_eye"] = samples
            if not any(record["face_visible"] for record in samples):
                errors.append(f"運転手視点で計器盤面が8方向すべて隠れる {name}")
        if radial > .001 or axis_error > 1:
            errors.append(f"盤面のUV中心・法線と針が不一致 {name}")
    seats = sorted(o.name for o in meshes if re.fullmatch(r"PassengerSeat_\d+",o.name))
    if seats != [f"PassengerSeat_{i:02}" for i in range(1,28)]:
        errors.append(f"乗客席の識別メッシュ {len(seats)}")
    if uv_zero:
        errors.append("面積ゼロのUV三角形")
    if spatial_zero:
        errors.append("面積ゼロの三角形")
    triangles = sum(len(s.triangles) for s in surfaces)
    largest = max(surfaces, key=lambda s:len(s.points))
    if triangles > 150000 or len(largest.points)>60000:
        errors.append("メッシュ予算超過")
    materials = sorted(m.name for m in bpy.data.materials if any(m in o.data.materials[:] for o in meshes))
    textures = {i.name:bool(i.packed_files) for i in bpy.data.images
                if i.users and i.type not in ("RENDER_RESULT","COMPOSITING")}
    if not all(textures.values()):
        errors.append("未パック画像")
    return surfaces, {"errors":errors, "objects":len(objects), "meshes":len(meshes),
                      "triangles":triangles, "max_vertices":len(largest.points), "largest_mesh":largest.name,
                      "zero_uv_triangles":uv_zero, "zero_3d_triangles":spatial_zero, "seat_count":len(seats),
                      "pivots":empties, "materials":materials, "packed_textures":textures}


def main():
    inside_parts, asset = read_interior()
    bpy.ops.wm.open_mainfile(filepath=str(EXTERIOR))
    deps = bpy.context.evaluated_depsgraph_get()
    outside_parts = [Surface.from_object(o,deps) for o in bpy.context.scene.objects
                     if o.type == "MESH" and o.name != "INTERIOR_PLACEHOLDER"]
    collisions = collision_check(inside_parts, outside_parts)
    bottom = [s for s in outside_parts if 'Undertray' in s.name or s.name in
              ('Underfloor_Centre','Bumper_Splashshield','Bumper_Splashshield.001')]
    skin = envelope_surface(outside_parts)
    envelope = envelope_check(inside_parts, union_tree(skin), union_tree(bottom))
    hull = hull_check(inside_parts, skin + bottom)
    errors = asset["errors"]
    if (collisions["crossing_pairs"] or collisions["coplanar_pairs"] or collisions["contained_pairs"]
            or envelope["outside"] or hull["outside"]):
        errors.append("外装との交差・内包・車外頂点")
    result = {
        "passed":not errors, "blender":bpy.app.version_string,
        "sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (INTERIOR,EXTERIOR)},
        "boundary":"外装全メッシュ（INTERIOR_PLACEHOLDERを除く）。閉扉・直進姿勢。"
                   "評価済み世界座標の三角形BVH overlap、epsilon=0。"
                   "同一平面は別途2D投影の面積重複を判定（面間距離0.001 mm以内）。"
                   "閉じたメッシュ間の包含は両向きの頂点と3方向レイ多数決。"
                   "別途、全内装頂点を外殻の凸包および外板・ガラス・扉・屋根・床下板の実在面と4方向で比較。"
                   "点の内外判定の許容差0.01 mm。開口で境界を拾えないレイは方向別に記録。",
        "asset":asset,"exterior_intersections":collisions, "shell_envelope":envelope,"convex_hull":hull}
    output = OUT/"verification.json"
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(f"{output}: triangles={asset['triangles']} meshes={asset['meshes']} "
          f"crossings={len(collisions['crossing_pairs'])} enclosed={len(collisions['contained_pairs'])} "
          f"outside={len(envelope['outside'])} errors={errors}")
    if errors:
        raise RuntimeError("Interior verification failed; see verification.json")


def self_test():
    def box(name, lo, hi):
        points = [(x,y,z) for x in (lo,hi) for y in (lo,hi) for z in (lo,hi)]
        faces = [(0,1,3),(0,3,2),(4,6,7),(4,7,5),(0,4,5),(0,5,1),
                 (2,3,7),(2,7,6),(0,2,6),(0,6,4),(1,5,7),(1,7,3)]
        return Surface.create(name,points,faces)
    shell = box("shell",-1,1)
    occupied = box("part",.9,1.1)
    enclosed = box("contained",-.5,.5)
    clear = box("clear",1.5,1.6)
    patch = Surface.create("coplanar",[(1,.2,.3),(1,.25,.3),(1,.2,.35)],[(0,1,2)])
    assert collision_check([patch],[shell])["coplanar_pairs"]
    assert collision_check([occupied],[shell])["crossing_pairs"]
    assert collision_check([enclosed],[shell])["contained_pairs"]
    assert not collision_check([clear],[shell])["aabb_candidates"]
    assert hull_check([clear],[shell])["outside"]
    assert not hull_check([enclosed],[shell])["outside"]
    assert envelope_check([clear],shell.tree,shell.tree)["outside"] == []  # ray gaps in 3 directions
    beyond = Surface.create("side_escape",[(1.2,0,.4),(1.3,.05,.4),(1.2,0,.5)],[(0,1,2)])
    assert envelope_check([beyond],shell.tree,shell.tree)["outside"]
    assert not envelope_check([enclosed],shell.tree,shell.tree)["outside"]
    print("BVH crossing / whole-object containment / shell ray escape / inside controls: PASS")


if __name__ == "__main__":
    self_test() if "--self-test" in sys.argv else main()
