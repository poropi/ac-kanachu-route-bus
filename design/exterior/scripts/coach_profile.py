"""Cross sections at the two ends, measured in the head-on views."""
import math


def clamp(x):
    return max(0., min(1., x))


def shaped_point(x, y, z):
    # Fade the terminal cross sections into the straight passenger bay.
    end = clamp((y-2.65)/1.62) if y > 0 else clamp((-y-3.12)/1.65)
    end = end*end*(3.-2.*end)
    rise = clamp((z-.87)/1.83)
    outside = clamp((abs(x)-.72)/.51)
    inset = (.076 if y>0 else .060)*end*rise**1.28*outside
    # Crown the brow across its width. Keep the centre of the rear roof and
    # the mounting surface under the equipment on the middle roof unchanged.
    crown = end * clamp((z-2.66)/.19)
    drop = crown * ((.019 if y>0 else 0.)+(.038 if y>0 else .017)*(abs(x)/1.20)**2)
    return (x-math.copysign(inset,x), y, z-drop)


def apply(root):
    for obj in root.children_recursive:
        if obj.type!='MESH' or obj.name.startswith(('Mirror','HVAC','Roof_Extractor','Roof_Vent','INTERIOR_')):
            continue
        if obj.parent.name.startswith('WHEEL_'):
            continue
        for vertex in obj.data.vertices:
            vertex.co = shaped_point(*vertex.co)
        obj.data.update()
