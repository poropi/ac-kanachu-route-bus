import json
import subprocess
from pathlib import Path

import pytest

import paths

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(not (paths.BLENDER and Path(paths.BLENDER).exists()), reason="Blender not found")


def blender(*args):
    return subprocess.run([paths.BLENDER, "-b", *args], capture_output=True, text=True)


def make(tmp, brk=""):
    out = tmp / ((brk or "ok") + ".blend")
    r = blender("--python", str(ROOT / "tests/fixtures/make_mini_driver.py"), "--", str(out), *([brk] if brk else []))
    assert out.exists(), r.stdout + r.stderr
    return out


def run_check(blend, tmp):
    js = tmp / (blend.stem + ".json")
    r = blender("--python", str(ROOT / "tools/check_driver.py"), "--", "--blend", str(blend), "--json", str(js))
    assert js.exists(), r.stdout + r.stderr
    return json.loads(js.read_text())


def test_mini_driver_passes(tmp_path):
    assert run_check(make(tmp_path), tmp_path) == []


def test_missing_bone_and_unweighted_vertex_fail(tmp_path):
    assert len(run_check(make(tmp_path, "missing_bone"), tmp_path)) >= 1
    assert len(run_check(make(tmp_path, "unweighted"), tmp_path)) >= 1


@pytest.mark.parametrize("brk,needle", [
    ("missing_bone", "HAND_Index5"),
    ("extra_bone", "RIG_Tail"),
    ("wrong_parent", "RIG_Foot_L"),
    ("unweighted", "重みの無い"),
    ("no_modifier", "Armature モディファイア"),
    ("head_not_bone", "DRIVER:HAIR"),
    ("bad_material", "mystery"),
    ("no_material", "DRIVER:CAP"),
    ("no_uv", "DRIVER:HAIR"),
    ("tall", "頭頂"),
    ("unpacked_image", "パック"),
    ("missing_mesh", "DRIVER:BODY"),
])
def test_each_violation_is_caught(tmp_path, brk, needle):
    problems = run_check(make(tmp_path, brk), tmp_path)
    assert any(needle in p for p in problems), problems
