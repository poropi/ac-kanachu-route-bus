"""スキン 2 種（0_new2023 = 既定、1_standard）を out/skins/ に作る。

各スキン: paint.dds（4096x2048・ミップ付き。主 kn5 の paint マテリアルの txDiffuse と同名なので AC が差し替える）、
livery.png（design/ui の 64x64 見本）、ui_skin.json、preview.jpg（1022x575）。
preview.jpg は Blender で外装にその塗装を貼ったレンダー。時間がかかるので design/skins/ に置いて git に入れ、
assemble は写すだけにする。塗装や外装を変えたら `python3 tools/skins.py --render` で描き直す。
"""
import argparse
import json
import subprocess
from pathlib import Path

import paths
import textures

ROOT = paths.WORK
SKINS = [
    # フォルダ, 表示名, priority, 塗装 PNG, 見本 PNG
    ("0_new2023", "新塗装（2023〜）", 0, "design/livery/paint_new2023.png", "design/ui/livery_new2023.png"),
    ("1_standard", "旧塗装（標準色）", 1, "design/livery/paint_standard.png", "design/ui/livery_standard.png"),
]
PREVIEW_DIR = ROOT / "design" / "skins"
PREVIEW_SIZE = (1022, 575)


def skin_json(name, priority):
    return {"skinname": name, "drivername": "", "country": "Japan", "team": "神奈川中央交通",
            "number": "", "priority": priority}


def build(out):
    """out/skins/<フォルダ>/ を作る。preview は design/skins/<フォルダ>.jpg を写す（無ければ例外）。"""
    for folder, name, prio, paint, livery in SKINS:
        d = Path(out) / "skins" / folder
        d.mkdir(parents=True, exist_ok=True)
        textures.write_paint(ROOT / paint, d / "paint.dds")
        (d / "livery.png").write_bytes((ROOT / livery).read_bytes())
        (d / "ui_skin.json").write_text(json.dumps(skin_json(name, prio), ensure_ascii=False, indent=2), encoding="utf8")
        pv = PREVIEW_DIR / (folder + ".jpg")
        if not pv.is_file():
            raise SystemExit("preview が無い: %s（python3 tools/skins.py --render）" % pv)
        # 公開・配布用: Blender が書き込むファイルの場所（作業者のホームのパス）などの埋め込み情報を落として保存し直す
        from PIL import Image
        with Image.open(pv) as im:
            clean = Image.new("RGB", im.size); clean.paste(im.convert("RGB"))   # info（コメント・EXIF）を持たない新しい画像に写す
            clean.save(d / "preview.jpg", "JPEG", quality=92)


def render_previews(samples=64):
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    for folder, _n, _p, paint, _l in SKINS:
        r = subprocess.run([paths.BLENDER, "-b", str(ROOT / "design/exterior/kanachu_exterior.blend"), "--python",
                            str(ROOT / "tools/render_skin_preview.py"), "--", "--paint", str(ROOT / paint),
                            "--out", str(PREVIEW_DIR / (folder + ".jpg")), "--samples", str(samples)],
                           capture_output=True, text=True)
        if r.returncode != 0 or not (PREVIEW_DIR / (folder + ".jpg")).is_file():
            raise RuntimeError("preview の描画に失敗: %s\n%s" % (folder, r.stdout[-800:] + r.stderr[-800:]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", action="store_true", help="design/skins/*.jpg を Blender で描き直す")
    ap.add_argument("--out", default=str(paths.BUILD))
    a = ap.parse_args()
    if a.render:
        render_previews()
    else:
        build(a.out)
