"""神奈中バスの UI 用原画を描き、実寸・4倍の見本を出力する。"""

from io import BytesIO
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

OUTPUT = Path(__file__).resolve().parents[1]

# design/livery/report.md の採用色（sRGB）
BLUE = "#0D55D9"
OLD_CREAM = "#D7CD8E"
OLD_ORANGE = "#CA763A"
OLD_RED = "#902C26"
SKIRT = "#B53139"
RED = "#EC2430"
ORANGE = "#DE7839"
CREAM = "#EADAC2"
GLASS = "#707885"
TIRE = "#413123"
HUB = "#A5ACB6"


def render(size, paths):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">{paths}</svg>'
    png = subprocess.run(["rsvg-convert"], input=svg.encode(), stdout=subprocess.PIPE, check=True)
    with Image.open(BytesIO(png.stdout)) as img:
        return img.convert("RGBA")


def path(outline, color):
    return f'<path d="{outline}" fill="{color}"/>'


def badge(size):
    # 塗装原画 artwork.logo の先頭文字。外接矩形 (2, 0)–(176, 168) を中央に置く。
    k = "M3 0H45V69L99 0H128L70 78L130 168H101L51 97L45 106V168H2Z"
    lines = "M143 0H154L96 79L154 168H143L83 79Z M169 0H175L115 79L176 168H169L107 79Z"
    scale = size * (92 / 128) / 168
    transform = f"translate({size / 2} {size / 2}) scale({scale}) translate(-89 -84)"
    return render(size, f'<g transform="{transform}">{path(k, BLUE)}{path(lines, BLUE)}</g>')


def livery(standard):
    # 2種類で同じ側面輪郭を使い、鼻先を左、後輪を右に置く。
    body = ("M3 30L4.4 23.5Q5 20 9 20H57Q61 20 61 24V40Q61 43 58 43H53"
            "A6 6 0 0 0 41 43H21A6 6 0 0 0 9 43H5Q2 43 2 40V33Z")
    parts = [f'<defs><clipPath id="body"><path d="{body}"/></clipPath></defs>']
    parts.append(path("M19 20L21 17H36L39 20Z", OLD_CREAM if standard else CREAM))
    parts.append(path(body, OLD_CREAM if standard else RED))
    parts.append('<g clip-path="url(#body)">')
    if standard:
        parts += [
            path("M10 21H61V22H10Z", OLD_RED),
            path("M2 32H62V37H2Z", OLD_RED),
            path("M2 33H62V36H2Z", OLD_ORANGE),
            path("M2 40H62V44H2Z", SKIRT),
        ]
    else:
        # 両端の赤、中央の広いクリームと、後輪付近で太さを変える交互線。
        for start, end, color in [
            (12, 17, ORANGE), (17, 41, CREAM), (41, 43, ORANGE),
            (43, 46, OLD_CREAM), (46, 49, ORANGE), (49, 51, OLD_CREAM),
            (51, 55, ORANGE),
        ]:
            parts.append(path(f"M{start} 19H{end}V44H{start}Z", color))
    # 窓を一筆の黒帯にせず、乗務員席・乗降扉・客窓の間に車体色の柱を残す。
    parts.append(path("M5.5 24H9V30H4.4Z M11 23H16V30H11Z M18 23H27V30H18Z "
                      "M29 23H37V30H29Z M39 23H48V30H39Z M50 23H58Q59 23 59 24V30H50Z", GLASS))
    parts.append("</g>")
    for x in (15, 47):
        parts.append(f'<circle cx="{x}" cy="43" r="4.8" fill="{TIRE}"/>')
        parts.append(f'<circle cx="{x}" cy="43" r="1.9" fill="{HUB}"/>')
    return render(64, "".join(parts))


def preview(icons):
    # ヘッダーと倍率の行名は絵の外に置き、各段を中心揃えにする。
    sheet = Image.new("RGBA", (1464, 768))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("Arial.ttf", 18)
    small = ImageFont.truetype("Arial.ttf", 15)
    left = 80
    draw.text((24, 110), "1×", font=font, fill=GLASS, anchor="lm")
    draw.text((24, 470), "4×", font=font, fill=GLASS, anchor="lm")
    for filename, img in icons.items():
        w = img.width
        center = left + w * 2
        draw.text((center, 18), filename, font=small, fill=GLASS, anchor="mt")
        for scale, y in ((1, 110), (4, 470)):
            tile = img if scale == 1 else img.resize((w * 4, w * 4), Image.Resampling.NEAREST)
            sheet.alpha_composite(tile, (center - tile.width // 2, y - tile.height // 2))
        left += w * 4 + 24
    return sheet


if __name__ == "__main__":
    icons = {
        "badge.png": badge(128),
        "logo.png": badge(64),
        "livery_standard.png": livery(True),
        "livery_new2023.png": livery(False),
    }
    for name, icon in icons.items():
        icon.save(OUTPUT / name)
    preview(icons).save(OUTPUT / "preview.png")
