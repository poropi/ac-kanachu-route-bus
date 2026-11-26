# 依頼 06c: 運転士モデルの左右を正しい向きに直す

依頼 06b の運転士モデル（`design/driver/kanachu_driver.blend`、`design/driver/scripts/`）の続きです。

## 何が違っていたか

依頼 06b の「+Y が前（顔の向き）、+X が本人の左」は**こちらの誤記**でした。Blender の座標で +Y を向いた人は、右手が +X 側に来ます。正しくは **+X が本人の右、−X が本人の左** です（依頼 06b も訂正済み）。

今のモデルは誤記に合わせたため、左右が鏡写しになっています。
- サイドポニーテールと `_L` の骨（`DRIVER:RIG_Arm_L` など）が +X（＝本人の右）にある。
- 胸と帽子の「Kanachu」の文字が、モデルの上では裏返し。
- レンダーは合成の Flip X で左右反転して、三面図と見た目を合わせている。

## 直すこと

1. **モデルを左右反転して正しい向きにする。** 顔とつま先は +Y のまま。サイドポニーテール・リボン・胸の刺繍と名札・`_L` の骨（腕・手・指 `HAND_L_Thumb*`・`HAND_Index1-3` など・脚）は **−X（本人の左）**、`_R` は +X。骨の名前は付け替えない（反転すれば名前と側が合う）。重み、法線の向き（裏返らないこと）、UV を保つ。「Kanachu」の文字は、正面から見て正しく読める向きにする。作り方は `scripts/build_driver.py` を直して、実行し直せば正しい向きの .blend ができるようにする（後から鏡写しを当てるだけの直しにしない）。
2. **レンダーの左右反転（Flip X）をやめる。** 正面のカメラは +Y の側から −Y を見る。このとき本人の左（−X）は画面の右に写る（三面図の正面と同じ）。
3. 着座の姿勢（フレーム 2）も、反転後の向きで直す。

## 確かめ方

- `blender -b --python tools/check_driver.py -- --blend design/driver/kanachu_driver.blend --json /tmp/check_driver.json` が `[]`。
- 骨の位置: `DRIVER:RIG_Arm_L`・`DRIVER:RIG_HAND_L`・`DRIVER:RIG_Leg_L` の x が負、`_R` の x が正。ポニーテールの頂点の重心の x が負。顔の前面とつま先が +Y。数値を `report.md` に書く。
- レンダー（反転なし）の正面で、ポニーテールが画面の右、胸の「Kanachu」が正しく読める。比較画像を作り直す。

## 作業場所と書き込みの範囲

- 書き込んでよいのは `design/driver/` の下だけ（`turnaround/` は読むだけ、`cockpit.json` は触らない）。git の操作はしない。Blender は `/opt/homebrew/bin/blender`。
