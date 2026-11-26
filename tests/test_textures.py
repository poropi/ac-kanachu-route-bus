import struct

import numpy as np
import pytest
from PIL import Image

import textures


def header(b):
    assert b[:4] == b"DDS "
    size, flags, h, w, pitch, depth, mips = struct.unpack_from("<7I", b, 4)
    caps = struct.unpack_from("<I", b, 108)[0]
    return flags, h, w, mips, caps


def expected_size(w, h):
    n = 0
    while True:
        n += w * h * 4
        if w == 1 and h == 1:
            return n
        w, h = max(1, w // 2), max(1, h // 2)


def test_4x4_has_full_mip_chain():
    # CSP は MIP 無しの DDS に "Bad texture. MIPs are missing" と警告する。4x4 の単色も 4→2→1 の 3 段にする
    b = textures.dds_bytes(4, (1, 2, 3, 255))
    flags, h, w, mips, caps = header(b)
    assert (h, w) == (4, 4) and mips == 3
    assert flags & 0x20000 and caps & 0x400000
    assert len(b) == 128 + (16 + 4 + 1) * 4
    b1 = textures.dds_bytes(1, (1, 2, 3, 255))
    assert header(b1)[3] <= 1


def test_default_64_has_full_mip_chain():
    b = textures.dds_bytes(64, (10, 20, 30, 255))
    flags, h, w, mips, caps = header(b)
    assert mips == 7 and flags & 0x20000 and caps & 0x400000 and caps & 0x8
    assert len(b) == 128 + expected_size(64, 64)


def test_rgba_array_nonsquare_mips_average():
    arr = np.zeros((4, 8, 4), np.uint8)       # 高さ 4、幅 8
    arr[..., 0] = np.arange(8)[None, :] * 10    # R に横方向の勾配
    arr[..., 3] = 255
    b = textures.dds_from_rgba(arr)
    flags, h, w, mips, caps = header(b)
    assert (h, w, mips) == (4, 8, 4)
    assert len(b) == 128 + expected_size(8, 4)
    # 先頭ミップは BGRA 順
    assert b[128 + 2] == 0 and b[128 + 4 + 2] == 10
    # 2 番目のミップ (4x2) の先頭ピクセルは R=(0+10)/2=5
    off = 128 + 8 * 4 * 4
    assert abs(b[off + 2] - 5) <= 1


def test_npot_mips():
    arr = np.full((900, 864, 4), 77, np.uint8)
    b = textures.dds_from_rgba(arr)
    flags, h, w, mips, caps = header(b)
    assert (h, w) == (900, 864) and len(b) == 128 + expected_size(864, 900)
    assert mips == 10  # 900 -> 1 は 10 段


def test_write_paint_from_png(tmp_path):
    png = tmp_path / "p.png"
    Image.new("RGB", (512, 256), (200, 30, 40)).save(png)
    out = tmp_path / "paint.dds"
    textures.write_paint(png, out, size=(256, 128))
    b = out.read_bytes()
    flags, h, w, mips, caps = header(b)
    assert (h, w, mips) == (128, 256, 9)
    assert b[128:132] == bytes((40, 30, 200, 255))
