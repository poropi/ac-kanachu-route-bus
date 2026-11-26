"""Blender 5.2: blender -b --python-exit-code 1 --python design/driver/scripts/build_driver.py"""
import math
from pathlib import Path
import subprocess
import sys

import bpy
from mathutils import Matrix, Vector

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent
DRIVER = SCRIPTS.parent
DESIGN = DRIVER.parent
RENDERS = DRIVER / "renders"
sys.path[:0] = [str(SCRIPTS), str(DESIGN.parent / "tools")]

from driver_skeleton import BONES, HEAD_MESHES, SKINNED_MESHES
from driver_gloves import build_gloves, hand_bones, grip, grip_frame


def rig_name(joint, side=None):
    return "DRIVER:RIG_" + joint + ("_" + side if side else "")


def landmark(px, py, y=0.0, sign=1):
    """Front and left elevation share a 1.15 mm pixel pitch and floor at row 1487."""
    return Vector((sign * (px - 512) * .00115, y, (1487 - py) * .00115))


def rest_skeleton():
    joints = {}
    def segment(name, start, end):
        joints[name] = (Vector(start), Vector(end))

    segment("DRIVER:DRIVER", (0, 0, 0), (0, 0, .13))
    segment(rig_name("Center"), (0, 0, .82), (0, 0, .86))
    segment(rig_name("Hips"), (0, 0, .86), (0, -.003, 1.064))
    segment(rig_name("Cest"), (0, -.003, 1.064), (0, -.003, 1.323))
    segment(rig_name("Nek"), (0, -.003, 1.323), (0, .013, 1.38))
    segment(rig_name("Head"), (0, .013, 1.38), (0, .0, 1.611))
    for side, sign in (("L", 1), ("R", -1)):
        def point(px, py, y):
            return landmark(px, py, y, sign)
        shoulder = point(613, 371, 0)
        elbow = point(670, 532, -.018)
        wrist = point(762, 728, -.006)
        twist = elbow.lerp(wrist, .86)
        hip = point(574, 763, 0)
        knee = point(578, 1023, .014)
        ankle = point(582, 1394, -.003)
        ball = point(582, 1469, .10)
        def limb(joint, a, b):
            segment(rig_name(joint, side), a, b)
        limb("Clave", point(539, 341, -.003), shoulder)
        limb("Shoulder", shoulder, shoulder.lerp(elbow, .20))
        limb("Arm", shoulder, elbow)
        limb("ForeArm", elbow, twist)
        limb("ForeArm_END", twist, wrist)
        limb("Leg", hip, knee)
        limb("Shin", knee, ankle)
        limb("Hill", ankle, ball)
        limb("Foot", ball, point(582, 1473, .151))
    joints.update(hand_bones())
    assert set(joints) == dict(BONES).keys()
    return joints


def create_rig():
    data = bpy.data.armatures.new("Kanachu driver")
    arm = bpy.data.objects.new("DRIVER:DRIVER", data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    arm.show_in_front = False
    data.display_type = "STICK"
    coords = rest_skeleton()
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent in BONES:
        bone = data.edit_bones.new(name)
        bone.head, bone.tail = coords[name]
        if parent:
            bone.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    return arm


def bind_character(arm):
    for name in SKINNED_MESHES:
        obj = bpy.data.objects[name]
        obj.parent = arm
        mod = obj.modifiers.new("Driver armature", "ARMATURE")
        mod.object = arm
        # AC blends bone matrices linearly. Render the same deformation in Blender.
        mod.use_deform_preserve_volume = False
        for vertex in obj.data.vertices:
            weights = [g.weight for g in vertex.groups if g.weight > 0]
            assert 1 <= len(weights) <= 4 and abs(sum(weights) - 1) < .0002, (name, vertex.index, weights)
    bpy.context.view_layer.update()
    for name in HEAD_MESHES:
        obj = bpy.data.objects[name]
        world = obj.matrix_world.copy()
        obj.parent = arm
        obj.parent_type = "BONE"
        obj.parent_bone = rig_name("Head")
        bpy.context.view_layer.update()
        obj.matrix_world = world
    bpy.context.view_layer.update()


def set_direction(bone, new_direction):
    """Swing a pose bone in armature space, retaining its inherited twist."""
    current = bone.tail - bone.head
    rotation = current.rotation_difference(Vector(new_direction))
    matrix = rotation.to_matrix().to_4x4() @ bone.matrix
    matrix.translation = bone.head
    bone.matrix = matrix
    bpy.context.view_layer.update()


def two_bone(elbow_origin, target, pole, upper, lower):
    difference = target - elbow_origin
    distance = difference.length
    if not abs(upper - lower) < distance < upper + lower:
        raise ValueError(f"Wrist target unreachable: {distance:.4f} (arm {upper + lower:.4f} m)")
    axis = difference.normalized()
    across = (pole - axis * pole.dot(axis)).normalized()
    along = (upper * upper - lower * lower + distance * distance) / (2 * distance)
    return elbow_origin + axis * along + across * math.sqrt(max(0, upper * upper - along * along))


# Local studio position. The rim and horn pad used for verification retain the
# bus model's 232 mm radius, 16 mm tube and 24-degree steering plane.
WHEEL = Vector((0, .390, 1.100))
GRIP_ANGLE = math.radians(44)
RAKE = math.radians(24)
RIM_RADIUS = .232


def basis(first, second):
    x = first.normalized()
    y = (second - x * second.dot(x)).normalized()
    return Matrix((x, y, x.cross(y))).transposed()


def seated_pose(arm):
    for bone in arm.pose.bones:
        bone.rotation_mode = "QUATERNION"
        bone.keyframe_insert(data_path="rotation_quaternion", frame=1, group=bone.name)
    center_bone = arm.pose.bones[rig_name("Center")]
    center_bone.keyframe_insert(data_path="location", frame=1, group=center_bone.name)
    bpy.context.scene.frame_set(2)
    set_direction(arm.pose.bones[rig_name("Cest")], (0, .32, 1))
    for side, s in (("L", 1), ("R", -1)):
        def pb(joint):
            return arm.pose.bones[rig_name(joint, side)]
        set_direction(pb("Leg"), (s * .19, .97, -.16))
        set_direction(pb("Shin"), (s * .02, .31, -.95))
        set_direction(pb("Hill"), (0, .80, -.60))
        set_direction(pb("Foot"), (0, 1, -.08))

        center, axis, rest_palm = (Vector(v) for v in grip_frame(side))
        radial = Vector((s * math.cos(GRIP_ANGLE), math.sin(GRIP_ANGLE) * math.cos(RAKE),
                         math.sin(GRIP_ANGLE) * math.sin(RAKE)))
        tangent = Vector((-s * math.sin(GRIP_ANGLE), math.cos(GRIP_ANGLE) * math.cos(RAKE),
                          math.cos(GRIP_ANGLE) * math.sin(RAKE)))
        # Four fingers wrap around a side of the wheel; the thumb points along
        # the rising forward tangent. The palm is pitched onto the upper surface of the rim.
        towards_rim = Vector((0, .30, -.87))
        rot = basis(tangent, towards_rim) @ basis(axis, rest_palm).transposed()
        hand = pb("HAND")
        hand_rest = hand.bone.head_local
        wheel_contact = WHEEL + radial * RIM_RADIUS
        wrist = wheel_contact - rot @ (center - hand_rest)
        shoulder = pb("Arm").head.copy()
        elbow = two_bone(shoulder, wrist, Vector((-s * .30, -.5, -1)),
                         pb("Arm").length, pb("ForeArm").length + pb("ForeArm_END").length)
        set_direction(pb("Arm"), elbow - shoulder)
        set_direction(pb("ForeArm"), wrist - elbow)
        hand_matrix = (rot @ hand.bone.matrix_local.to_3x3()).to_4x4()
        hand_matrix.translation = hand.head
        hand.matrix = hand_matrix
        bpy.context.view_layer.update()
        # The auxiliary shoulder is a sibling of the upper arm.
        set_direction(pb("Shoulder"), (elbow - shoulder).lerp(pb("Shoulder").tail - pb("Shoulder").head, .50))
    grip(arm)
    bpy.context.view_layer.update()
    # Put the seated shoes on the same floor as the standing shoes.
    evaluated = bpy.data.objects[SKINNED_MESHES[0]].evaluated_get(bpy.context.evaluated_depsgraph_get())
    sole_z = min((evaluated.matrix_world @ v.co).z for v in evaluated.data.vertices)
    translation = Vector((0, 0, -sole_z))
    matrix = center_bone.matrix.copy()
    matrix.translation += translation
    center_bone.matrix = matrix
    center_bone.keyframe_insert(data_path="location", frame=2, group=center_bone.name)
    arm["preview_rim_center_m"] = list(WHEEL + translation)
    for bone in arm.pose.bones:
        bone.keyframe_insert(data_path="rotation_quaternion", frame=2, group=bone.name)
    scene = bpy.context.scene
    scene.frame_end = 2
    scene.timeline_markers.new("A pose", frame=1)
    scene.timeline_markers.new("Seated grip", frame=2)
    arm.animation_data.action.name = "Kanachu | A pose and seated grip"
    scene.frame_set(1)


def paper_background(scene):
    tree = bpy.data.node_groups.new("Turnaround projection", "CompositorNodeTree")
    scene.compositing_node_group = tree
    tree.interface.new_socket(name="Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    source = tree.nodes.new("CompositorNodeRLayers")
    flip = tree.nodes.new("CompositorNodeFlip")
    flip.inputs["Flip X"].default_value = True
    tree.links.new(source.outputs["Image"], flip.inputs["Image"])
    over = tree.nodes.new("CompositorNodeAlphaOver")
    over.inputs["Background"].default_value = (1, 1, 1, 1)
    tree.links.new(flip.outputs["Image"], over.inputs["Foreground"])
    output = tree.nodes.new("NodeGroupOutput")
    tree.links.new(over.outputs[0], output.inputs[0])
    return over


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def camera(name, location, target, lens=None):
    data = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(cam)
    cam.location = location
    aim(cam, target)
    if lens:
        data.lens = lens
    else:
        data.type = "ORTHO"
        data.ortho_scale = 1536 * .00115
    data.clip_start = .012
    data.display_size = .075
    return cam


def setup_studio(arm):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 10
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 3
    scene.cycles.diffuse_bounces = 1
    scene.render.film_transparent = True
    scene.render.resolution_percentage = 100
    scene.render.resolution_x = 1024
    scene.render.resolution_y = 1536
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "Standard"
    scene.world = bpy.data.worlds.new("Soft daylight")
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .74
    for name, pos, power, size in [
        ("Softbox", (1.4, 2.2, 3.25), 48, 3.0),
        ("Edge light", (-1.3, -1.6, 2.5), 38, 2.5),
    ]:
        lamp = bpy.data.lights.new(name, "AREA")
        lamp.energy, lamp.shape, lamp.size = power, "DISK", size
        obj = bpy.data.objects.new(name, lamp)
        bpy.context.collection.objects.link(obj)
        obj.location = pos
        aim(obj, (0, 0, 1.02))
    middle_z = (1487 - 768) * .00115
    center = (0, 0, middle_z)
    scene.frame_set(2)
    head = arm.pose.bones[rig_name("Head")]
    from_rest = head.matrix @ head.bone.matrix_local.inverted()
    eye = from_rest @ landmark(512, 221, .084)
    hub = Vector(arm["preview_rim_center_m"])
    scene.frame_set(1)
    cams = {
        "front": camera("Front", (0, 3.0, middle_z), center),
        "side": camera("Left side", (3, (505 - 512)*.00115, middle_z), (0, (505 - 512)*.00115, middle_z)),
        "back": camera("Back", (0, -3.0, middle_z), center),
        "seated_hands": camera("Driver eye", eye, hub + Vector((0, .043, -.028)), 20),
    }
    scene.camera = cams["front"]
    return scene, cams, paper_background(scene)


def borrow_preview_wheel(center):
    names = ["Steering_Rim", "Steering_Spokes_and_Pad"]
    path = DESIGN / "interior" / "kanachu_interior.blend"
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        assert all(n in src.objects for n in names)
        dst.objects = names
    matrix = Matrix.Translation(center) @ Matrix.Rotation(RAKE - math.pi, 4, "X")
    for obj in dst.objects:
        obj.parent = None
        bpy.context.collection.objects.link(obj)
        obj.matrix_world = matrix


def save_master(arm, cams):
    scene = bpy.context.scene
    scene.frame_set(1)
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    bpy.context.view_layer.objects.active = arm
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                space = area.spaces.active
                space.overlay.show_overlays = False
                space.shading.type = "SOLID"
                space.shading.color_type = "TEXTURE"
                space.region_3d.view_rotation = cams["front"].rotation_euler.to_quaternion()
                space.region_3d.view_perspective = "ORTHO"
                space.region_3d.view_distance = 2.62
                space.region_3d.view_location = (0, 0, .829)
    scene.render.filepath = "//renders/front.png"
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(DRIVER / "kanachu_driver.blend"), compress=True)


def render_all(scene, cameras, background):
    for view, cam in cameras.items():
        scene.camera = cam
        if view == "seated_hands":
            scene.frame_set(2)
            for name in HEAD_MESHES:
                bpy.data.objects[name].hide_render = True
            borrow_preview_wheel(Vector(bpy.data.objects["DRIVER:DRIVER"]["preview_rim_center_m"]))
            # Inside the bus the white cotton receives less sky fill than in the
            # white studio. Retain both the glove seams and the lighter knuckles.
            scene.world.node_tree.nodes["Background"].inputs[1].default_value = .54
            scene.render.resolution_x, scene.render.resolution_y = 1250, 920
            background.inputs["Background"].default_value = (.45, .49, .55, 1)
        scene.render.filepath = str(RENDERS / (view + ".png"))
        bpy.ops.render.render(write_still=True)
    subprocess.run(["/usr/bin/python3", "-B", str(SCRIPTS / "compare_driver.py")], check=True)


def main():
    from driver_body import build_body
    from driver_head import build_head
    bpy.ops.wm.read_factory_settings(use_empty=True)
    RENDERS.mkdir(exist_ok=True)
    arm = create_rig()
    build_body()
    build_gloves()
    build_head()
    bind_character(arm)
    seated_pose(arm)
    scene, cameras, background = setup_studio(arm)
    save_master(arm, cameras)
    render_all(scene, cameras, background)


if __name__ == "__main__":
    main()
