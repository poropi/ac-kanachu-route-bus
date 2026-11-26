# いすゞ エルガ（LV290 系 N尺）と神奈中塗装の調査（2026-11-25）

一次資料（いすゞ公式 主要諸元表、2WG-LV290N5 世代。本フォルダに保存済み）:
- A = `erga_syogen_diesel.pdf`（https://www.isuzu.co.jp/product/bus/erga_rt/common/pdf/diesel/syogen_diesel.pdf）
- B = `erga_pv_syogen.pdf`（https://www.isuzu.co.jp/product/bus/erga_rt/common/pdf/pv_spec/erga_pv_syogen.pdf）

A・B の値は 2026-11-25 に pdftotext で表の行を読み、照合した。PDF はいすゞ自動車の著作物なので、このリポジトリには入れていない（上の URL から取得できる）。

## 1. 諸元

| 項目 | 値 | 出典 | 確度 |
|---|---|---|---|
| 全長 | 10,430 mm（N尺） | A「車両全長」 | 一次 |
| 全幅 | 2,485 mm | A「車両全幅」 | 一次 |
| 全高 | 3,105 mm | A「車両全高」 | 一次（N5。N3/N4 の値は未確認） |
| ホイールベース | 5,300 mm | A | 一次 |
| トレッド 前／後 | 2,065 / 1,820 mm | A | 一次 |
| 最低地上高 | 130 mm | A | 一次 |
| アプローチ／デパーチャアングル | 9.6° / 8.4° | A | 一次 |
| 客室内側寸法 長さ／幅／高さ | 9,495 / 2,310 / 2,405 mm | A | 一次 |
| 車両重量 | 9,790 kg（A 左列、79 人仕様） | A | 一次（N5） |
| 車両総重量 | 14,135 kg | A | 一次（N5） |
| 乗車定員 | 79 人（座席 27＋立席 51＋乗務員 1） | A | 一次 |
| エンジン | 4HK1-TCH 直 4 ターボ・インタークーラー、5,193 cc | A | 一次 |
| 最高出力 | 169 kW（230 PS）/ 2,150 rpm（ネット） | A | 一次（N5）。N3 世代は 177 kW（240 PS）表記あり（https://www.isuzu-global.com/ja/newsroom/20200611_01.html） |
| 最大トルク | 773 N·m / 1,600 rpm（ネット） | A | 一次 |
| 変速機 | 6 速 AT。1〜6 速 3.486 / 1.864 / 1.409 / 1.000 / 0.749 / 0.652、後退 5.027 | A | 一次 |
| 最終減速比 | 6.500 | A | 一次 |
| タイヤ | 275/70R22.5 148/145J（前後共）。148/145 は単輪/複輪の荷重指数 → **後輪は複輪（ダブル）** | A | 一次（サイズ）。複輪の判断は荷重指数の表記と後トレッドが狭いことから |
| タイヤ外径 | 計算 571.5 + 2×192.5 = 956.5 mm（半径 0.478 m） | 計算 | 計算値（実測なし） |
| サスペンション | 前後とも車軸式エアサス。前車軸 逆エリオット、後車軸 全浮動 | A | 一次 |
| 最小回転半径 | 8.3 m | A | 一次 |
| 扉 | 前折戸＋中引戸 | A「扉仕様」 | 一次 |
| 前／後オーバーハング | 2,300 / 2,830 mm（2,300＋5,300＋2,830＝10,430） | いすゞ 旋回軌跡図 LV290N5（`erga_n5_kiseki.pdf`、https://www.isuzu.co.jp/support/data/pdf/bus/01kiseki.pdf） | 一次（2026-11-26 astra が見つけ、pdftotext で照合） |
| 扉幅、窓の枚数、床面高、軸重 | 見つからず | — | 実車写真から比率で出す |

## 2. 神奈中の車種

- 2005 年時点で 9 割以上が三菱車（https://ja.wikipedia.org/wiki/神奈川中央交通、二次）。
- 2015 年頃から新車はノンステップ短尺に統一。近年の新車はエルガが中心（同上、https://rootbus.yu-nagi.com/kc-no11/kc-isuzu2.htm、二次）。
- 2DG-LV290N3 #43 の写真が rootbus にある（旧塗装）。メーカー別の台数統計は見つからず。

## 3. 塗装

### 旧塗装（標準色、1949 年〜）
- 黄色に近いクリーム地、下部に赤、窓下に赤と橙の帯（Wikipedia、https://bestcarweb.jp/?p=1425399、二次）。
- 下部の赤は 1987 年に波形から直線へ。2012 年 6 月から前・側・後に青い「Kanachu」ブランドマーク（Wikipedia）。
- 帯の寸法・色コードは公式資料なし → 写真から拾う。

### 新塗装（2023 年度下期〜、奥山清行氏デザイン）
- 2023-10-27 リリース。テーマ「調和（Harmony）」。赤・橙・黄の 3 本の縦ライン＋グラデーション、ベースカラーの色味を変更（https://www.bcnretail.com/market/detail/20231101_374208.html、https://tabi-mag.jp/kanaghu-colordesign/、二次）。
- 縦ラインの位置・幅・グラデーション方向の文章資料なし → 写真から決める。

### 参照写真（参照のみ。成果物に貼らない）
- 旧: https://tabi-mag.jp/wp-content/uploads/kanaghu-colordesign03.jpg 、https://busmagazine.bestcarweb.jp/images/205951/5 、https://upload.wikimedia.org/wikipedia/commons/f/fa/P-LV314L_Kanachu_Ma18_Machi28.jpg 、http://rootbus.yu-nagi.com/kc-no11/2019103001-fu43.jpg
- 新: https://bcnretail.kuroco.app/v=1698786007/files/user/202310311010_1.jpg 、https://bcnretail.kuroco.app/v=1698786007/files/user/202310311010_2.jpg 、https://busmagazine.bestcarweb.jp/images/183233/1 、https://busmagazine.bestcarweb.jp/images/183233/2 、https://busmagazine.bestcarweb.jp/images/205951/6 、https://busmagazine.bestcarweb.jp/images/205951/7 、https://tabi-mag.jp/wp-content/uploads/kanaghu-colordesign02.jpg

## 4. AC 上の既存バス MOD（ゲーム PC、参考に読んだだけ）

- `tky_bus_jetset`: WHEELBASE 6.487、後輪 WIDTH 0.65（複輪を 1 本の広いタイヤで表現）、RADIUS 0.57。TOTALMASS 3,835・LIMITER 8,000 など物理は乗用車寄りで、バスの参考にはならない。data.acd ではなく data/ フォルダのまま読み込まれている。
