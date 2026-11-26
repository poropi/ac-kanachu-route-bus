"""sfx/: kanachu_route_bus.bank と GUIDs.txt を置く。

tools/fmod_build.py が audio/build/ に作った自作の bank と GUIDs.txt をそのまま写す。
（bank は Pixabay の効果音を加工した素材から FMOD Studio 1.08.12 で作ったもの。作り方は README の「音の bank を作り直す」）
"""
import argparse
import shutil
from pathlib import Path

import paths

OWN = paths.WORK / "audio" / "build"


def build(out=None):
    out = Path(out or paths.BUILD)
    dst = out / "sfx"
    dst.mkdir(parents=True, exist_ok=True)
    for f in (paths.CAR_NAME + ".bank", "GUIDs.txt"):
        if not (OWN / f).exists():
            raise FileNotFoundError("audio/build/%s が無い。python3 tools/fmod_build.py build で作る" % f)
        shutil.copyfile(OWN / f, dst / f)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(paths.BUILD))
    build(ap.parse_args().out)
