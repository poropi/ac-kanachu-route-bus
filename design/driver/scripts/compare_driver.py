"""Make the three registered reference/render pairs at half native resolution."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DRIVER = Path(__file__).resolve().parents[1]
VIEWS = [("front", "正面"), ("side", "左側面"), ("back", "背面")]


def font(size):
    paths = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    return ImageFont.truetype(next(p for p in paths if Path(p).exists()), size)


def main():
    sheet = Image.new("RGB", (3072, 869), "white")
    draw = ImageDraw.Draw(sheet)
    title_font, label_font = font(27), font(21)
    for i, (name, title) in enumerate(VIEWS):
        base = i * 1024
        draw.text((base + 30, 19), title, font=title_font, fill="#202238")
        draw.line((base + 30, 65, base + 994, 65), fill="#ccd3df", width=2)
        for j, (folder, label) in enumerate([("turnaround", "三面図"), ("renders", "3D モデル")]):
            with Image.open(DRIVER / folder / (name + ".png")) as im:
                assert im.size == (1024, 1536)
                im = im.convert("RGB").resize((512, 768), Image.Resampling.LANCZOS)
            sheet.paste(im, (base + 512*j, 69))
            draw.text((base + 256 + 512*j, 849), label, font=label_font, anchor="mm", fill="#495264")
        if i:
            draw.line((base, 18, base, 850), fill="#dfe3e9", width=2)
    sheet.save(DRIVER / "renders" / "compare.png")


if __name__ == "__main__":
    main()
