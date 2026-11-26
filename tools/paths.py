import os
import shutil
from pathlib import Path

WORK = Path(__file__).resolve().parent.parent
CAR_NAME = "kanachu_route_bus"
BUILD = WORK / "build" / CAR_NAME
BLENDER = (os.environ.get("BLENDER") or shutil.which("blender")
           or "/Applications/Blender.app/Contents/MacOS/Blender")
