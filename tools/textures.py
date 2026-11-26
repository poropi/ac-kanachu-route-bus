"""既定テクスチャ（単色の無圧縮 A8R8G8B8 DDS）を書き出す。"""
import struct
from pathlib import Path

import numpy as np

# 名前 -> (サイズ, (R, G, B, A))
DEFAULTS = {
    "flat_nm.dds": (4, (128, 128, 255, 255)),
    "maps_default.dds": (4, (255, 128, 0, 255)),
    "detail_white.dds": (4, (255, 255, 255, 255)),
    "darkgrey.dds": (4, (40, 40, 40, 255)),
    "white.dds": (4, (255, 255, 255, 255)),
    "chrome.dds": (4, (205, 208, 212, 255)),
    "rim_grey.dds": (4, (150, 152, 156, 255)),
    "tyre_black.dds": (4, (24, 24, 26, 255)),
    "glass.dds": (4, (28, 32, 36, 46)),             # 風防・運転席窓: 暗い無彩色、不透明度 0.18（運転の視界）
    "glass_tint.dds": (4, (18, 22, 26, 166)),       # 客室窓・後窓・扉ガラス: 濃い着色、不透明度 0.65（実車の写真に合わせる）
    "glass_light.dds": (4, (220, 230, 235, 140)),   # 灯火のレンズ: 明るい無彩色、不透明度 0.55
    "led_orange.dds": (4, (255, 150, 20, 255)),
    "paint.dds": (64, (0xF3, 0xE6, 0xB0, 255)),  # 神奈中バスのクリーム #F3E6B0
}

def _mip_chain(arr):
    """(h, w, 4) uint8 から、1x1 までの縮小列を作る（2x2 の平均。奇数の端は最後の列・行を重ねる）。"""
    chain = [arr]
    while arr.shape[0] > 1 or arr.shape[1] > 1:
        h, w = arr.shape[:2]
        h2, w2 = max(1, h // 2), max(1, w // 2)
        y0 = np.minimum(np.arange(h2) * 2, h - 1); y1 = np.minimum(y0 + 1, h - 1)
        x0 = np.minimum(np.arange(w2) * 2, w - 1); x1 = np.minimum(x0 + 1, w - 1)
        a = arr.astype(np.uint16)
        s = a[y0][:, x0] + a[y0][:, x1] + a[y1][:, x0] + a[y1][:, x1]
        arr = ((s + 2) // 4).astype(np.uint8)
        chain.append(arr)
    return chain


def dds_from_rgba(arr):
    """(h, w, 4) uint8 の RGBA 配列から、無圧縮 A8R8G8B8 の DDS を作る。縦横どちらかが 1 を超えるとミップマップ付き
    （CSP が MIPs 無しの DDS に "Bad texture. MIPs are missing" と警告するため。1x1 だけは無し）。"""
    arr = np.ascontiguousarray(arr, np.uint8)
    h, w = arr.shape[:2]
    chain = _mip_chain(arr) if max(h, w) > 1 else [arr]
    flags, caps = 0x100F, 0x1000
    if len(chain) > 1:
        flags |= 0x20000; caps |= 0x400000 | 0x8
    hdr = b"DDS " + struct.pack("<7I", 124, flags, h, w, w * 4, 0, len(chain) if len(chain) > 1 else 0)
    hdr += bytes(44)  # reserved1[11]
    hdr += struct.pack("<8I", 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    hdr += struct.pack("<5I", caps, 0, 0, 0, 0)
    assert len(hdr) == 128
    return hdr + b"".join(m[..., [2, 1, 0, 3]].tobytes() for m in chain)


def dds_bytes(size, rgba):
    return dds_from_rgba(np.broadcast_to(np.array(rgba, np.uint8), (size, size, 4)))


def write_paint(png, out, size=(4096, 2048)):
    """塗装の PNG を size=(幅, 高さ) に拡縮して、ミップマップ付き DDS で書く。"""
    from PIL import Image
    im = Image.open(png).convert("RGBA")
    if im.size != tuple(size):
        im = im.resize(tuple(size), Image.LANCZOS)
    Path(out).write_bytes(dds_from_rgba(np.asarray(im)))


def make_default_textures(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    names = []
    for name, (size, rgba) in DEFAULTS.items():
        (out / name).write_bytes(dds_bytes(size, rgba)); names.append(name)
    return names
