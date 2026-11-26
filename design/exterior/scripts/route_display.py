"""Hand-drawn destination glyphs. Coordinates are individual LED addresses."""
import sys
from PIL import Image, ImageDraw


# Each path follows the centre of a stroke. Front and side use 20 x 25
# cells per glyph. The rear hardware has a shorter, 15 x 15 design.
FRONT = {
    '神': [
        [(4,0),(4,4)], [(0,5),(8,5),(6,8),(1,14),(0,14)],
        [(4,11),(4,24)], [(5,11),(8,15)],
        [(10,5),(18,5),(18,17),(10,17),(10,5)],
        [(10,11),(18,11)], [(14,0),(14,24)]],
    '奈': [
        [(9,0),(9,4),(7,7),(2,12),(0,13)], [(1,4),(17,4)],
        [(10,5),(13,8),(18,12)], [(4,12),(15,12)],
        [(1,16),(18,16)], [(9,16),(9,23),(8,24),(6,24)],
        [(5,19),(3,21),(0,23)], [(13,19),(15,21),(18,23)]],
    '川': [
        [(4,1),(4,13),(3,19),(2,22),(0,24)],
        [(10,2),(10,21)], [(17,0),(17,24)]],
    '中': [
        [(1,6),(18,6),(18,17),(1,17),(1,6)],
        [(1,17),(1,19)], [(18,17),(18,19)], [(9,0),(9,24)]],
    '央': [
        [(3,15),(3,6),(16,6),(16,15)], [(0,15),(19,15)],
        [(10,0),(10,12),(9,16),(7,19),(4,22),(0,24)],
        [(10,16),(12,19),(15,22),(19,24)]],
    '交': [
        [(9,0),(9,3)], [(0,4),(18,4)],
        [(6,7),(4,10),(1,13)], [(12,7),(15,10),(18,12)],
        [(4,13),(6,16),(10,20),(14,22),(19,24)],
        [(15,13),(13,16),(9,20),(5,22),(0,24)]],
    '通': [
        [(0,1),(1,3),(3,5)], [(0,9),(4,9),(4,20),(2,22),(0,23)],
        [(4,21),(7,23),(12,24),(19,24)],
        [(6,1),(18,1),(16,3),(13,6)], [(9,4),(13,7)],
        [(7,20),(7,8),(18,8),(18,20),(16,20)],
        [(7,12),(18,12)], [(7,16),(18,16)], [(12,8),(12,20)]],
}

REAR = {
    '神': [[(3,0),(3,2)], [(0,3),(5,3),(3,6),(0,9)], [(3,6),(3,14)],
          [(4,7),(5,8)], [(7,3),(14,3),(14,10),(7,10),(7,3)],
          [(7,6),(14,6)], [(10,0),(10,14)]],
    '奈': [[(7,0),(7,2),(5,4),(1,6)], [(1,2),(13,2)], [(8,3),(10,5),(14,6)],
          [(4,7),(11,7)], [(1,9),(13,9)], [(7,9),(7,14),(5,14)],
          [(4,11),(1,13)], [(10,11),(13,13)]],
    '川': [[(3,0),(3,8),(2,12),(1,14)], [(7,1),(7,12)], [(13,0),(13,14)]],
    '中': [[(1,3),(13,3),(13,10),(1,10),(1,3)], [(7,0),(7,14)]],
    '央': [[(2,9),(2,3),(12,3),(12,9)], [(0,9),(14,9)],
          [(7,0),(7,7),(6,10),(4,12),(0,14)], [(7,10),(10,12),(14,14)]],
    '交': [[(7,0),(7,2)], [(0,2),(14,2)], [(4,4),(1,7)], [(10,4),(13,7)],
          [(3,7),(5,10),(9,12),(14,14)], [(11,7),(9,10),(5,12),(0,14)]],
    '通': [[(0,0),(2,2)], [(0,5),(2,5),(2,11),(0,13)], [(2,12),(5,14),(14,14)],
          [(4,0),(13,0),(9,3)], [(6,2),(9,4)], [(5,12),(5,4),(13,4),(13,12),(12,12)],
          [(5,7),(13,7)], [(5,9),(13,9)], [(9,4),(9,12)]],
}


def panel(grid, starts, top, glyphs, weight, colour, diameter):
    cols, rows = grid
    matrix = Image.new('1', grid)
    pen = ImageDraw.Draw(matrix)
    for letter, start in zip('神奈川中央交通', starts):
        for stroke in glyphs[letter]:
            pen.line([(start+x, top+y) for x,y in stroke], fill=1, width=weight)

    # Supersample the round lenses before reducing to the packed atlas.
    scale = 3
    width, height = 864, 168
    dx, dy = width*scale/cols, height*scale/rows
    image = Image.new('RGB', (width*scale, height*scale), (11,17,17))
    leds = ImageDraw.Draw(image)
    for y in range(rows):
        for x in range(cols):
            ink = colour if matrix.getpixel((x,y)) else (25,30,31)
            cx, cy = (x+.5)*dx, (y+.5)*dy
            rx, ry = diameter*dx/2, diameter*dy/2
            leds.ellipse((cx-rx,cy-ry,cx+rx,cy+ry), fill=ink)
    return image.resize((width,height),Image.Resampling.LANCZOS)


def draw(output):
    # Each 300 px strip has the original UV layout. Strip 0 is at the
    # bottom in Blender UV space and retains the original pictogram pixels.
    sheet = Image.new('RGB',(864,900),(9,14,15))
    starts = (11,34,56,78,101,124,147)
    sheet.paste(panel((177,36),starts,5,FRONT,2,(239,247,255),.51),(0,600))
    sheet.paste(panel((177,49),starts,12,FRONT,2,(239,247,255),.51),(0,300))
    sheet.paste(panel((128,29),range(5,108,17),4,REAR,1,(255,117,37),.55),(0,0))
    for col in (0,1):
        badge=Image.new('RGB',(128,128),(22,88,143))
        b=ImageDraw.Draw(badge)
        ink=(237,242,235)
        if col==1:
            b.ellipse((54,15,73,34),fill=ink)
            b.arc((20,51,87,111),58,305,fill=ink,width=7)
            b.line([(58,41),(63,67),(85,67),(99,93),(110,90)],fill=ink,width=8,joint='curve')
            b.line([(61,55),(81,55)],fill=ink,width=6)
        else:
            b.ellipse((29,15,48,34),fill=ink)
            b.line([(37,41),(38,66),(25,99)],fill=ink,width=8,joint='curve')
            b.line([(38,65),(51,95)],fill=ink,width=7)
            b.line([(39,42),(54,55),(65,54)],fill=ink,width=6)
            b.line([(60,50),(76,87),(100,87)],fill=ink,width=5)
            b.pieslice((65,42,111,85),0,180,fill=ink)
            b.ellipse((70,90,81,101),fill=ink);b.ellipse((94,90,105,101),fill=ink)
        sheet.paste(badge,(col*128,772))
    sheet.save(output)

if __name__=='__main__':
    draw(sys.argv[1])
