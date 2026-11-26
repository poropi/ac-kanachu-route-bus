#!/usr/bin/env python3
"""build/kanachu_route_bus/ を作り直し、build/kanachu_route_bus.zip を作る。

使い方: python3 tools/assemble.py [--model exterior|box]
主 kn5 は既定で design/exterior/kanachu_exterior.blend（tools/prepare_blend.py で書き出し用に整える）から、
--model box なら blender/m1_box.blend から書き出す。collider.kn5 は blender/m1_collider.blend（Blender が要る）。
音は audio/build/（tools/fmod_build.py で作った自作 bank）。ドライバー 3 ファイルは vendor/driver_jetset/（別の MOD からの借り物。公開版では自作のものに差し替える）。
"""
import argparse
import hashlib
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import paths
import physics
import lights
import sfx
import skins
import textures
import ui

ROOT = paths.WORK
DRIVER_VENDOR = ROOT / "vendor" / "driver_jetset"
# (vendor/driver_jetset/ 内, build 内)。無いと CSP が物理開始直後に落ちる。
DRIVER_FILES = [("driver3d.ini", "data/driver3d.ini"), ("driver_base_pos.knh", "driver_base_pos.knh"),
                ("animations/steer.ksanim", "animations/steer.ksanim")]
EXTERIOR_BLEND = ROOT / "design" / "exterior" / "kanachu_exterior.blend"
PAINT_PNG = ROOT / "design" / "livery" / "paint_new2023.png"


def export_kn5(blend, out, tex_dir):
    r = subprocess.run([paths.BLENDER, "-b", str(blend), "--python", str(ROOT / "tools/blend_to_kn5.py"), "--",
                        "--materials", str(ROOT / "tools/materials.json"),
                        "--tex-dir", str(tex_dir), "--out", str(out)], capture_output=True, text=True)
    if r.returncode != 0 or not Path(out).exists():
        raise RuntimeError("kn5 書き出しに失敗: %s\n%s%s" % (blend, r.stdout[-800:], r.stderr[-800:]))


def export_exterior(out, tex_dir, work):
    """外装 .blend を書き出し用に整え（prepare_blend）、パック画像を tex_dir に DDS で書き、kn5 にする。
    塗装は design/livery/paint_new2023.png から paint.dds（4096x2048、ミップ付き）を作る。"""
    prepared = Path(work) / "exterior_prepared.blend"
    r = subprocess.run([paths.BLENDER, "-b", str(EXTERIOR_BLEND), "--python", str(ROOT / "tools/prepare_blend.py"), "--",
                        "--out", str(prepared), "--tex-dir", str(tex_dir)], capture_output=True, text=True)
    if r.returncode != 0 or not prepared.exists():
        raise RuntimeError("外装の準備に失敗: %s\n%s%s" % (EXTERIOR_BLEND, r.stdout[-800:], r.stderr[-800:]))
    textures.write_paint(PAINT_PNG, Path(tex_dir) / "paint.dds")
    export_kn5(prepared, out, tex_dir)


def driver_md5_problems(src_dir):
    """SOURCE.txt（行: "<vendor 内の相対パス> md5=<大文字 MD5>"）と実ファイルの MD5 を照合し、食い違いの一覧を返す。"""
    src_dir = Path(src_dir)
    sf = src_dir / "SOURCE.txt"
    if not sf.is_file():
        return ["SOURCE.txt が無い"]
    want = {}
    for line in sf.read_text(encoding="utf8").splitlines():
        if " md5=" in line:
            name, md5 = line.rsplit(" md5=", 1)
            want[name.strip()] = md5.strip().upper()
    probs = []
    for src, _ in DRIVER_FILES:
        f = src_dir / src
        if src not in want:
            probs.append("SOURCE.txt に %s の MD5 が無い" % src)
        elif f.is_file() and hashlib.md5(f.read_bytes()).hexdigest().upper() != want[src]:
            probs.append("%s の MD5 が SOURCE.txt と違う" % src)
    return probs


def copy_driver(out):
    out = Path(out)
    miss = [src for src, _ in DRIVER_FILES if not (DRIVER_VENDOR / src).is_file()]
    if miss:
        raise SystemExit("ドライバーのファイルが無い (%s): vendor/driver_jetset/ が要る（自作の運転手ファイルに差し替えるまで）" % ", ".join(miss))
    probs = driver_md5_problems(DRIVER_VENDOR)
    if probs:
        raise SystemExit("ドライバーのファイルが SOURCE.txt と合わない: %s" % "; ".join(probs))
    for src, dst in DRIVER_FILES:
        (out / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DRIVER_VENDOR / src, out / dst)


def blurred_ellipse(size, fx, fy, sigma, peak=191):
    """上から見た外形の楕円（画像の上が前）。fx, fy は画像に占める幅・高さの割合。灰色 + A=255。"""
    m = Image.new("L", (size, size), 0)
    w, h = size * fx / 2, size * fy / 2
    ImageDraw.Draw(m).ellipse([size / 2 - w, size / 2 - h, size / 2 + w, size / 2 + h], fill=peak)
    m = m.filter(ImageFilter.GaussianBlur(sigma))
    return Image.merge("RGBA", (m, m, m, Image.new("L", (size, size), 255)))


def write_shadows(out):
    blurred_ellipse(128, 0.62, 0.86, 5).save(out / "body_shadow.png")
    for i in range(4):
        blurred_ellipse(64, 0.6, 0.8, 4).save(out / ("tyre_%d_shadow.png" % i))


def assemble(out=None, zip_path=None, model="exterior"):
    """out を消して作り直す。model は exterior（既定）か box（M1 の箱）。zip_path があれば zip も作る（既定は build/<車名>.zip、None なら作らない）。"""
    out = Path(out or paths.BUILD)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as t:
        tex = Path(t) / "tex"
        textures.make_default_textures(tex)
        main_kn5 = out / (paths.CAR_NAME + ".kn5")
        if model == "box":
            export_kn5(ROOT / "blender/m1_box.blend", main_kn5, tex)
        elif model == "exterior":
            export_exterior(main_kn5, tex, t)
        else:
            raise ValueError("model は exterior か box: %r" % model)
        export_kn5(ROOT / "blender/m1_collider.blend", out / "collider.kn5", tex)
    physics.build(out / "data")
    copy_driver(out)
    sfx.build(out)
    ui.build(out)
    skins.build(out)
    if model == "exterior":   # M1 の箱には灯火のメッシュが無い
        lights.write_ext_config(out, main_kn5)
    else:
        print("WARN: model=%s には灯火のメッシュが無いので extension/ext_config.ini を作らない" % model)
    write_shadows(out)
    if zip_path:
        Path(zip_path).parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(out.rglob("*")):
                if f.is_file():
                    z.write(f, Path(out.name) / f.relative_to(out))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["exterior", "box"], default="exterior")
    o = assemble(paths.BUILD, paths.BUILD.parent / (paths.CAR_NAME + ".zip"), ap.parse_args().model)
    print("WROTE", o)
