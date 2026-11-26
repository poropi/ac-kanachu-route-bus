#!/usr/bin/env python3
"""公開前の検査: git に入っているファイルと、配布する zip に、公開してはいけない物が無いかを見る。

使い方: python3 tools/check_public.py [--forbid 文字列 ...]
- 個人の情報: 既定で `/Users/<名前>/`・`C:\\Users\\<名前>\\` の形の絶対パス。手元のユーザー名やホスト名は
  `--forbid` か環境変数 PUBLIC_FORBID（カンマ区切り）で足す（この検査自体に名前を書かないため）。
- 他者の著作物の置き場所: 参考写真の比較画像（compare/）、PDF、借り物の運転手（vendor/driver_jetset/）。
問題が無ければ "OK" と出して 0 で終わる。
"""
import argparse
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
FORBIDDEN_PATHS = (re.compile(r"(^|/)compare/"), re.compile(r"\.pdf$", re.I), re.compile(r"^vendor/driver_jetset/"))


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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--forbid", nargs="*", default=[])
    a = ap.parse_args(argv)
    words = [w for w in a.forbid + os.environ.get("PUBLIC_FORBID", "").split(",") if w.strip()]
    bad = []
    for p in tracked():
        if any(r.search(p) for r in FORBIDDEN_PATHS):
            bad.append("%s: 公開しない場所のファイル" % p)
            continue
        if p == "tools/check_public.py" or p.startswith("tests/"):
            continue                                  # 検査の定義そのもの（パターンを書いている）
        f = ROOT / p
        if f.is_file():
            bad += scan_bytes(p, f.read_bytes(), words)
    if ZIP.is_file():
        with zipfile.ZipFile(ZIP) as z:
            for n in z.namelist():
                if n.endswith(("driver3d.ini", "driver_base_pos.knh", "steer.ksanim")):
                    bad.append("zip:%s: 借り物の運転手のファイル（自作に差し替えるまで公開しない）" % n)
                bad += scan_bytes("zip:" + n, z.read(n), words)
    for b in bad:
        print("NG", b)
    print("OK" if not bad else "NG %d 件" % len(bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
