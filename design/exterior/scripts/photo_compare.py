"""Lay out photo comparisons without geometric warps or per-image alignment."""
import json
from pathlib import Path
import sys
import unicodedata

import numpy as np
from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).resolve().parent
PHOTOS = HERE.parents[2]/'refs'/'photos'
CAPTIONS = {'front34':'ふ43　左斜め前', 'rear34':'ふ43　右斜め後',
            'front':'な39　正面', 'rear':'ち85　後面'}
FONT = next(p for p in Path('/System/Library/Fonts').glob('*.ttc')
            if unicodedata.normalize('NFC', p.stem)=='ヒラギノ角ゴシック W5')


def edges(path):
    raw = np.array(Image.open(path).convert('RGBA')).astype(np.int16)
    h, w = raw.shape[:2]
    result = np.zeros((h,w),np.uint8)
    for axis in (0,1):
        # Exact region transitions from an un-antialiased, flat visibility pass.
        diff = np.max(np.abs(np.diff(raw,axis=axis)),axis=2) > 20
        if axis==0:
            result[1:,:] |= diff
        else:
            result[:,1:] |= diff
    detail = np.array(Image.open(str(path).replace('-id.png','-inside.png')).convert('RGB'),dtype=np.int16)[:,:,0]
    result[1:,:] |= np.abs(np.diff(detail,axis=0))>20
    result[:,1:] |= np.abs(np.diff(detail,axis=1))>20
    return result


def compare(key, work, out):
    data = json.loads((work/(key+'.json')).read_text())
    photo = Image.open(PHOTOS/data['photo']).convert('RGB')
    shot = Image.open(work/(key+'-beauty.png')).convert('RGB')
    assert shot.size == photo.size == tuple(data['size'])
    native = edges(work/(key+'-id.png'))
    w,h = photo.size
    title = CAPTIONS[key]
    def frame(images, labels, name):
        panel_w = 1600//len(images)
        panel_h = round(h*panel_w/w)
        canvas = Image.new('RGB',(1600,panel_h+52),(27,39,45))
        draw = ImageDraw.Draw(canvas)
        font = ImageFont.truetype(str(FONT),22)
        for i,(im,label) in enumerate(zip(images,labels)):
            canvas.paste(im.resize((panel_w,panel_h),Image.Resampling.LANCZOS),(i*panel_w,52))
            draw.text((i*panel_w+20,26),label,font=font,fill=(242,248,248),anchor='lm')
        if len(images)==2:
            draw.line((panel_w,52,panel_w,51+panel_h),fill=(235,239,240),width=2)
        canvas.save(out/(key+'_'+name+'.png'))
    frame([photo,shot],[title+'　｜　参照写真','同一カメラ　｜　外装モデル'],'pair')
    # Keep the underlying boundary legible through the coloured stroke.
    mask=Image.fromarray(native*255)
    overlay=Image.composite(Image.blend(photo,Image.new('RGB',photo.size,(0,241,224)),.87),photo,mask)
    frame([overlay],[title+'　｜　水色の線はモデルの可視輪郭・部品境界'],'edges')


if __name__=='__main__':
    work,out=(Path(x).resolve() for x in sys.argv[1:3])
    for key in CAPTIONS:
        compare(key,work,out)
