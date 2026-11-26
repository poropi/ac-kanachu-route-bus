"""Metre-scale vector artwork shared by the two body finishes."""
from functools import lru_cache
from pathlib import Path
import unicodedata

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont


def rect(x, y, w, h, color):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}"/>'


def _fit(fragment, x, y, w, h, bounds, reverse):
    x0, y0, x1, y1 = bounds
    sx, sy = w/(x1-x0), h/(y1-y0)
    origin = x+w if reverse else x
    return (f'<g transform="translate({origin} {y}) scale({-sx if reverse else sx} {sy}) '
            f'translate({-x0} {-y0})">{fragment}</g>')


def logo(x, y, w, h, color, reverse=False, accent=None):
    """Hand-built Kanachu outlines. Proportions from the head-on な39 photograph."""
    # The two hairlines follow the inside angles of the broad K.
    k = 'M3 0H45V69L99 0H128L70 78L130 168H101L51 97L45 106V168H2Z'
    lines = 'M143 0H154L96 79L154 168H143L83 79Z M169 0H175L115 79L176 168H169L107 79Z'
    a = ('M185 88C188 63 207 49 239 49C275 49 293 62 293 88V145Q293 159 296 168H265'
         'Q262 164 262 156Q247 173 221 173C194 173 179 160 179 138C179 114 196 105 225 102'
         'L247 99Q261 97 261 87Q261 70 239 70Q217 70 215 88Z '
         'M261 110Q255 116 235 118Q209 121 209 137Q209 152 227 152Q260 152 261 129Z')
    n = ('M310 54H341V66Q354 50 379 50Q422 50 422 94V168H390V101Q390 74 368 74'
         'Q344 74 342 101V168H310Z')
    c = ('M676 96H644Q640 74 618 74C596 74 589 90 589 112Q589 150 618 150Q640 150 644 128H676'
         'Q670 173 618 173C577 173 558 149 558 112C558 74 579 50 618 50Q669 50 676 96Z')
    hpath = ('M690 13H722V66Q735 50 760 50Q802 50 802 95V168H771V102Q771 74 748 74'
             'Q722 74 722 103V168H690Z')
    u = ('M818 55H850V125Q850 151 871 151Q897 151 897 119V55H929V168H899V155'
         'Q884 173 858 173Q818 173 818 132Z')
    fragment = (f'<g fill="{color}" fill-rule="evenodd"><path d="{k}"/><path fill="{accent or color}" d="{lines}"/>'
                f'<path d="{a}"/><path d="{n}"/><path transform="translate(254 0)" d="{a}"/>'
                f'<path d="{c}"/><path d="{hpath}"/><path d="{u}"/></g>')
    return _fit(fragment, x,y,w,h, (2,0,929,173),reverse)


@lru_cache(None)
def _font(path):
    return TTFont(str(path), fontNumber=0)


@lru_cache(None)
def _type(text, italic, family):
    base = Path('/System/Library/Fonts')
    if any(ord(c) > 127 for c in text):
        path = next(p for p in base.glob('*.ttc') if unicodedata.normalize('NFC', p.stem) == 'ヒラギノ角ゴシック W6')
    else:
        name = 'Times New Roman' if family == 'serif' else 'Arial'
        path = base/'Supplemental'/(name+(' Bold Italic' if italic else ' Bold')+'.ttf')
    font = _font(path)
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    pos = 0
    paths, bounds = [], []
    for char in text:
        glyph = glyphs[cmap[ord(char)]]
        pen = SVGPathPen(glyphs)
        glyph.draw(pen)
        box = BoundsPen(glyphs)
        glyph.draw(box)
        if box.bounds:
            a,b,c,d = box.bounds
            bounds.append((pos+a,-d,pos+c,-b))
            paths.append(f'<path transform="translate({pos} 0) scale(1 -1)" d="{pen.getCommands()}"/>')
        pos += glyph.width
    return ''.join(paths), (min(b[0] for b in bounds),min(b[1] for b in bounds),
                            max(b[2] for b in bounds),max(b[3] for b in bounds))


def lettering(text,x,y,w,h,color,reverse=False,italic=False,font='sans'):
    paths, bounds = _type(text,italic,font)
    return _fit(f'<g fill="{color}">{paths}</g>',x,y,w,h,bounds,reverse)
