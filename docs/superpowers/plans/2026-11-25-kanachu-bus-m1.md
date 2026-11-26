# 神奈中バス MOD 実装計画 — M1（箱のバスをゲームで走らせる）＋ M2〜M5 の枠

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 寸法どおりの箱と 4 輪（後輪ダブル）だけのバスを、テンプレート無しの kn5 と新しく書いた物理一式で組み、ゲーム PC の Assetto Corsa で読み込み・自動運転・測定まで通す。

**Architecture:** 諸元は `tools/spec.json` の 1 か所に置き、物理 ini・UI・箱のモデルはすべてそこから生成する。モデルは Blender（`blender -b`）で .blend を作り、ZC32S 由来の `kn5io.py` で kn5 に書き出す（テンプレートの kn5 は使わず、マテリアルは `tools/materials.json` から作る）。組み立ては `build/kanachu_route_bus/` を毎回作り直し、ゲーム PC へは写しを送って Lua アプリで走らせ、ログと画像を Mac へ回収する。

**Tech Stack:** Python 3（numpy, Pillow, pytest）、Blender 5.2（`/Applications/Blender.app/Contents/MacOS/Blender`、無ければ `which blender`）、ssh/scp で ゲーム PC（PowerShell）、CSP の Lua アプリ。

**Spec:** `docs/superpowers/specs/2026-11-25-kanachu-bus-design.md`（諸元の出典は `docs/research/erga_specs.md`）

## Global Constraints

- 車のフォルダ名 `kanachu_route_bus`、主 kn5 は `kanachu_route_bus.kn5`。
- 座標: Blender は Z 上・+Y 前・+X 右、原点は前後車軸の中点の真下の地面・車幅の中心。kn5 へは `(x,y,z) = (-bx, bz, by)`（ZC32S と同じ変換）。単位 m。右ハンドル。
- 寸法: 全長 10.430、全幅 2.485、全高 3.105、WB 5.300、トレッド 前 2.065／後 1.820、最低地上高 0.130、タイヤ外径 0.9565（半径 0.478）、275/70R22.5。
- 物理の公式値: 車両重量 9,790 kg、773 N·m @1,600 rpm、169 kW @2,150 rpm、ギア 3.486/1.864/1.409/1.000/0.749/0.652、後退 5.027、最終 6.500、最小回転半径 8.3 m。
- 仮定値（spec.json で `"src": "assumption"` を付ける）: ドライバー 75 kg、重心 前 40%、アイドル 600 rpm、リミッター 2,600 rpm、後輪の物理幅 0.60、ばねの固有振動数 1.2 Hz、CD 0.6、ハンドル片側 900°、燃料タンク 160 L、（前後オーバーハングは 2026-11-26 に公式の旋回軌跡図の前 2.30 m・後 2.83 m に変更。src は isuzu_kiseki）。
- ノード名・マテリアル名は設計書 §3「受け渡しの決まり」のとおり（`WHEEL_LF/RF/LR/RR`、`SUSP_*`、`STEER_HR`、`COCKPIT_HR`、マテリアル `paint`・`trim_black`・`glass`・`tyre`・`rim` ほか）。
- 1 メッシュの頂点は 65,535 以下（kn5 の u16 インデックス）。
- ゲーム PC: 始める前に `acs` プロセスが無いことを確かめる。`Documents\Assetto Corsa\cfg\race.ini`・`video.ini` を控えて終了時に戻す。入れた Lua アプリは終了時に `apps\lua` の外へ移す。`content\cars\kanachu_route_bus` 以外の車・コースに書き込まない。
- 完成品は Mac の `build/` に組み上げ、ゲーム PC には写しを送るだけ。
- 外部から借りる物（Kunos 車の音）は `refs/` に置き、git には入れない（`.gitignore`）。

## Review Focus

1. **車輪の向きと位置がゲーム内でずれる**（左右・前後の取り違え、後輪ダブルの中心が後トレッドからずれる）— Task 3 のテストで kn5 上の `WHEEL_*` の行列の平行移動を数値で固定する。
2. **静止時に車体が沈み込む・揺れ続ける**（10 t に対してばね・タイヤの FZ0 が乗用車の値のまま、1.2 Hz のばねの 17 cm のたわみを車高で補っていない）— Task 4 で静的たわみと静止時の車高をテストし、Task 7 のゲーム確認 2 で見る。
3. **ゲームが車を読めない／必須ファイル不足で落ちる**（skins が空、sfx が無い、ui_car.json の書式）— Task 5 の `validate.py` で必須ファイルの一覧を検査する。
4. **回転がリミッターに張り付く・自動変速しない**（AUTO_SHIFTER の rpm がディーゼルの域と合わない）— Task 4 で UP < LIMITER、DOWN > アイドル をテストし、Task 7 の drag400 で回転の記録を見る。
5. **ゲーム PC の設定を壊す**（race.ini を戻し忘れる、Lua アプリが残る）— Task 6 の終了処理で SHA256 を比べ、Task 7 の各回の後に確かめる。

---

### Task 1: ツールの土台（kn5io・acd の流用と往復テスト）

**Files:**
- Create: `tools/kn5io.py`（`~/Documents/develop/ac_swift_zc32s/tools/kn5io.py` の写し。先頭に出典の 1 行）
- Create: `tools/acd.py`（同 `acd.py` の写し）
- Create: `tools/paths.py`（`WORK`、`CAR_NAME="kanachu_route_bus"`、`BUILD=WORK/build/CAR_NAME`、`BLENDER`（環境変数 `BLENDER` か既定パス））
- Create: `tests/test_kn5io.py`、`pyproject.toml`（pytest の設定だけ。`[tool.pytest.ini_options] testpaths=["tests"]`）

**Interfaces:**
- Produces: `kn5io.read(path) -> Kn5`、`kn5io.write(k: Kn5, path)`、`kn5io.walk(node)`、`kn5io.Kn5/Node/Mat/Tex`（ZC32S と同じ）。`acd.pack(data_dir, out, name)`／`acd.unpack(path, out_dir, name)`（ZC32S の関数名に合わせる。違えば ZC32S 側の名前を使う）。`paths.*`。

- [ ] **Step 1: テストを書く** — `test_roundtrip_ht81s`: `~/Documents/develop/nix_suzuki_swift_sport_ht81s/suzuki_swift_sport_ht81s.kn5` を read→write した結果が元とバイト一致（ファイルが無ければ skip）。`test_acd_roundtrip`: 一時フォルダに ini 2 つを作り、名前 `kanachu_route_bus` で pack→unpack して中身が一致。
- [ ] **Step 2: 失敗を確かめる** — `python3 -m pytest tests/test_kn5io.py -v` → ImportError。
- [ ] **Step 3: 3 ファイルを置く**（写しと paths.py）。
- [ ] **Step 4: 通ることを確かめる** — 同じコマンドで 2 passed。
- [ ] **Step 5: コミット** — `git add tools tests pyproject.toml && git commit -m "ツールの土台: kn5io・acd を ZC32S から流用"`

### Task 2: テンプレート無しの kn5 書き出し

**Files:**
- Create: `tools/materials.json` — マテリアル名 → `{"shader", "blend", "alpha_tested", "depth_mode", "props": [[名前, 値], ...], "tex": [[スロット名, 番号, テクスチャ名], ...]}`。属性の並びは HT81S の同じシェーダに合わせる（`ksPerPixelMultiMap`: ksAmbient…sunSpecularEXP の 18 個、`ksPerPixel`: 6 個、`ksWindscreen`: 6 個、`ksTyres`: 14 個、`ksPerPixelReflection`: 10 個）。M1 で使うのは `paint`（ksPerPixelMultiMap、txDiffuse=`paint.dds`、txNormal/txMaps/txDetail=`flat_nm.dds`/`maps_default.dds`/`detail_white.dds`）、`trim_black`（ksPerPixel）、`glass`（ksWindscreen、blend 1）、`tyre`（ksTyres）、`rim`（ksPerPixel）。
- Create: `tools/textures.py` — `make_default_textures(out_dir) -> list[str]`: 上の既定テクスチャ（単色 4×4〜64×64 の DDS。DXT 不要、無圧縮 A8R8G8B8）と M1 用の `paint.dds`（単色クリーム #F3E6B0）を書く。DDS は Pillow の DDS 書き出し、無理なら自前で 128 バイトのヘッダを書く。
- Create: `tools/blend_to_kn5.py` — ZC32S 版をもとに、`--template` を外し `--materials tools/materials.json --tex-dir DIR --out OUT [--root NAME]` にする。kn5 の version は 5、extra は None、textures は `--tex-dir` の `*.dds` をマテリアルが参照する順に `Tex(1, name, bytes)` で入れる。参照されているのに無いテクスチャはエラーで止める。
- Test: `tests/test_blend_to_kn5.py`

**Interfaces:**
- Consumes: Task 1 の `kn5io`。
- Produces: `blender -b X.blend --python tools/blend_to_kn5.py -- --materials M --tex-dir D --out O.kn5`。オブジェクトのカスタムプロパティ `kn5_name`（必須）・`kn5_material`・`kn5_order` は ZC32S と同じ意味。`textures.make_default_textures(out_dir)`。

- [ ] **Step 1: テストを書く** — Blender を subprocess で起動して小さな .blend を作る補助スクリプト `tests/fixtures/make_cube.py`（空の親 `ROOT`(kn5_name=`kanachu_route_bus`) の下に、位置 (bx,by,bz)=(0.5, 2.0, 1.0) の 1 m 立方体 `CUBE`(kn5_name=`BODY_TEST`, kn5_material=`paint`)）。`test_export_cube`: 書き出した kn5 を read して、ノード名 `kanachu_route_bus`→`BODY_TEST`、マテリアル名に `paint`、三角形数 12、頂点の x の平均 ≈ −0.5・y ≈ 1.0・z ≈ 2.0（±1e-4）、テクスチャ名に `paint.dds` が含まれる。`test_missing_texture_fails`: tex-dir が空なら終了コード ≠ 0。Blender が無ければ skip。
- [ ] **Step 2: 失敗を確かめる** — `python3 -m pytest tests/test_blend_to_kn5.py -v` → FAIL。
- [ ] **Step 3: 実装する**（materials.json・textures.py・blend_to_kn5.py）。
- [ ] **Step 4: 通ることを確かめる** — 2 passed。さらに `tests/test_kn5io.py` も通ったまま。
- [ ] **Step 5: コミット** — `git commit -m "テンプレート無しの kn5 書き出しとマテリアル定義"`

### Task 3: 諸元の 1 か所化と箱のバスのモデル

**Files:**
- Create: `tools/spec.json` — Global Constraints の値をすべて入れる。各値は `{"v": 値, "src": "isuzu_A" | "calc" | "assumption"}`。
- Create: `tools/spec.py` — `load() -> dict[str, float]`（`v` だけを返す）と `derived(s) -> dict`（`tyre_radius=0.4783`、`rear_overhang=2.68`、`axle_z_front=+2.65`、`axle_z_rear=-2.65`（kn5 の z、原点は車軸の中点）、`steer_angle_deg = degrees(asin(WB/8.3)) ≈ 39.7`）。
- Create: `blender/m1_box_bus.py` — `blender -b --python blender/m1_box_bus.py -- --out blender/m1_box.blend`。作る物: 親の空 `ROOT`（kn5_name=`kanachu_route_bus`）。車体の箱 `BODY`（paint、x ±1.2425、y 前端 +2.65+2.45=5.10・後端 −5.33、z 0.13〜3.105、角を 0.1 m 面取り）、前面の窓の板 `WINDSHIELD`（glass）、黒い帯 `SKIRT`（trim_black）。空の `WHEEL_LF/RF/LR/RR`（位置: 前 (bx=∓1.0325, by=+2.65, bz=0.478)、後 (bx=∓0.91, by=−2.65, bz=0.478)、左が −bx）。各 WHEEL の子に円柱のタイヤ（tyre、半径 0.478、幅 0.275、32 分割）とホイール板（rim）。後輪はタイヤ 2 本を WHEEL の中心から ±0.16 m（X 方向）に置く。空の `SUSP_LF/RF/LR/RR`（WHEEL と同じ位置）、空の `STEER_HR`（運転席の前、bx=+0.75, by=+4.3, bz=1.75、ハンドル軸を後ろへ 20° 起こす）、空の `COCKPIT_HR`。
- Create: `blender/m1_collider.py` — 同じ寸法の箱 1 つ（12 三角形）の `collider.kn5` 用 .blend を作る（ノード名 `COLLIDER_BODY`、マテリアル `trim_black`）。
- Test: `tests/test_spec.py`、`tests/test_m1_model.py`

**Interfaces:**
- Consumes: Task 2 の書き出し。
- Produces: `spec.load()`、`spec.derived()`、`blender/m1_box.blend`、`blender/m1_collider.blend`。

- [ ] **Step 1: テストを書く** — `test_spec_values`: `load()["length"]==10.430`、`["wheelbase"]==5.300`、`["track_f"]==2.065`、`["track_r"]==1.820`、`["mass_vehicle"]==9790`、`derived()["tyre_radius"]` ≈ 0.4783、`["steer_angle_deg"]` ≈ 39.68（±0.05）、`spec.json` の各値に `src` がある。`test_box_bus_kn5`（Blender が無ければ skip）: 2 つの .blend を作って書き出し、kn5 の全頂点の外接箱が x 幅 2.485、y 高 3.105（最低 0.130 以下に面が無い、タイヤを除く）、z 長 10.430（各 ±0.02）。`WHEEL_LF` の行列の平行移動が (x=+1.0325, y=0.478, z=+2.65)、`WHEEL_RR` が (x=−0.91, y=0.478, z=−2.65)（±0.005、kn5 座標。+x が左）。ノード名に `SUSP_LF`…`SUSP_RR`、`STEER_HR`、`COCKPIT_HR` がある。collider は三角形 12。
- [ ] **Step 2: 失敗を確かめる** — `python3 -m pytest tests/test_spec.py tests/test_m1_model.py -v` → FAIL。
- [ ] **Step 3: 実装する。**
- [ ] **Step 4: 通ることを確かめる**、Blender でレンダー 1 枚（斜め前、Workbench）を `docs/progress/m1_box.png` に出して目で見る（車輪が車体の下に 4 つ、後輪が 2 本ずつ）。
- [ ] **Step 5: コミット** — `git commit -m "諸元の1か所化と M1 の箱のバス"`

### Task 4: 物理 ini 一式

**Files:**
- Create: `tools/physics.py` — `build(out_dir) -> list[str]`（書いたファイル名の一覧）。`python3 tools/physics.py --out build/data`。値は `spec` からだけ取る。書式（キーの並び・必須セクション）は `~/Documents/develop/ac_swift_zc32s/docs/research/ht81s_data_unpacked/` の同名ファイルに合わせる。書くファイル: car.ini、suspensions.ini、tyres.ini、drivetrain.ini、engine.ini、power.lut、brakes.ini、aero.ini、electronics.ini、damage.ini、setup.ini、lods.ini（LOD は主 kn5 だけ）、colliders.ini、cameras.ini、dash_cam.ini、mirrors.ini、lights.ini、sounds.ini、ambient_shadows.ini、ai.ini、fuel_cons.ini、tyre の lut（荷重特性・温度特性は HT81S の lut の形を流用してよい）。driver3d.ini は書かない（M1 は人形なし）。
- Test: `tests/test_physics.py`

決めてある計算（ほかは実装者が HT81S の書式に合わせて決める）:
- TOTALMASS = 9,790 + 75 = 9,865。CG_LOCATION = 0.40。
- power.lut は rpm|N·m。600 rpm から 2,600 rpm まで 100 rpm 刻み。1,600 で 773、2,150 で 750.6（169,000 W ÷ (2,150×2π/60)）、1,000〜1,600 は線形に上がり、2,150〜2,600 は 2,150 の出力をほぼ保って下がる。値には ZC32S と同じ駆動損失の係数 0.87 を掛ける（ゲーム内表示とカタログ値を合わせる AC の流儀）。
- ばね（SPRING_RATE、輪あたり）= 輪あたりのばね上質量 × (2π×1.2)²。ばね上質量 = 軸重/2 − HUB_MASS（前 250 kg、後 400 kg）。減衰は減衰比 0.3（BUMP）／0.45（REBOUND）で `2ζ√(k·m)`。
- タイヤ: RADIUS 0.478、RIM_RADIUS 0.298、WIDTH 前 0.275／後 0.60、FZ0 = 静止時の輪荷重（N）、DY0 0.85、DX0 0.90、LS_EXPY/LS_EXPX 0.85。
- ハンドル: STEER_LOCK 900、STEER_RATIO = 900 / 39.68 ≈ 22.7（符号は HT81S に合わせる）。
- drivetrain: TRACTION RWD、GEARS は公式値、FINAL 6.500、AUTO_SHIFTER UP 2,300／DOWN 1,200、AUTOCLUTCH の MIN_RPM 700／MAX_RPM 1,200、[AUTOCLUTCH] FORCED_ON=1（AT の代わり）。
- engine: MINIMUM 600、LIMITER 2,600、INERTIA 1.2（大きな回転部の仮定）。
- 空力: 車体の抵抗だけ。CD 0.6 × 面積 2.485×(3.105−0.130)=7.39 m²。
- brakes: 0.8 G で止まる合計トルク（9,865×9.81×0.8×0.478 ≈ 37,000 N·m）を前後 0.55／0.45 で分ける。MAX_TORQUE の単位（輪あたりか）を HT81S の値と車重から確かめてから入れる。

**Interfaces:**
- Consumes: Task 3 の `spec.load()`／`spec.derived()`。
- Produces: `physics.build(out_dir) -> list[str]`、`physics.read_ini(path) -> dict[section][key] -> str`（テストと validate が使う）。

- [ ] **Step 1: テストを書く** — `test_core_values`: car.ini の TOTALMASS 9865、suspensions の WHEELBASE 5.3・FRONT TRACK 2.065・REAR TRACK 1.82、tyres の FRONT RADIUS 0.478・REAR WIDTH 0.6、drivetrain の GEAR_1 3.486…GEAR_6 0.652・FINAL 6.5・GEAR_R −5.027、engine LIMITER 2600。`test_power_curve`: power.lut の 1,600 rpm の値 = 773×0.87（±1）、出力の最大が 2,000〜2,300 rpm にある。`test_static_deflection`: 各輪の静的たわみ（ばね上質量×9.81 ÷ SPRING_RATE）が 0.173±0.01 m（1.2 Hz の定義から決まる値）で、ROD_LENGTH で静止時の最低地上高が 0.130 m（±0.02）になるよう車高を合わせ、BUMPSTOP_UP が 0.08 m 以上残る。`test_shifter_window`: 600 < DOWN < UP < LIMITER。`test_all_files_parse`: 書いた ini が全部 `read_ini` で読め、重複キーが無い。
- [ ] **Step 2: 失敗を確かめる** — `python3 -m pytest tests/test_physics.py -v` → FAIL。
- [ ] **Step 3: 実装する。**
- [ ] **Step 4: 通ることを確かめる** — 全部 PASS。
- [ ] **Step 5: コミット** — `git commit -m "物理 ini 一式を諸元から生成"`

### Task 5: 組み立てと検査（音・UI・スキン・影を含む）

**Files:**
- Create: `tools/pick_sound.py` — ゲーム PC の Kunos 車（`ks_*`）の `data.acd` を scp で `refs/kunos_acd/` に取り、`acd.unpack` で engine.ini の LIMITER を読み、低い順に 5 台を表示する。いちばん低い車の `sfx/<車名>.bank` を `refs/sound/` に取る（借りた車名を `refs/sound/SOURCE.txt` に書く）。
- Create: `tools/sfx.py` — `build(out)`: `refs/sound/<src>.bank` を `sfx/kanachu_route_bus.bank` にコピーし、`GUIDs.txt` の車名を書き換える（ZC32S の sfx.py と同じ手順。GUIDs.txt も ゲーム PC から取る）。
- Create: `tools/ui.py` — `ui/ui_car.json`（name `Kanachu City Bus (Large Non-step)`、brand `Kanachu`、class `street`、specs: bhp 227（169 kW）、torque `773Nm`、weight `9790kg`、topspeed `110km/h`、torqueCurve／powerCurve は power.lut から）と `ui/badge.png`（M1 は単色の仮の絵。M4 で astra の絵に替える）。
- Create: `tools/assemble.py` — `build/kanachu_route_bus/` を消して作り直す: 主 kn5（Task 3）、`collider.kn5`、`data/`（Task 4。data.acd は作らない）、`sfx/`、`ui/`、`skins/0_test/`（`ui_skin.json`・`livery.png`・`preview.jpg` を仮の単色で）、`body_shadow.png`（上から見た外形の楕円ぼかし 128×128）と `tyre_0..3_shadow.png`（64×64）。最後に zip `build/kanachu_route_bus.zip`。
- Create: `tools/validate.py` — `validate(car_dir) -> list[str]`（空なら合格）。必須ファイル（上の全部と data の全 ini）、主 kn5 に `WHEEL_LF/RF/LR/RR`・`SUSP_*`・`STEER_HR`・`COCKPIT_HR` があること、全メッシュの頂点 ≤ 65,535、skins に 1 つ以上、ui_car.json が JSON として読めること。
- Test: `tests/test_assemble.py`

**Interfaces:**
- Consumes: Task 2〜4。
- Produces: `python3 tools/assemble.py` → `build/kanachu_route_bus/` と zip。`validate.validate(car_dir) -> list[str]`。

- [ ] **Step 1: テストを書く** — `test_validate_detects_missing`: 一時フォルダに組み立てたものから `data/car.ini` を消すと `validate` が 1 件以上返す。`test_build_valid`（Blender と refs/sound が無ければ skip）: `assemble` の結果に `validate` が空。
- [ ] **Step 2: 失敗を確かめる。**
- [ ] **Step 3: `pick_sound.py` を走らせて音の出どころを決める**（借りた車名と LIMITER を報告に書く）。続けて sfx・ui・assemble・validate を実装する。
- [ ] **Step 4: 通ることを確かめる** — `python3 -m pytest -v` 全部 PASS、`python3 tools/assemble.py && python3 tools/validate.py build/kanachu_route_bus` が「OK」。
- [ ] **Step 5: コミット**（refs/ と build/ は入れない）— `git commit -m "組み立てと検査、借りた音・仮の UI とスキン"`

### Task 6: ゲーム PC で走らせる仕組み

**Files:**
- Create: `tools/ac/KanachuProbe/manifest.ini`・`KanachuProbe.lua` — `hakone_mod_ac/tools/ac/HakoneProbe/` をもとにする。車が `kanachu_route_bus` のときだけ動く（`ac.getCarID(0)` で判定）。モードを `mode.txt` から読む:
  - `drive`: 5 秒待って自動運転、`duration` 秒。0.1 秒ごとに t, x, y, z, 速度 km/h, rpm, ギア, 車体のロール・ピッチ（度）を `log-<tag>.csv` に書く。最初の 5 秒（止まっている間）も記録する。30 秒ごとに撮影。
  - `accel`: drag400 で自動運転（全開になる区間）。同じ記録。
  - `circle`: ハンドルを最大に切って 10 km/h で旋回させる。CSP の Lua SDK でハンドルとアクセルを指示する関数を探して使う（ゲーム PC の `assettocorsa\extension\internal\lua-sdk\` の定義ファイルを grep する）。指示する手段が無ければ circle は作らず、その旨を報告する。
  - 撮影は追従カメラ・横・運転席の 3 つ（`ac.setCurrentCamera` 等、SDK で確かめた関数）。
- Create: `tools/ac/launch.ps1` — hakone の launch.ps1 をもとに: `-Tag -Track -Layout -Mode -Duration`。race.ini の [CAR_0] MODEL を `kanachu_route_bus`・SKIN を `0_test`、[RACE] TRACK／CONFIG_TRACK を引数に。控え→起動→終了→戻す→Lua アプリを外へ移す→ログ回収、は hakone と同じ。戻した後に race.ini・video.ini の SHA256 を控えと比べて `restored-<tag>.txt` に書く。
- Create: `tools/ac/run.sh` — `tools/ac/run.sh <track> <layout> <mode> [秒]`: AC 使用中なら止まる → `build/kanachu_route_bus` を `content\cars\kanachu_route_bus` へ送る（毎回消して置き直す）→ Lua アプリを zip で送る → launch → 完了待ち → `export/ac/<tag>/` へ回収。
- Create: `tools/ac/summarize.py` — `summarize(csv) -> dict`: `settle_s`（静止中にロール・ピッチの変化が 0.05° 未満になるまでの秒）、`max_rpm`、`t_0_40`（0→40 km/h の秒）、`vmax`、`max_roll_deg`、`flipped`（ロール > 45°）、`turn_radius_m`（circle のとき、位置の円当てはめ）、`max_lat_g`。
- Test: `tests/test_summarize.py`（合成した csv で各値を確かめる: 半径 8.3 m の円の点列 → turn_radius_m 8.3±0.05、40 km/h まで 10 秒で線形に加速 → t_0_40 10.0±0.1、静止中のロールが 1.0 秒で収まる → settle_s 1.0±0.1）

**Interfaces:**
- Consumes: Task 5 の `build/kanachu_route_bus/`。
- Produces: `tools/ac/run.sh`、`summarize.summarize(csv) -> dict`。`export/ac/<tag>/`（log csv、AC と CSP のログ、png、restored txt）。

- [ ] **Step 1: summarize のテストを書く**、失敗を確かめる。
- [ ] **Step 2: summarize.py を実装して通す。**
- [ ] **Step 3: Lua アプリ・launch.ps1・run.sh を書く。** CSP の Lua SDK の関数名は ゲーム PC の定義ファイルで確かめてから使う（確かめた関数名とファイルを報告に書く）。
- [ ] **Step 4: 空走らせ** — `tools/ac/run.sh yabitsu s1_up drive 30` を 1 回。AC が起動して車が読まれ、csv が 300 行前後回収され、`restored-<tag>.txt` に SHA256 一致と書かれ、`apps\lua\KanachuProbe` が残っていないこと。
- [ ] **Step 5: コミット**（export/ は .gitignore）— `git commit -m "ゲーム PC で走らせて記録を取る仕組み"`

### Task 7: M1 の試走と物理の調整

**Files:**
- Modify: `tools/spec.json`（仮定値だけ。公式値は変えない）
- Create: `docs/progress/m1_report.md`

- [ ] **Step 1: 3 本走らせる** — `run.sh yabitsu s1_up drive 180`、`run.sh ks_drag drag400 accel 60`、`run.sh drift "" circle 60`（drift はレイアウト無し）。
- [ ] **Step 2: 判定する** — 設計書 §8 の 1〜5: AC・CSP のログにこの車のエラーが無い（`kanachu` を含む行を全部読む）、`settle_s ≤ 2`、`flipped` が偽で y の急な落ち込みが無い、`max_rpm ≤ 2600`・`8 ≤ t_0_40 ≤ 16`・`vmax ≤ 115`、`turn_radius_m` 8.3±0.5・`max_lat_g ≤ 0.7`。撮影した画像は全部開いて見る。
- [ ] **Step 3: 外れた項目を直す** — 直すのは仮定値だけ（ばね・減衰・タイヤの DY0/DX0・後輪幅・AUTO_SHIFTER・INERTIA・ハンドル）。1 項目 3 回まで。直したら該当の 1 本だけ走らせ直す。3 回で外れたままなら値を記録して先へ進む。
- [ ] **Step 4: 報告を書く** — `docs/progress/m1_report.md` に、各項目の値・合否・使ったログの場所・直した仮定値と理由・借りた音の車名・circle の可否。data.acd に固めるかの判断（data/ のままで読めたなら固めない）も書く。
- [ ] **Step 5: コミット** — `git commit -m "M1: 箱のバスの試走と物理の調整"`

---

## M2 外装の取り込み（2026-11-26 追記。astra の外装 design/exterior/kanachu_exterior.blend は写真 4 枚と照合済み）

M2 の Global Constraints（M1 に加えて）:
- astra の .blend のオブジェクト名がそのまま kn5 のノード名になる（設計書 §3 の名前）。マテリアル名は `paint`・`trim_black`・`chrome`・`glass`・`glass_light`・`light_emit`・`dest_led`・`tyre`・`rim`・`rubber`（と M3 で `interior_*`）だけ。
- collider.kn5 は 根→ダミー→メッシュ の 3 段（M1 の実機で確定）。ドライバー 3 点は M1 と同じ。
- 主 kn5 の三角形は外装 11 万程度。LOD は B 8 万・C 2.5 万・D 6 千（±10 %）。

### Task 8: 外装の規約検査と kn5 書き出し

**Files:**
- Create: `tools/check_design.py` — `check(blend_path) -> list[str]`（Blender の中で実行。`blender -b X.blend --python tools/check_design.py -- --json out.json`）。検査: 必須のオブジェクト名（`ROOT`、`WHEEL_LF/RF/LR/RR`、`SUSP_*`、灯火 12、`DEST_*` 3、`DOOR_FRONT`・`DOOR_MID`）、マテリアル名が許可リストだけ、`WHEEL_*` の位置（±0.005、M1 の Task 3 と同じ値）、車体の外接箱（ミラー・ワイパー・ナンバーを除き 10.430 × 2.485 × 3.105 ±0.02）、1 メッシュの頂点 ≤ 65,535、全メッシュに UV、`paint` の UV が 0〜1 で重ならない。
- Create: `tools/prepare_blend.py` — astra の .blend を読み、書き出し用の一時 .blend を作る: 各オブジェクトに `kn5_name`＝オブジェクト名、`kn5_material`＝マテリアル名を入れる。モディファイアは適用。パックされた画像を `build/tex/` に DDS で書き出す（`textures.py` を使い、ミップマップ付き）。`ROOT` の `kn5_name` は `kanachu_route_bus`。
- Modify: `tools/materials.json`（`paint` の txDiffuse を `paint.dds`、灯火・行先の発光は ksPerPixel の ksEmissive を使う）。
- Modify: `tools/assemble.py` — 主 kn5 を箱のバスから外装に替える（`--model box|exterior`、既定 exterior）。
- Test: `tests/test_check_design.py`（壊した小さな .blend で各検査が引っかかること）、`tests/test_exterior_export.py`（外装の書き出し結果のノード名・マテリアル名・外接箱・WHEEL の行列）

### Task 9: LOD と当たり判定を外装から作る

**Files:**
- Create: `tools/lods.py`（ZC32S の lods.py をもとに、Decimate で B/C/D を作る。テンプレート無し版の blend_to_kn5 を使う）、`lods.ini` に LOD_1〜3。
- Create: `blender/collider_from_exterior.py` — 外装の車体から凸包を作り 200 三角形以下に削った collider（根→ダミー→メッシュ）。
- Test: LOD の三角形数、collider の階層と外接箱。

### Task 10: ゲームで外装を確かめる（ユーザーに本数の了解を取ってから）

- `run.sh yabitsu s1_up drive 120` を 1 本。撮影（追従・横・運転席）を全部見て、穴・ちらつき・裏向きで消える面・車輪の位置ずれが無いか確かめる。AC・CSP のログにこの車のエラーが無いこと。
- 結果を `docs/progress/m2_report.md` に書く。

## M3 内装の組み込み（2026-11-26 追記。astra の内装 design/interior/kanachu_interior.blend はユーザー OK）

### Task 11: 外装と内装を 1 つの主 kn5 にまとめ、運転席・計器を AC につなぐ

**前提:** 内装は親 `COCKPIT_HR`（原点 0,0,0）の下にあり、`STEER_HR`（原点＝ハンドルの回転中心、ローカル Z＝回転軸）、`ARROW_SPEED`・`ARROW_RPM`（原点＝針の回転中心、ローカル Z＝回転軸、0 の位置で作成。0 と最大（160 km/h・4,000 rpm）の角度は design/interior/report.md）、`DRIVER_EYE`（0.642, 3.407, 1.985）がある。マテリアルは `interior_*`。三角形 約 12 万。

**Files:**
- Modify: `tools/prepare_blend.py` — 外装と内装を 1 つの一時 .blend にまとめる（内装は append）。外装の `INTERIOR_PLACEHOLDER` を除く。Task 8 の仮の `STEER_HR`・`COCKPIT_HR` は内装の本物に置き換える。`interior_*` マテリアルを書き出しの対象に加える（シェーダは ksPerPixel、パックされた画像は DDS に書き出し。テクスチャの無いものは単色の DDS）。
- Modify: `tools/materials.json` または prepare_blend 側で `interior_*` を自動定義。
- Modify: `tools/physics.py` — car.ini の `DRIVEREYES` と dash_cam.ini を `DRIVER_EYE` から（kn5 座標へ変換、さらに GRAPHICS_OFFSET を考慮して物理座標へ）。`analog_instruments.ini` を作る: [ARROW_SPEED]（NAME=ARROW_SPEED、MIN/MAX と角度は内装の報告の 0・最大角）・[ARROW_RPM]。STEER_HR の回転は AC 標準（ノード名で回る）。
- Modify: `tools/check_design.py` — 内装の必須名（COCKPIT_HR、STEER_HR、ARROW_SPEED、ARROW_RPM、DRIVER_EYE）と `interior_*` の検査を足す。
- Test: まとめた主 kn5 に COCKPIT_HR の下の STEER_HR・ARROW_* があり INTERIOR_PLACEHOLDER が無いこと、1 メッシュ ≤ 65,535 頂点、三角形 ≤ 30 万、DRIVEREYES が DRIVER_EYE の変換と一致、analog_instruments.ini の値。

## M4 スキン・UI・灯火（2026-11-26 追記。絵は design/livery・design/ui に確定済み）

### Task 12: スキン 2 種と UI の絵を組み込み、灯火を点くようにする

**Files:**
- Modify: `tools/skins.py`（ZC32S 由来の名前だけ残っていれば作り直し）または新規 — `skins/0_new2023/`（既定）と `skins/1_standard/` を作る。各スキン: `paint.dds`（design/livery/paint_new2023.png・paint_standard.png から 4096×2048、ミップ付き。主 kn5 の `paint` マテリアルのテクスチャ名と同名にして差し替える）、`livery.png`（design/ui/livery_new2023.png・livery_standard.png）、`ui_skin.json`（skinname「新塗装（2023〜）」「旧塗装（標準色）」、drivername なし、country Japan、team「神奈川中央交通」、priority 0/1）、`preview.jpg`（1022×575。Blender で外装をその塗装でレンダー、斜め前 3/4 の構図）。M1 の `0_test` は消す。
- Modify: `tools/ui.py` — `ui/badge.png`＝design/ui/badge.png、車フォルダの `logo.png`＝design/ui/logo.png（validate の WARN 対象から logo.png が消える）。ui_car.json の説明文（日英）を設計書 §7 の内容で書き直す（基準車種・諸元の出典・音の出典 Pixabay・個人利用）。
- Modify: `tools/physics.py` — `lights.ini` を書く: [HEADER] VERSION=3、[LIGHT_0..] ヘッドライト（LIGHT_HEAD_L/R）、[BRAKE_0..] ブレーキ灯（LIGHT_BRAKE_L/R）、テール（LIGHT_TAIL_L/R はヘッドライトと連動）、ウインカー・バック灯は CSP 側。書式は HT81S の lights.ini に合わせる。
- Create: `extension/ext_config.ini` を assemble で置く — CSP の灯火: ウインカー（LIGHT_IND_*、左右と非常点滅）、バック灯（LIGHT_REVERSE_*）、行先表示の発光（DEST_FRONT/SIDE/REAR を常時点灯、夜に明るく）、ヘッドライトの光源（[LIGHT_HEADLIGHT_0..] 位置は LIGHT_HEAD_* の中心から）。書式は HT81S の extension/ext_config.ini と CSP の公式の書式に合わせる。
- Test: スキン 2 つのファイル一式と paint.dds の大きさ・ミップ、ui_skin.json の値、lights.ini の節とノード名が kn5 に存在すること、ext_config.ini の参照ノード名が kn5 に存在すること。

## 音の bank（2026-11-26 追記。ユーザーがゲーム PC に FMOD Studio 1.08.12 を入れた。AC の FMOD 部品も 1.8.12）

### Task S1: Pixabay の素材から kanachu_route_bus.bank を作る

**前提:** 素材は `design/sound/engine/*.wav`（車外・車内 × load・coast × 600/900/1300/1800/2400 rpm、表は `design/sound/samples.md`）と `design/sound/effects/`（扉の開・閉、エアブレーキ）。ひな形はゲーム PC の `<AC>\sdk\audio\ac_fmod_sdk_1_9`（FMOD 1.08 のプロジェクト。手本の車 Abarth の event がある）と手順書 `refs/audio_sdk/pipeline.pdf`。FMOD はゲーム PC の `C:\Program Files\FMOD SoundSystem\FMOD Studio 1.08.12\`（`fmodstudiocl.exe` あり）。

**Files:**
- Create: `audio/fmod_project/`（SDK のひな形の写しに、kanachu_route_bus の event を足したもの。git に入れる。Abarth などの元の音声は消すか、bank に入れない）
- Create: `tools/fmod_build.py` — (1) ひな形の Metadata（XML）から手本の車の event（engine_ext・engine_int ほか手順書が必須とする event）を写し、車名・音声ファイル・各サンプルの自然な回転数（autopitch の基準）・rpms の範囲（手順書の推奨どおり実回転の 2 倍まで、上限 5,200）・throttle の音量曲線を入れる。horn など素材の無い event は手本の音のままにせず、無音か扉・エアブレーキの音を当てて、手順書が必須とする event をそろえる。(2) プロジェクトをゲーム PC の作業フォルダ `C:\Users\<ユーザー>\Documents\kanachu-validation\fmod\` に送り、`fmodstudiocl.exe -build` で bank を作る。(3) `kanachu_route_bus.bank` と `GUIDs.txt` を Mac の `audio/build/` に取り戻す。
- Modify: `tools/sfx.py` — 音の出どころに `kind=own`（`audio/build/` の bank と GUIDs.txt をそのまま使う）を足し、既定にする。jetset の借用は `--source tky_bus_jetset` で残す。
- Test: `tests/test_fmod_build.py`（生成した XML の event 名・パラメータ名・サンプル数と自然回転数、GUIDs.txt に `event:/cars/kanachu_route_bus/engine_ext` などの必須 event があり、他の車名が混ざらない）

**決まり:** ゲーム PC では作業フォルダの中だけに書く（AC 本体・SDK のひな形は読むだけ）。AC は起動しない（ゲームでの確認は controller がユーザーの了解を取って行う）。

## M2〜M5 の枠（各マイルストーンに入るときに、このファイルへ詳しい手順を書き足す）

- **M2 外装**: 上の Task 8〜10。
- **M3 内装**: `02_interior.md` → 検査 → 運転席の目の位置（DRIVEREYES・dash_cam）・計器（analog_instruments.ini の ARROW_SPEED／ARROW_RPM）・`STEER_HR` → 人形の合わせ込みを試す → ゲーム PC の運転席視点の撮影。
- **M4 塗装・UI・灯火**: `03_livery.md`（UV 配置図の上に旧・新の 2 枚）・`04_ui.md` → スキン 2 つ・preview（Blender）→ CSP の ext_config（灯火・行先表示の発光）・lights.ini → ゲーム PC で昼夜とスキン切り替えの撮影 → 比較画像をユーザーに見せて進む。
- **M5 最終照合**: 設計書 §8 を全部やり直し、§9 の表を実測で更新、zip を作る。
