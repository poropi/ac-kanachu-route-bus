"""Bake metre-scale vector drawings onto the existing Blender paint UVs.

Run with /usr/bin/python3 -B paint_livery.py [standard|new2023 ...].
The blend is opened read-only. Temporary geometry lives below design/livery.
"""
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import argparse
import importlib
import os
import shutil
import subprocess

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

SCRIPTS = Path(__file__).resolve().parent
OUTPUT = SCRIPTS.parent
MODEL = OUTPUT.parent/'exterior'/'kanachu_exterior.blend'
FACES = ('LEFT','RIGHT','FRONT','REAR','ROOF','HVAC')
W, H = 4096, 2048
SCALE = 238  # SVG sampling density. Actual atlas placement always comes from the saved UVs.
BLEED = 24
BORDER = .1


def make_maps(mesh):
    """Rasterize triangle-centre samples in the atlas and retain world projections."""
    face_map = np.full((H,W), -1, np.int8)
    coords = np.zeros((H,W,2), np.float32)
    for uv, xyz, face in zip(mesh['uv'],mesh['xyz'],mesh['group']):
        lo = np.maximum(0,np.ceil(uv.min(axis=0)-.5).astype(int))
        hi = np.minimum([W,H],np.floor(uv.max(axis=0)-.5).astype(int)+1)
        if (lo >= hi).any():
            continue
        x0,y0 = lo
        x1,y1 = hi
        y,x = np.ogrid[y0:y1,x0:x1]
        dx,dy = x+.5-uv[0,0], y+.5-uv[0,1]
        a,b = uv[1:]-uv[0]
        det = a[0]*b[1]-a[1]*b[0]
        p,q = (dx*b[1]-dy*b[0])/det,(dy*a[0]-dx*a[1])/det
        inside = (p>=-1.e-8)&(q>=-1.e-8)&(p+q<=1+1.e-8)
        if not inside.any():
            continue
        X,Y,Z = xyz.T
        if face in (0,1):
            u,v = 4.950-Y, 3.105-Z
        elif face in (2,3):
            u,v = 1.2425+(-X if face==2 else X), 3.105-Z
        else:
            u,v = 4.950-Y, 1.2425+X
        face_map[y0:y1,x0:x1][inside] = face
        out = coords[y0:y1,x0:x1]
        for dim,values in enumerate((u,v)):
            out[:,:,dim][inside] = values[0]+p[inside]*(values[1]-values[0])+q[inside]*(values[2]-values[0])
    return face_map, coords


def vector_image(fragment,face):
    width = 2.485 if face in ('FRONT','REAR') else 10.43
    height = 2.485 if face in ('ROOF','HVAC') else 3.105
    px = int(np.ceil((width+2*BORDER)*SCALE))
    py = int(np.ceil((height+2*BORDER)*SCALE))
    # Fourfold area sampling softens the fine stripes and small type before UV reprojection.
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{px*4}" height="{py*4}" '
           f'viewBox="{-BORDER} {-BORDER} {px/SCALE} {py/SCALE}">{fragment}</svg>')
    program = shutil.which('rsvg-convert') or '/opt/homebrew/bin/rsvg-convert'
    png = subprocess.run([program],input=svg.encode(),capture_output=True,check=True).stdout
    with Image.open(BytesIO(png)) as img:
        if img.mode == 'RGBA' and img.getchannel('A').getextrema()[0] < 255:
            raise ValueError(f'{face} の作図範囲には不透明な下地が必要です')
        return np.asarray(img.convert('RGB').resize((px,py),Image.Resampling.LANCZOS))


def verify_padding(rgb,face_map):
    """Report where two differently painted chart edges compete within 16 texels."""
    conflicts = []
    for i,face in enumerate(FACES):
        rows,cols = np.where(face_map == i)
        region = np.s_[max(0,rows.min()-16):rows.max()+17, max(0,cols.min()-16):cols.max()+17]
        local = face_map[region]
        dist,nearest = distance_transform_edt(local!=i,return_indices=True)
        margin = (local<0)&(dist<=16)
        pixels = rgb[region]
        expected = pixels[nearest[0][margin],nearest[1][margin]]
        # Ignore one level of 8-bit rounding at antialiased boundaries.
        different = np.max(np.abs(expected.astype(int)-pixels[margin]),axis=1)>1
        if different.any():
            closest = dist[margin][different].min()
            conflicts.append(f'{face}: {different.sum()} px (最短距離 {closest:.1f} px)')
    return '、'.join(conflicts) or 'なし'


def bake(skin,face_map,coords,bleed,nearest):
    module = importlib.import_module(skin)
    result = np.full((H,W,3), (77,80,81), np.uint8)
    for i,face in enumerate(FACES):
        source = vector_image(module.artwork(face),face)
        rows,cols = np.where(face_map==i)
        ys = slice(rows.min(),rows.max()+1)
        xs = slice(cols.min(),cols.max()+1)
        sample = (coords[ys,xs]+BORDER)*SCALE-.5
        sampled = cv2.remap(source,sample,None,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
        used = face_map[ys,xs]==i
        result[ys,xs][used] = sampled[used]
    result[bleed] = result[nearest[0][bleed],nearest[1][bleed]]
    target = OUTPUT/f'paint_{skin}.png'
    Image.fromarray(result,'RGB').save(target)
    print(f'{target.name}: {W} × {H} RGB, 塗装 {np.sum(face_map>=0):,} px、外縁拡張 {bleed.sum():,} px',flush=True)
    print('16 px 内で隣の区画の色と競合する余白:',verify_padding(result,face_map),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skins',nargs='*',metavar='SKIN')
    skins = parser.parse_args().skins or ['standard','new2023']
    if any(s not in ('standard','new2023') for s in skins):
        parser.error('standard / new2023 を指定してください')
    with TemporaryDirectory(dir=OUTPUT,prefix='.paint-') as temp:
        dest = Path(temp)/'projected.npz'
        subprocess.run(['/opt/homebrew/bin/blender','-b','--factory-startup','--disable-autoexec',str(MODEL),
                        '--python-exit-code','1','--python',str(SCRIPTS/'export_faces.py'),'--',str(dest)],
                       env={**os.environ,'TMPDIR':temp,'PYTHONDONTWRITEBYTECODE':'1'},check=True)
        with np.load(dest) as mesh:
            # Materialize once instead of decompressing an array for each triangle.
            maps, coords = make_maps(dict(mesh))
    distance,nearest = distance_transform_edt(maps<0,return_indices=True)
    bleed = (maps<0)&(distance<=BLEED)
    for skin in skins:
        bake(skin,maps,coords,bleed,nearest)


if __name__=='__main__':
    main()
