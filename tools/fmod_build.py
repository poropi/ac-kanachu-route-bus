"""kanachu_route_bus.bank を作る。

(1) generate: AC の音の SDK（ac_fmod_sdk_1_9、FMOD Studio 1.08 のプロジェクト）の Metadata から、手本の車 tatuusfa1 の
    19 event を写し、engine_ext / engine_int だけ design/sound/engine の 20 本で組み直した FMOD プロジェクトを作る。
    - 全オブジェクトの GUID を作り直す（手順書: 手本を複製して新しい GUID にする）。決定的に作るので GUIDs.txt は再現できる。
    - engine_*: load / coast の 2 トラック × 5 サンプル。各サンプルは rpms 軸に置き、autopitch の基準 = 自然回転数、
      隣り合うサンプルだけを相乗平均の位置を中心に交差させる。音量は throttle の曲線（load は踏むと出て、coast は離すと出る）。
    - door: 扉の開・閉。素材の無い event（horn・wind・wheel など）は無音の WAV を当てる（手本の音は 1 つも残さない）。
    - ミキサー（Group・VCA・Master）と common の MasterBank は SDK のまま（bus/vca/bank:/common の GUID が AC と同じになる）。
(2) build_remote: プロジェクトをゲーム PC の作業フォルダへ送り、fmodstudiocl.exe -build -export-guids で bank と GUIDs.txt を作り、
    Mac の audio/build/ に取り戻す。GUIDs.txt は make_guids_txt で自分の車の行だけに絞る。
"""
import argparse
import os
import copy
import re
import shutil
import subprocess
import uuid
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

import paths

CAR = paths.CAR_NAME
WORK = paths.WORK
SOUND_DIR = WORK / "design" / "sound"
SDK_FULL = WORK / "refs" / "audio_sdk" / "ac_fmod_sdk_1_9" / "Metadata"   # ゲーム PC の SDK の写し（git 管理外）
SDK_META = WORK / "audio" / "fmod_template" / "Metadata"                   # そこから generate に要るぶんだけ抜いたもの（git 管理）
PROJECT = WORK / "audio" / "fmod_project"
OUT_BUILD = WORK / "audio" / "build"

REMOTE_HOST = os.environ.get("GAME_PC", "")   # ゲーム PC の ssh ホスト名（tools/ac/local.env と同じ GAME_PC）
REMOTE_SUBDIR = r"Documents\kanachu-validation\fmod"   # ゲーム PC のホームからの相対
REMOTE_SCP = "Documents/kanachu-validation/fmod"
FMOD_CL = r"C:\Program Files\FMOD SoundSystem\FMOD Studio 1.08.12\fmodstudiocl.exe"

NS = uuid.UUID("6f1d1c54-5a0e-4c35-9d6b-7a0d2f9a8b11")
TEMPLATE_CAR = "tatuusfa1"
ROOT_ASSET_FOLDER = "{9ac7c7a7-33f8-4512-bd5e-63894d4a368b}"
SERIALIZATION = "Studio.01.08.00"

REQUIRED_EVENTS = sorted([
    "backfire_ext", "backfire_int", "bodywork", "door", "engine_ext", "engine_int", "gear_ext", "gear_grind",
    "gear_int", "horn", "limiter", "skid_ext", "skid_int", "tractioncontrol_ext", "tractioncontrol_int",
    "transmission", "turbo", "wheel", "wind"])

RPM_MAX = 5200            # 実回転の上限 2,600 rpm の 2 倍（手順書の推奨）
CROSS_WIDTH = 0.10        # 交差の半幅 = 境界回転数の 10 %
STEALING = "3"            # 手本のサンプルがすべて持つ値
MASTER_REMOVE_STOP = {"Event", "GameParameter", "DistanceParameter", "AngleParameter", "EventMixerMaster",
                      "EventMixer", "MasterTrack", "Timeline", "MixerInput", "EventAutomatableProperties",
                      "MarkerTrack"}

# 素材のある event だけ音を当てる。それ以外は無音（手本の音を残さない）。
DOOR_FILES = {"door_open.wav": "door_open", "door_close.wav": "door_close"}
SILENCE = "silence"


def gid(key):
    return "{%s}" % uuid.uuid5(NS, CAR + "/" + key)


# ---- samples.md / 配置 ---------------------------------------------------

def natural_rpms(text):
    """samples.md の「エンジンループ」表から {ファイル名（拡張子なし）: 自然回転数}。"""
    out = {}
    for m in re.finditer(r"^\|\s*\[(engine_(?:ext|int)_(?:load|coast)_\d{4})\]\([^)]*\)\s*\|[^|]*\|\s*(\d+)\s*\|",
                         text, re.M):
        out[m.group(1)] = int(m.group(2))
    return out


def layout(roots, maximum, width=CROSS_WIDTH):
    """rpms 軸への置き方。roots は自然回転数の昇順。隣り合う 2 本だけが、相乗平均を中心に ±width で交差する。"""
    bounds = [(a * b) ** 0.5 for a, b in zip(roots, roots[1:])]
    out = []
    for i, r in enumerate(roots):
        start = 0 if i == 0 else round(bounds[i - 1] * (1 - width))
        end = maximum if i == len(roots) - 1 else round(bounds[i] * (1 + width))
        fin = None if i == 0 else (start, round(bounds[i - 1] * (1 + width)))
        fout = None if i == len(roots) - 1 else (round(bounds[i] * (1 - width)), end)
        out.append({"root": r, "start": start, "length": end - start, "fade_in": fin, "fade_out": fout})
    return out


# ---- XML ------------------------------------------------------------------

def read(path):
    return ET.parse(path).getroot()


def write(path, root):
    ET.indent(root, space="    ")
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ET.tostring(root, encoding="unicode")
    path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n", encoding="utf8", newline="\n")


def new_root():
    return ET.Element("objects", {"serializationModel": SERIALIZATION})


def prop(o, name):
    e = o.find("property[@name='%s']/value" % name)
    return None if e is None else e.text


def set_prop(o, name, value):
    p = o.find("property[@name='%s']" % name)
    if p is None:
        p = ET.SubElement(o, "property", {"name": name})
        # property は relationship より前に置く
        o.remove(p)
        idx = len(o.findall("property"))
        o.insert(idx, p)
        ET.SubElement(p, "value")
    p.find("value").text = str(value)


def rels(o, name):
    return [d.text for d in o.findall("relationship[@name='%s']/destination" % name)]


def set_rel(o, name, ids):
    for r in o.findall("relationship[@name='%s']" % name):
        o.remove(r)
    if ids:
        r = ET.SubElement(o, "relationship", {"name": name})
        for i in ids:
            ET.SubElement(r, "destination").text = i


def make_obj(root, cls, oid, props=None, relations=None):
    o = ET.SubElement(root, "object", {"class": cls, "id": oid})
    for k, v in (props or {}).items():
        p = ET.SubElement(o, "property", {"name": k})
        ET.SubElement(p, "value").text = str(v)
    for k, ids in (relations or {}).items():
        r = ET.SubElement(o, "relationship", {"name": k})
        for i in ids:
            ET.SubElement(r, "destination").text = i
    return o


def remap(root, key):
    """このファイルの中で定義されている ID だけを作り直す（外部の GUID への参照はそのまま）。"""
    local = {o.get("id") for o in root}
    mp = {old: gid("%s/%s" % (key, old)) for old in local}
    for o in root:
        o.set("id", mp[o.get("id")])
        for d in o.iter("destination"):
            if d.text in mp:
                d.text = mp[d.text]
    return mp


# ---- WAV --------------------------------------------------------------------

def wav_info(path):
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), w.getnchannels(), w.getnframes() / w.getframerate()


def write_silence(path, seconds=1.0, rate=48000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))


def audio_sources(sound_dir):
    """{アセットの相対パス: 元ファイル}。"""
    src = {}
    for view in ("ext", "int"):
        for load in ("load", "coast"):
            for n in sorted((sound_dir / "engine").glob("engine_%s_%s_*.wav" % (view, load))):
                src["%s/Engine %s/%s" % (CAR, view.upper(), n.name)] = n
    for n in ("door_open.wav", "door_close.wav"):
        src["%s/Effects/%s" % (CAR, n)] = sound_dir / "effects" / n
    return src


# ---- 生成 ---------------------------------------------------------------------

def folder_chain(folder_id, folders):
    chain = []
    while folder_id in folders:
        chain.append(folder_id)
        folder_id = folders[folder_id][1]
    return chain


def generate(sdk_meta, out, sound_dir, samples_md):
    sdk_meta, out, sound_dir = Path(sdk_meta), Path(out), Path(sound_dir)
    natural = natural_rpms(Path(samples_md).read_text(encoding="utf8"))
    meta = out / "Metadata"
    if out.exists():
        if (WORK / "audio").resolve() in out.resolve().parents:
            shutil.rmtree(out)
        elif any(out.iterdir()):
            raise ValueError("空でない %s は消さない（消してよいのはリポジトリの audio/ の下だけ）" % out)
    meta.mkdir(parents=True)
    (out / (CAR + ".fspro")).write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<objects serializationModel="%s"/>\n' % SERIALIZATION, encoding="utf8")

    # 1. ミキサー・VCA・Workspace などは SDK のまま
    for name in ("Group", "VCA", "MixerView", "Return", "Snapshot", "SnapshotGroup", "BankFolder"):
        (meta / name).mkdir()
        for f in (sdk_meta / name).glob("*.xml"):
            shutil.copyfile(f, meta / name / f.name)
    for name in ("Master.xml", "Mixer.xml", "Tags.xml", "Workspace.xml"):
        shutil.copyfile(sdk_meta / name, meta / name)

    # 2. 音声アセット（AudioFile）
    (meta / "AudioFile").mkdir()
    audio_id = {}
    src = audio_sources(sound_dir)
    write_silence(out / "Assets" / CAR / "Silence" / "silence.wav")
    for rel_path in sorted(src):
        dst = out / "Assets" / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src[rel_path], dst)
    for dst in sorted((out / "Assets").rglob("*.wav")):
        rel_path = dst.relative_to(out / "Assets").as_posix()
        rate, ch, length = wav_info(dst)
        oid = gid("audiofile/" + rel_path)
        audio_id[rel_path] = oid
        root = new_root()
        make_obj(root, "AudioFile", oid,
                 {"assetPath": rel_path, "frequencyInKHz": repr(rate / 1000.0), "channelCount": ch,
                  "length": repr(length)},
                 {"masterAssetFolder": [ROOT_ASSET_FOLDER]})
        write(meta / "AudioFile" / (oid + ".xml"), root)

    # 根のアセットフォルダ（MasterAssetFolder）。他の Asset（SDK の個別フォルダ設定）は持ち込まない
    (meta / "Asset").mkdir()
    shutil.copyfile(sdk_meta / "Asset" / (ROOT_ASSET_FOLDER + ".xml"), meta / "Asset" / (ROOT_ASSET_FOLDER + ".xml"))

    # 3. EncodingSetting: プラットフォームと根のアセットフォルダのものだけ（SDK の showroom 用は捨てる）
    (meta / "EncodingSetting").mkdir()
    for f in (sdk_meta / "EncodingSetting").glob("*.xml"):
        enc = rels(read(f)[0], "encodable")
        if enc and enc[0] != "{08d44889-4b3a-4fe1-8b15-45f90de6e896}":
            shutil.copyfile(f, meta / "EncodingSetting" / f.name)

    # 4. 銀行: common（MasterBank）は SDK のまま、車用は手本の複製
    (meta / "Bank").mkdir()
    template_bank = None
    for f in (sdk_meta / "Bank").glob("*.xml"):
        o = read(f)[0]
        if o.get("class") == "MasterBank":
            shutil.copyfile(f, meta / "Bank" / f.name)
        elif prop(o, "name") == TEMPLATE_CAR:
            template_bank = read(f)
    bank_root = template_bank
    remap(bank_root, "bank")
    bank = bank_root[0]
    bank_id = bank.get("id")
    set_prop(bank, "name", CAR)
    write(meta / "Bank" / (bank_id + ".xml"), bank_root)

    # 5. EventFolder: 手本のフォルダの祖先 + 自分の車のフォルダ
    (meta / "EventFolder").mkdir()
    folders = {}
    for f in (sdk_meta / "EventFolder").glob("*.xml"):
        o = read(f)[0]
        p = rels(o, "folder")
        folders[o.get("id")] = (prop(o, "name"), p[0] if p else None, f)
    tpl_folder = next(i for i, (n, p, f) in folders.items() if n == TEMPLATE_CAR)
    cars_folder = folders[tpl_folder][1]
    for i in folder_chain(cars_folder, folders):
        shutil.copyfile(folders[i][2], meta / "EventFolder" / folders[i][2].name)
    car_folder = gid("eventfolder")
    root = new_root()
    make_obj(root, "EventFolder", car_folder, {"name": CAR}, {"folder": [cars_folder]})
    write(meta / "EventFolder" / (car_folder + ".xml"), root)

    # 6. Event
    (meta / "Event").mkdir()
    sdk_audio = {}
    for f in (sdk_meta / "AudioFile").glob("*.xml"):
        o = read(f)[0]
        sdk_audio[o.get("id")] = prop(o, "assetPath")
    count = 0
    for f in sorted((sdk_meta / "Event").glob("*.xml")):
        root = read(f)
        ev = next(o for o in root if o.get("class") == "Event")
        if rels(ev, "folder") != [tpl_folder]:
            continue
        name = prop(ev, "name")
        remap(root, "event/" + name)
        ev = next(o for o in root if o.get("class") == "Event")
        set_rel(ev, "folder", [car_folder])
        set_rel(ev, "banks", [bank_id])
        if name in ("engine_ext", "engine_int"):
            build_engine(root, ev, name[len("engine_"):], natural, audio_id)
        else:
            repoint_audio(root, sdk_audio, audio_id)
        write(meta / "Event" / (ev.get("id") + ".xml"), root)
        count += 1
    assert count == len(REQUIRED_EVENTS), count


def repoint_audio(root, sdk_audio, audio_id):
    for s in root:
        if s.get("class") != "SingleSound":
            continue
        old = sdk_audio[rels(s, "audioFile")[0]]
        base = old.rsplit("/", 1)[-1]
        if base in DOOR_FILES:
            new = "%s/Effects/%s" % (CAR, base)
        else:
            new = "%s/Silence/silence.wav" % CAR
        set_rel(s, "audioFile", [audio_id[new]])


def build_engine(root, ev, view, natural, audio_id):
    objs = {o.get("id"): o for o in root}
    cls = {i: o.get("class") for i, o in objs.items()}
    # 手本の load / coast トラックから、グループのパンナーの設定だけを借りる
    panner = {}
    for gt in rels(ev, "groupTracks"):
        grp = objs[rels(objs[gt], "mixerGroup")[0]]
        n = prop(grp, "name")
        for kind in ("load", "coast"):
            if kind in n and kind not in panner:
                panner[kind] = copy.deepcopy(objs[rels(grp, "panner")[0]])
    master = next(i for i, c in cls.items() if c == "EventMixerMaster")
    # 手本のトラックと、そこから届くオブジェクトを全部消す
    remove, stack = set(), list(rels(ev, "groupTracks"))
    while stack:
        i = stack.pop()
        if i in remove or i not in objs or cls[i] in MASTER_REMOVE_STOP:
            continue
        remove.add(i)
        for d in objs[i].iter("destination"):
            stack.append(d.text)
    for i in remove:
        root.remove(objs[i])
    for o in root:
        for r in list(o.findall("relationship")):
            for d in list(r.findall("destination")):
                if d.text in remove:
                    r.remove(d)
            if not r.findall("destination"):
                o.remove(r)
    params = {prop(o, "name"): o for o in root if o.get("class") == "GameParameter"}
    rpms, throttle = params["rpms"], params["throttle"]
    set_prop(rpms, "maximum", RPM_MAX)
    set_prop(throttle, "minimum", 0)
    set_prop(throttle, "maximum", 1)
    set_rel(rpms, "modules", [])
    track_ids, all_modules, curves = [], [], []
    curve_points = {"load": [(0.05, -80.0, -0.35), (0.85, 0.0, None)],
                    "coast": [(0.1, 0.0, 0.56), (0.85, -80.0, None)]}
    for kind in ("load", "coast"):
        key = "engine_%s/%s" % (view, kind)
        files = sorted(n for n in natural if n.startswith("engine_%s_%s_" % (view, kind)))
        roots = [natural[n] for n in files]
        lay = layout(roots, RPM_MAX)
        ids = {r: gid("%s/%s" % (key, r)) for r in
               ("track", "auto", "curve", "group", "chain", "fader", "panner")}
        sounds = [gid("%s/sound%d" % (key, i)) for i in range(len(files))]
        fouts = [gid("%s/fout%d" % (key, i)) for i in range(len(files))]
        fins = [gid("%s/fin%d" % (key, i)) for i in range(len(files))]
        make_obj(root, "GroupTrack", ids["track"], None,
                 {"automationTracks": [ids["auto"]], "modules": sounds, "mixerGroup": [ids["group"]]})
        make_obj(root, "AutomationTrack", ids["auto"], {"nameOfPropertyBeingAutomated": "volume"},
                 {"automationCurves": [ids["curve"]], "objectBeingAutomated": [ids["group"]]})
        pts = []
        for j, (pos, val, shape) in enumerate(curve_points[kind]):
            pid = gid("%s/point%d" % (key, j))
            pts.append(pid)
            p = {"position": pos, "value": val}
            if shape is not None:
                p["curveShape"] = shape
            make_obj(root, "AutomationPoint", pid, p)
        make_obj(root, "AutomationCurve", ids["curve"], None, {"automationPoints": pts})
        curves.append(ids["curve"])
        make_obj(root, "EventMixerGroup", ids["group"], {"name": kind},
                 {"effectChain": [ids["chain"]], "panner": [ids["panner"]], "output": [master]})
        make_obj(root, "MixerBusEffectChain", ids["chain"], None, {"effects": [ids["fader"]]})
        make_obj(root, "MixerBusFader", ids["fader"])
        pn = panner[kind]
        pn.set("id", ids["panner"])
        root.append(pn)
        for i, (name, spec) in enumerate(zip(files, lay)):
            rel_path = "%s/Engine %s/%s.wav" % (CAR, view.upper(), name)
            ap = gid("%s/autopitch%d" % (key, i))
            make_obj(root, "AutopitchModulator", ap, {"nameOfPropertyBeingModulated": "pitch", "root": spec["root"]})
            relations = {"modulators": [ap], "audioFile": [audio_id[rel_path]]}
            if spec["fade_in"]:
                relations["fadeInCurve"] = [fins[i]]
            if spec["fade_out"]:
                relations["fadeOutCurve"] = [fouts[i]]
            make_obj(root, "SingleSound", sounds[i],
                     {"start": spec["start"], "length": spec["length"], "voiceStealing": STEALING,
                      "looping": "true"}, relations)
            # 隣り合う 2 本の交差: 後ろの fade-in と前の fade-out は、互いを relatedModule にする
            if spec["fade_in"]:
                a, b = spec["fade_in"]
                sp, ep = gid("%s/fin%d/s" % (key, i)), gid("%s/fin%d/e" % (key, i))
                make_obj(root, "AutomationPoint", sp, {"position": a, "value": 0, "curveShape": -0.2547})
                make_obj(root, "AutomationPoint", ep, {"position": b, "value": 1})
                make_obj(root, "FadeCurve", fins[i], None,
                         {"startPoint": [sp], "endPoint": [ep], "relatedModule": [sounds[i - 1]]})
            if spec["fade_out"]:
                a, b = spec["fade_out"]
                sp, ep = gid("%s/fout%d/s" % (key, i)), gid("%s/fout%d/e" % (key, i))
                make_obj(root, "AutomationPoint", sp, {"position": a, "value": 1, "curveShape": 0.2547})
                make_obj(root, "AutomationPoint", ep, {"position": b, "value": 0})
                make_obj(root, "FadeCurve", fouts[i], None,
                         {"startPoint": [sp], "endPoint": [ep], "relatedModule": [sounds[i + 1]]})
        track_ids.append(ids["track"])
        all_modules += sounds
    set_rel(ev, "groupTracks", track_ids)
    set_rel(rpms, "modules", all_modules)
    set_rel(throttle, "automationCurves", curves)


def extract_template(sdk_full, dest):
    """SDK の Metadata から generate が読むものだけを dest に写す（音声は無い）。"""
    sdk_full, dest = Path(sdk_full), Path(dest)
    if dest.exists():
        if (WORK / "audio").resolve() not in dest.resolve().parents:
            raise ValueError("%s は消さない" % dest)
        shutil.rmtree(dest)
    shutil.copytree(sdk_full, dest, ignore=shutil.ignore_patterns("Event", "AudioFile", "Asset"))
    folders = {}
    for f in (sdk_full / "EventFolder").glob("*.xml"):
        o = read(f)[0]
        folders[o.get("id")] = prop(o, "name")
    tpl = next(i for i, n in folders.items() if n == TEMPLATE_CAR)
    used = set()
    (dest / "Event").mkdir()
    for f in (sdk_full / "Event").glob("*.xml"):
        root = read(f)
        ev = next(o for o in root if o.get("class") == "Event")
        if rels(ev, "folder") == [tpl]:
            shutil.copyfile(f, dest / "Event" / f.name)
            used |= {d.text for s in root if s.get("class") == "SingleSound" for d in s.findall("relationship[@name='audioFile']/destination")}
    (dest / "AudioFile").mkdir()
    for u in used:
        shutil.copyfile(sdk_full / "AudioFile" / (u + ".xml"), dest / "AudioFile" / (u + ".xml"))
    (dest / "Asset").mkdir()
    shutil.copyfile(sdk_full / "Asset" / (ROOT_ASSET_FOLDER + ".xml"), dest / "Asset" / (ROOT_ASSET_FOLDER + ".xml"))


# ---- GUIDs.txt ----------------------------------------------------------------

def make_guids_txt(exported, car=CAR):
    """FMOD の export-guids 出力から AC に要る行だけ（自分の bank・common・bus・vca・自分の event）。ASCII・CRLF。"""
    own_bank, common, shared, events = [], [], [], []
    for line in exported.splitlines():
        m = re.match(r"^(\{[0-9a-fA-F-]+\})\s+(\S+)\s*$", line)
        if not m:
            continue
        guid, name = m.groups()
        row = "%s %s" % (guid, name)
        if name == "bank:/" + car:
            own_bank.append(row)
        elif name == "bank:/common":
            common.append(row)
        elif name.startswith(("bus:", "vca:", "snapshot:")):
            shared.append(row)
        elif name.startswith("event:/cars/%s/" % car):
            events.append(row)
    if not own_bank:
        raise ValueError("bank:/%s が GUIDs に無い" % car)
    return "\r\n".join(own_bank + common + shared + sorted(events, key=lambda r: r.split(" ", 1)[1])) + "\r\n"


# ---- ゲーム PC で bank を作る ----------------------------------------------------

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def ps(script):
    """ゲーム PC で PowerShell を走らせて出力を返す。ssh が失敗したら例外。"""
    r = subprocess.run(["ssh", REMOTE_HOST, script], capture_output=True)
    out = r.stdout.decode("cp932", "replace")
    if r.returncode != 0:
        raise RuntimeError("ssh が失敗（exit %d）: %s\n%s" % (r.returncode, script[:80], out))
    return out


PROC_FILTER = "$_.Name -like 'fmodstudio*' -or $_.Name -like 'FMOD Studio*'"


def build_remote(project=PROJECT, out_dir=OUT_BUILD):
    project, out_dir = Path(project), Path(out_dir)
    if not REMOTE_HOST:
        raise SystemExit("GAME_PC にゲーム PC の ssh ホスト名を入れてください")
    remote_dir = ps("Write-Output $HOME").strip() + "\\" + REMOTE_SUBDIR
    remote = remote_dir + r"\fmod_project"
    if "FRESH" not in ps("New-Item -ItemType Directory -Force '%s' | Out-Null; "
                         "if (Test-Path '%s') { Remove-Item '%s' -Recurse -Force -ErrorAction Stop }; "
                         "if (Test-Path '%s') { 'STALE' } else { 'FRESH' }" % (remote_dir, remote, remote, remote)):
        raise RuntimeError("ゲーム PC の古い %s が消せない" % remote)
    run(["scp", "-q", "-r", str(project), "%s:%s/" % (REMOTE_HOST, REMOTE_SCP)])
    fspro = remote + "\\" + CAR + ".fspro"
    if "OK" not in ps("if ((Test-Path '%s') -and -not (Test-Path '%s\\fmod_project')) { 'OK' }" % (fspro, remote)):
        raise RuntimeError("送ったプロジェクトの配置がおかしい（入れ子になっている）")
    # 自分が起動した FMOD だけ止める（ユーザーが開いている FMOD Studio は触らない）: 実行前の PID を控えて差分を取る
    before = {int(x) for x in ps("Get-Process | Where-Object { %s } | ForEach-Object { $_.Id }" % PROC_FILTER).split()}
    try:
        log = ps("& '%s' -build -banks %s -export-guids '%s' 2>&1 | Out-String; 'EXIT=' + $LASTEXITCODE"
                 % (FMOD_CL, CAR, fspro))
    finally:
        after = {int(x) for x in ps("Get-Process | Where-Object { %s } | ForEach-Object { $_.Id }" % PROC_FILTER).split()}
        for pid in sorted(after - before):
            print("自分が起動した FMOD プロセスを止める: PID", pid)
            ps("Stop-Process -Id %d -Force" % pid)
    print(log)
    if "Build completed successfully" not in log or "GUIDs exported successfully" not in log or "EXIT=0" not in log:
        raise RuntimeError("FMOD のビルドに失敗")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / "_remote"
    tmp.mkdir(exist_ok=True)
    run(["scp", "-q", "%s:%s/fmod_project/Build/Desktop/%s.bank" % (REMOTE_HOST, REMOTE_SCP, CAR), str(tmp)])
    run(["scp", "-q", "%s:%s/fmod_project/Build/GUIDs.txt" % (REMOTE_HOST, REMOTE_SCP), str(tmp)])
    shutil.copyfile(tmp / (CAR + ".bank"), out_dir / (CAR + ".bank"))
    guids = make_guids_txt((tmp / "GUIDs.txt").read_text(encoding="ascii"))
    (out_dir / "GUIDs.txt").write_bytes(guids.encode("ascii"))
    shutil.rmtree(tmp)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["template", "generate", "build", "all"])
    a = ap.parse_args()
    if a.step == "template":
        extract_template(SDK_FULL, SDK_META)
    if a.step in ("generate", "all"):
        generate(SDK_META, PROJECT, SOUND_DIR, SOUND_DIR / "samples.md")
    if a.step in ("build", "all"):
        build_remote()
