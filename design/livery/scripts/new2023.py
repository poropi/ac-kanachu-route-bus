"""2023年塗装。前後の板はエルガ実車、側面の長手位置は公式側面図が基準。"""
from artwork import lettering, logo, rect

RED = "#EC2430"
ORANGE = "#DE7839"
CREAM = "#EADAC2"
BLUE = "#0D55D9"
WHITE = "#FEFEFC"
SMALL_TYPE = "#707885"

# x座標は小さい公式4面図における原寸画素。細線のサブピクセル位置は
# 大判図の同じ移行部（橙4本・地色4本）で線幅を判読して内挿した。
# 順序は車の前から後。運転席側の公式立面は車の前が画像の右側。
TRANSITIONS = {
    "LEFT": (231.0, 264.0, 264.6, 268.6, 269.8, 272.7, 274.2, 276.2, 278.8,
             279.8, 436.3, 437.2, 439.8, 441.8, 443.5, 446.4, 447.6, 451.6, 452.2, 476.0),
    "RIGHT": (441.0, 408.4, 407.8, 403.8, 402.6, 399.7, 398.0, 396.0, 393.4,
              392.5, 235.8, 234.7, 232.1, 230.1, 228.6, 225.5, 224.3, 220.3, 219.7, 199.0),
}


def station(side, pixel):
    """元図の車体両端を保存モデルの10.430 mに合わせる。"""
    front, tail = (146.5, 525.0) if side == "LEFT" else (526.0, 147.0)
    return (pixel - front) * 10.430 / (tail - front)


def bands(face):
    # 同じ色面が腰板・窓上・屋根肩の順に続く。
    # 車幅左右で数cm異なる境界は屋根中央へ線形に接続する。
    left = [station("LEFT", p) for p in TRANSITIONS["LEFT"]]
    right = [station("RIGHT", p) for p in TRANSITIONS["RIGHT"]]
    colors = [ORANGE, CREAM] * 10
    # 配列中央の長い中央部分はクリーム。その次は橙から細線が始まる。
    colors[-1] = RED
    marks = rect(-1, -1, 14, 6, RED)
    for i, color in enumerate(colors):
        if face == "ROOF":
            a, b = left[i], right[i]
            marks += (f'<path fill="{color}" d="M {a} -1 H 12 V 4 H {b} '
                      f'V 2.39 L {a} .095 Z"/>')
        else:
            x = left[i] if face == "LEFT" else right[i]
            marks += rect(x, -1, 12 - x, 6, color)
    return marks


def artwork(face):
    if face == "HVAC":
        return rect(-1, -1, 14, 6, CREAM)
    if face == "ROOF":
        return bands(face)
    if face in ("LEFT", "RIGHT"):
        marks = bands(face)
        if face == "LEFT":
            x = station(face, 461.6)
            marks += logo(x, 1.838, station(face, 507.3) - x, .245, WHITE)
            marks += lettering("Non Step Bus", 5.28, 1.897, .86, .095, SMALL_TYPE)
        else:
            x = station(face, 507.7)
            marks += logo(x, 1.838, station(face, 462.4) - x, .245, WHITE, reverse=True)
        return marks
    marks = rect(-1, -1, 14, 6, RED)
    if face == "FRONT":
        # な39の台形の板。実車写真と同じカメラで、風防下から
        # ヘッドランプ内側の点検蓋の目地までを合わせる。
        marks += (f'<path fill="{CREAM}" d="M .424 1.925 H 2.061 '
                  'L 2.039 2.040 L 1.981 2.426 L 1.968 2.449 '
                  'L 1.940 2.460 H .545 L .517 2.449 L .504 2.426 '
                  'L .446 2.040 Z"/>')
        marks += logo(.830, 1.998, .825, .152, BLUE)
    elif face == "REAR":
        # ち85。窓直下から灯火の外側まで続く板と、灯火の下で
        # わずかに外へ張り出し、赤いバンパーの目地で終わる点検蓋。
        # 上段の黒い縁は窓下で細く、灯火の高さでは数px見える。
        marks += (f'<path fill="#362D29" d="M .148 1.097 H 2.337 '
                  'L 2.357 1.883 H .128 Z"/>')
        marks += (f'<path fill="{CREAM}" d="M .151 1.097 H 2.334 '
                  'V 1.883 H 2.348 V 2.495 H .137 V 1.883 H .151 Z"/>')
        marks += logo(.825, 1.218, .833, .154, BLUE)
    return marks
