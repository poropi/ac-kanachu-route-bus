"""UV展開した白手袋。掌から指先まで連続した面で作る。"""
from math import cos, exp, pi, radians, sin, sqrt

import bmesh
import bpy
import numpy as np
from mathutils import Quaternion, Vector


SIDES = ("L", "R")
FINGERS = ("Pinkie", "Ring", "Middle", "Index", "Thumb")
KNUCKLES = {
    "Pinkie": (.071, -.0234, .054),
    "Ring":   (.075, -.0078, .068),
    "Middle": (.078,  .0078, .074),
    "Index":  (.076,  .0234, .069),
}


def hand_frame(side):
    """手首、指先向き、親指側、手の甲向き（アーマチュアのレスト座標）。"""
    sign = 1 if side == "L" else -1
    wrist = Vector((sign * .2875, -.006, (1487 - 728) * .00115))
    axis = Vector((.594, 0, -.805)).normalized()
    outer = Vector((-axis.z, 0, axis.x))
    thumb = Vector((0, .932, 0)) - .362 * outer
    back = .932 * outer + Vector((0, .362, 0))
    for v in (axis, thumb, back):
        v.x *= sign
    return wrist, axis, thumb.normalized(), back.normalized()


def position(side, s, w, d):
    wrist, axis, thumb, back = hand_frame(side)
    return wrist + s * axis + w * thumb + d * back


def bone_names(side, digit):
    if digit == "Thumb":
        return [f"DRIVER:HAND_{side}_Thumb{n}" for n in range(1, 4)]
    first = 1 if side == "L" else 4
    return [f"DRIVER:HAND_{digit}{n}" for n in range(first, first + 3)]


def finger_joints(digit):
    if digit == "Thumb":
        # 母指球から外へ開き、末節は掌側へ軽く倒す。
        return [(.038, .042, -.002), (.059, .052, -.010),
                (.080, .057, -.017), (.099, .059, -.022)]
    base, width, length = KNUCKLES[digit]
    return [(base + length * t, width * (1 + .26 * t), -.001 - .010 * t*t)
            for t in (0, .45, .74, 1)]


def hand_bones():
    bones = {}
    for side in SIDES:
        bones[f"DRIVER:RIG_HAND_{side}"] = (
            position(side, 0, 0, 0), position(side, .076, 0, -.001))
        for digit in FINGERS:
            joints = [position(side, *p) for p in finger_joints(digit)]
            for i, name in enumerate(bone_names(side, digit)):
                bones[name] = (joints[i], joints[i + 1])
    return bones


def grip_frame(side):
    """半径16 mmのリム中心、接線、掌の法線（レスト座標）。"""
    wrist, distal, thumb, dorsal = hand_frame(side)
    return (wrist + .069 * distal - .023 * dorsal,
            (thumb + .10 * distal - .055 * dorsal).normalized(), -dorsal)


def grip(arm):
    """レスト時の掌の幅軸を各指節のローカル座標へ移し、3節を個別に屈曲。"""
    # リム外面に指腹を添える角度。親指の対向と末節の屈曲は軸が異なる。
    settings = {
        "Thumb": ((61, 40, 20.5), (-19.5, -78, -78)),
        "Index": ((38, 72, 31), (8.5,) * 3),
        "Middle": ((45.5, 79, 27), (7,) * 3),
        "Ring": ((37, 77, 27), (6.5,) * 3),
        "Pinkie": ((27.5, 70, 15.5), (5.5,) * 3),
    }
    for side in SIDES:
        _, _, thumb_side, dorsum = hand_frame(side)
        for digit, (angles, planes) in settings.items():
            for name, angle, plane in zip(bone_names(side, digit), angles, planes):
                toward = -dorsum * cos(radians(plane)) + thumb_side * sin(radians(plane))
                pb = arm.pose.bones[name]
                direction = (pb.bone.tail_local - pb.bone.head_local).normalized()
                axis = direction.cross(toward).normalized()
                rest_rotation = pb.bone.matrix_local.to_quaternion()
                pb.rotation_mode = 'QUATERNION'
                pb.rotation_quaternion = Quaternion(rest_rotation.inverted() @ axis, radians(angle))


# 画像内の各領域には左右共通の手袋柄を一度だけ描く。
PANELS = {"back": (.03, .52, .47, .97), "palm": (.53, .52, .97, .97),
          "finger": (.03, .04, .64, .46), "edge": (.69, .04, .97, .46)}


def glove_material():
    n = 768
    y, x = np.mgrid[:n, :n].astype(np.float32) / (n - 1)
    rgb = np.zeros((n, n, 3), dtype=np.float32)
    base = np.array([.925, .911, .941], np.float32)
    ink = np.array([.73, .70, .79], np.float32)
    rgb[:] = base
    for part, (x0, y0, x1, y1) in PANELS.items():
        u, v = (x - x0) / (x1 - x0), (y - y0) / (y1 - y0)
        mask = (u >= -.025) & (u <= 1.025) & (v >= -.025) & (v <= 1.025)
        shade = np.zeros_like(u)
        if part in ("back", "palm"):
            # Rolled side seams tint the outside of the white cotton panels.
            shade += .32 * (np.abs(u - .5) * 2).clip(0, 1)**3
        if part == "back":
            # 三本の飾り縫い。手首では寄せ、指の付け根では広げる。
            envelope = np.clip(np.sin(np.clip((v-.21)/.61, 0, 1)*pi)*3, 0, 1)
            for offset in (-.215, 0, .215):
                line = .5 + offset * (.38 + .93 * v) + .03 * np.sin(v*pi)
                shade += envelope * .52 * np.exp(-((u-line)/.011)**2)
            shade += .12 * np.exp(-((v - .14 - .025*u)/.018)**2)
            shade += .10 * np.exp(-((v - .86 - .045*np.cos(u*pi*7))/.027)**2)
        elif part == "palm":
            for level, slope in ((.42, -.24), (.68, .19)):
                shade += .21 * np.exp(-((v-level-slope*(u-.5)-.08*(u-.5)**2)/.016)**2)
        elif part == "finger":
            # 指側面の接ぎ目と、指を曲げた時に見える掌側の関節のしわ。
            for boundary in (.38, .88):
                shade += .5 * np.exp(-((u-boundary)/.012)**2)
            for t in (.45, .74):
                shade += .28 * np.exp(-((v-t+.022*np.cos(2*pi*u))/.017)**2) * np.exp(-((u-.63)/.24)**2)
        if part in ("back", "palm", "edge"):
            shade += .48 * np.exp(-((v-.058)/.012)**2) + .22 * np.exp(-((v-.095)/.008)**2)
        weave = .003 * np.sin(2*pi*165*x) * np.sin(2*pi*160*y)
        paint = base + (ink-base) * np.clip(shade, 0, 1)[..., None] + weave[..., None]
        rgb[mask] = paint[mask]
    pixels = np.ones((n, n, 4), dtype=np.float32)
    # Non-float generated sRGB images accept encoded sRGB values through pixels.
    pixels[:, :, :3] = rgb
    image = bpy.data.images.new("driver_gloves_cotton.png", n, n, alpha=False)
    image.colorspace_settings.name = 'sRGB'
    image.pixels.foreach_set(pixels.ravel())
    image.pack()
    mat = bpy.data.materials.new("driver_gloves")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = .86
    shader.inputs["Specular IOR Level"].default_value = .18
    texture = nodes.new("ShaderNodeTexImage")
    texture.image = image
    mat.node_tree.links.new(texture.outputs["Color"], shader.inputs["Base Color"])
    return mat


class GloveGeometry:
    def __init__(self):
        self.verts, self.faces, self.uvs, self.weights = [], [], [], []

    def vertex(self, point, weights):
        self.verts.append(point)
        self.weights.append(weights)
        return len(self.verts) - 1

    def face(self, vertices, uv, panel):
        rect = PANELS[panel]
        self.faces.append(tuple(vertices))
        self.uvs.append([(rect[0]+u*(rect[2]-rect[0]), rect[1]+v*(rect[3]-rect[1])) for u, v in uv])

    def quad(self, vertices, u0, v0, u1, v1, panel):
        self.face(vertices, ((u0,v0), (u1,v0), (u1,v1), (u0,v1)), panel)

    def make_digit(self, side, digit, root_ring):
        hand = f"DRIVER:RIG_HAND_{side}"
        names = bone_names(side, digit)
        joints = [Vector(j) for j in finger_joints(digit)]
        fractions = (0, .45, .74, 1)
        prev = root_ring
        prev_t = 0
        for t in (.10,.19,.32,.385,.45,.515,.62,.685,.74,.795,.87,.93,.977):
            section = 0 if t < .45 else 1 if t < .74 else 2
            f = (t-fractions[section])/(fractions[section+1]-fractions[section])
            c = joints[section].lerp(joints[section+1], f)
            direction = (joints[section+1]-joints[section]).normalized()
            if digit == "Thumb":
                wide = Vector((-.6,.8,0))
            else:
                wide = Vector((0,1,0))
            wide = (wide - direction*wide.dot(direction)).normalized()
            thick = direction.cross(wide).normalized()
            if thick.z < 0:
                thick.negate()
            rw = {"Pinkie":.0065, "Ring":.0077, "Middle":.0080, "Index":.0079, "Thumb":.0097}[digit]
            rd = rw * (1.00 if digit == "Thumb" else .92)
            taper = 1.00 - .23 * t
            taper += .045 * exp(-((t-.45)/.06)**2) + .038 * exp(-((t-.74)/.05)**2)
            if t > .87:
                taper *= sqrt(max(.045, 1-((t-.87)/.13)**2))
            weights = {names[section]:1.0}
            for joint, before, after, spread in ((0,hand,names[0],.24), (.45,names[0],names[1],.102), (.74,names[1],names[2],.10)):
                if abs(t-joint)<spread:
                    amount = .5 + (t-joint)/(2*spread)
                    weights = {before:1-amount, after:amount}
            row = []
            for k in range(8):
                # 掌の最終断面の並びに合わせ、甲→親指側→掌を巡回。
                a = -pi*.25 + k*pi/4
                p = c + wide*(rw*taper*sin(a)) + thick*(rd*taper*cos(a))
                row.append(self.vertex(position(side,*p), weights))
            for k in range(8):
                nxt = (k+1)%8
                self.quad((prev[k],prev[nxt],row[nxt],row[k]), k/8,prev_t,(k+1)/8,t,"finger")
            prev, prev_t = row, t
        tip = self.vertex(position(side,*joints[-1]), {names[-1]:1.0})
        for k in range(8):
            self.face((prev[k],prev[(k+1)%8],tip), ((k/8,prev_t),((k+1)/8,prev_t),((k+.5)/8,1)), "finger")

    def make_hand(self, side):
        hand = f"DRIVER:RIG_HAND_{side}"
        fore = f"DRIVER:RIG_ForeArm_END_{side}"
        # 長さ、半幅、厚み。親指を出す2区画には側面を張らない。
        rows = [(-.012,.022,.0152),(-.009,.0228,.0158),(-.005,.0230,.0158),
                (.001,.0221,.0150),(.009,.0217,.0144),(.018,.0228,.0142),
                (.027,.0251,.0147),(.039,.0285,.0155),(.051,.0304,.0144),
                (.062,.0313,.0127),(.069,.0317,.0110),(.076,.0312,.0092)]
        top, bottom, edges = [], [], []
        for rid, (s,width,depth) in enumerate(rows):
            up, down = [], []
            v = (s+.012)/.088
            for j in range(9):
                w = (j/4-1)*width
                # 弧を描く中手骨と、指の間で掌側へ下がる水かき。
                end = [.066,.071,.070,.075,.073,.078,.074,.076,.070][j]
                dist = s + (end-.076)*max(0,(s-.060)/.016)
                if s < .027:
                    share = .95 * (.027-s)/.039
                    weights = {hand:1-share, fore:share}
                elif rid == len(rows)-1:
                    neighbors = [FINGERS[min(j//2,3)]] if j%2 or j in (0,8) else FINGERS[j//2-1:j//2+1]
                    weights = {hand:.72, **{bone_names(side,d)[0]:.28/len(neighbors) for d in neighbors}}
                else:
                    weights = {hand:1}
                d = depth*(.57+.43*(1-(w/width)**2))
                web = (1-.13*(j%2==0)) if rid==len(rows)-1 else 1
                up.append(self.vertex(position(side,dist,w,d*web),weights))
                thenar = .0028*exp(-((s-.042)/.020)**2-((w-.011)/.013)**2)
                # 中手骨の掌側は母指球・小指球の間でくぼみ、指の付け根で再び厚くなる。
                hollow = .0048 * exp(-((dist-.064)/.018)**2 - ((w+.007)/.035)**2)
                down.append(self.vertex(position(side,dist,w,-d*web-thenar+hollow),weights))
            top.append(up)
            bottom.append(down)
            edges.append([self.vertex(position(side,s,-width*1.045,0),self.weights[up[0]]),
                          self.vertex(position(side,s,width*1.045,0),self.weights[up[8]]) if rid != 7 else None])
            if rid == 0:
                self.face(up + [edges[0][1]] + down[::-1] + [edges[0][0]],
                          [(j/8,.8) for j in range(9)] + [(1,.5)] + [(j/8,.2) for j in reversed(range(9))] + [(0,.5)], "edge")
                continue
            old_v = (rows[rid-1][0]+.012)/.088
            for j in range(8):
                for surface, panel in ((top,"back"),(bottom,"palm")):
                    self.quad((surface[rid-1][j],surface[rid-1][j+1],surface[rid][j+1],surface[rid][j]),
                              j/8,old_v,(j+1)/8,v,panel)
            for edge, j in ((0,0),(1,8)):
                if edge == 1 and rid in (7,8):
                    continue
                rail = [top[rid-1][j],edges[rid-1][edge],bottom[rid-1][j]]
                nxt = [top[rid][j],edges[rid][edge],bottom[rid][j]]
                for k in range(2):
                    self.quad((rail[k],rail[k+1],nxt[k+1],nxt[k]),k/2,old_v,(k+1)/2,v,"edge")

        # 4本の指の股で同じ辺を共有する。
        separators = [edges[-1][0]]
        for j in (2,4,6):
            pt = (self.verts[top[-1][j]]+self.verts[bottom[-1][j]])*.5
            separators.append(self.vertex(pt,self.weights[top[-1][j]]))
        separators.append(edges[-1][1])
        for i, digit in enumerate(FINGERS[:4]):
            a = i*2
            ring = top[-1][a:a+3] + [separators[i+1]] + bottom[-1][a:a+3][::-1] + [separators[i]]
            self.make_digit(side,digit,ring)
        # 指の横軸は母指の場合には手首側を向く。
        thumb_ring = [top[8][8],top[7][8],top[6][8],edges[6][1],
                      bottom[6][8],bottom[7][8],bottom[8][8],edges[8][1]]
        self.make_digit(side,"Thumb",thumb_ring)


def build_gloves():
    geo = GloveGeometry()
    for side in SIDES:
        geo.make_hand(side)
    mesh = bpy.data.meshes.new("Tailored cotton gloves")
    mesh.from_pydata(geo.verts,[],geo.faces)
    mesh.update()
    mesh.materials.append(glove_material())
    uv = mesh.uv_layers.new(name="Glove atlas")
    for poly, poly_uv in zip(mesh.polygons,geo.uvs):
        poly.use_smooth = True
        for loop, coord in zip(poly.loop_indices,poly_uv):
            uv.data[loop].uv = coord
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm,faces=bm.faces[:])
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("DRIVER:GLOVES",mesh)
    bpy.context.collection.objects.link(obj)
    groups = {}
    for idx, weights in enumerate(geo.weights):
        for name, weight in weights.items():
            if weight <= 0:
                continue
            if name not in groups:
                groups[name] = obj.vertex_groups.new(name=name)
            groups[name].add([idx],weight,"REPLACE")
    return obj
