"""Driver station, animated instrument pivots, fare equipment and operator guard."""
import math
from geometry import Part, empty, rot, tr
from cabin import cushion

EYE=(.642,3.407,1.985)
HUB=(.642,4.098,1.392)
PANEL=(.642,4.473,1.485)
RAKE=24
TILT=-32


def lathe(p,c,rings,mat,n=48):
    x,y,z=c
    p.loft([[(x+r*math.cos(i*math.tau/n),y+r*math.sin(i*math.tau/n),z+h)
              for i in range(n)] for h,r in rings],mat)


def steering(root,m):
    pivot=empty('STEER_HR',root,tr(*HUB) @ rot('X',-180+RAKE))
    pivot['rim_plane_degrees_from_horizontal']=RAKE
    p=Part('Steering_Rim',pivot)
    p.tube([(.232*math.cos(i*math.tau/80),.232*math.sin(i*math.tau/80),0)
            for i in range(80)],.016,m['grip'],16,closed=True)
    p.finish()
    p=Part('Steering_Spokes_and_Pad',pivot)
    for s in (-1,1):
        # Tapered moulded bridges meet lower left and lower right of the rim.
        rings=[]
        for x,y,z,wide,thick in [(s*.078,.024,.017,.077,.042),(s*.132,.054,.012,.051,.031),
                                   (s*.190,.089,.005,.039,.027),(s*.204,.105,0,.045,.026)]:
            rings.append([(x,y+wide*math.cos(i*math.tau/12)/2,z+thick*math.sin(i*math.tau/12)/2) for i in range(12)])
        p.loft(rings,m['grip'])
    # Slightly domed horn pad, broad shoulders with rounded lower corners.
    outline=[(-.069,-.093),(.069,-.093),(.084,-.084),(.113,-.027),(.121,.030),(.102,.064),
             (.078,.077),(-.078,.077),(-.102,.064),(-.121,.030),(-.113,-.027),(-.084,-.084)]
    rings=[[(x*sc,y*sc,z) for x,y in outline] for z,sc in [(-.029,.83),(-.025,.94),(-.018,1),(.015,1),(.039,.83)]]
    p.loft(rings,m['pad'])
    lathe(p,(0,-.026,-.029),[(-.002,.032),(0,.036),(.003,.035)],m['grip'])
    for j in range(4):
        p.box((0,-.031+j*.003,-.032),(.033,.0009,.001),m['dash'],0)
    p.finish()
    p=Part('Steering_Column_and_Stalks',root)
    with p.at(tr(*HUB) @ rot('X',-180+RAKE)):
        lathe(p,(0,0,0),[(.028,.048),(.065,.054),(.10,.068),(.16,.071),(.29,.049),(.39,.049)],m['dash'])
        for k in range(6):
            lathe(p,(0,0,.205+k*.012),[(0,.051),(.004,.061),(.009,.05)],m['grip'],24)
        for s in (-1,1):
            p.tube([(s*.044,-.015,.118),(s*.112,-.052,.112),(s*.166,-.068,.095)],.009,m['grip'],12,.014)
            p.tube([(s*.136,-.059,.103),(s*.187,-.072,.088)],.013,m['dash'],14)
    p.finish()


def dial(assembly,root,m,offset,speed):
    local=tr(*PANEL) @ rot('X',TILT) @ tr(offset,-.067,.0) @ rot('X',90)
    r=.069
    with assembly.at(local):
        lathe(assembly,(0,0,0),[(-.015,r+.010),(-.006,r+.011),(-.001,r+.009),(.002,r+.005),(.001,r)],m['bezel'])
        n=80; points=[(0,0,.002)]+[(r*math.cos(i*math.tau/n),r*math.sin(i*math.tau/n),.002) for i in range(n)]
        fs=[(0,i+1,(i+1)%n+1) for i in range(n)]
        uv=[(.5+x/(r*2),.5+y/(r*2)) for x,y,_ in points]
        assembly.geom(points,fs,m['speed' if speed else 'rpm'],maps=[[uv[j] for j in f] for f in fs])
    pivot=empty('ARROW_SPEED' if speed else 'ARROW_RPM',root,local @ tr(0,0,.004))
    pivot['face_angle_zero_clockwise_from_12']=-103
    pivot['face_angle_max_clockwise_from_12']=105 if speed else 68
    pivot['maximum']=160 if speed else 4000
    needle=Part('Speed_Pointer' if speed else 'Tachometer_Pointer',pivot)
    with needle.at(rot('Z',103)):
        needle.loft([[(-.0025,-.013,z),(.0025,-.013,z),(.0022,.035,z),(.0007,.058,z),(-.0007,.058,z),(-.0022,.035,z)] for z in [0,.0015]],m['needle'],False)
    lathe(needle,(0,0,.002),[(0,.0085),(.002,.0085),(.003,.0067)],m['grip'],24)
    needle.finish()


def dashboard(root,m):
    p=Part('Instrument_Fascia_and_Instruments',root)
    with p.at(tr(*PANEL) @ rot('X',TILT)):
        p.box((0,.033,-.053),(.793,.148,.309),m['dash'],.044)
        p.box((0,-.039,-.014),(.754,.019,.219),m['panel'],.019)
        # Cowl protrudes toward the driver. Its curved lip shades the dials.
        path=[(-.393,-.026,-.088),(-.380,-.044,.074),(-.350,-.044,.112),
              (.301,-.044,.112),(.355,-.040,.095),(.384,-.033,.045),(.389,-.030,-.092)]
        p.tube(path,.013,m['grip'],14,.037)
        for a,b in zip(path,path[1:]):
            p.geom([a,b,(b[0],b[1]+.133,b[2]+.002),(a[0],a[1]+.133,a[2]+.002)],[(0,1,2,3)],m['dash'])
        p.sticker(0,-.051,.020,.088,.044,m['cluster'])
        p.sticker(0,-.052,-.039,.092,.016,m['telltales'])
        for s in (-1,1):
            x=s*.223
            for j in range(2):
                with p.at(tr(x,-.053,.044-j*.086) @ rot('X',90)):
                    lathe(p,(0,0,0),[(0,.032),(.004,.032),(.006,.028)],m['grip'],24)
                    for k in range(9):
                        with p.at(rot('Z',105-26*k)):
                            p.box((0,.022,.007),(.0015,.006,.001),m['ivory'],0)
                    with p.at(rot('Z',35-j*54)):
                        p.box((0,.010,.009),(.002,.023,.001),m['needle'],0)
        for row in range(3):
            for col in range(3):
                x=.273+.034*col;z=.050-row*.055
                p.box((x,-.053,z),(.031,.016,.044),m['amber'] if (row,col)==(0,2) else m['grip'],.003)
                p.box((x,-.063,z),(.023,.012,.034),m['dash'],.003)
                w,h=.022,.032
                low=1-(row+1)/3;high=1-row/3
                p.geom([(x-w/2,-.070,z-h/2),(x+w/2,-.070,z-h/2),
                        (x+w/2,-.070,z+h/2),(x-w/2,-.070,z+h/2)],[(0,1,2,3)],m['rockers'],
                       maps=[[(col/3,low),((col+1)/3,low),((col+1)/3,high),(col/3,high)]])
        for col in range(2):
            x=-.330+.037*col
            p.box((x,-.055,-.006),(.030,.024,.072),m['grip'],.005)
            p.box((x,-.068,.012),(.015,.003,.003),m['ivory'],0)
    dial(p,root,m,-.13,False);dial(p,root,m,.13,True)
    p.finish()
    base=Part('Cab_Dash_and_Driving_Controls',root)
    base.box((.645,4.55,1.183),(.85,.23,.38),m['sidewall'],.047)
    base.box((-.144,4.478,1.205),(.741,.365,.281),m['sidewall'],.047)
    base.box((-.144,4.475,1.359),(.747,.384,.056),m['dash'],.039)
    base.box((-.142,4.490,1.389),(.648,.268,.009),m['panel'],.021)
    base.box((-.158,4.507,1.398),(.141,.091,.014),m['grip'],.012)
    with base.at(tr(.024,4.368,1.394) @ rot('X',-90)):
        base.sticker(0,0,0,.237,.06,m['notice'])
    base.box((-.145,4.570,.811),(.660,.234,.540),m['sidewall'],.028)
    base.box((-.145,4.447,.869),(.521,.020,.272),m['sill'],.020)
    base.box((-.145,4.431,.869),(.503,.015,.253),m['sidewall'],.016)
    base.box((.049,4.420,.959),(.057,.008,.016),m['grip'],.005)
    # Demister outlets follow the foot of the windshield and turn into the side trim.
    base.box((.053,4.646,1.297),(2.048,.094,.076),m['dash'],.030)
    for x in (-.73,-.36,.03,.42,.82):
        base.box((x,4.646,1.338),(.240,.041,.011),m['seal'],.012)
        for k in (-1,0,1):
            base.box((x,4.646+k*.009,1.344),(.208,.003,.003),m['ventblade'],0)
    base.box((-.162,4.290,1.263),(.299,.035,.080),m['grip'],.008)
    base.sticker(-.162,4.271,1.263,.276,.062,m['radio'])
    for x in (-.429,.109):
        base.box((x,4.285,1.268),(.094,.020,.056),m['vent'],.008)
        for k in range(4):
            base.box((x,4.272,1.250+.012*k),(.077,.006,.004),m['ventblade'],0)
    # Suspended microphone cradle and its flexible lead.
    base.box((.105,4.280,1.198),(.057,.030,.076),m['grip'],.011)
    base.box((.105,4.250,1.209),(.047,.029,.089),m['pad'],.016)
    for j in range(5):
        base.box((.105,4.234,1.225+j*.004),(.023,.003,.0017),m['grip'],0)
    cord=[(.105+.009*math.cos(j*.9),4.26+.009*math.sin(j*.9),1.164-j*.0018) for j in range(62)]
    cord.extend([(.111,4.27,1.034),(.122,4.30,1.046),(.122,4.32,1.108)])
    base.tube(cord,.0022,m['grip'],7)
    # AMT selector in its own housing beside the steering column.
    base.box((.187,4.141,.996),(.198,.315,.244),m['sidewall'],.052)
    base.box((.187,4.137,1.124),(.154,.240,.025),m['grip'],.039)
    base.tube([(.187,4.142,1.126),(.185,4.116,1.222)],.013,m['metal'])
    base.box((.185,4.111,1.226),(.058,.076,.059),m['pad'],.021)
    for j in range(4):base.box((.24,4.172-j*.025,1.138),(.011,.008,.002),m['ivory'],0)
    base.box((.651,3.963,.494),(.843,1.294,.292),m['wheeltrim'],.028)
    base.box((.651,3.963,.642),(.843,1.294,.012),m['floor'],.012)
    base.box((.642,4.219,.65),(.565,.548,.013),m['grip'],.022)
    for x,width in [(.60,.102),(.755,.061)]:
        base.tube([(x,4.31,.664),(x,4.347,.812)],.015,m['foot'])
        with base.at(tr(x,4.312,.801) @ rot('X',48)):
            base.box((0,0,0),(width,.143,.024),m['grip'],.012)
            for j in range(6):
                base.box((0,-.049+.019*j,.014),(width*.81,.005,.004),m['dash'],0)
    # Driver's right-hand switch ledge and handbrake.
    base.box((1.023,3.961,1.098),(.191,.918,.329),m['sidewall'],.037)
    base.box((1.023,3.966,1.267),(.180,.907,.027),m['sill'],.028)
    for j in range(4):
        for col in range(2):
            base.box((.985+.045*col,3.93+.064*j,1.289),(.031,.051,.019),m['grip'],.005)
    base.tube([(1.007,3.744,1.28),(.996,3.716,1.37)],.012,m['metal'])
    base.box((.994,3.706,1.372),(.037,.082,.033),m['pad'],.013)
    for x in (1.001,1.071):
        with base.at(tr(x,3.879,1.288) @ rot('X',6)):
            lathe(base,(0,0,0),[(0,.018),(.007,.020),(.021,.016)],m['grip'],16)
            base.box((0,0,.022),(.002,.017,.001),m['ivory'],0)
    base.finish()


def operator(root,m):
    p=Part('Drivers_Seat',root)
    with p.at(tr(.642,3.535,1.115)):
        cushion(p,.492,m,'driver_cloth',True)
        for x in (-.205,.205):
            p.box((x,0,-.12),(.047,.41,.069),m['foot'],.009)
        p.box((0,-.009,-.195),(.34,.35,.092),m['foot'],.023)
        for z in [-.245,-.29,-.335,-.38]:
            p.box((0,-.009,z),(.335,.341,.053),m['grip'],.03)
        p.box((0,-.012,-.448),(.392,.404,.059),m['foot'],.023)
    p.finish()
    guard=Part('Cab_Safety_Screen',root)
    for x in (.251,1.015):
        guard.tube([(x,3.255,1.102),(x,3.255,2.245)],.015,m['metal'],14)
    guard.box((.634,3.255,1.398),(.767,.036,.536),m['sidewall'],.026)
    guard.box((.634,3.255,1.959),(.739,.009,.594),m['guardglass'],.030)
    guard.tube([(.251,3.255,2.245),(.253,3.255,2.274),(1.000,3.255,2.274),(1.015,3.255,2.245)],.015,m['metal'],14,.03)
    guard.box((.635,3.255,1.660),(.774,.046,.024),m['sill'],.007)
    guard.sticker(.635,3.233,1.52,.241,.082,m['partition_sign'])
    guard.tube([(.251,3.255,1.42),(.188,3.34,1.42),(.188,3.684,1.42),(.188,3.72,.654)],.019,m['orange'],12,.055)
    guard.box((.192,3.481,1.154),(.015,.348,.45),m['guardglass'],.018)
    guard.finish()
    empty('DRIVER_EYE',root,tr(*EYE))


def fare_equipment(root,m):
    p=Part('Farebox_and_IC_Reader',root)
    with p.at(tr(-.177,3.923,.359)):
        p.box((0,.010,.086),(.296,.417,.146),m['foot'],.034)
        p.box((0,0,.477),(.334,.480,.685),m['sidewall'],.043)
        p.box((0,-.242,.457),(.255,.016,.493),m['sill'],.018)
        p.box((0,-.252,.455),(.226,.009,.457),m['sidewall'],.016)
        p.box((.072,-.263,.618),(.044,.012,.019),m['grip'],.005)
        p.box((0,0,.841),(.362,.505,.081),m['dash'],.034)
        p.box((.015,.128,.887),(.263,.171,.033),m['metal'],.017)
        p.box((.015,.117,.905),(.178,.045,.006),m['grip'],.013)
        for s in (-1,1):
            p.box((.015+s*.106,.124,.919),(.009,.144,.039),m['guardglass'],.004)
        p.box((.015,.060,.910),(.216,.008,.018),m['metal'],.003)
        with p.at(tr(.02,.188,.905) @ rot('X',-90)):
            p.sticker(0,0,0,.192,.042,m['fare_slot'])
        with p.at(tr(0,-.118,.894) @ rot('X',12)):
            p.box((0,0,0),(.202,.185,.031),m['bezel'],.023)
            with p.at(rot('X',-90)):
                p.sticker(0,-.017,0,.177,.150,m['ic'])
        p.tube([(-.096,.189,.875),(-.096,.20,1.071)],.019,m['foot'])
        with p.at(tr(-.069,.184,1.071) @ rot('X',-15)):
            p.box((0,0,0),(.205,.053,.151),m['panel'],.013)
            p.sticker(0,-.028,0,.163,.091,m['pay_screen'])
        # Returned coins drop into a cupped tray on the passenger side.
        p.box((-.170,-.040,.602),(.018,.160,.114),m['grip'],.014)
        p.box((-.200,-.040,.545),(.072,.166,.017),m['metal'],.008)
    p.finish()
    q=Part('Middle_Door_Ticket_Dispenser',root)
    with q.at(tr(-.90,-1.499,.315) @ rot('Z',165)):
        q.box((0,0,.348),(.145,.135,.676),m['foot'],.019)
        q.box((0,0,.819),(.271,.218,.402),m['sill'],.026)
        q.box((0,-.109,.851),(.247,.024,.288),m['sidewall'],.018)
        q.sticker(0,-.123,.923,.211,.069,m['ticket'])
        q.box((0,-.127,.817),(.139,.022,.035),m['grip'],.007)
        q.box((0,-.149,.809),(.046,.04,.002),m['ivory'],0)
        q.box((.169,-.023,.930),(.078,.155,.232),m['dash'],.022)
        q.sticker(.169,-.102,.933,.063,.101,m['ic'])
    q.finish()
    f=Part('Passenger_Fare_Display',root)
    with f.at(tr(-.225,3.985,2.326) @ rot('X',8)):
        f.box((0,.025,0),(.924,.103,.395),m['panel'],.034)
        f.box((0,-.024,0),(.882,.024,.354),m['grip'],.021)
        f.sticker(0,-.037,0,.851,.316,m['fare'])
        for x in [-.32,.32]:
            f.box((x,.032,.249),(.041,.068,.147),m['foot'],.008)
        for j in range(5):f.box((.352+j*.014,-.038,-.170),(.006,.002,.004),m['sill'],0)
    f.finish()
