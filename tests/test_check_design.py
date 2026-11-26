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
    r = blender("--python", str(ROOT / "tests/fixtures/make_mini_design.py"), "--", str(out), *([brk] if brk else []))
    assert out.exists(), r.stdout + r.stderr
    return out


def run_check(blend, tmp):
    js = tmp / (blend.stem + ".json")
    r = blender("--python", str(ROOT / "tools/check_design.py"), "--", "--blend", str(blend), "--json", str(js))
    assert js.exists(), r.stdout + r.stderr
    return json.loads(js.read_text())


def test_valid_mini_design_passes(tmp_path):
    assert run_check(make(tmp_path), tmp_path) == []


@pytest.mark.parametrize("brk,needle", [
    ("missing_object", "LIGHT_TAIL_L"),
    ("missing_wheel", "WHEEL_RR"),
    ("bad_material", "mystery"),
    ("no_material", "Body"),
    ("wheel_pos", "WHEEL_LF"),
    ("susp_pos", "SUSP_RR"),
    ("bbox", "外接箱"),
    ("mirror_not_excluded", "外接箱"),
    ("no_uv", "Side"),
    ("uv_range", "0〜1"),
    ("uv_overlap", "重な"),
    ("too_many_verts", "Big"),
])
def test_each_violation_is_caught(tmp_path, brk, needle):
    problems = run_check(make(tmp_path, brk), tmp_path)
    assert any(needle in p for p in problems), problems


def test_real_exterior_passes(tmp_path):
    blend = ROOT / "design/exterior/kanachu_exterior.blend"
    if not blend.exists():
        pytest.skip("exterior missing")
    assert run_check(blend, tmp_path) == []


def test_real_interior_passes(tmp_path):
    blend = ROOT / "design/interior/kanachu_interior.blend"
    if not blend.exists():
        pytest.skip("interior missing")
    js = tmp_path / "interior.json"
    r = blender("--python", str(ROOT / "tools/check_design.py"), "--", "--blend", str(blend), "--interior", "--json", str(js))
    assert js.exists(), r.stdout + r.stderr
    assert json.loads(js.read_text()) == []


def run_interior(tmp, code):
    """内装を開いて code（bpy）で壊してから check_interior を呼ぶ。問題のリストを返す。"""
    js = tmp / "i.json"
    blend = ROOT / "design/interior/kanachu_interior.blend"
    body = ("import sys, json, bpy\nsys.path.insert(0, %r)\nimport check_design\n"
            "bpy.ops.wm.open_mainfile(filepath=%r)\n%s\njson.dump(check_design.check_interior(), open(%r, 'w'))\n"
            % (str(ROOT / "tools"), str(blend), code, str(js)))
    f = tmp / "run.py"
    f.write_text(body)
    r = blender("--python", str(f))
    assert js.exists(), r.stdout + r.stderr
    return json.loads(js.read_text())


@pytest.mark.parametrize("code,needle", [
    ("bpy.data.objects.remove(bpy.data.objects['ARROW_RPM'])", "ARROW_RPM"),
    ("bpy.data.objects['STEER_HR'].parent = None", "STEER_HR"),
    ("bpy.data.materials['interior_back'].name = 'mystery'", "mystery"),
    ("bpy.data.objects['COCKPIT_HR'].location.x = 1", "COCKPIT_HR"),
])
def test_interior_violations_are_caught(tmp_path, code, needle):
    if not (ROOT / "design/interior/kanachu_interior.blend").exists():
        pytest.skip("interior missing")
    problems = run_interior(tmp_path, code)
    assert any(needle in p for p in problems), problems
