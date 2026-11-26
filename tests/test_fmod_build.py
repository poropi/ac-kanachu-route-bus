"""fmod_build: SDK のひな形から kanachu_route_bus の FMOD プロジェクトを作る処理と GUIDs.txt の絞り込み。"""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import fmod_build
import paths

ROOT = Path(__file__).resolve().parent.parent
SDK_META = ROOT / "audio" / "fmod_template" / "Metadata"
COMMITTED = ROOT / "audio" / "fmod_project" / "Metadata"
SAMPLES_MD = ROOT / "design" / "sound" / "samples.md"
CAR = paths.CAR_NAME
NATURAL = {"0600": None, "0900": 901, "1300": 1299, "1800": 1800, "2400": 2401}


def test_natural_rpms_from_samples_md():
    n = fmod_build.natural_rpms(SAMPLES_MD.read_text(encoding="utf8"))
    assert len(n) == 20
    assert n["engine_ext_load_0600"] == 601 and n["engine_int_load_0600"] == 602
    assert n["engine_ext_coast_1300"] == 1299 and n["engine_int_coast_2400"] == 2401


def test_layout_pairwise_crossfade_covers_range():
    roots = [601, 901, 1299, 1800, 2401]
    lay = fmod_build.layout(roots, 5200)
    assert [s["root"] for s in lay] == roots
    assert lay[0]["start"] == 0 and lay[-1]["start"] + lay[-1]["length"] == 5200
    for a, b in zip(lay, lay[1:]):
        a_end = a["start"] + a["length"]
        # 隣とだけ重なり、重なりの幅は fade の幅と同じ
        assert b["start"] < a_end
        assert a["fade_out"] == (b["start"], a_end) and b["fade_in"] == (b["start"], a_end)
        # 重なりの中心は隣り合う自然回転数の相乗平均
        assert abs((b["start"] + a_end) / 2 - (a["root"] * b["root"]) ** 0.5) < 1
    for a, c in zip(lay, lay[2:]):
        assert c["start"] >= a["start"] + a["length"]  # 3 つ重ならない
    assert lay[0]["fade_in"] is None and lay[-1]["fade_out"] is None


GUIDS = """{1} bank:/common
{2} bus:/
{3} bus:/grp_door
{4} vca:/vca_wind
{5} event:/cars/kanachu_route_bus/engine_ext
{6} event:/cars/kanachu_route_bus/door
{7} event:/cars/tatuusfa1/engine_ext
{8} event:/collisions/car/hit
{9} bank:/kanachu_route_bus
{a} bank:/showroom
{b} snapshot:/x
""".replace("{", "{0000000").replace("}", "-0000-0000-0000-000000000000}")


def test_make_guids_txt_filters_to_own_car():
    out = fmod_build.make_guids_txt(GUIDS, CAR)
    lines = out.split("\r\n")
    assert lines[-1] == ""
    names = [l.split(" ", 1)[1] for l in lines[:-1]]
    assert names[0] == "bank:/" + CAR and names[1] == "bank:/common"
    assert "event:/cars/%s/engine_ext" % CAR in names and "event:/cars/%s/door" % CAR in names
    assert "bus:/grp_door" in names and "vca:/vca_wind" in names
    assert not any("tatuusfa1" in n or "collisions" in n or "showroom" in n for n in names)
    out.encode("ascii")


def test_make_guids_txt_requires_own_bank():
    with pytest.raises(ValueError):
        fmod_build.make_guids_txt(GUIDS.replace("bank:/" + CAR, "bank:/other"), CAR)


# ---- 生成したプロジェクト -------------------------------------------------

def load_all(meta):
    objs, dests = {}, []
    for f in meta.rglob("*.xml"):
        for o in ET.parse(f).getroot():
            assert o.get("id") not in objs, "ID の重複: " + o.get("id")
            objs[o.get("id")] = (o, f)
            dests += [(o.get("id"), d.text) for d in o.iter("destination")]
    return objs, dests


def prop(o, name):
    e = o.find("property[@name='%s']/value" % name)
    return None if e is None else e.text


def rel(o, name):
    return [d.text for d in o.findall("relationship[@name='%s']/destination" % name)]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    if not SDK_META.exists():
        pytest.skip("audio/fmod_template がない")
    out = tmp_path_factory.mktemp("fmodproj")
    fmod_build.generate(SDK_META, out, ROOT / "design" / "sound", SAMPLES_MD)
    return out


@pytest.fixture(params=["generated", "committed"])
def meta(request, project):
    if request.param == "generated":
        return project / "Metadata"
    if not COMMITTED.exists():
        pytest.skip("audio/fmod_project がまだない")
    return COMMITTED


def events(meta):
    objs, _ = load_all(meta)
    res = {}
    for i, (o, f) in objs.items():
        if o.get("class") == "Event":
            res[prop(o, "name")] = (o, f)
    return res


def test_required_events_and_no_other_car(meta):
    ev = events(meta)
    assert set(ev) == set(fmod_build.REQUIRED_EVENTS)
    assert len(ev) == 19
    for name in ("engine_ext", "engine_int", "bodywork", "gear_ext", "gear_int", "wind", "wheel",
                 "skid_int", "skid_ext", "gear_grind", "backfire_ext", "backfire_int", "horn", "door",
                 "tractioncontrol_ext", "tractioncontrol_int", "transmission", "turbo", "limiter"):
        assert name in ev
    text = "".join(f.read_text(encoding="utf8") for f in meta.rglob("*.xml"))
    assert "tatuus" not in text.lower() and "Abarth" not in text and "common/" not in text
    folders = {prop(o, "name"): i for i, (o, f) in load_all(meta)[0].items() if o.get("class") == "EventFolder"}
    assert set(folders) == {"Master", "cars", CAR} or {"cars", CAR} <= set(folders)


def test_all_references_resolve_and_ids_unique(meta):
    objs, dests = load_all(meta)  # ID の重複は load_all が検出する
    bad = [(a, b) for a, b in dests if b not in objs and not b.startswith("{" + "0" * 8)
           and b not in EXTERNAL_OK]
    assert bad == []


# 参照先は全部プロジェクト内で定義されていること（FMOD は未定義の参照があるとプロジェクトを開けない）
EXTERNAL_OK = set()


def test_event_ids_differ_from_sdk(meta):
    if not SDK_META.exists():
        pytest.skip("SDK なし")
    sdk, _ = load_all(SDK_META)
    mine, _ = load_all(meta)
    sdk_events = {i for i, (o, f) in sdk.items() if o.get("class") == "Event"}
    assert sdk_events and not (sdk_events & set(mine))
    sdk_all = {i for i, (o, f) in sdk.items() if f.parent.name in ("Event", "AudioFile", "EventFolder")}
    assert not ({i for i, (o, f) in mine.items() if f.parent.name == "Event"} & sdk_all)


def engine_sounds(meta, name):
    objs, _ = load_all(meta)
    ev = events(meta)[name][0]
    mod = {i: objs[i][0] for i in objs}
    audio = {i: prop(o, "assetPath") for i, (o, f) in objs.items() if o.get("class") == "AudioFile"}
    out = {}
    for gt in rel(ev, "groupTracks"):
        g = mod[gt]
        gname = prop(mod[rel(g, "mixerGroup")[0]], "name")
        snd = []
        for m in rel(g, "modules"):
            s = mod[m]
            ap = mod[rel(s, "modulators")[0]]
            snd.append((int(float(prop(s, "start"))), int(float(prop(s, "length"))),
                        float(prop(ap, "root")), audio[rel(s, "audioFile")[0]]))
        out[gname] = sorted(snd)
    return ev, mod, out


@pytest.mark.parametrize("view", ["ext", "int"])
def test_engine_events_structure(meta, view):
    natural = fmod_build.natural_rpms(SAMPLES_MD.read_text(encoding="utf8"))
    ev, mod, tracks = engine_sounds(meta, "engine_" + view)
    assert set(tracks) == {"load", "coast"}
    params = {prop(mod[p], "name"): mod[p] for p in rel(ev, "parameters") if prop(mod[p], "name")}
    assert {"rpms", "throttle"} <= set(params)
    assert float(prop(params["rpms"], "maximum")) == 5200
    for tname, snd in tracks.items():
        assert len(snd) == 5
        assert [s[0] for s in snd] == sorted(s[0] for s in snd) and snd[0][0] == 0
        assert snd[-1][0] + snd[-1][1] == 5200
        for start, length, root, path in snd:
            stem = Path(path).stem
            assert path == "%s/Engine %s/%s.wav" % (CAR, view.upper(), stem)
            assert stem.startswith("engine_%s_%s_" % (view, tname))
            assert root == natural[stem]  # autopitch の基準 = 自然回転数
    # rpms parameter が全サウンドを持ち、throttle に load/coast の音量曲線がある
    all_mods = {m for g in rel(ev, "groupTracks") for m in rel(mod[g], "modules")}
    assert set(rel(params["rpms"], "modules")) == all_mods
    assert len(rel(params["throttle"], "automationCurves")) == 2


def test_engine_throttle_curves_crossfade(meta):
    ev, mod, _ = engine_sounds(meta, "engine_ext")
    thr = [mod[p] for p in rel(ev, "parameters") if prop(mod[p], "name") == "throttle"][0]
    curves = {}
    for g in rel(ev, "groupTracks"):
        name = prop(mod[rel(mod[g], "mixerGroup")[0]], "name")
        at = mod[rel(mod[g], "automationTracks")[0]]
        assert prop(at, "nameOfPropertyBeingAutomated") == "volume"
        c = mod[rel(at, "automationCurves")[0]]
        assert rel(c, "automationPoints") and c.get("id") in rel(thr, "automationCurves")
        curves[name] = sorted((float(prop(mod[p], "position")), float(prop(mod[p], "value")))
                              for p in rel(c, "automationPoints"))
    assert curves["load"][0][1] == -80 and curves["load"][-1][1] == 0   # アクセルを離すと load は消える
    assert curves["coast"][0][1] == 0 and curves["coast"][-1][1] == -80  # 踏むと coast は消える


def test_door_uses_our_effects_and_others_silent(meta):
    objs, _ = load_all(meta)
    audio = {i: prop(o, "assetPath") for i, (o, f) in objs.items() if o.get("class") == "AudioFile"}
    used = {}
    for name, (ev, f) in events(meta).items():
        if name.startswith("engine_"):
            continue
        evid = ev.get("id")
        for i, (o, ff) in objs.items():
            if ff == f and o.get("class") == "SingleSound":
                used.setdefault(name, set()).add(audio[rel(o, "audioFile")[0]])
    assert used["door"] == {"%s/Effects/door_open.wav" % CAR, "%s/Effects/door_close.wav" % CAR}
    for name, paths_ in used.items():
        if name != "door":
            assert paths_ == {"%s/Silence/silence.wav" % CAR}, name


def test_audio_files_exist_and_no_sdk_audio(project):
    objs, _ = load_all(project / "Metadata")
    for i, (o, f) in objs.items():
        if o.get("class") == "AudioFile":
            p = project / "Assets" / prop(o, "assetPath")
            assert p.exists(), p
            assert float(prop(o, "frequencyInKHz")) == 48 and prop(o, "channelCount") == "1"
    wavs = [p.relative_to(project / "Assets") for p in (project / "Assets").rglob("*") if p.is_file()]
    assert len(wavs) == 20 + 2 + 1  # エンジン 20 + 扉 2 + 無音
    assert all(w.parts[0] == CAR for w in wavs)


def test_bank_has_only_our_events(meta):
    objs, _ = load_all(meta)
    banks = {prop(o, "name"): i for i, (o, f) in objs.items() if o.get("class") in ("Bank", "MasterBank")}
    assert set(banks) == {CAR, "common"}
    assert banks["common"] == "{47dcf37a-6a8d-4ef6-9f82-2e0398fa69f9}"  # AC の common.bank と同じ GUID
    for name, (ev, f) in events(meta).items():
        assert rel(ev, "banks") == [banks[CAR]]
    # 混ぜ物のミキサー（bus/VCA）は SDK のまま
    assert len(list((meta / "Group").glob("*.xml"))) == 22 and len(list((meta / "VCA").glob("*.xml"))) == 6


def test_generation_is_deterministic(project, tmp_path):
    fmod_build.generate(SDK_META, tmp_path, ROOT / "design" / "sound", SAMPLES_MD)
    a = {p.relative_to(project): p.read_bytes() for p in (project / "Metadata").rglob("*.xml")}
    b = {p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "Metadata").rglob("*.xml")}
    assert a == b


def test_committed_project_matches_generator(project):
    if not COMMITTED.exists():
        pytest.skip("audio/fmod_project がまだない")
    a = {p.relative_to(project): p.read_bytes() for p in (project / "Metadata").rglob("*.xml")}
    b = {p.relative_to(COMMITTED.parent): p.read_bytes() for p in COMMITTED.rglob("*.xml")}
    assert a == b


def test_committed_guids_txt():
    g = ROOT / "audio" / "build" / "GUIDs.txt"
    if not g.exists():
        pytest.skip("audio/build/GUIDs.txt がまだない")
    text = g.read_bytes().decode("ascii")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    lines = text.split("\r\n")[:-1]
    names = [re.match(r"^\{[0-9a-f-]{36}\} (\S+)$", l).group(1) for l in lines]
    assert names[0] == "bank:/" + CAR
    for ev in fmod_build.REQUIRED_EVENTS:
        assert "event:/cars/%s/%s" % (CAR, ev) in names
    assert not any(n.startswith("event:/") and not n.startswith("event:/cars/%s/" % CAR) for n in names)
    assert "tatuusfa1" not in text


def test_throttle_range_explicit(meta):
    for name in ("engine_ext", "engine_int"):
        ev, mod, _ = engine_sounds(meta, name)
        thr = [mod[p] for p in rel(ev, "parameters") if prop(mod[p], "name") == "throttle"][0]
        assert float(prop(thr, "minimum")) == 0 and float(prop(thr, "maximum")) == 1


def test_generate_refuses_to_delete_foreign_dir(tmp_path):
    (tmp_path / "precious.txt").write_text("x")
    with pytest.raises(ValueError):
        fmod_build.generate(SDK_META, tmp_path, ROOT / "design" / "sound", SAMPLES_MD)
    assert (tmp_path / "precious.txt").exists()


def test_extract_template_matches_full_sdk(tmp_path):
    full = ROOT / "refs" / "audio_sdk" / "ac_fmod_sdk_1_9" / "Metadata"
    if not full.exists():
        pytest.skip("refs の SDK なし")
    a, b = tmp_path / "a", tmp_path / "b"
    fmod_build.generate(full, a, ROOT / "design" / "sound", SAMPLES_MD)
    fmod_build.generate(SDK_META, b, ROOT / "design" / "sound", SAMPLES_MD)
    fa = {p.relative_to(a): p.read_bytes() for p in a.rglob("*.xml")}
    fb = {p.relative_to(b): p.read_bytes() for p in b.rglob("*.xml")}
    assert fa == fb
