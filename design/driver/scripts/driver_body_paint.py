"""Paint original cloth, embroidery and leather into the driver's UV atlas."""
import math
import sys

import numpy as np

from PIL import Image, ImageDraw, ImageFont

S = 2
W, H = 2048, 1536
canvas = Image.new("RGB", (W*S, H*S), "#393646")
draw = ImageDraw.Draw(canvas)
ox = 0


def pts(points):
    return [(round((x+ox)*S), round(y*S)) for x, y in points]


def fill(points, color):
    draw.polygon(pts(points), fill=color)


def line(points, color, width=1):
    draw.line(pts(points), fill=color, width=max(1, round(width*S)), joint="curve")


def curve(points):
    """Interpolated knots of an open cloth seam."""
    path = []
    p = [points[0], *points, points[-1]]
    for a,b,c,d in zip(p,p[1:],p[2:],p[3:]):
        for step in range(8):
            t = step / 8
            path.append(tuple(.5*((2*j)+(-i+k)*t+(2*i-5*j+4*k-l)*t*t+
                                  (-i+3*j-3*k+l)*t**3) for i,j,k,l in zip(a,b,c,d)))
    return path+[points[-1]]


def seam(points, color, width=1):
    line(curve(points),color,width)


def fold(points, width, color):
    center = curve(points)
    left, right = [], []
    for i,(x,y) in enumerate(center):
        a,b=center[max(0,i-1)],center[min(len(center)-1,i+1)]
        dx,dy=b[0]-a[0],b[1]-a[1]
        n=math.hypot(dx,dy) or 1
        q=width*math.sin(math.pi*i/(len(center)-1))**.8
        left.append((x-dy/n*q,y+dx/n*q))
        right.append((x+dy/n*q,y-dx/n*q))
    fill(left+right[::-1],color)


def reflected(points,sign):
    return [(512+sign*(x-512),y) for x,y in points]


def textile(back):
    # Silhouette and panel volume are supplied by the 3D cloth surface.
    fill([(305,275),(718,275),(718,1435),(305,1435)],"#393747")
    for side in (-1,1):
        def P(points):
            return reflected(points, side)
        # Long tailoring seams from armhole to hip.
        seam(P([(605,358),(598,398),(588,440),(578,479),(569,540),(575,604),(593,688),(603,748)]),
             "#2e2b39",1.55)
        seam(P([(606,356),(600,400),(590,441),(580,479),(571,541),(577,604),(595,689)]),
             "#424050",.7)
        fold(P([(630,398),(604,440),(579,464)]),2.2,"#33313f")
        fold(P([(590,488),(578,531),(571,548)]),1.4,"#383443")
        fold(P([(571,544),(581,565),(600,577)]),2,"#302d3b")
        if back:
            fold(P([(600,533),(571,551),(527,558)]),4,"#322f40")
            fold(P([(606,545),(572,562),(535,565)]),2,"#403c4c")
        # Pressed trouser crease, side seams, bent-knee and ankle creases.
        seam(P([(590,760),(587,831),(586,909),(581,985),(580,1022),(587,1089),
                (590,1184),(585,1320),(581,1409)]),"#2c2b38",1.7)
        seam(P([(592,762),(589,832),(588,911),(583,986),(582,1021)]),"#454151",1)
        seam(P([(647,769),(635,856),(624,945),(617,1000),(622,1072),(630,1151),
                (623,1256),(619,1377)]),"#302c3b",1.35)
        for path,thick,color in [
                ([(515,774),(536,790),(555,794)],3.0,"#2e2b39"),
                ([(614,762),(595,778),(573,786)],2.5,"#33303e"),
                ([(613,993),(607,1005),(600,1012)],2.5,"#302d3a"),
                ([(614,1005),(604,1021),(594,1035)],3,"#444050"),
                ([(532,1045),(542,1060),(551,1085)],3.1,"#302f3d"),
                ([(540,1296),(554,1324),(572,1345)],3.2,"#322e3e"),
                ([(620,1306),(610,1332),(595,1353)],3.7,"#302b39"),
                ([(609,1336),(598,1355),(583,1365)],2.5,"#423e4e"),
                ([(548,1382),(565,1371),(584,1366)],2.6,"#302c3c"),
                ([(617,1393),(606,1390),(596,1384)],2,"#302c3a")]:
            fold(P(path),thick,color)
        # Broader, angular folds over the top of the thigh and at the break in the trouser.
        for path,thick,color in [
            ([(512,758),(530,774),(555,779)],4.2,"#302c3b"),
            ([(518,766),(536,777),(551,787)],3.5,"#413b50"),
            ([(628,746),(603,752),(583,765)],3.2,"#403b50"),
            ([(615,988),(613,1004),(602,1022)],3.5,"#302d3d"),
            ([(544,1052),(549,1060),(556,1079)],3.7,"#464051"),
            ([(545,1376),(558,1355),(570,1346)],4.2,"#484353"),
            ([(611,1393),(607,1380),(592,1366)],3.6,"#302b3b")]:
            fold(P(path),thick,color)
        seam(P([(548,1402),(575,1406),(602,1407),(619,1404)]),"#272632",1.5)
    if back:
        seam([(516,320),(516,393),(516,470),(515,541),(517,620),(518,740)],"#282735",2)
        seam([(518,330),(518,446),(517,542),(519,621),(520,738)],"#454151",.8)
        seam([(348,727),(400,737),(452,742),(511,744),(570,741),(620,735),(665,726)],
             "#282634",2)
        seam([(382,770),(419,791),(457,799),(493,793),(513,781),(536,790),(569,796),(606,789),(648,770)],"#2e2a38",2)
        return
    # Center closure, buttonhole welts and upper edge of lower front panels.
    seam([(518,454),(524,482),(524,560),(523,620),(518,680),(509,726),(497,744)],"#252431",2.4)
    seam([(521,476),(526,508),(526,576),(525,625),(520,683),(512,724)],"#494454",.8)
    for yy in (496,563,629):
        line([(497,yy+1),(513,yy+1)],"#262432",2.7)
        line([(498,yy+2.3),(510,yy+2.3)],"#5c5665",.9)
    for side in (-1,1):
        P=lambda p:reflected(p,side)
        seam(P([(513,706),(520,727),(532,741),(554,743),(606,738),(661,727)]),"#292734",2.0)
        flap=P([(559,596),(619,594),(629,622),(570,627),(565,624)])
        fill(flap,"#252535")
        fill(P([(561,598),(618,596),(625,619),(570,622),(567,619)]),"#444152")
        line(P([(561,600),(566,618),(569,623),(625,620)]),"#397cc5",3.4)
        line(P([(563,598),(618,596)]),"#514b5b",1.0)
    # Left breast welt, original white embroidery and blank card.
    fill([(556,417),(611,418),(611,428),(557,427)],"#2a2937")
    line([(559,418),(610,419)],"#4b4656",1)
    word_font=ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",11*S)
    draw.text(pts([(565,398)])[0],"Kanachu",font=word_font,fill="#f2f1fa",stroke_width=0)
    fill([(566,436),(611,436),(611,457),(566,457)],"#242632")
    fill([(569,438),(609,438),(609,454),(569,454)],"#f9f9ff")
    line([(570,439),(607,439)],"#d5d3db",1)
    fill([(586,419),(594,419),(594,440),(586,440)],"#373640")
    fill([(588,420),(592,420),(592,438),(588,438)],"#c6c4cc")
    line([(589,422),(589,434)],"#f7f6f3",1)
    # Triangular opening reveals shirt. Folded shirt collar and silk tie.
    fill([(476,292),(548,292),(549,310),(530,322),(513,329),(494,320),(473,313)],"#f1bba7")
    fill([(474,310),(490,304),(512,320),(535,304),(551,311),(555,341),(514,455),(475,353)],"#eeedf6")
    fill([(499,328),(516,322),(529,328),(535,340),(521,357),(528,405),(513,452),(497,414),(506,357),(494,341)],"#242d48")
    tie=[(500,329),(516,324),(527,329),(532,339),(518,355),(526,405),(513,448),(498,410),(508,355),(496,342)]
    fill(tie,"#37496e")
    # Clip woven diagonal silk stripes to the knot and blade.
    mask=Image.new("1",canvas.size)
    ImageDraw.Draw(mask).polygon(pts(tie), fill=1)
    pattern=canvas.copy()
    pd=ImageDraw.Draw(pattern)
    for y in range(294,480,23):
        pd.line(pts([(482,y+30),(539,y-12)]), fill="#8aa9d6",width=4*S)
        pd.line(pts([(482,y+33),(539,y-9)]), fill="#536b98",width=2*S)
    canvas.paste(pattern,mask=mask)
    for side in (-1,1):
        def P(path):
            # Button closure overlaps on the wearer’s left. The two lapel tips share one edge.
            return [(xx+(0.18*max(0,p-419) if p>419 else 0),p) for xx,p in reflected(path,side)]
        fill(P([(512,324),(537,303),(550,308),(548,333),(535,360),(526,341)]),"#a9a7b6")
        fill(P([(512,324),(537,305),(548,309),(546,333),(535,355),(528,339)]),"#faf9ff")
        fill(P([(547,310),(570,325),(584,354),(572,357),(587,367),(566,401),(526,462),(514,482),(517,451),(542,377),(548,348)]),"#282736")
        fill(P([(548,313),(568,327),(582,353),(568,356),(583,369),(563,399),(527,456),(517,469),(520,451),(544,375),(550,346)]),"#3e3c4b")
        line(P([(568,327),(582,353),(568,356)]),"#3679bf",3.2)
        line(P([(570,361),(583,369),(565,396),(529,452),(518,469)]),"#3c82c8",3.3)
        line(P([(580,368),(564,393),(528,449)]),"#65a0d4",.8)
    fill([(487,434),(511,456),(519,472),(523,488),(514,475)],"#343244")
    line([(515,468),(521,478),(523,488)],"#3a80c9",3.0)
    seam([(514,697),(513,714),(507,731),(498,741),(488,744)],"#211e30",2.0)
    seam([(514,704),(521,728),(532,741),(547,744)],"#242132",2.2)


textile(False)
ox=1024
textile(True)
ox=0

# The sleeve UV runs around its whole circumference, with the seam under the arm.
fill([(15,274),(273,274),(273,734),(15,734)],"#393746")
for p,w,c in [
    ([(24,321),(66,332),(106,346)],3,"#413e4d"),
    ([(55,350),(90,367),(130,374)],2.6,"#33303d"),
    ([(56,372),(82,384),(114,385)],3.7,"#302e3d"),
    ([(83,386),(129,399),(156,405)],3,"#423d4d"),
    ([(92,399),(129,413),(155,414)],3.4,"#302e3c"),
    ([(182,408),(157,425),(140,432)],2.7,"#322f40"),
    ([(222,459),(192,470),(168,476)],2.6,"#2f2e3c"),
    ([(41,469),(79,489),(121,497)],3.6,"#322f3d"),
    ([(45,475),(83,495),(106,497)],1.8,"#45404f"),
    ([(115,495),(98,504),(72,509)],2.6,"#302e3d"),
    ([(192,485),(170,499),(149,509)],3.1,"#433f50"),
    ([(210,504),(191,515),(163,519)],3.5,"#322f3e"),
    ([(100,542),(86,562),(70,587)],2.1,"#373442")]:
    fold(p,w,c)
seam([(26,304),(28,377),(36,435),(36,490),(34,560),(31,704)],"#2b2937",1.5)
line([(16,647),(271,647)],"#252a3a",6)
line([(16,646),(271,646)],"#397dc8",5)
line([(16,644),(271,644)],"#5195d6",1)
line([(16,697),(271,697)],"#272633",2)

# Small islands share one texture with the uniform. Dedicated material slots set roughness.
colors={
    "white":"#f3f0f7", "ink":"#252431", "silver":"#bebac0", "rim":"#686570",
    "shine":"#f0edef", "navy":"#373645", "blue":"#3b7bc4", "skin":"#f4ccba",
    "sole":"#232229", "shoe":"#302d35", "band":"#39353c", "thread":"#56505a",
    "welt":"#403a43","shirt_shadow":"#ccc9d8"
}
for i,c in enumerate(colors.values()):
    x=18+i*12
    draw.rectangle(pts([(x-5,39),(x+5,51)]),fill=c)
# Painted patent-leather highlights. The U-axis circles the shoe; V goes heel to toe.
fill([(292,62),(749,62),(749,247),(292,247)],"#302c35")
for path,w,color in [
    ([(534,69),(545,85),(548,100),(544,121)],4,"#534d59"),
    ([(544,103),(540,130),(530,140)],6,"#625a66"),
    ([(531,153),(541,177),(550,199),(549,219)],6,"#443d49"),
    ([(466,153),(470,177),(476,201),(487,222)],7,"#5e5765"),
    ([(470,176),(476,195),(487,210),(499,214)],4.0,"#aaa1ad"),
    ([(470,180),(477,197),(486,205)],1.9,"#e1dbe2"),
    ([(507,224),(525,229),(540,226),(548,217)],2.8,"#77717c"),
    ([(556,225),(566,217),(574,201)],2.6,"#8d8792")]:
    fold(path,w,color)

# Shift the neutral grey of woven cloth toward the blue-violet in the turnaround.
# Metallic fittings, exposed skin, shirt whites and the two printed logos retain their own palette.
im=np.array(canvas.resize((W,H),Image.Resampling.LANCZOS)).astype(np.int16)
r,g,b=im[:,:,0].copy(),im[:,:,1].copy(),im[:,:,2].copy()
yy,xx=np.ogrid[:H,:W]
cloth=(r>27)&(r<104)&(np.abs(r-g)<12)&(b>r+2)&(yy>=276)
for idx,delta in enumerate((-6,-6,2)):
    im[:,:,idx]+=cloth*delta
Image.fromarray(np.clip(im,0,255).astype('uint8')).save(sys.stdout.buffer,format="PNG",optimize=False)
