# オリジナルの運転士 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 借り物の運転手（tky_bus_jetset の 3 ファイル）を、神奈中の運転士の姿をしたオリジナルの運転手（`content/driver/kanachu_driver.kn5`）と自作の `driver3d.ini`・`driver_base_pos.knh`・`steer.ksanim` に置き換え、MIT で公開できる配布物にする。

**Architecture:** 見た目は astra（Codex `gpt-6.2-astra`）が Blender で作る（三面図 → 低ポリゴン＋AC 標準の運転手と同じ名前の骨組み＋重み）。こちらは、骨で動くメッシュの kn5 書き出し、運転席の寸法から座った姿勢を解く knh、ハンドルの角度ごとの腕を解く ksanim、配布の組み立て、検査、ゲームでの確認を作る。こちらの道具は、astra のモデルを待たずに、AC の骨組みだけ持つ試験用の .blend で先に作って試す。

**Tech Stack:** Python 3.12（numpy、Pillow、pytest）、Blender 5.2（`blender -b`、サンドボックスなし）、既存の `tools/kn5io.py`（種類 3 の読み書きは 1887951 で対応済み）、`tools/textures.py`（DDS）。

**Spec:** `docs/superpowers/specs/2026-11-26-kanachu-driver-design.md`（親: `2026-11-25-kanachu-bus-design.md`）

## Global Constraints

- 骨の名前と親子は AC 標準の運転手と同じ（`tools/driver_skeleton.py` の `BONES` が唯一の定義。中身は `refs/kunos_driver/driver.kn5` の種類 1 のノード 57 個から名前と親だけを写す。行列・形・動きは写さない）。
- 運転手の kn5 は `content/driver/kanachu_driver.kn5`。配布 zip は `content/cars/kanachu_route_bus/…` と `content/driver/kanachu_driver.kn5` の形。
- `driver3d.ini`: `[MODEL] NAME=kanachu_driver`、`POSITION=0,0,0`、`[STEER_ANIMATION] NAME=steer.ksanim`、`[SHIFT_ANIMATION]` は残す、`[HIDE_OBJECT_0..2]` = `DRIVER:GEO_Driver_FACE`・`DRIVER:HAIR`・`DRIVER:CAP`。**（2026-11-26 追加）** `[HIDE_OBJECT_3]` = `DRIVER:BODY_SUB3`（首の肌）。**（2026-11-26 改訂、ユーザー判断）** `[HIDE_OBJECT_3]` = `DRIVER:NECK`（首の肌を頭の骨の固定メッシュにしたもの。骨で動くメッシュは隠れなかった）。`[HEAD_MOVEMENT]` は FILTER=0.15・MAX_G=0.3・ROLL_MAX_DEG=0・PITCH_MAX_DEG=0・YAW_MAX_DEG=5（首を傾けない。ユーザー判断）。
- 席の位置は `driver_base_pos.knh` の `DRIVER:RIG_Center` の行列で表す。**（2026-11-26 改訂）** 体はモデルの大きさのまま（拡大しない）、腰は座面、上体の前傾 ≤ 20°、肘の曲げ ≥ 15°、手はリムの真上から 60°〜100° で届くいちばん上、頭は `DRIVER_EYE` より下（目を合わせる条件は取りやめ）。
- 手のひらの中心と目標の距離 ≤ 0.02 m（ハンドルの回転角 0°、+90°、−90°）。**（2026-11-26 改訂: 手のひらはリムの管の上、指を曲げて握る）** 目標は管の中心線から、外向きを運転手の側（上）へ倒した向きへ（管の半径 0.016 + 手のひらの厚みの半分）ずらした点。
- 1 メッシュ 60,000 頂点以下。骨で動く頂点の重みは 4 本まで、合計 1。
- Kunos・他の MOD のファイルを配布物とリポジトリに入れない。`refs/`（イラスト・Kunos の運転手）は git 管理外。
- 「Kanachu」は帽子の徽章と胸の刺繍だけ（描き直した字）。名札は無地。表情は目を開けた笑顔。
- kn5 の座標は Blender (bx, by, bz) → kn5 (−bx, bz, by)（`blend_to_kn5.to_kn5` と同じ）。
- ゲームの試走はユーザーの承認した本数まで。`.ps1` は ASCII だけ。

## Review Focus

1. **ハンドルを ±90° より大きく回したとき**、腕の関節が急に裏返ったり（IK の解の飛び）、腕が胴やダッシュに刺さったりしない。→ Task 6 にコマ間の関節角の変化量の上限テスト。
2. **左右の手の取り違え**（右手の指は `HAND_R_Thumb1-3`・`HAND_Index4-6`…、左は `HAND_L_Thumb1-3`・`HAND_Index1-3`…）。→ Task 1 に、`BONES` の手の指が正しい側の `RIG_HAND_*` の子であるテスト。
3. **重みが 4 本を超える・合計が 1 でない・重みの無い頂点**があっても、書き出しが黙って壊れた kn5 を作らない。→ Task 4 に、5 本の重みの頂点は上位 4 本に切って正規化、重み 0 の頂点はエラーにするテスト。
4. **astra のモデルに骨が欠けている・名前が違う**ときは、組み立ての前に止まる。→ Task 1 の `check_driver.py` と Task 7 の validate にテスト。
5. **配布 zip の中の場所の間違い**（運転手の kn5 が車のフォルダに入る、`content/` が抜ける）。→ Task 7 に zip の中のパス一覧のテスト。

---

### Task 1: 骨組みの定義と、モデルの規約検査

**Files:**
- Create: `tools/driver_skeleton.py`、`tools/check_driver.py`（Blender の中で動く）、`tests/fixtures/make_mini_driver.py`、`tests/test_driver_skeleton.py`、`tests/test_check_driver.py`

**Interfaces:**
- Produces: `driver_skeleton.BONES: list[tuple[str, str | None]]`（名前, 親。`DRIVER:DRIVER` が根で親 None、順は親が先）、`driver_skeleton.HEAD_MESHES = ("DRIVER:GEO_Driver_FACE", "DRIVER:HAIR", "DRIVER:CAP")`、`driver_skeleton.SKINNED_MESHES = ("DRIVER:BODY", "DRIVER:GLOVES")`。
- Produces: `check_driver.check(blend_path=None) -> list[str]`（問題のリスト、空なら合格）と CLI `blender -b --python tools/check_driver.py -- --blend X.blend --json out.json`（`check_design.py` と同じ形）。規約: アーマチュアのオブジェクト名 `DRIVER:DRIVER`、骨名が `BONES` と一致（多い・少ないとも問題）、`SKINNED_MESHES` は Armature モディファイアと頂点グループ（骨名）を持ち、全頂点に重みがある、`HEAD_MESHES` は `DRIVER:RIG_Head` に骨で親子付け（bone parent）、全メッシュに UV、1 メッシュ 60,000 頂点以下、マテリアル名は `driver_` で始まる、テクスチャはパック済み、立ち姿の身長（頭頂の z）1.55〜1.70 m。
- Produces: `tests/fixtures/make_mini_driver.py <out.blend>` — `BONES` の全骨を A ポーズで置き、箱のメッシュを `SKINNED_MESHES` と `HEAD_MESHES` の名前で付けた、規約を満たす最小の .blend（Task 4〜6 の試験用）。

- [ ] **Step 1: テストを書く** — `test_bones_match_kunos_names_only`（`refs/kunos_driver/driver.kn5` があれば、その種類 1 のノード名と親の集合が `BONES` と一致。無ければ skip）、`test_finger_bones_on_correct_side`（`HAND_R_Thumb1`・`HAND_Index4`・`HAND_Middle4`・`HAND_Ring4`・`HAND_Pinkie4` の祖先に `DRIVER:RIG_HAND_R`、`HAND_L_Thumb1`・`HAND_Index1` などの祖先に `DRIVER:RIG_HAND_L`）、`test_mini_driver_passes`（fixture を作って `check()` が `[]`）、`test_missing_bone_and_unweighted_vertex_fail`（fixture から骨 1 本を消す／頂点 1 つの重みを消すと、それぞれ問題が 1 件以上）。Blender が要るテストは無ければ skip。
- [ ] **Step 2: 失敗を確かめる** — `python3 -m pytest -q tests/test_driver_skeleton.py tests/test_check_driver.py` が import エラーで落ちる。
- [ ] **Step 3: 実装する**（`BONES` は kn5 から自動で作らず、名前と親を文字で書く。kn5 は照合に使うだけ）。
- [ ] **Step 4: 通ることを確かめる** — 同じコマンドが PASS。
- [ ] **Step 5: コミット**

### Task 2: astra への依頼と三面図（D1）

**Files:**
- Create: `design/requests/06_driver.md`（依頼文。既存の `design/requests/01_exterior.md`〜`05` と同じ書き方）
- astra の成果物: `design/driver/turnaround/{front,side,back}.png`、`design/driver/turnaround/report.md`

**Interfaces:**
- Consumes: 設計書 §2・§9 の見た目、`refs/driver/illustration.png`（参照のみ）。
- Produces: 三面図 3 枚（目を開けた笑顔、立ち姿、腕を体から少し離す A ポーズ、同じ身長・同じ足元の高さ、無地の背景）。

- [ ] **Step 1: 依頼文を書く** — 書き込んでよいのは `design/driver/` の下だけ、git 操作をしない、イラストは参照だけ（貼らない）、見た目の表（設計書 §2）、表情、A ポーズ、「Kanachu」は徽章と胸だけ・名札は無地、届ける物。
- [ ] **Step 2: 依頼する** — `codex exec -m gpt-6.2-astra` で依頼文を渡す（Blender は使わない段階）。
- [ ] **Step 3: 確かめる** — 3 枚の身長と足元が揃っている（足元の y の差 ≤ 2 %、頭頂の差 ≤ 2 %）、元絵の要素（帽子の徽章・青い縁取り・ネクタイ・サイドポニーテール・リボン・白手袋・ズボン・ローファー）が全部ある。足りなければ直してもらう（最大 2 回）。
- [ ] **Step 4: ユーザーに見せる**（元絵と三面図を並べた 1 枚）。返事を待たずに Task 3 へ進む（見せて進む）。直しの指示が来たら Task 3 より優先する。
- [ ] **Step 5: コミット**（三面図と依頼文。`refs/` は入れない）

### Task 3: astra の 3D モデル（D2）

**Files:**
- 依頼文: `design/requests/06b_driver_model.md`
- astra の成果物: `design/driver/kanachu_driver.blend`（テクスチャはパック）、`design/driver/scripts/build_driver.py`（実行すると .blend とレンダーができる）、`design/driver/renders/{front,side,back,cockpit_hands}.png`、`design/driver/report.md`

**Interfaces:**
- Consumes: Task 1 の規約（`check_driver.py` を astra に渡し、`[]` になるまで直してもらう）、Task 2 の三面図。
- Produces: 規約を満たす .blend。立ち姿の A ポーズで原点は足元の中心、+Y が前、+X が本人の左（車の .blend と同じ向き）。顔の目・眉・口と「Kanachu」の文字はテクスチャ。

- [ ] **Step 1: 依頼文を書く** — 規約（Task 1 の Interfaces を全文）、頂点数の目安（体＋手袋で 3,000〜8,000、頭まわり 2,000〜6,000）、AC の ksPerPixel で見えるように色はテクスチャのベースカラーで持たせる（セル調のノードに頼らない）、レンダー 4 枚、元絵と三面図に並べた比較画像。
- [ ] **Step 2: 依頼する**（サンドボックスなし）。
- [ ] **Step 3: 確かめる** — `blender -b --python tools/check_driver.py -- --blend design/driver/kanachu_driver.blend --json /tmp/x.json` が `[]`。比較画像を開いて、見た目の要素がそろっているかを 1 つずつ見る。足りなければ直してもらう（最大 2 回。それでも届かなければユーザーに選択肢を出す）。
- [ ] **Step 4: ユーザーに見せる**（比較画像）。見せて進む。
- [ ] **Step 5: コミット**

### Task 4: 骨で動くメッシュの kn5 書き出し（D3）

**Files:**
- Create: `tools/driver_to_kn5.py`（Blender の中で動く）、`tests/test_driver_export.py`
- Modify: なし（`blend_to_kn5.py` は車用のまま）

**Interfaces:**
- Consumes: `driver_skeleton.BONES`・`SKINNED_MESHES`・`HEAD_MESHES`、`kn5io`（`Node` の種類 1／2／3）、`textures.dds_from_rgba`。
- Produces: CLI `blender -b X.blend --python tools/driver_to_kn5.py -- --out build/driver/kanachu_driver.kn5`。kn5 の構成: 根 `DRIVER:DRIVER`（種類 1）の下に骨の階層（種類 1、行列は親からの相対、kn5 座標）、`HEAD_MESHES` は `DRIVER:RIG_Head` の子の種類 2、`SKINNED_MESHES` は根の直下の種類 1 `<名前>` の子の種類 3 `<名前>`（Kunos の `DRIVER:suit` と同じ形）。種類 3 の `bones` は（骨名, 逆バインド行列 4×4 を kn5 の並びで 64 バイト）、頂点は 76 バイト（位置・法線・UV・接線・重み 4・骨番号 4 を float で）。マテリアルは ksPerPixel、`txDiffuse` にパック画像を DDS にしたもの。

- [ ] **Step 1: テストを書く**（fixture を Task 1 の `make_mini_driver.py` で作り、書き出して `kn5io.read` で読む）— `test_bone_hierarchy_matches_skeleton`（種類 1 のノード名と親が `BONES` と一致）、`test_skinned_weights_valid`（全頂点で重みの合計 1±1e-4、骨番号が `bones` の範囲内）、`test_bind_pose_identity`（各骨の世界行列 × 逆バインド行列 ≈ 単位行列、誤差 1e-4）、`test_head_meshes_under_head_bone`、`test_more_than_four_influences_truncated`（5 本の重みの頂点を作ると上位 4 本で正規化される）、`test_unweighted_vertex_is_error`（SystemExit）、`test_roundtrip_bytes`（書いた kn5 を読んで書き直すとバイト一致）。
- [ ] **Step 2: 失敗を確かめる**
- [ ] **Step 3: 実装する**
- [ ] **Step 4: 通ることを確かめる** — `python3 -m pytest -q tests/test_driver_export.py`
- [ ] **Step 5: コミット**

### Task 5: 運転席の寸法と、座った姿勢（knh、D4）

**Files:**
- Create: `tools/knh.py`、`tools/cockpit_geometry.py`（Blender の中で動く）、`design/driver/cockpit.json`（測った値、git 管理）、`tools/driver_pose.py`、`tests/test_knh.py`、`tests/test_driver_pose.py`

**Interfaces:**
- Produces: `knh.read(path) -> KnhNode`、`knh.write(root: KnhNode, path)`、`KnhNode(name: str, matrix: tuple[16 float], children: list)`。形式: 名前（int 長さ＋utf8）、行列 16 float（kn5 と同じ並び、平行移動は 12〜14 番目）、子の数 int、子を順に。
- Produces: `cockpit_geometry.py -- --blend design/interior/kanachu_interior.blend --out design/driver/cockpit.json`。JSON の中身（すべて kn5 座標、m）: `eye`（`DRIVER_EYE`）、`wheel_center`・`wheel_axis`（`STEER_HR` の位置とローカル Z、運転手から遠ざかる向き）、`rim_radius`（`Steering_Rim` の管の中心線の半径）、`seat_point`（`Drivers_Seat` の座面の中央）、`backrest_angle_deg`、`pedal_accel`・`pedal_brake`（`Cab_Dash_and_Driving_Controls` の床の前寄りから推定。推定した根拠を `"notes"` に書く）。
- Produces: `driver_pose.solve_seated(rest: dict[str, np.ndarray], cockpit: dict, grip_deg: float = 60.0) -> dict[str, np.ndarray]`（骨名 → 親からの相対行列 4×4）と `driver_pose.to_knh(local: dict) -> KnhNode`。`rest` は Task 4 の kn5 の種類 1 のノードから作る（骨名 → 親からの相対行列）。手はリムの「10 時と 2 時」（`grip_deg=60` は真上から左右に 60°）を握る。腕・脚は 2 本の骨の解析的 IK、腰は座面、頭は目の位置。
- CLI: `python3 tools/driver_pose.py --kn5 build/driver/kanachu_driver.kn5 --cockpit design/driver/cockpit.json --out build/driver/driver_base_pos.knh`

- [ ] **Step 1: テストを書く** — `test_knh_roundtrip`（手で作った 3 段の木を書いて読むと一致、`refs` に借り物の knh があれば読めて骨 57 個）、`test_seated_eye_and_hands`（fixture の kn5 と `cockpit.json` で解くと、目と `eye` の距離 ≤ 0.03 m、左右の手のひらの中心とリムの管の中心線の距離 ≤ 0.02 m）、`test_seated_no_intersection_proxy`（腰の骨の位置が座面より上 0.05〜0.20 m、膝がハンドルの柱の包絡箱に入らない）。
- [ ] **Step 2: 失敗を確かめる**
- [ ] **Step 3: 実装する**（`cockpit.json` は一度測って git に入れる。テストは JSON を読むだけで Blender を要らないようにする）
- [ ] **Step 4: 通ることを確かめる**
- [ ] **Step 5: コミット**

### Task 6: ハンドルを回す腕の動き（ksanim、D5）

**Files:**
- Create: `tools/ksanim.py`、`tools/driver_steer.py`、`tests/test_ksanim.py`、`tests/test_driver_steer.py`

**Interfaces:**
- Produces: `ksanim.read(path) -> dict[str, list[Frame]]`、`ksanim.write(tracks: dict[str, list[Frame]], path)`、`Frame(rot: tuple[x, y, z, w], pos: tuple[3], scale: tuple[3])`。形式（版 2）: int 版=2、int 骨の数、骨ごとに 名前（int 長さ＋utf8）・int コマ数・コマごとに 10 float（四元数 x y z w、位置 3、大きさ 3）。
- Produces: `driver_steer.build_steer(seated: dict, rest: dict, cockpit: dict, lock_deg: float, frames: int = 101) -> dict[str, list[Frame]]`。コマ i のハンドルの回転角 = −lock + 2·lock·i/(frames−1)（2026-11-26 訂正: lock は片側の角度）（**仮定**。Task 8 のゲームで確かめ、違えば対応を直す）。|角度| ≤ 90° は両手がリムの同じ点を握ったまま回る（リム上の握り点をハンドルの軸まわりに回し、腕を IK で解く）。それより先は、手の握り点を ±90° の位置で止める（リムから手が離れる）。腕以外の骨は全コマで座った姿勢のまま。`lock_deg` は `driver3d.ini` の `LOCK` と同じ値で、既定 90（2026-11-26 訂正: LOCK は片側の角度。当初は 180 としていたが誤り）。
- CLI: `python3 tools/driver_steer.py --kn5 … --cockpit … --lock 180 --out build/driver/steer.ksanim`

- [ ] **Step 1: テストを書く** — `test_ksanim_roundtrip`（`refs` に借り物があれば読めて 55 本×101 コマ。自作の 2 本×3 コマを書いて読むと一致）、`test_hands_on_rim_within_90`（0°・+90°・−90° のコマで、手のひらの中心とリムの距離 ≤ 0.02 m）、`test_no_ik_flip`（隣のコマどうしで肘の角度の変化 ≤ 10°、肘の位置の移動 ≤ 0.05 m。全 101 コマで）、`test_other_bones_static`（腕・手・指以外の骨は全コマで座った姿勢と一致）。
- [ ] **Step 2: 失敗を確かめる**
- [ ] **Step 3: 実装する**
- [ ] **Step 4: 通ることを確かめる**
- [ ] **Step 5: コミット**

### Task 7: driver3d.ini、組み立て、検査、README（D6）

**Files:**
- Create: `tools/driver.py`（運転手の一式を作る入口）
- Modify: `tools/assemble.py`（借り物の `vendor/driver_jetset` を使うのをやめ、`tools/driver.py` の成果物を使う。zip を `content/` の形にする）、`tools/validate.py`、`tools/check_public.py`（借り物の運転手を禁止する規則を、「`vendor/` を参照していない」検査に替える）、`tools/ac/run.sh`・`tools/ac/launch.ps1`（運転手の kn5 も `content/driver/` に置く。置いたものは試走の後も残してよい）、`README.md`（導入は zip を `assettocorsa/` に展開する、または Content Manager に入れる）、`tests/test_assemble.py`

**Interfaces:**
- Consumes: Task 4〜6 の CLI。
- Produces: `driver.build(out_car: Path, out_driver_dir: Path) -> None` — `kanachu_driver.kn5` を `out_driver_dir` に、`data/driver3d.ini`・`driver_base_pos.knh`・`animations/steer.ksanim` を `out_car` に書く。`driver.driver3d_ini(lock_deg: float = 180) -> str`。
- Produces: zip の中: `content/cars/kanachu_route_bus/…`、`content/driver/kanachu_driver.kn5`。`build/` の手元のフォルダは `build/kanachu_route_bus/`（今まで通り）と `build/driver/kanachu_driver.kn5`。

- [ ] **Step 1: テストを書く** — `test_driver3d_ini_values`（Global Constraints の値どおり）、`test_zip_layout`（zip の名前一覧に `content/cars/kanachu_route_bus/data/driver3d.ini`・`content/driver/kanachu_driver.kn5` があり、`kanachu_route_bus/` で始まる名前が無い）、`test_no_vendor_reference`（`assemble.py` が `vendor/` を読まない。`vendor/` を一時的に無い状態にして組み立てが通る）、`test_validate_detects_missing_driver_bone`（運転手の kn5 から骨 1 本を消すと validate が問題を返す）。
- [ ] **Step 2: 失敗を確かめる**
- [ ] **Step 3: 実装する**
- [ ] **Step 4: 通ることを確かめる** — 全テスト、`python3 tools/assemble.py`、`python3 tools/validate.py`、`PUBLIC_FORBID=… python3 tools/check_public.py` が OK
- [ ] **Step 5: コミット**

### Task 8: ゲームでの確認（D7）

**Files:**
- Modify: `tools/ac/KanachuProbe/KanachuProbe.lua`（止まった状態で −90° に切る撮影を足す。運転席の視点と、車外から窓越しの運転手を狙う撮影）

- [ ] **Step 1: 試走の本数をユーザーに承認してもらう**（基本 1 本、直したら 1 本）。
- [ ] **Step 2: 走らせる** — `bash tools/ac/run.sh drift '' circle 60`。
- [ ] **Step 3: 判定する** — 落ちない、CSP のログにこの運転手のエラーが無い、0°・+90°・−90° で手がリムを握っている（`steer90` と新しい −90° の撮影、走行中のいっぱいの撮影）、車外から運転士が見える、運転席の視点に帽子・髪が入らない。ハンドルの角度とコマの対応（Task 6 の仮定）が合っているかを、+90° の撮影で手の位置から確かめる。
- [ ] **Step 4: 外れたら直して 1 本だけ走らせ直す**。
- [ ] **Step 5: ユーザーに結果を見せ、記録を更新する**（M5 報告・設計書 §9 の「運転手の人形」の行・README）。
