"""Blender・refs/ なしで走る validate の単体テスト。最小の車フォルダを tmp に作る。"""
import shutil
from pathlib import Path

import numpy as np
import pytest

import kn5io
import paths
import physics
import validate

# M1 ビルドに無い（実機で無くても動いた）共通ファイル。増減・綴り間違いをここで検出する
EXPECTED_ABSENT = {
    "data/throttle.lut", "data/suspension_graphics.ini", "data/proview_nodes.ini",
    "data/digital_instruments.ini", "data/escmode.ini", "data/wing_animations.ini",
    "data/wing_front_AOA_CD.lut", "data/wing_front_AOA_CL.lut", "data/wing_rear_AOA_CD.lut",
    "data/wing_rear_AOA_CL.lut"}


IDENT = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


def kn5(levels):
    mesh = kn5io.Node(2, "COLLIDER_BODY", 1)
    mesh.vertices = b"\0" * 44
    mesh.indices = [0, 0, 0]
    inner = mesh
    for _ in range(levels - 2):
        inner = kn5io.Node(1, "COLLIDER_BODY", 1, children=[inner], matrix=IDENT)
    root = kn5io.Node(1, paths.CAR_NAME, 1, children=[inner], matrix=IDENT)
    return kn5io.Kn5(5, None, [], [], root)


def make_car(tmp, levels=3, skip=()):
    car = Path(tmp) / paths.CAR_NAME
    files = list(validate.FIXED) + ["data/" + n for n in validate.data_files()]
    for f in files + ["skins/0/ui_skin.json", "skins/0/livery.png", "skins/0/preview.jpg"]:
        if f in skip:
            continue
        p = car / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"{}" if f == "ui/ui_car.json" else b"x")
    for name in (validate.MAIN, "collider.kn5"):
        if name not in skip:
            kn5io.write(kn5(3 if name == validate.MAIN else levels), car / name)
    return car


def test_minimal_car_ok(tmp_path):
    car = make_car(tmp_path)
    # 主 kn5 は NODES が無いので、その分だけ指摘される。collider とファイル欠落は無い
    bad = validate.validate(car)
    assert not [b for b in bad if "collider" in b or b.startswith("無い")], bad


def test_two_level_collider_flagged(tmp_path):
    bad = validate.validate(make_car(tmp_path, levels=2))
    assert any("collider" in b and "dummy" in b for b in bad), bad


def test_three_level_collider_not_flagged(tmp_path):
    assert not any("collider" in b for b in validate.validate(make_car(tmp_path, levels=3)))


@pytest.mark.parametrize("f", ["driver_base_pos.knh", "data/driver3d.ini", "animations/steer.ksanim"])
def test_missing_driver_file_flagged(tmp_path, f):
    bad = validate.validate(make_car(tmp_path, skip=(f,)))
    assert any(f in b for b in bad), bad


def test_m1_absent_pinned_and_subset_of_common():
    assert validate.M1_ABSENT == EXPECTED_ABSENT
    assert validate.M1_ABSENT <= set(validate.COMMON_ALL)
    for f in ("data/driver3d.ini", "driver_base_pos.knh", "animations/steer.ksanim"):
        assert f in validate.FIXED


def test_absent_files_reported_as_warnings_not_problems(tmp_path):
    car = make_car(tmp_path)
    warns = []
    bad = validate.validate(car, warns)
    assert len(warns) == 1 and all(f in warns[0] for f in EXPECTED_ABSENT)
    assert not any("throttle.lut" in b for b in bad)


def test_mesh_with_children_is_flagged():
    child = kn5io.Node(1, "HINGE", 1, matrix=IDENT)
    mesh = kn5io.Node(2, "DOOR_FRONT", 1, children=[child])
    mesh.vertices = b"\0" * 44
    mesh.indices = [0, 0, 0]
    root = kn5io.Node(1, paths.CAR_NAME, 1, children=[mesh], matrix=IDENT)
    bad = validate.mesh_children_problems(root)
    assert len(bad) == 1 and "DOOR_FRONT" in bad[0]
    dummy = kn5io.Node(1, "DOOR_FRONT", 1, children=[kn5io.Node(2, "DOOR_FRONT_GEO", 1), child], matrix=IDENT)
    assert validate.mesh_children_problems(kn5io.Node(1, paths.CAR_NAME, 1, children=[dummy], matrix=IDENT)) == []


def _axis_tree(arrow_z=1.0, flat=True):
    """針: 文字盤（ローカル Z が薄い）を持つダミー。目は原点、針は前（+z）にある。"""
    pts = [[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 0.01]] if flat else [[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, 1, 5]]
    v = np.zeros((4, 11), "<f4"); v[:, :3] = pts
    m = kn5io.Node(2, "DISC", 1); m.vertices = v.tobytes(); m.indices = [0, 1, 2]
    M = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, arrow_z, 0, 0, 0, 5, 1)
    arrow = kn5io.Node(1, "ARROW_SPEED", 1, matrix=M, children=[m])
    eye = kn5io.Node(1, "DRIVER_EYE", 1, matrix=IDENT)
    return kn5io.Node(1, paths.CAR_NAME, 1, children=[eye, arrow], matrix=IDENT)


def test_axis_problems():
    import numpy as _np  # noqa: F401
    assert validate.axis_problems(_axis_tree()) == []
    assert any("向いている" in p for p in validate.axis_problems(_axis_tree(arrow_z=-1.0)))
    assert any("薄くない" in p for p in validate.axis_problems(_axis_tree(flat=False)))
    # 針もハンドルも無い（M1 の箱）なら対象外
    assert validate.axis_problems(kn5io.Node(1, paths.CAR_NAME, 1, children=[], matrix=IDENT)) == []


def test_axis_problems_checks_steer_without_arrow():
    # ARROW_SPEED が無くても STEER_HR の軸は検査する
    tree = _axis_tree()
    arrow = tree.children[1]
    arrow.name = "STEER_HR"
    assert validate.axis_problems(tree) == []
    arrow.matrix = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -1.0, 0, 0, 0, 5, 1)
    assert any("STEER_HR" in p and "向いている" in p for p in validate.axis_problems(tree))
    # 目が無ければ STEER_HR だけでも指摘する
    tree.children = [arrow]
    assert validate.axis_problems(tree) == ["DRIVER_EYE が無い"]


@pytest.mark.parametrize("f", validate.DRIVER_FILES)
def test_empty_driver_file_flagged(tmp_path, f):
    car = make_car(tmp_path)
    (car / f).write_bytes(b"")
    assert any(b == "空: " + f for b in validate.validate(car))


def _main_kn5_problems(tmp_path, drop):
    car = make_car(tmp_path)
    names = list(validate.NODES) + ["ARROW_SPEED", "ARROW_RPM", "DRIVER_EYE"]
    kids = [kn5io.Node(1, n, 1, matrix=IDENT) for n in names if n != drop]
    root = kn5io.Node(1, paths.CAR_NAME, 1, children=kids, matrix=IDENT)
    kn5io.write(kn5io.Kn5(5, None, [], [], root), car / validate.MAIN)
    return validate.validate(car)


@pytest.mark.parametrize("name", validate.COCKPIT_NODES)
def test_cockpit_requires_arrows_and_eye(tmp_path, name):
    assert any(name in b and "無い" in b for b in _main_kn5_problems(tmp_path, name))


def test_cockpit_nodes_all_present_is_ok(tmp_path):
    assert not any("無い" in b and validate.MAIN in b for b in _main_kn5_problems(tmp_path, None))
