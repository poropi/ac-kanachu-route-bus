# 神奈中バス・エルガ N尺の内装

[内装モデル](kanachu_interior.blend) ／ [運転席からの眺め](renders/01_driver_eye.png) ／ [生成スクリプト](scripts/build_interior.py) ／ [保存ファイルの検査結果](verification.json)

外装「ふ43」に合わせた右ハンドルの運転台と、都市型N尺の客席27席を収録した。保存モデルは **121,334三角形**。閉扉・直進状態の外装と重ね、窓、扉、外板、タイヤ、床下部品との面の交差は0件だった。

## 外装への組み込み

外装の `INTERIOR_PLACEHOLDER` を非表示にし、内装の `COCKPIT_HR` とその子孫を原寸で配置する。空の親は世界原点、回転ゼロ、スケール1。座標はm単位で、右が＋X、前が＋Y、上が＋Z。外装、道路、撮影機材は内装ファイルの外にある。

| 用途 | オブジェクト | 世界座標 (X, Y, Z) m | 軸・寸法 |
|---|---|---|---|
| 運転手の目 | `DRIVER_EYE` | (+0.642, +3.407, 1.985) | 運転席座面中心より128 mm後ろ。レンダーの水平画角60° |
| ハンドル中心 | `STEER_HR` | (+0.642, +4.098, 1.392) | 外径496 mm。リム面は水平から24°、前縁が高い。ローカル＋Zは車両前下方 (0, +0.40674, −0.91355) |
| 左・回転計の針 | `ARROW_RPM` | (+0.512, +4.41279, 1.52262) | ローカル＋Zは運転手側 (0, −0.84805, +0.52992) |
| 右・速度計の針 | `ARROW_SPEED` | (+0.772, +4.41279, 1.52262) | 同上。左右とも、針の親原点は盤面から手前へ2.00 mm |

展示車の運転席写真では、横に広いホーンパッドから左右手前へスポークが伸び、その奥に黒い計器盤がある。輪の形、リムと計器ひさしの前後関係、右側窓の下端を手掛かりに上表の外径・高さ・傾きを決めた。これらはモデルの採用寸法。写真から実車のチルト調整位置や運転手の目の高さを絶対寸法として確定することはできない。座面中央の基準高は1.115 m。透明保護板は運転席の後ろと通路側に置いた。[運転席全景](https://commons.wikimedia.org/wiki/File:Isuzu_Motors_ERGA_Non_Step_LV290_AMT_Cockpit.jpg) ／ [チルト機構の取材記事](https://response.jp/article/2016/10/08/283228.html)

### 計器の角度

盤面を運転手側から正対して見て、12時が0°、時計回りが正。両方とも左下がゼロ。保存時の針はすでにゼロ位置にある。ゲーム側で動かすときは、親の初期取付姿勢に対して下表の**ローカルZ追加回転**を与える。

| 盤面 | ゼロの方向 | 最大目盛の方向 | ゼロから最大までのローカルZ追加回転 |
|---|---:|---:|---:|
| 速度計 0〜160 km/h | −103° | ＋105° | 0° → −208° |
| 回転計 0〜4,000 rpm | −103° | ＋68° | 0° → −171° |

保存ファイルを開き、両親をローカルZで実際に「初期 → 最大 → 初期」と回した。針先の中点を元の盤面に投影した実測角は、速度が −102.9998° → ＋104.9997° → −102.9998°、回転が −102.9998° → ＋67.9999° → −102.9998°だった。

盤面中心は左 (+0.512, +4.41448, 1.52156)、右 (+0.772, +4.41448, 1.52156) m。文字盤径138 mm、面の傾きは鉛直から32°。2本の針、ハンドルのリム・スポーク・パッドはそれぞれ指定の親の子メッシュにした。コラムとレバー、盤面と目盛りは固定している。左タコ・右速度、赤色帯、朱色の針、中央LCDはLV290展示車の写真に合わせた。現行ディーゼルの公式装備表には120 km/h計の記載がある。ここでは文字を読み取れた2015年展示車の160 km/h計を採用した。「ふ43」固有の計器仕様は確認できていない。[展示車の原寸写真](https://upload.wikimedia.org/wikipedia/commons/6/6c/Isuzu_Motors_ERGA_Non_Step_LV290_AMT_Cockpit.jpg) ／ [いすゞ主要装備一覧表、カタログpp.24–25](https://www.isuzu.co.jp/product/bus/erga_rt/common/pdf/diesel/soubi_diesel.pdf)

## 客席と乗降動線

乗客27席、立席51人、乗務員1人の仕様。公式の都市型座席図では、右側の4席は壁沿いに折り畳んだ状態で描かれている。メーカーの装備表と神奈中の使用時・収納時の写真を照合し、モデルでは全4席を使用時の前向き姿勢にした。固定の横向き席は0席。左低床部は優先席3席で、濃い青の表皮、通路側の肘掛け、窓下の優先席表示を付けた。[都市型N尺の定員](https://www.isuzu.co.jp/product/bus/erga_rt/erga_rt.html) ／ [公式座席図](https://www.isuzu.co.jp/product/bus/erga_rt/images/rt/rt_bus_shape_1.jpg) ／ [神奈中の跳上席・収納時](https://www.kanachu.co.jp/routebus/files/img_norikata_information_03.jpg) ／ [使用時](https://www.kanachu.co.jp/routebus/files/img_norikata_information_baby_02.jpg)

| 場所 | 席数 | 座面基準のY座標 m（前から順） |
|---|---:|---|
| 右前輪上の単席 | 1 | +2.42 |
| 右低床部の跳上席 | 4 | +1.44、+0.75、+0.06、−0.64 |
| 左低床部の優先席 | 3 | +1.37、+0.65、−0.06 |
| 中扉の向かい・右2人掛け | 2 | −1.45 |
| 段上・左右各2人掛け×3列 | 12 | −2.12、−2.96、−3.69 |
| 最後部の5人掛け | 5 | −4.52 |

席の前後位置はメーカー図面の両車軸を基準に割り出し、後列と前輪上は外装側の内張りの端、仕切り、車輪覆いに合わせた。図面の単席幅460 mm・2人掛け幅810 mmを参考に、表皮幅を単席447〜450 mm、後部2人掛けの1席分を396 mmとした。公式寸法図にある都市型N尺の平面図は前乗りの代表例で、中乗りの車内設備・乗降方向は神奈中の写真で補った。[主要図面、カタログp.26](https://www.isuzu.co.jp/product/bus/erga_rt/common/pdf/diesel/sunpou_diesel.pdf) ／ [神奈中・バスの乗り方](https://www.kanachu.co.jp/routebus/norikata.html)

中扉の後ろ側に整理券発行機と乗車用IC読取器、運転席の左側に現金投入口・精算画面・IC読取面のある料金箱を配置した。前方上部に客室を向く運賃表示器、車内に縦・横の手すり、左右計30個のつり革、押し面が赤い降車ボタン、千鳥配置の天井灯4本、側天井の冷房吹き出し口を設けた。運賃額、時刻、走行距離は描き起こした表示例である。

## 外装との取り合い

生成時に外装ファイルから仮内張りの面、左右13区画の側窓ガラス、前・中扉の世界座標を取得した。室内の基準端面はY=−4.800〜+4.695 m、中央内幅はX=±1.155 m。中央通路Z=0.315 mから内天井Z=2.720 mまでが2.405 mで、室内長は9.495 m。窓の見付け枠、側天井のダクト、座席はこの基準面から室内側に張り出す。

| 取り合い | 外装の保存メッシュで確認した位置 | 内装の処理 |
|---|---|---|
| 側窓 | ガラス下端Z=1.346、上端2.492 m。左右の各枚で前後端が異なる | 各ガラスの前後端から内枠を配置。右最前部にはスイッチ台と窓台を設置 |
| 前折戸 / 中引戸 | 前Y=+3.565〜+4.695、中Y=−1.395〜−0.260 m | ガラス面を空けて内側の縦枠、戸袋側の化粧板、内側上箱と敷居を配置 |
| 車輪覆い | 前後車軸Y=±2.650。外装のアーチ戻り頂部Z=1.065、背板上端1.067 m | 覆い上面Z=1.099。背板端を避けて覆いを車軸前後に643 mmずつ確保 |
| 通路と段差 | 仮床は後ろへY=−1.580でZ=0.530、−1.910でZ=0.785 m | 同じ位置に二段の蹴上げと黄色の段鼻を設置。前の乗降部は床下板に沿い、床を入口前端で約0.355 mまで上げた |

### 保存後の検査

Blender 5.2.2の別プロセスで保存済みの両ファイルを開いた。閉扉・直進姿勢で、仮内張りを除く外装465メッシュと内装48メッシュの **22,320組** を検査した。境界箱が接近した136組に、世界座標で三角形BVHの交差判定を実施。さらに同一平面の面積重複（面間隔0.001 mm以内）、閉体内部に収まった部品も検査し、いずれも0件だった。[検証スクリプト](scripts/verify_interior.py) ／ [検証結果・対象ファイルのSHA-256](verification.json)

内装の各メッシュで重複座標を除いた計62,446か所から、側面、前後端、屋根、床下板の方向について車外からのレイで境界位置を確かめた。実在する境界に当たったレイで測った最小の軸方向余裕は順に27.02、27.66、61.18、9.55 mm。開口などで片側の境界を拾えないレイは検証JSONに別計上した。外殻の凸包を超えた内装頂点も0件だった。検査の対象はBlenderの静止モデルで、ゲーム内で扉を開いた軌跡や操舵アニメーションは対象外である。

| 引き渡し項目 | 保存ファイルの検査値 |
|---|---:|
| 総三角形数 | 121,334 / 150,000 |
| 1メッシュの最大頂点数 | 11,564 / 60,000 |
| UVのないメッシュ、面積ゼロの立体・UV三角形 | いずれも0 |
| 使用材質 | 48種、すべて `interior_` で始まる |
| 画像 | 自作21枚すべてパック済み |
| ルートと動作点 | `COCKPIT_HR` 配下に全形状、ハンドル・針2本・視点の空オブジェクトを確認 |
| 運転席からの計器視認 | 両盤面の円周方向8点ずつ、全16点で最初の交点が該当の盤面 |

## レンダーと再生成

| 視点 | 確認できる箇所 |
|---|---|
| [運転席・水平60°](renders/01_driver_eye.png) | `DRIVER_EYE` からの前方視界、リム全体、左右の針、シフト、足元 |
| [客室後方から前方](renders/02_saloon_to_front.png) | 後部段床、通路、座席背面、運賃表示器 |
| [客室前方から後方](renders/03_saloon_to_rear.png) | 優先席・跳上席、後部の二段、つり革と照明 |
| [右の閉じた窓越し](renders/04_through_glazing.png) | 外装の窓枠と座席・手すりの位置関係 |
| [前扉側から運転台](renders/05_driver_station.png) | 料金箱、運転席保護板、ハンドルと座席の高低差 |
| [外装本来のガラス材質・右前](renders/06_exterior_glass_original.png) | 外装のガラス・ミラー・窓柱を含む状態での見え方 |
| [同じ目位置・16対9](renders/07_driver_eye_wide.png) | 運転台の左右と前方視界を同時に見るための補助画像。垂直画角60°、水平約91.5° |

7枚とも外装をメモリに読み込んだCyclesレンダー。1〜5枚目および7枚目は、厚さ3 mmのガラスの両面で透過が減衰するため、撮影用コピーのガラスのアルファを0.115に設定した。6枚目は外装保存時のアルファ0.57で撮影した。全視点でガラスと扉の形状は入っている。路面と白線は視線の向きを確認するための撮影セット。

リポジトリ直下で以下を実行する。1行目で内装と7枚のレンダーを再生成し、2行目で検査結果を更新する。盤面・文字・表皮はmacOSのシステムPython、Pillow、日本語フォントを使って描画する。

```sh
/opt/homebrew/bin/blender -b --factory-startup --python-exit-code 1 --python design/interior/scripts/build_interior.py
/opt/homebrew/bin/blender -b --factory-startup --python-exit-code 1 --python design/interior/scripts/verify_interior.py
```

## 写真資料

写真は造形、配色、配置の参照に使用した。車内から見た「ふ43」固有の運転台・座席生地を特定できる画像は今回確認できず、神奈中公式の機器・車内写真と、いすゞの都市型N尺図面、LV290展示車を組み合わせた。テクスチャはすべて自作。

| 資料 | 用途・参照画像 |
|---|---|
| [神奈川中央交通・バスの乗り方](https://www.kanachu.co.jp/routebus/norikata.html) | [跳上席収納時](https://www.kanachu.co.jp/routebus/files/img_norikata_information_03.jpg)、[青い前向き席](https://www.kanachu.co.jp/routebus/files/img_norikata_information_baby_02.jpg)、[中扉の整理券発行機](https://www.kanachu.co.jp/routebus/files/img_norikata_payment_afte_board.png)、[運賃箱のIC読取面と現金投入口](https://www.kanachu.co.jp/routebus/files/img_norikata_payment_afte_pay_03.jpg)、[降車ボタン](https://www.kanachu.co.jp/routebus/files/img_norikata_payment_afte_pay_01.jpg) |
| [いすゞ・乗降性／室内空間](https://www.isuzu.co.jp/product/bus/erga_rt/approach_interior.html) | [前向き優先席の肘掛け・表皮・背上グリップ](https://www.isuzu.co.jp/product/bus/erga_rt/images/app_inter/app_inter_4.jpg)、[通路と座席](https://www.isuzu.co.jp/product/bus/erga_rt/images/app_inter/app_inter_9.jpg)、[乗降口](https://www.isuzu.co.jp/product/bus/erga_rt/images/app_inter/app_inter_1.jpg) |
| [いすゞ・都市型のラインナップ](https://www.isuzu.co.jp/product/bus/erga_rt/erga_rt.html) | [N尺の席数と並び](https://www.isuzu.co.jp/product/bus/erga_rt/images/rt/rt_bus_shape_1.jpg) |
| [Comyu撮影・2015年展示車の運転席](https://commons.wikimedia.org/wiki/File:Isuzu_Motors_ERGA_Non_Step_LV290_AMT_Cockpit.jpg) | [原寸](https://upload.wikimedia.org/wikipedia/commons/6/6c/Isuzu_Motors_ERGA_Non_Step_LV290_AMT_Cockpit.jpg)。計器の左右・最大値・目盛りの方向、リム、パッド形状、運転席左の機器 |
| [いすゞプラザ展示車の写真記事](https://acv30gsv40.blog.fc2.com/blog-entry-4813.html) | [運転台と仕切り](https://blog-imgs-166.fc2.com/a/c/v/acv30gsv40/20231208163407e91.jpg)、[写真2](https://blog-imgs-166.fc2.com/a/c/v/acv30gsv40/20231208164005812.jpg)、[写真3](https://blog-imgs-166.fc2.com/a/c/v/acv30gsv40/202312081739029d3.jpg)、[写真4](https://blog-imgs-166.fc2.com/a/c/v/acv30gsv40/2023120817534769a.jpg) |
| [いすゞプラザ・エルガ運転席編](https://acv30gsv40.blog.fc2.com/blog-entry-3922.html) | [展示車の運転席写真](https://blog-imgs-116.fc2.com/a/c/v/acv30gsv40/20171208192240ee7.jpg)。ハンドル・運転機器の別角度 |
| 神奈中「ふ43」 | 車外から窓越しに見える手すり・吊手の位置を確認。[右後方の写真](https://rootbus.yu-nagi.com/kc-no11/2019103002-fu43r.jpg) |
