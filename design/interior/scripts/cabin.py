"""N-wheelbase urban saloon: trimmed body, forward-facing seats and passenger hardware."""
import math
from mathutils import Vector
from geometry import Part, rot, tr


def deck(y):
    if y < -1.91:
        return .785
    if y < -1.58:
        return .530
    return .315 + max(0, y-3.30)*.029


def surface(part, coords, mat, reverse=False):
    coords=list(reversed(coords)) if reverse else coords
    part.geom(coords,[tuple(range(len(coords)))],mat)


def lining(root,m,ex):
    # The removable lining's polygon boundaries describe the actual gaps for doors,
    # floors, risers and wheel wells. Rebuild with different finish per face.
    p=Part('Saloon_Lining',root)
    for vs in ex['liner']:
        c=sum((Vector(v) for v in vs),Vector())/len(vs)
        if c.x < -1.16 and c.z < .45:
            continue  # use sill plates clear of the door mechanism
        if c.z > 2.5: key='headliner'
        elif max(v[2] for v in vs)-min(v[2] for v in vs)<.07: key='floor'
        elif abs(c.x)<.03 and abs(c.y+4.80)>.001 and abs(c.y-4.695)>.001: key='floor'
        elif c.z<1.10 and abs(abs(c.y)-2.65)<.66: key='wheeltrim'
        else:key='sidewall'
        pts=[]
        for x,y,z in vs:
            if abs(abs(abs(y)-2.65)-.61)<.0001:
                y+=math.copysign(.033,y-math.copysign(2.65,y))
            if y>3.29 and z<.38:
                z=deck(y)
            pts.append((x,y,z))
        normal=(Vector(pts[1])-Vector(pts[0])).cross(Vector(pts[2])-Vector(pts[0]))
        reverse=False
        if abs(normal.y)>abs(normal.x)+abs(normal.z):
            if abs(c.y-4.695)<.001: desired=-1
            elif abs(c.y+4.80)<.001 or abs(c.y+1.91)<.001 or abs(c.y+1.58)<.001: desired=1
            else: desired=math.copysign(1,c.y-math.copysign(2.65,c.y))
            reverse=normal.y*desired<0
        surface(p,pts,m[key],reverse)
    p.finish()
    mould=Part('Window_Reveals',root)
    for name,(low,high) in ex['windows'].items():
        sign=1 if name.startswith('Right') else -1
        a=max(-4.78,low[1]-.018); b=min(4.67,high[1]+.018)
        for y in [a,b]:
            mould.box((sign*1.095,y,1.916),(.044,.041,1.21),m['sidewall'],.012)
        mould.box((sign*1.105,(a+b)/2,1.318),(.09,b-a,.052),m['sill'],.012)
        mould.box((sign*1.095,(a+b)/2,2.504),(.055,b-a,.035),m['seal'],.009)
        if name.startswith('Right_Window_01'):
            mould.box((1.062,(a+b)/2,1.285),(.145,b-a,.064),m['dash'],.02)
    mould.finish()

    doors=Part('Door_Interior_Fittings',root)
    for name,(lo,hi) in ex['doors'].items():
        a,b=lo[1],hi[1]; mid=(a+b)/2
        doors.box((-1.070,mid,2.493),(.135,b-a+.02,.152),m['sidewall'],.024)
        doors.box((-1.070,mid,2.402),(.141,b-a+.02,.030),m['sill'],.01)
        z=deck(mid)
        with doors.at(tr(-1.08,mid,z+.013) @ rot('X',1.65 if mid>0 else 0)):
            doors.box((0,0,0),(.16,b-a-.03,.016),m['edge'],.003)
            for k in range(4):
                doors.box((-.059+k*.034,0,.009),(.004,b-a-.06,.004),m['sill'],0)
        # Separate inner door leaf fittings sit inside the actual exterior glazing.
        for y in ([a+.077,mid,b-.077] if mid>0 else [a+.089,b-.083]):
            doors.box((-1.111,y,1.39),(.023,.030,1.97),m['seal'],.006)
        if mid<0:
            doors.box((-1.125,a+.241,.834),(.024,.40,.85),m['sidewall'],.02)
            doors.tube([(-1.115,b-.095,1.14),(-1.052,b-.095,1.19),
                        (-1.052,b-.095,1.76),(-1.115,b-.095,1.81)],.015,m['orange'],bend=.045)
        with doors.at(tr(-1.008,mid,2.495) @ rot('Z',90)):
            doors.sticker(0,0,0,.225,.079,m['exit_sign' if mid>0 else 'boarding'])
    doors.finish()
    step=Part('Stair_Nosings',root)
    for y,z in [(-1.58,.530),(-1.91,.785)]:
        step.box((0,y-.031,z+.002),(2.265,.061,.004),m['edge'],0)
        for d in (.015,.033):
            step.box((0,y-d,z+.0045),(2.23,.005,.002),m['grip'],0)
    step.finish()


def cushion(p,w,m,fabric,driver=False):
    # Longitudinal sections of a bucket shell from the seat nose up to the top.
    # Profile and lumbar bolsters are continuous across both halves.
    top=.69 if driver else .525
    profile=[(.222,-.037,.89),(.223,.008,.95),(.180,.033,1),(.090,.026,1),
             (-.065,.013,.98),(-.133,.035,.97),(-.150,.085,.94),
             (-.164,.18,.92),(-.183,.31,.95),(-.205,top-.064,.96),(-.215,top-.015,.93),(-.224,top,.84)]
    shell=[]; front=[]
    across=[-1,-.89,-.68,-.32,0,.32,.68,.89,1]
    for y,z,taper in profile:
        back=z>.075
        row=[]; base=[]
        for u in across:
            edge=abs(u)
            bolster=math.sin(edge*math.pi/1.65)**3
            v=(u*w*.5*taper,y+(.030*bolster if back else 0),z+(.019*bolster if not back else 0))
            row.append(v)
            base.append((v[0]*1.023,v[1]-(.030 if back else .010),v[2]-(.010 if back else .037)))
        front.append(row); shell.append(base)
    n=len(across); rows=len(front)
    quads=[(j*n+i,j*n+i+1,(j+1)*n+i+1,(j+1)*n+i) for j in range(rows-1) for i in range(n-1)]
    # U follows seat width, V follows arc length in the same direction on every seat.
    dist=[0.]
    for a,b in zip(profile,profile[1:]):
        dist.append(dist[-1]+math.hypot(a[0]-b[0],a[1]-b[1]))
    uv=[((across[i]+1)*w*1.9,dist[j]*3.8) for j in range(rows) for i in range(n)]
    p.geom([v for row in front for v in row],[f[::-1] for f in quads],m[fabric],True,[[uv[k] for k in f[::-1]] for f in quads])
    p.geom([v for row in shell for v in row],quads,m['back'],True)
    ids=list(range(n))+[j*n+n-1 for j in range(1,rows)]+list(range(rows*n-2,(rows-1)*n-1,-1))+[j*n for j in range(rows-2,0,-1)]
    inner=[v for row in front for v in row]; outer=[v for row in shell for v in row]
    p.loft([[inner[i] for i in ids],[outer[i] for i in ids]],m['piping'],True,False)
    if not driver:
        for side in (-1,1):
            p.box((side*w*.366,-.239,top-.09),(.040,.024,.063),m['back'],.009)
        p.tube([(-w*.37,-.237,top-.08),(-w*.36,-.239,top+.063),
                (w*.36,-.239,top+.063),(w*.37,-.237,top-.08)],.016,m['grip'],10,.043)


def seats(root,m):
    layout=[]
    def add(x,y,z,w=.448,kind='standard'):
        layout.append((x,y,z,w,kind))
    add(.868,2.42,1.408)
    for y in (1.44,.75,.06,-.64): add(.888,y,.764,.447,'fold')
    for y in (1.37,.65,-.06): add(-.884,y,.764,.45,'priority')
    for x in (.507,.913):add(x,-1.45,.818,.397)
    for y in (-2.12,-2.96,-3.69):
        for x in (-.920,-.514,.514,.920):
            add(x,y,1.465 if y> -3.3 else 1.425,.396)
    for i in range(5):add((i-2)*.448,-4.52,1.485,.44)
    for i,(x,y,z,w,kind) in enumerate(layout,1):
        p=Part(f'PassengerSeat_{i:02d}',root)
        with p.at(tr(x,y,z)):
            cushion(p,w,m,'priority' if kind=='priority' else 'moquette')
            s=-1 if x>0 else 1
            base=(1.099 if abs(abs(y)-2.65)<.645 and abs(x)>.604 else deck(y))
            if -3.29 < y < -2 and abs(x)>.29:base=1.099
            if y < -3.3:base=1.045
            if kind=='fold':
                p.tube([(s*-.18,.025,-.05),(s*-.18,.025,-.22),(s*-.21,-.095,-.26)],.027,m['metal'])
                p.tube([(s*.165,-.126,-.035),(s*.165,-.126,-.42)],.014,m['metal'])
            else:
                p.box((0,-.056,(base-z-.06)/2),(.095,.16,z-base-.06),m['foot'],.015)
                p.box((0,-.056,base-z+.009),(.20,.20,.018),m['foot'],.012)
            if kind in ('priority','fold') or i==1:
                p.tube([(s*w*.49,.101,-.054),(s*w*.49,.102,.165),(s*w*.49,.044,.205),
                        (s*w*.49,-.126,.205),(s*w*.49,-.174,.147)],.013,m['grip'],10,.04)
        obj=p.finish();obj['seat_number']=i;obj['seat_type']=kind;obj['facing']='+Y'
    rear=Part('Rear_Seat_Plinths',root)
    for x in [-.74,.74]:
        # Seat-side footboard alongside the rear wheel housing, level with its top.
        rear.box((math.copysign(.448,x),-2.649,.941),(.311,1.278,.315),m['wheeltrim'],.011)
        rear.box((math.copysign(.305,x),-2.649,1.100),(.021,1.258,.007),m['edge'],.003)
        rear.box((x,-3.79,.92),(.81,1.019,.27),m['wheeltrim'],.028)
    rear.box((0,-4.53,.915),(2.25,.52,.26),m['wheeltrim'],.02)
    rear.finish()


def stop_button(p,x,y,z,m,angle):
    with p.at(tr(x,y,z) @ rot('Z',angle)):
        p.box((0,0,0),(.064,.045,.126),m['buttoncream'],.013)
        p.box((0,-.026,-.021),(.045,.011,.046),m['stopred'],.013)
        p.sticker(0,-.024,.032,.048,.025,m['stop'])


def fittings(root,m):
    rail=Part('Saloon_Stanchions',root)
    for s,ys in [(-1,[2.00,1.00,.17,-1.49,-1.99]),(1,[3.04,1.88,.955,.25,-.43,-1.10,-1.86])]:
        for i,y in enumerate(ys):
            x=s*(.605 if y< -1.56 else .648)
            bottom=deck(y)
            if abs(abs(y)-2.65)<.646 and abs(x)>.605:bottom=1.099
            rail.tube([(x,y,bottom+.012),(x,y,1.37),(s*.54,y,1.67),(s*.54,y,2.40),(s*.59,y,2.57)],.016,m['orange'],12,.13)
            rail.tube([(x,y,bottom),(x,y,bottom+.048)],.029,m['metal'],12)
            rail.tube([(s*.54,y,2.31),(s*.54,y,2.355)],.022,m['joint'])
            if i%2==0:stop_button(rail,x,y,1.205 if bottom<.8 else 1.52,m,-90 if s>0 else 90)
    for s in [-1,1]:
        rail.tube([(s*.54,-4.44,2.336),(s*.54,3.20,2.336)],.016,m['metal'],14)
        for y in (-4.26,-3.31,-2.67,-1.76,-.38,.92,2.28,3.10):
            rail.tube([(s*.54,y,2.336),(s*.54,y,2.63)],.012,m['sill'])
        for y1,y2 in ([(-4.38,-1.56),(-.20,1.89),(2.04,3.49)] if s<0 else [(-4.37,2.04)]):
            rail.tube([(s*1.101,y1,1.548),(s*1.061,y1+.036,1.548),(s*1.061,y2-.036,1.548),(s*1.101,y2,1.548)],.013,m['orange'],10,.036)
        for j in range(15):
            y=-3.96+j*.481
            rail.tube([(s*.54,y-.025,2.336),(s*.54,y+.025,2.336)],.023,m['grip'],10)
            z=2.119 if y> -1.58 else 2.165
            rail.box((s*.54,y,(2.33+z)/2),(.010,.032,2.33-z),m['strap'],.004,0)
            # Triangle is in the aisle-facing YZ plane with a rounded grip.
            rail.tube([(s*.54,y,z+.018),(s*.54,y-.079,z-.099),(s*.54,y+.079,z-.099)],.0115,m['ivory'],10,.034,True)
    rail.finish()
    left=Part('Front_Luggage_Shelf',root)
    left.box((-.865,2.64,1.142),(.515,1.12,.085),m['sill'],.045)
    left.box((-.865,2.64,1.188),(.494,1.085,.014),m['grip'],.03)
    for y in (2.125,3.155):
        left.tube([(-1.086,y,1.19),(-1.086,y,1.42),(-.654,y,1.42),(-.654,y,1.19)],.019,m['orange'],12,.068)
    left.finish()
    trim=Part('Saloon_Signs_and_Trim',root)
    for y in [-.06,.65,1.37]:
        with trim.at(tr(-1.151,y,1.194) @ rot('Z',90)):
            trim.sticker(0,0,0,.242,.083,m['priority_sign'])
    for side in [-1,1]:
        for y in [-3.76,-2.13,.38,1.68]:
            if side<0 and -1.4<y<-.26:continue
            trim.box((side*1.147,y,1.03 if y != -2.13 else 1.202),(.014,.009,.49 if y != -2.13 else .16),m['sill'],0)
    # Recessed wheelchair restraints and access hatch occupy the unobstructed floor.
    for y in (-.63,.16,1.10):
        for x in (.28,.79):
            trim.box((x,y,.3168),(.071,.107,.003),m['metal'],.010)
            trim.box((x,y,.319),(.042,.072,.002),m['grip'],.008)
            trim.tube([(x-.016,y,.321),(x+.016,y,.321)],.0035,m['metal'],8)
    for x in (-.341,.341):
        trim.box((x,-.855,.3165),(.006,.81,.002),m['seal'],0)
    for y in (-1.26,-.45):
        trim.box((0,y,.3165),(.688,.006,.002),m['seal'],0)
    for side in (-1,1):
        for y in (-3.64,2.00):
            with trim.at(tr(side*1.107,y,2.516) @ rot('Z',-90*side)):
                trim.sticker(0,-.030,0,.315,.068,m['notice'])
    trim.finish()


def ceiling(root,m):
    p=Part('Ceiling_Ducts_and_Lighting',root)
    for s in [-1,1]:
        # A formed, sloped side duct runs above the windows and carries the grilles.
        ring=[(s*x,z) for x,z in ((.51,2.708),(.54,2.635),(.83,2.566),(1.052,2.512),(1.065,2.699))]
        p.loft([[(x,y,z) for x,z in ring] for y in [-4.77,4.55]],m['headliner'],False)
        for y in [-4.04,-2.59,-1.14,.31,1.76,3.18]:
            with p.at(tr(s*.692,y,2.591) @ rot('Y',s*13)):
                p.box((0,0,.004),(.151,.55,.020),m['sill'],.02)
                p.box((0,0,-.006),(.120,.512,.008),m['vent'],.012)
                for j in range(5):
                    p.box(((j-2)*.023,0,-.011),(.010,.484,.010),m['ventblade'],.003,0)
        for y in ([-3.52,.13] if s<0 else [-1.84,1.97]):
            p.box((s*.40,y,2.681),(.128,1.38,.060),m['sill'],.05)
            p.box((s*.40,y,2.653),(.108,1.285,.039),m['lamp'],.043)
            for k in (-1,1):
                p.box((s*.40,y+k*.637,2.655),(.113,.024,.035),m['sidewall'],.008)
    for y in [-3.56,-1.8,.02,1.85,3.55]:
        p.box((0,y,2.714),(1.04,.012,.008),m['sill'],0)
    for y in [-2.55,1.01]:
        p.box((0,y,2.707),(.585,.65,.018),m['sill'],.038)
        p.box((0,y,2.696),(.560,.627,.015),m['headliner'],.031)
        p.box((0,y-.236,2.683),(.104,.026,.016),m['grip'],.01)
    p.finish()
