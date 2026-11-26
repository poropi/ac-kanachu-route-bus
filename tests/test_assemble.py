import io
import shutil
import zipfile
from pathlib import Path

import pytest

import assemble
import paths
import validate

ROOT = Path(__file__).resolve().parent.parent
HAVE_BLENDER = bool(paths.BLENDER and Path(paths.BLENDER).exists())
HAVE_DRIVER = (ROOT / "design" / "driver" / "kanachu_driver.blend").exists()
OPENED = []
HAVE_SOUND = (ROOT / "audio" / "build" / "kanachu_route_bus.bank").exists()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    if not (HAVE_BLENDER and HAVE_SOUND and HAVE_DRIVER):
        pytest.skip("Blender, audio/build or design/driver missing")
    out = tmp_path_factory.mktemp("asm") / paths.CAR_NAME
    # 組み立ての間に vendor/ を開こうとしないことを見張る（test_no_vendor_reference）
    opened = []
    real_open = io.open

    def spy(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)
    real_read_bytes = Path.read_bytes

    def spy_rb(self):
        opened.append(str(self))
        return real_read_bytes(self)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(io, "open", spy)
        mp.setattr(Path, "read_bytes", spy_rb)
        assemble.assemble(out, zip_path=out.parent / "car.zip")
    OPENED.extend(opened)
    return out


def test_validate_detects_missing(built, tmp_path):
    car = tmp_path / paths.CAR_NAME
    shutil.copytree(built, car)
    assert validate.validate(car) == []
    (car / "data" / "car.ini").unlink()
    assert len(validate.validate(car)) >= 1


def test_validate_detects_missing_skin(built, tmp_path):
    car = tmp_path / paths.CAR_NAME
    shutil.copytree(built, car)
    shutil.rmtree(car / "skins" / "0_new2023")
    shutil.rmtree(car / "skins" / "1_standard")
    assert any("skins" in p for p in validate.validate(car))


def test_build_valid(built):
    assert validate.validate(built) == []
    assert (built / "data").is_dir() and not (built / "data.acd").exists()
    for f in ["body_shadow.png"] + ["tyre_%d_shadow.png" % i for i in range(4)]:
        assert (built / f).exists()
    assert (built / "sfx" / "GUIDs.txt").read_text().count("kanachu_route_bus") >= 10


def test_built_guids_horn_and_no_leftovers(built):
    g = (built / "sfx" / "GUIDs.txt").read_text()
    assert "event:/cars/kanachu_route_bus/horn" in g
    assert "tky_bus_jetset" not in g and "ks_" not in g


def test_build_has_driver_files(built):
    for f in ("data/driver3d.ini", "driver_base_pos.knh", "animations/steer.ksanim"):
        assert (built / f).stat().st_size > 0, f
    assert (built.parent / "driver" / "kanachu_driver.kn5").stat().st_size > 0
    assert validate.validate(built, driver_kn5=built.parent / "driver" / "kanachu_driver.kn5") == []


def test_driver3d_ini_values():
    import physics
    import driver
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "driver3d.ini"
        f.write_text(driver.driver3d_ini(), encoding="utf8")
        ini = physics.read_ini(f, strict=True)
        f.write_text(driver.driver3d_ini(450), encoding="utf8")
        assert physics.read_ini(f, strict=True)["STEER_ANIMATION"]["LOCK"] == "450"
    assert ini["MODEL"] == {"NAME": "kanachu_driver", "POSITION": "0,0,0"}
    assert ini["STEER_ANIMATION"] == {"NAME": "steer.ksanim", "LOCK": "90"}
    assert "SHIFT_ANIMATION" in ini and int(ini["SHIFT_ANIMATION"]["PRELOAD_RPM"]) < 2600   # 回転は 2,600 rpm まで
    assert [ini["HIDE_OBJECT_%d" % i]["NAME"] for i in range(3)] == ["DRIVER:GEO_Driver_FACE", "DRIVER:HAIR", "DRIVER:CAP"]
    assert not any(k.startswith("HIDE_OBJECT_") and k not in ("HIDE_OBJECT_0", "HIDE_OBJECT_1", "HIDE_OBJECT_2") for k in ini)


def test_zip_layout(built):
    names = zipfile.ZipFile(built.parent / "car.zip").namelist()
    assert "content/cars/kanachu_route_bus/data/driver3d.ini" in names
    assert "content/cars/kanachu_route_bus/kanachu_route_bus.kn5" in names
    assert "content/driver/kanachu_driver.kn5" in names
    assert not any(n.startswith("kanachu_route_bus/") for n in names)
    assert all(n.startswith(("content/cars/kanachu_route_bus/", "content/driver/")) for n in names)
    assert not any(n.endswith("kanachu_driver.kn5") and "/cars/" in n for n in names)   # 運転手の kn5 は車のフォルダに入れない


def test_no_vendor_reference(built):
    import driver
    for mod in (assemble, driver):
        assert "vendor" not in Path(mod.__file__).read_text(encoding="utf8"), mod.__name__
    assert not hasattr(assemble, "DRIVER_VENDOR") and not hasattr(assemble, "copy_driver")
    assert OPENED and not [p for p in OPENED if "vendor" in p]   # 組み立ての間に vendor/ を読んでいない


def _drop_leaf_bone(kn5_in, kn5_out):
    k = kn5io.read(kn5_in)
    for n in kn5io.walk(k.root):
        for c in list(n.children):
            if c.cls == 1 and not c.children:
                n.children.remove(c)
                kn5io.write(k, kn5_out)
                return c.name
    raise AssertionError("葉の骨が無い")


def test_validate_detects_missing_driver_bone(built, tmp_path):
    src = built.parent / "driver" / "kanachu_driver.kn5"
    dst = tmp_path / "driver" / "kanachu_driver.kn5"
    dst.parent.mkdir()
    gone = _drop_leaf_bone(src, dst)
    probs = validate.validate(built, driver_kn5=dst)
    assert any(gone in p for p in probs), probs


def test_validate_driver_ini_name_and_tracks(built, tmp_path):
    car = tmp_path / paths.CAR_NAME
    shutil.copytree(built, car)
    drv = built.parent / "driver" / "kanachu_driver.kn5"
    ini = car / "data" / "driver3d.ini"
    ini.write_text(ini.read_text().replace("NAME=kanachu_driver", "NAME=driver"))
    assert any("MODEL NAME" in p for p in validate.validate(car, driver_kn5=drv))
    import ksanim
    t = ksanim.read(car / "animations" / "steer.ksanim")
    t.pop(next(iter(t)))
    ksanim.write(t, car / "animations" / "steer.ksanim")
    assert any("steer.ksanim" in p for p in validate.validate(car, driver_kn5=drv))


def test_validate_detects_missing_driver_file(built, tmp_path):
    car = tmp_path / paths.CAR_NAME
    shutil.copytree(built, car)
    (car / "driver_base_pos.knh").unlink()
    assert any("driver_base_pos.knh" in p for p in validate.validate(car))


def test_validate_detects_two_level_collider(built, tmp_path):
    import kn5io
    car = tmp_path / paths.CAR_NAME
    shutil.copytree(built, car)
    k = kn5io.read(car / "collider.kn5")
    (dummy,) = k.root.children
    k.root.children = dummy.children          # root -> mesh の 2 階層に戻す
    kn5io.write(k, car / "collider.kn5")
    assert any("collider" in p and "dummy" in p for p in validate.validate(car))


def test_sfx_default_is_own_bank(tmp_path):
    import sfx
    if not HAVE_SOUND:
        pytest.skip("audio/build missing")
    sfx.build(tmp_path)
    own = ROOT / "audio" / "build"
    assert (tmp_path / "sfx" / "kanachu_route_bus.bank").read_bytes() == (own / "kanachu_route_bus.bank").read_bytes()
    assert (tmp_path / "sfx" / "GUIDs.txt").read_bytes() == (own / "GUIDs.txt").read_bytes()


def test_box_model_still_builds(tmp_path):
    if not (HAVE_BLENDER and HAVE_SOUND and HAVE_DRIVER):
        pytest.skip("Blender, audio/build or design/driver missing")
    import kn5io
    out = assemble.assemble(tmp_path / paths.CAR_NAME, zip_path=None, model="box")
    assert validate.validate(out, cockpit=False) == []
    names = {n.name for n in kn5io.walk(kn5io.read(out / (paths.CAR_NAME + ".kn5")).root)}
    assert "BODY" in names and "INTERIOR_PLACEHOLDER" not in names


def test_exterior_is_default_model(built):
    import kn5io
    names = {n.name for n in kn5io.walk(kn5io.read(built / (paths.CAR_NAME + ".kn5")).root)}
    assert "INTERIOR_PLACEHOLDER" not in names and "LIGHT_HEAD_L" in names and "ARROW_SPEED" in names


# ---- M4: スキン・UI・灯火 ----
import json
import struct

import kn5io
import physics
from PIL import Image

SKINS = {"0_new2023": ("新塗装（2023〜）", 0, "paint_new2023", "livery_new2023"),
         "1_standard": ("旧塗装（標準色）", 1, "paint_standard", "livery_standard")}


def kn5_names(car):
    return {n.name for n in kn5io.walk(kn5io.read(car / (paths.CAR_NAME + ".kn5")).root)}


def test_skins_files(built):
    assert sorted(p.name for p in (built / "skins").iterdir()) == sorted(SKINS)
    for folder, (name, prio, _paint, livery) in SKINS.items():
        d = built / "skins" / folder
        j = json.loads((d / "ui_skin.json").read_text(encoding="utf8"))
        assert j["skinname"] == name and j["priority"] == prio
        assert j["country"] == "Japan" and j["team"] == "神奈川中央交通" and j["drivername"] == ""
        assert (d / "livery.png").read_bytes() == (ROOT / "design/ui" / (livery + ".png")).read_bytes()
        assert Image.open(d / "preview.jpg").size == (1022, 575)
        b = (d / "paint.dds").read_bytes()
        assert b[:4] == b"DDS "
        _, flags, h, w, _, _, mips = struct.unpack_from("<7I", b, 4)
        assert (w, h, mips) == (4096, 2048, 13)
        assert len(b) == 128 + sum(max(1, 4096 >> i) * max(1, 2048 >> i) * 4 for i in range(13))


def test_skin_paint_differs_and_matches_kn5_texture(built):
    a = (built / "skins/0_new2023/paint.dds").read_bytes()
    b = (built / "skins/1_standard/paint.dds").read_bytes()
    assert a != b
    k = kn5io.read(built / (paths.CAR_NAME + ".kn5"))
    paint = [m for m in k.materials if m.name == "paint"][0]
    assert ("txDiffuse", 0, "paint.dds") in paint.tex   # スキンの paint.dds がこれを差し替える


def test_ui_images_and_description(built):
    assert (built / "logo.png").read_bytes() == (ROOT / "design/ui/logo.png").read_bytes()
    assert (built / "ui/badge.png").read_bytes() == (ROOT / "design/ui/badge.png").read_bytes()
    c = json.loads((built / "ui/ui_car.json").read_text(encoding="utf8"))
    d = c["description"]
    for w in ("エルガ", "10,430", "9,790", "169 kW", "773", "Pixabay", "個人利用", "Isuzu Erga", "Personal use"):
        assert w in d
    assert "車両重量" in d and "curb" in d and "総重量" not in d and "GVW" not in d
    assert "奥山清行" in d and "calculated" in d and c["year"] == 2019
    assert c["name"] == "Kanachu City Bus (Large Non-step)"


def test_lights_ini_nodes_exist(built):
    ini = physics.read_ini(built / "data/lights.ini", strict=True)
    names = kn5_names(built)
    assert ini["HEADER"]["VERSION"] == "3"
    lights = [s for s in ini if s.startswith("LIGHT_")]
    brakes = [s for s in ini if s.startswith("BRAKE_")]
    assert len(lights) == 4 and len(brakes) == 2
    assert {ini[s]["NAME"] for s in lights + brakes} == {
        "LIGHT_HEAD_L", "LIGHT_HEAD_R", "LIGHT_TAIL_L", "LIGHT_TAIL_R", "LIGHT_BRAKE_L", "LIGHT_BRAKE_R"}
    assert {ini[s]["NAME"] for s in lights + brakes} <= names


def test_ext_config_nodes_exist(built):
    import re
    text = (built / "extension/ext_config.ini").read_text(encoding="utf8")
    names = kn5_names(built)
    used = set()
    for line in text.splitlines():
        m = re.match(r"NAME=(.+)", line)
        if m:
            used |= {x.strip() for x in m.group(1).split(",")}
    assert used and used <= names, used - names
    # 全灯火ノードのどれかが使われる
    import lights
    assert set(lights.ALL_NODES) <= used
    for sec in ("LIGHT_HEADLIGHT_0", "LIGHT_HEADLIGHT_1", "EMISSIVE_TURNSIGNAL_LEFT_0", "EMISSIVE_TURNSIGNAL_RIGHT_0",
                "EMISSIVE_REVERSE_0", "EMISSIVE_BRAKE_0", "LIGHT_TURNSIGNAL_LEFT_0", "LIGHT_TURNSIGNAL_RIGHT_1"):
        assert "[%s]" % sec in text, sec


def test_headlight_positions_from_nodes(built):
    import lights
    c = lights.node_centers(built / (paths.CAR_NAME + ".kn5"))
    ini = physics.read_ini(built / "extension/ext_config.ini")
    for i, n in enumerate(lights.HEAD):
        pos = [float(x) for x in ini["LIGHT_HEADLIGHT_%d" % i]["POSITION"].split(",")]
        assert max(abs(pos[0] - c[n][0]), abs(pos[1] - c[n][1])) < 1e-3 and 0 < pos[2] - c[n][2] < 0.2
    assert c["LIGHT_HEAD_L"][0] > 0 > c["LIGHT_HEAD_R"][0]   # 左が +x


def test_skin_previews_carry_no_local_paths(tmp_path):
    """配布する preview.jpg に作業者のパス（Blender の埋め込み情報）が残らない。"""
    import skins
    skins.build(tmp_path)
    found = list(tmp_path.rglob("preview.jpg"))
    assert len(found) == 2
    for p in found:
        b = p.read_bytes()
        assert b"/Users/" not in b and b"Blender:" not in b, p
