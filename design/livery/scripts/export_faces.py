"""Read the saved paint triangles, with their final UVs and world coordinates."""
from pathlib import Path
import sys
import bpy
import numpy as np

FACE_NAMES = ('LEFT','RIGHT','FRONT','REAR','ROOF','AUX_HVAC')
uv, xyz, group = [], [], []
for obj in bpy.context.scene.objects:
    if obj.type != 'MESH':
        continue
    slots = {s.slot_index for s in obj.material_slots if s.material and s.material.name == 'paint'}
    if not slots:
        continue
    mesh = obj.data
    mesh.calc_loop_triangles()
    vertices = np.array([tuple(obj.matrix_world @ v.co) for v in mesh.vertices])
    tex = np.array([tuple(item.uv) for item in mesh.uv_layers.active.data])
    for tri in mesh.loop_triangles:
        if tri.material_index in slots:
            uv.append(tex[list(tri.loops)] * [4096,-2048] + [0,2048])
            xyz.append(vertices[list(tri.vertices)])
            group.append(FACE_NAMES.index(obj['chart']))
np.savez_compressed(Path(sys.argv[-1]), uv=uv, xyz=xyz, group=group)
