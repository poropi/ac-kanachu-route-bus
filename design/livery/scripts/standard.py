"""神奈中標準色。寸法は、ふ43の写真カメラで得た世界座標に基づく（m）。"""
from artwork import lettering, logo, rect


CREAM = "#D7CD8E"
SKIRT = "#B53139"
ORANGE = "#CA763A"
RED = "#902C26"
BLUE = "#3D5181"
INK = "#413123"
SILVER = "#A5ACB6"
HEIGHT = 3.105
WIDTH = 2.485
LENGTH = 10.43


def band_path(points, color):
    """入力は車体の左端または前端からの距離と路面からの高さ。"""
    vertices = " ".join(f"{u:.4f},{HEIGHT-z:.4f}" for u, z in points)
    return f'<polygon points="{vertices}" fill="{color}"/>'


def belt_line(sections, rim_top=.023, rim_bottom=.017):
    def ribbon(top_inset, bottom_inset, color):
        top = [(u, z_top-top_inset) for u, z_top, z_bottom in sections]
        base = [(u, z_bottom+bottom_inset) for u, z_top, z_bottom in reversed(sections)]
        return band_path(top + base, color)
    return ribbon(0, 0, RED) + ribbon(rim_top, rim_bottom, ORANGE)


def front_belt():
    # 窓の直下。ロゴ直下では帯の裾が約8 cm下がり、両端は前柱の角に沿って上がる。
    # 展開の前面座標の左は、車両を正面から見た時の左。
    center = WIDTH / 2

    def shape(top, base, drop, color):
        bottom = [(-1, base-.025), (.060, base-.025), (.320, base-.017),
                  (center-.35, base-.008), (center-.29, drop-.003),
                  (center+.30, drop+.007), (center+.35, base+.004),
                  (WIDTH-.25, base+.012), (WIDTH-.090, base+.014),
                  (WIDTH-.055, base+.020), (WIDTH+1, base+.022)]
        upper = [(-1, top+.082), (.032, top+.082), (.057, top+.031),
                 (.100, top+.004), (.130, top), (WIDTH-.130, top),
                 (WIDTH-.100, top+.004), (WIDTH-.057, top+.031),
                 (WIDTH-.032, top+.082), (WIDTH+1, top+.082)]
        return band_path(upper + list(reversed(bottom)), color)

    return shape(1.174, 1.002, .917, RED) + shape(1.150, 1.018, .933, ORANGE)


def artwork(face):
    design = rect(-1, -1, 14, 6, CREAM)
    if face in ("ROOF", "HVAC"):
        return design

    if face == "FRONT":
        design += rect(-1, HEIGHT-.597, 5, 2, SILVER)
        design += front_belt()
        design += logo(.988, HEIGHT-1.033, .503, .086, BLUE)
        design += lettering("Non-Step Bus", 1.057, HEIGHT-.865, .389, .055,
                            BLUE, font="serif")
        return design

    if face == "REAR":
        design += rect(-1, HEIGHT-.609, 5, 2, SILVER)
        design += belt_line([(-1, 1.235, 1.042), (0, 1.235, 1.042),
                            (WIDTH, 1.272, 1.084), (WIDTH+1, 1.272, 1.084)])
        design += logo(1.504, HEIGHT-1.988, .802, .145, BLUE)
        return design

    if face not in ("LEFT", "RIGHT"):
        raise ValueError(face)
    right = face == "RIGHT"
    design += rect(-1, HEIGHT-(.624 if right else .618), 14, 2, SKIRT)
    # 下端の銀灰色は、塗装されたバンパーの回り込み。後部エンジン点検蓋の前で止まる。
    design += rect(-1, HEIGHT-.624, 1.255, 2, SILVER)
    design += rect(9.970, HEIGHT-.624, 2.5, 2, SILVER)
    if right:
        design += belt_line([(-1, 1.248, .977), (.23, 1.248, .977),
                            (.30, 1.251, 1.036), (.44, 1.251, 1.055),
                            (5.5, 1.270, 1.075), (8.8, 1.272, 1.084),
                            (11.5, 1.272, 1.084)])
    else:
        design += belt_line([(-1, 1.256, 1.024), (.224, 1.256, 1.024),
                            (.25, 1.256, 1.033), (.29, 1.256, 1.064),
                            (9.9, 1.256, 1.064), (10.21, 1.235, 1.042),
                            (11.5, 1.235, 1.042)], rim_top=.024, rim_bottom=.016)
    # 雨樋の下の赤い見切りは、前扉・運転席の上にあるロゴの手前で止まる。
    design += rect(1.365, HEIGHT-2.553, (9.975 if right else 10.11)-1.365,
                   .025, RED)
    design += logo(.395 if right else .556, HEIGHT-(2.758 if right else 2.711),
                   .730 if right else .619, .126, BLUE, reverse=right)
    design += lettering("Non-Step Bus", 3.006 if right else 3.048,
                        HEIGHT-(.950 if right else .946), 1.224 if right else 1.228,
                        .172 if right else .186, BLUE,
                        reverse=right, font="serif")

    # 右側も前から「神奈川中央交通」。車体を正対して見ると右から左へ読む。
    # 写真上の文字中心（車両Y）。「川」「中」は左中扉のすぐ前と蹴り板上に載る。
    stations = ([2.106, 1.193, .287, -.681, -1.595, -2.510, -3.409] if right else
                [1.623, .718, -.086, -.981, -2.214, -3.181, -4.129])
    for kanji, station in zip("神奈川中央交通", stations):
        design += lettering(kanji, 4.95-station-.051, HEIGHT-(1.226 if right else 1.211),
                            .102, .104,
                            INK, reverse=right)
    return design
