"""Original print, upholstery and instrument artwork for the LV290 interior."""
from pathlib import Path
import math
import random
import sys
from PIL import Image, ImageDraw, ImageFont

OUT=Path(sys.argv[1])
OUT.mkdir(exist_ok=True,parents=True)
JP=next(Path('/System/Library/Fonts').glob('*角*W5.ttc'))
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
BOLD='/System/Library/Fonts/Supplemental/Arial Bold.ttf'

def font(sz, jp=False, bold=False):
    return ImageFont.truetype(str(JP if jp else BOLD if bold else FONT),sz)

def label(draw,xy,value,sz,color,jp=False,bold=False,anchor='mm'):
    draw.text(xy,value,fill=color,font=font(sz,jp,bold),anchor=anchor)

def save(im,name):
    im.save(OUT/(name+'.png'),optimize=True)

def gauge(speed):
    im=Image.new('RGB',(768,768),'#181c22')
    d=ImageDraw.Draw(im)
    def point(a,r):
        t=math.radians(a)
        return (384+math.sin(t)*r,384-math.cos(t)*r)
    end=105 if speed else 68
    num=80 if speed else 40
    for i in range(num+1):
        a=-103+(end+103)*i/num
        major=i%(10 if speed else 10)==0
        middle=i%5==0
        col='#ef6a50' if not speed and i>=30 else '#f2f1e9'
        d.line((point(a,307 if major else 318 if middle else 329),point(a,346)),fill=col,width=7 if major else 4)
        if major or (not speed and i==40):
            label(d,point(a,264),str(i*2 if speed else i//10),54,col,bold=True)
    if not speed:
        for i in range(100):
            a=-103+171*(.75+.25*i/100)
            d.line((point(a,350),point(a,358)),fill='#e44936',width=5)
    label(d,(384,452),'km/h' if speed else 'x1000 r/min',37,'#d4d7d4')
    if speed:
        d.rounded_rectangle((240,515,530,581),9,fill='#34302b',outline='#111417',width=6)
        label(d,(385,548),'018637 km',39,'#ffb671')
    else:
        label(d,(384,553),'ENGINE',22,'#a8adb2',bold=True)
    save(im,'speed' if speed else 'rpm')

def textile(name,base,palette,driver=False):
    rand=random.Random(15)
    im=Image.new('RGB',(256,256),base)
    d=ImageDraw.Draw(im)
    for j in range(10 if driver else 18):
        for i in range(12 if driver else 17):
            x=(i+.65*rand.random())*(256/(12 if driver else 17))
            y=(j+.8*rand.random())*(256/(10 if driver else 18))
            c=rand.choice(palette)
            w=rand.randint(5,15) if driver else rand.randint(2,8)
            for dx in (-256,0,256):
                for dy in (-256,0,256):
                    X=x+dx; Y=y+dy
                    d.polygon([(X,Y),(X+w,Y-4),(X+w-2,Y+5),(X-2,Y+9)],fill=c)
    px=im.load()
    for y in range(256):
        for x in range(256):
            f=rand.randrange(-7,8)+(4 if (x%3==0) != (y%3==0) else -3)
            px[x,y]=tuple(max(0,min(255,k+f)) for k in px[x,y])
    save(im,name)

def panel(name,size,bg):
    im=Image.new('RGB',size,bg)
    return im,ImageDraw.Draw(im)

def graphics():
    gauge(True); gauge(False)
    textile('moquette','#185893',['#2471a9','#18528a','#23649a','#4083ad','#194c83'])
    textile('priority','#204888',['#345ba1','#295397','#3272aa','#233c76'])
    textile('driver_cloth','#195793',['#2478aa','#2a66ab','#4e83c4','#244981','#b26380','#508b7c'],True)
    rnd=random.Random(315)
    im=Image.new('RGB',(256,256)); im.putdata([tuple(max(0,c+n) for c in (72,75,79)) for n in [rnd.randrange(-18,19) for _ in range(65536)]]);save(im,'linoleum')

    im,d=panel('fare',(1024,380),'#142234')
    d.rectangle((0,0,1024,95),fill='#eaf1ec')
    d.rectangle((0,0,120,95),fill='#176d65')
    label(d,(60,48),'長39',45,'white',True)
    label(d,(153,48),'次は　藤沢駅北口',54,'#142e35',True,anchor='lm')
    label(d,(995,52),'Fujisawa Sta.',24,'#395355',anchor='rm')
    for row in range(2):
        for col in range(8):
            i=row*8+col; x=col*128;y=95+row*142
            d.rectangle((x+1,y+1,x+126,y+139),outline='#536577',width=2)
            label(d,(x+64,y+28),'現金' if i==0 else str(i),31,'#e2e7df',i==0)
            label(d,(x+64,y+86),str(340-max(0,i-1)*10 if i<12 else 230),48,'#ffc86a',bold=True)
    save(im,'fare')
    im,d=panel('cluster',(350,172),'#90a888')
    label(d,(22,32),'N',52,'#263d32',bold=True,anchor='lm')
    label(d,(333,35),'11:42',34,'#283d32',anchor='rm')
    d.line((15,65,335,65),fill='#405844',width=3)
    label(d,(175,110),'ODO    018637 km',31,'#273e31')
    save(im,'cluster')
    im,d=panel('rockers',(384,512),'#383d41')
    for row,words in enumerate([['上昇','標準','下降'],['前扉','中扉','開閉'],['照明','室内','換気']]):
        for col,title in enumerate(words):
            x=col*128; y=row*170
            d.rounded_rectangle((x+17,y+7,x+109,y+158),14,fill='#303438',outline='#737775',width=3)
            label(d,(x+64,y+41),title,23,'#f0eee2',True)
            d.line((x+38,y+91,x+89,y+91),fill='#a2aaa5',width=4)
            d.rectangle((x+43,y+125,x+83,y+134),fill='#b5b98d')
    save(im,'rockers')
    im,d=panel('radio',(760,170),'#35393b')
    d.rounded_rectangle((30,24,342,103),8,fill='#8e9c84')
    label(d,(181,64),'FM  84.7 MHz',33,'#283728',bold=True)
    for i in range(6):
        x=364+i*60;d.rounded_rectangle((x,27,x+50,94),5,fill='#202429')
        label(d,(x+25,58),str(i+1),20,'#deded2')
    label(d,(360,134),'AM / FM     •     TRANSIT AUDIO',17,'#c5cace',bold=True)
    save(im,'radio')
    im,d=panel('pay_screen',(440,260),'#14242d')
    d.rectangle((0,0,440,63),fill='#17455b')
    label(d,(220,32),'運賃精算',37,'#edf1ed',True)
    label(d,(220,151),'230 円',75,'#ffda7b',True)
    label(d,(220,222),'おとな　1人',24,'#b2d0d6',True)
    save(im,'pay_screen')
    for name,text1,text2,bg,fg in [
        ('priority_sign','優先席','PRIORITY SEAT','#fff8ed','#a35135'),
        ('ticket','整理券','乗車時にお取りください','#ece9da','#af3b37'),
        ('stop','とまります','STOP','#973e30','#fff4d8'),
        ('fare_slot','運賃投入口','FARE  /  COINS','#f5f3e5','#333b40'),
        ('exit_sign','出口','EXIT','#f5f3e8','#335a4c'),
        ('boarding','入口','ENTRANCE','#f5f3e8','#335a4c'),
        ('notice','走行中の移動はご遠慮ください','車内事故防止にご協力ください','#f2edda','#46494a'),
        ('partition_sign','乗務員室','安全運行にご協力ください','#e8e5da','#354c53')]:
        im,d=panel(name,(540,184),bg)
        d.rounded_rectangle((4,4,535,179),10,outline=fg,width=3)
        label(d,(270,65),text1,44 if len(text1)<8 else 30,fg,True)
        label(d,(270,136),text2,25,fg,True)
        save(im,name)
    im,d=panel('ic',(320,300),'#252f38')
    d.ellipse((48,27,271,251),fill='#1769ae',outline='#6aa3c4',width=6)
    label(d,(155,119),'IC',77,'#f1f6f3',bold=True)
    label(d,(160,191),'タッチ',27,'white',True)
    label(d,(160,274),'IC CARD READER',17,'#c6cfd3',bold=True)
    save(im,'ic')
    im,d=panel('telltales',(768,82),'#23272a')
    for i,(symbol,color) in enumerate([('◀','#77ac85'),('ABS','#dca252'),('P','#ee7364'),('!', '#db644f'),('D','#d4a359'),('N','#8fae88'),('▶','#78aa87')]):
        x=7+i*109
        d.rounded_rectangle((x,8,x+97,74),9,fill='#303738',outline='#535955',width=2)
        label(d,(x+48,40),symbol,34,color,True)
    save(im,'telltales')

if __name__=='__main__':
    graphics()
