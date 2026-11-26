import gzip
import shutil
import subprocess
import zipfile

import pytest

import check_public as cp

HAVE_ZSTD = shutil.which("zstd") is not None
try:
    import zstandard  # noqa: F401
    HAVE_ZSTD = True
except ImportError:
    pass


def _zstd(data):
    try:
        import zstandard
        return zstandard.ZstdCompressor().compress(data)
    except ImportError:
        return subprocess.run(["zstd", "-c"], input=data, capture_output=True, check=True).stdout


@pytest.mark.skipif(not HAVE_ZSTD, reason="zstd がない")
def test_zstd_blend_with_forbidden_word_is_caught():
    raw = b"BLENDER-v500" + b"\0aabbaabbaaaabbbb" * 400 + b"/Users/someone/work/x.png" + b"gpuwin" + b"\0aabb" * 300
    blob = _zstd(raw)
    assert blob[:4] == cp.ZSTD_MAGIC and cp.expand(blob) == (raw, None)
    bad, warn = cp.scan_blob("a.blend", blob, ["gpuwin"])
    assert any("禁止語" in b for b in bad) and any("絶対パス" in b for b in bad) and warn == []


def test_gzip_blend_is_caught():
    bad, warn = cp.scan_blob("a.blend", gzip.compress(b"BLENDER" + b"C:\\Users\\bob\\x"), [])
    assert any("絶対パス" in b for b in bad)


def test_undecompressible_is_warning_not_silence(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "zstandard", None)    # import を失敗させる
    monkeypatch.setattr(cp.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    bad, warn = cp.scan_blob("a.blend", b"\x28\xb5\x2f\xfd" + b"junk", [])
    assert bad == [] and len(warn) == 1 and "未検査" in warn[0]


def test_vendor_md5_copy_is_caught(tmp_path):
    v = tmp_path / "vendor" / "driver_jetset"
    (v / "animations").mkdir(parents=True)
    (v / "driver3d.ini").write_bytes(b"[MODEL]\nNAME=driver\n")
    (v / "SOURCE.txt").write_text("x")
    md5s = cp.vendor_md5s(v)
    assert len(md5s) == 1
    bad, _ = cp.scan_blob("zip:content/x/data/driver3d.ini", b"[MODEL]\nNAME=driver\n", [], md5s)
    assert any("vendor/driver_jetset/driver3d.ini" in b for b in bad)
    assert cp.scan_blob("ok.ini", b"[MODEL]\nNAME=kanachu_driver\n", [], md5s) == ([], [])
    assert cp.vendor_md5s(tmp_path / "nope") == {}                       # vendor/ が無ければ MD5 の照合はしない


def test_main_flags_vendor_tracked_and_zip_copy(tmp_path, monkeypatch, capsys):
    v = tmp_path / "vendor" / "driver_jetset"
    v.mkdir(parents=True)
    (v / "driver_base_pos.knh").write_bytes(b"BORROWED-BYTES")
    z = tmp_path / "x.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("content/cars/c/driver_base_pos.knh", b"BORROWED-BYTES")
    monkeypatch.setattr(cp, "VENDOR", v)
    monkeypatch.setattr(cp, "ZIP", z)
    monkeypatch.setattr(cp, "tracked", lambda: ["vendor/driver_jetset/a.bin", "README.md"])
    monkeypatch.setattr(cp, "ROOT", tmp_path)
    assert cp.main([]) == 1
    out = capsys.readouterr().out
    assert "vendor/driver_jetset/a.bin: 公開しない場所" in out and "driver_base_pos.knh と同じ中身" in out


def test_clean_zip_is_ok(tmp_path, monkeypatch, capsys):
    z = tmp_path / "x.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("content/driver/kanachu_driver.kn5", b"own")
    monkeypatch.setattr(cp, "VENDOR", tmp_path / "none")
    monkeypatch.setattr(cp, "ZIP", z)
    monkeypatch.setattr(cp, "tracked", lambda: [])
    assert cp.main([]) == 0
    assert capsys.readouterr().out.strip().endswith("OK")


@pytest.mark.parametrize("data", [b"abc\x00/Users/someone\x00def", b'x "/Users/someone" y', b"p /Users/someone", b"C:\\Users\\someone\x00",
                                  b"x/Users/someone/y"])
def test_user_path_without_trailing_separator_is_caught(data):
    assert cp.scan_bytes("f", data, []) != []


@pytest.mark.parametrize("data", [b"/Users/<name>/x", b"Users\\<name>", b"see /Users/ here", b"/Users/\x00"])
def test_placeholder_or_bare_users_is_allowed(data):
    assert cp.scan_bytes("f", data, []) == []
