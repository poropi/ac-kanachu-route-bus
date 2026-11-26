from pathlib import Path

import pytest

import driver_skeleton as sk

ROOT = Path(__file__).resolve().parent.parent
KUNOS = ROOT / "refs/kunos_driver/driver.kn5"


def ancestors(name):
    parent = dict(sk.BONES)
    while parent[name] is not None:
        name = parent[name]
        yield name


def test_bones_are_well_formed():
    names = [n for n, _ in sk.BONES]
    assert len(names) == len(set(names)), "骨名が重複している"
    assert sk.BONES[0] == ("DRIVER:DRIVER", None)
    seen = set()
    for n, p in sk.BONES:
        assert p is None or p in seen, "親が先に並んでいない: " + n
        seen.add(n)
    assert [n for n, p in sk.BONES if p is None] == ["DRIVER:DRIVER"]


@pytest.mark.skipif(not KUNOS.exists(), reason="refs/kunos_driver/driver.kn5 が無い")
def test_bones_match_kunos_names_only():
    """kn5 の種類 1 のうち、根・RIG_*・HAND_* の名前と骨だけをたどった親が BONES と一致する。"""
    import kn5io
    got = []

    def walk(n, parent):
        is_bone = n.cls == 1 and (n.name == "DRIVER:DRIVER" or n.name.startswith(("DRIVER:RIG_", "DRIVER:HAND_")))
        if is_bone:
            got.append((n.name, parent))
        for c in n.children:
            walk(c, n.name if is_bone else parent)

    walk(kn5io.read(str(KUNOS)).root, None)
    assert set(got) == set(sk.BONES)
    assert len(got) == len(sk.BONES)


def test_finger_bones_on_correct_side():
    # 右手は Thumb1-3・Index4-6・Middle4-6・Ring4-6・Pinkie4-6、左手は Thumb1-3・Index1-3…
    right = ["HAND_R_Thumb1", "HAND_Index4", "HAND_Middle4", "HAND_Ring4", "HAND_Pinkie4"]
    left = ["HAND_L_Thumb1", "HAND_Index1", "HAND_Middle1", "HAND_Ring1", "HAND_Pinkie1"]
    for n in right:
        assert "DRIVER:RIG_HAND_R" in ancestors("DRIVER:" + n), n
        assert "DRIVER:RIG_HAND_L" not in ancestors("DRIVER:" + n), n
    for n in left:
        assert "DRIVER:RIG_HAND_L" in ancestors("DRIVER:" + n), n
        assert "DRIVER:RIG_HAND_R" not in ancestors("DRIVER:" + n), n
    # 指は左右 15 本ずつ
    assert len([n for n, _ in sk.BONES if n.startswith("DRIVER:HAND_")]) == 30


def test_mesh_name_constants():
    assert sk.HEAD_MESHES == ("DRIVER:GEO_Driver_FACE", "DRIVER:HAIR", "DRIVER:CAP")
    assert sk.SKINNED_MESHES == ("DRIVER:BODY", "DRIVER:GLOVES")
