# 依頼 06b: 神奈中バスの運転士の 3D モデル（Assetto Corsa の運転手）

あなたは 3D のキャラクターモデラーです。依頼 06 の三面図（`design/driver/turnaround/front.png`・`side.png`・`back.png`）の運転士を、Assetto Corsa（AC）の運転席に座らせる運転手として、Blender で作ってください。運転席の視点からは腕・手・脚、車外からは窓越しの上半身が見えます。AC 標準の運転手と同じくらい軽いモデルにします。

## 作業場所と書き込みの範囲

- 作業フォルダ: このリポジトリの最上位（`ac_kanachu_bus/`）
- **書き込んでよいのは `design/driver/` の下だけ**（`turnaround/` は読むだけ）。git の操作はしない。
- Blender は `/opt/homebrew/bin/blender`（5.2）。モデルは `design/driver/scripts/build_driver.py` で作る（実行すると `design/driver/kanachu_driver.blend` とレンダーができる作り）。
- 元絵 `refs/driver/illustration.png` は見るだけ（貼らない）。三面図を正とする。

## 決まり（必ず守る。`tools/check_driver.py` で検査する）

`blender -b --python tools/check_driver.py -- --blend design/driver/kanachu_driver.blend --json /tmp/check_driver.json` の結果が `[]`（問題 0 件）になるまで直す。中身:

- **骨組み**: アーマチュアのオブジェクト名は `DRIVER:DRIVER`。骨の名前と親子は `tools/driver_skeleton.py` の `BONES` と完全に一致（多くても少なくても不可）。骨の位置は、このモデルの体の関節（肩・肘・手首・指の関節・股・膝・かかと・足先・首・頭）に合わせる。
- **骨で動くメッシュ**（`tools/driver_skeleton.py` の `SKINNED_MESHES`）:
  - `DRIVER:BODY`: 制服の上着・シャツの見える部分・ネクタイ・ズボン・靴・首。
  - `DRIVER:GLOVES`: 白い手袋（手）。指は親指・人差し指・中指・薬指・小指を骨で曲げられる形に。
  - どちらも Armature モディファイア（`DRIVER:DRIVER`）と、骨の名前の頂点グループで重みを付ける。**全頂点に重み**（重み 0 の頂点を作らない）、1 頂点の重みは 4 本まで。座って腕を曲げたときに肘・肩・膝・股がつぶれすぎない重みに。
- **頭まわりのメッシュ**（`HEAD_MESHES`）: `DRIVER:GEO_Driver_FACE`（顔と首の上の肌）、`DRIVER:HAIR`（髪・サイドポニーテール・薄紫のリボン）、`DRIVER:CAP`（制帽と徽章）。3 つとも骨 `DRIVER:RIG_Head` に**骨で親子付け**（Parent: Bone）。重みは付けない。運転席の視点ではこの 3 つを隠すので、別のオブジェクトにする。
- 全メッシュに UV。1 メッシュ 60,000 頂点以下。目安は `BODY`＋`GLOVES` で 3,000〜8,000 頂点、頭まわり合計 2,000〜6,000 頂点。
- マテリアル名は `driver_` で始める（例 `driver_uniform`、`driver_skin`、`driver_face`、`driver_hair`、`driver_gloves`、`driver_cap`）。**色はベースカラーのテクスチャで持つ**（AC は ksPerPixel で描くので、セル調のノードや Shader to RGB に頼らない）。テクスチャは .blend にパックする。
- **顔の目・眉・口はテクスチャで描く**（目を開けた笑顔。三面図の正面の顔）。
- 「Kanachu」の文字は制帽の徽章と胸の刺繍だけ（テクスチャ）。名札は白い無地。ほかに文字・ロゴを入れない。
- 向きと原点: 立ち姿の A ポーズ（三面図と同じ）、**原点は両足の間の床**、**+Y が前（顔の向き）、+X が本人の右（−X が本人の左）**、+Z が上。身長（帽子を除く頭頂）1.55〜1.70 m。（2026-11-26 訂正: 初版は「+X が本人の左」と誤記していた）

## 確かめ方と届ける物（すべて `design/driver/` の下）

1. `kanachu_driver.blend`（テクスチャはパック）と `scripts/build_driver.py`
2. レンダー: `renders/front.png`・`side.png`・`back.png`（三面図と同じ向き・同じ縮尺。テクスチャの色がそのまま見える明るい平らな光で）、`renders/seated_hands.png`（腕を前に出して、ハンドルを握るように手を曲げた姿勢を、目の高さから見下ろした図。骨を回して作る。ゲームでの見え方の確認用）
3. `renders/compare.png`: 三面図とレンダーを左右に並べた比較（正面・横・後ろ）
4. `report.md`: 頂点数（メッシュごと）、骨の位置の決め方、重みの付け方、`check_driver.py` の結果、三面図との違いと理由、描けなかった物
