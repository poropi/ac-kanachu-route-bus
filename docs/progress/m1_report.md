# M1 試走と物理の調整 報告（箱のバス）

> 2026-11-26 追記：ここに書いた「不合格」はその後の直しで解消した（0→40 km/h 8.39 s、最高速 101 km/h、旋回半径 8.33〜8.35 m）。現在の §8 の判定は [m5_report.md](m5_report.md) を見る。

結論: AC は落ちずに走る（9 回とも起動・復元 OK）。ただし M1 の物理の合格条件は **加速（0-40 km/h、最高速）と旋回半径が未達**。
9 回の枠を使い切った。直したのは `limiter_rpm` の 1 つだけ。残りの原因は仮定値の調整では届かない所にある疑いが強く、次の手がかりを末尾に書いた。

## 走った 9 回

ログは `export/ac/<タグ>/`（git には入れない）。

| # | コース / モード | 変更 | 結果 |
|---|---|---|---|
| 1 | yabitsu s1_up / drive 180 s（`drive_yabitsu_075459`） | 無し（初期値） | settle 0.0 s、max_rpm 2604、vmax 3.29、flipped 偽、roll 最大 2.2°。AI は 1〜3 km/h でしか進まず、83 s 付近で 30 m 位置が飛んだ（AI の復帰による再配置と思われる。落下ではない） |
| 2 | ks_drag drag400 / accel 60 s（`accel_ks_drag_075927`） | 無し | max_rpm 2611、vmax 18.73、40 km/h に届かず。1 速と 2 速を行き来し続けた |
| 3 | drift / circle 60 s（`circle_drift_080113`） | 無し | ギアが中立のまま（probe の `requestedGearIndex` が効かない）。走行データ無し |
| 4 | accel（`accel_ks_drag_080404`） | limiter 2600→2550、shift_down 1200→900 | max_rpm 2562、vmax 18.69。行き来は残る |
| 5 | accel（`accel_ks_drag_080616`） | （probe）AI にアクセル 1.0 を上乗せ | max_rpm 2567、vmax 19.46。変わらず |
| 6 | accel（`accel_ks_drag_080832`） | engine_inertia 1.2→3.0、shift_down 900→700 | max_rpm 2636、vmax 21.54。変わらず、回転は悪化 |
| 7 | circle（`circle_drift_081041`） | （probe）AI 走行 + 手動ハンドル | **AI がブレーキを 1.0 のまま掛けていた**（`dbg` 行）。動かず。AI 走行（run 1〜6）は車の性能を測れないと判明 |
| 8 | circle（`circle_drift_081250`） | （probe）手動運転（gearUp のパルスでギアを入れる） | 1 速には入った。最初からフルロックで 1.8 km/h で這うだけ |
| 9 | circle 90 s（`circle_drift_081517`） | （probe）まず直進でフルアクセル → 減速 → フルロック | 直進も最高 17.7 km/h。ハンドル 0 なのに曲がり続ける（後述）。旋回は 1.75 km/h で 55 秒続き、半径が測れた |

回収した画像のうち、各回の代表（still / 走行中の chase・side・cockpit）を開いて確認した（全枚数は見ていない）。

## 設計書 §8 の判定

| 項目 | 基準 | 実測 | 合否 | ログ |
|---|---|---|---|---|
| この車のエラーが無い | `kanachu` を含む行 | `ERROR: NO STAT FOR kanachu_route_bus`（新車の統計ファイルが無いだけ）と `Missing texture: logo.png`（任意ファイル）のみ。クラッシュ無し、restored 全て True | 合格 | 全 9 回の aclog / csplog |
| settle_s | ≤ 2 | 0.0 | 合格 | 全 9 回 |
| flipped / y の落ち込み | 偽・急落なし | flipped 偽（roll 最大 2.2°）。y は run 1 の位置の飛び（上記）以外は 0.1 m 以内 | 合格 | run 1〜9 |
| max_rpm | ≤ 2600 | run 1: 2604、run 2: 2611（limiter 2600 の超過）。limiter 2550 にして run 4: 2562、run 5: 2567、run 6: 2636（inertia 3.0）、run 9: 2484 | 初期値では不合格。2550 で run 4・5 は合格。run 6 は超過 | run 1,2,4,5,6,9 |
| t_0_40 | 8〜16 s | **測れない**（どの回も 40 km/h に届かない。最高 21.5 km/h） | 不合格 | run 2,4,5,6,9 |
| vmax | ≤ 115 | 21.5 km/h（上限は満たすが、加速できない結果なので合格とは扱わない） | 未達 | run 6 |
| 旋回半径（外側前輪） | 8.3 ± 0.5 m | 20.7 m（CG 軌跡 19.1 m、1.75 km/h で這った状態の円当てはめ。summarize.py は定常速度が無く None を返したので、同じ式で手計算） | 不合格 | run 9 |
| max_lat_g | ≤ 0.7 | 0.117（速度が出ていないので意味は薄い） | 合格（参考） | run 9 |

## 直した仮定値と理由

最終の `tools/spec.json` で変わったのは次の 1 つだけ。

| キー | 旧 | 新 | 理由 |
|---|---|---|---|
| `limiter_rpm` | 2600 | 2550 | リミッター付近で 4〜11 rpm 超過し max_rpm 2604 / 2611 になった。2550 で 2562 / 2567 に収まった |

試して戻した値（証拠が無かったため）: `shift_down_rpm`（900 / 700）、`engine_inertia`（3.0）。1 速と 2 速の行き来は最初これで直ると考えたが、run 4〜6 で直らず、原因は AI のブレーキ（run 7 で判明）だった。engine_inertia 3.0 は run 6 で回転の超過を悪化させたので 1.2 に戻した。
`front_susp_type` の AXLE は、他の基準が DWB で通っていないため、試していない（設計の指示どおり）。

## 判明したこと（次に効く手がかり）

1. **AI 走行（`physics.setCarAutopilot`）は車の性能の測定に使えない。** AI はブレーキ 1.0 を掛けたまま、アクセルの上乗せも効かない。probe を手動運転（`overrideCarControls` + `combineAxis=false` + `gearUp` のパルス）に変えた（`tools/ac/KanachuProbe/KanachuProbe.lua`、**未コミット**。drive モードだけ AI のまま）。
2. **手動運転でも 17〜18 km/h で頭打ち。** 1 速の初期加速は約 1.5 m/s² で出る（0→17 km/h が 2.3 s）が、そこから伸びない。タイヤ・駆動系の抵抗が異常に大きい挙動。
3. **ハンドル 0 で曲がり続ける**（run 9 直進中、ヨー約 10°/s、半径およそ 24 m）。前輪が常に切れている状態（トーやステアリング・ロッドの幾何のずれ）で、前輪がこすれて加速を止め、旋回半径も大きくなる説明になる。**最有力の次の一手は、前輪の DWB のステア幾何（`WBCAR_STEER` / `WBTYRE_STEER` / `ROD_LENGTH`）の確認と、`front_susp_type`: AXLE の試走。**
4. ハンドルの切れ角は `STEER_LOCK / STEER_RATIO` が常に 39.68° になる作りなので、`steer_lock_deg` を変えても切れ角は変わらない（調整の対象ではない）。
5. **外装が車の外から見えない可能性。** 車外カメラ（side）の画像には車体が写らず影だけ、chase は車内のような一色、cockpit は箱の内壁だけが見える。箱の面の向き（法線）が内向きか、描画側の問題。M2 で外装を作り直すので優先度は低いが、M2 の検査項目に「外から見える」を入れたい。
6. 車外カメラ（side）の画像は上下が逆になる回がある（probe の `mat4x4.look` の向き）。物理の判定には使っていない。

## その他の判断

- **data.acd に固めるか: 固めない。** `data/` のままで AC が読めた（aclog に `Data path: content/cars/kanachu_route_bus/data/`、全 ini・lut を読込）。
- **借りた音**: `tky_bus_jetset`（sfx のバンク）。M1 の仮。
- **driver3d.ini は借り物**（LOCK=450、この車の STEER_LOCK=900 と合わない）。M3 で合わせる。cockpit の画像で運転手の腕は表示される。
- 画像: 各回の `export/ac/<タグ>/cap_*.png`（still / t030〜t150 / end × chase / side / cockpit）。代表: `export/ac/accel_ks_drag_080832/cap_accel_ks_drag_080832_t030_side.png`（影のみ）、`export/ac/drive_yabitsu_075459/cap_drive_yabitsu_075459_t060_cockpit.png`（箱の内壁と腕）。
