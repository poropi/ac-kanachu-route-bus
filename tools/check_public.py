#!/usr/bin/env python3
"""公開前の検査: git に入っているファイルと、配布する zip に、公開してはいけない物が無いかを見る。

使い方: python3 tools/check_public.py [--forbid 文字列 ...]
- 個人の情報: 既定で `/Users/<名前>/`・`C:\\Users\\<名前>\\` の形の絶対パス。手元のユーザー名やホスト名は
  `--forbid` か環境変数 PUBLIC_FORBID（カンマ区切り）で足す（この検査自体に名前を書かないため）。
- 他者の著作物の置き場所: 参考写真の比較画像（compare/）、PDF、vendor/ 以下（別の MOD から借りたファイルの置き場）。
  手元に vendor/driver_jetset/ があれば、その中のファイルと MD5 が同じファイルが git・zip に入っていないかも見る。
- .blend は zstd/gzip で圧縮されていることがあるので、展開してから絶対パス・禁止語を探す（展開できなければ WARN: 未検査 と出す。合否には影響しない）。
問題が無ければ "OK" と出して 0 で終わる。
"""
import argparse
import gzip
import hashlib
import io
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP = ROOT / "build" / "kanachu_route_bus.zip"
ABS_PATH = re.compile(rb"(/Users/[A-Za-z0-9._-]+/|[A-Za-z]:\\\\?Users\\\\?[A-Za-z0-9._-]+\\\\?)")
ALLOWED_ABS = (b"/Users/<", b"Users\\<")          # 書類の中の伏せ字（<ユーザー>）は許す
FORBIDDEN_PATHS = (re.compile(r"(^|/)compare/"), re.compile(r"\.pdf$", re.I), re.compile(r"^vendor/"))
VENDOR = ROOT / "vendor" / "driver_jetset"       # 借りたファイルが置いてある唯一の場所（git に入れない）
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
GZIP_MAGIC = b"\x1f\x8b"


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return [p for p in out.decode("utf8").split("\0") if p]


def scan_bytes(name, data, words):
    bad = []
    for m in ABS_PATH.finditer(data):
        if not any(data[m.start():m.start() + len(a)] == a for a in ALLOWED_ABS):
            bad.append("%s: 絶対パス %r" % (name, m.group()[:40]))
            break
    low = data.lower()
    for w in words:
        if w.lower().encode() in low:
            bad.append("%s: 禁止語 %r" % (name, w))
    return bad


def vendor_md5s(vendor=None):
    """手元の vendor/driver_jetset/ のファイルの MD5（空でないもの）→ 相対パス。無ければ空。"""
    vendor = VENDOR if vendor is None else Path(vendor)
    if not vendor.is_dir():
        return {}
    out = {}
    for f in sorted(vendor.rglob("*")):
        if f.is_file() and f.name != "SOURCE.txt" and f.stat().st_size:
            out[hashlib.md5(f.read_bytes()).hexdigest()] = str(f.relative_to(vendor))
    return out


def expand(data):
    """zstd・gzip で圧縮された中身を展開して返す。(展開後のバイト列, 理由)。展開しないときの理由は None、
    展開したくてもできなかったときは理由の文字列（その場合の中身は元のまま）。"""
    if data[:4] == ZSTD_MAGIC:
        try:
            import zstandard
            return zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)).read(), None
        except ImportError:
            pass
        try:
            r = subprocess.run(["zstd", "-dc"], input=data, capture_output=True)
        except OSError:
            return data, "zstd で圧縮されているが展開する道具（zstandard モジュール・zstd コマンド）が無い"
        if r.returncode != 0:
            return data, "zstd の展開に失敗"
        return r.stdout, None
    if data[:2] == GZIP_MAGIC:
        try:
            return gzip.decompress(data), None
        except Exception:
            return data, "gzip の展開に失敗"
    return data, None


def scan_blob(name, data, words, vendor=None):
    """1 ファイルの検査。(問題のリスト, 警告のリスト)。圧縮は展開してから見る。vendor は vendor_md5s() の結果。"""
    bad, warn = [], []
    if vendor and data and hashlib.md5(data).hexdigest() in vendor:
        bad.append("%s: vendor/driver_jetset/%s と同じ中身（借り物）" % (name, vendor[hashlib.md5(data).hexdigest()]))
    body, why = expand(data)
    if why:
        warn.append("%s: 未検査（%s）" % (name, why))
    return bad + scan_bytes(name, body, words), warn


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--forbid", nargs="*", default=[])
    a = ap.parse_args(argv)
    words = [w for w in a.forbid + os.environ.get("PUBLIC_FORBID", "").split(",") if w.strip()]
    bad, warn = [], []
    vendor = vendor_md5s()
    for p in tracked():
        if any(r.search(p) for r in FORBIDDEN_PATHS):
            bad.append("%s: 公開しない場所のファイル" % p)
            continue
        if p == "tools/check_public.py" or p.startswith("tests/"):
            continue                                  # 検査の定義そのもの（パターンを書いている）
        f = ROOT / p
        if f.is_file():
            b, w = scan_blob(p, f.read_bytes(), words, vendor)
            bad += b
            warn += w
    if ZIP.is_file():
        with zipfile.ZipFile(ZIP) as z:
            for n in z.namelist():
                b, w = scan_blob("zip:" + n, z.read(n), words, vendor)
                bad += b
                warn += w
    for w in warn:
        print("WARN", w)
    for b in bad:
        print("NG", b)
    print("OK" if not bad else "NG %d 件" % len(bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
