#!/bin/bash
# 使い方: tools/ac/run.sh <track> <layout> <mode> [秒]
#   layout が無いコースは '' を渡す（NONE として送り launch.ps1 で空に戻す）。mode は drive / accel / circle。
#   環境変数 CAR=<車フォルダ>（既定 kanachu_route_bus）: 別の既存の車で走らせる（こちらの車は送らない）。
#   環境変数 SKIN=<スキンのフォルダ名>（既定: 車のスキンを名前順に並べた最初、0_new2023）。NIGHT=1: 夜（SUN_ANGLE 120 ≒ 21 時）にしてヘッドライトを点ける。
#   環境変数 NOPROBE=1: Lua アプリを入れず、ログの SESSION INFO RECEIVED（物理開始後）+20 秒で閉じる。
# AC が使われていなければ、build/kanachu_route_bus をゲーム PC（ssh のホスト名は環境変数 GAME_PC、または tools/ac/local.env）に置き直し、Lua アプリを送り、走らせて記録を export/ac/<tag>/ に回収する。
set -u
TRACK=${1:?track}; LAYOUT=${2-}; MODE=${3:?mode}; DUR=${4:-30}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CAR=${CAR:-kanachu_route_bus}; NOPROBE=${NOPROBE:-0}
T="${MODE}_${TRACK}_$(date +%Y%m%d_%H%M%S)"
# ゲーム PC の ssh ホスト名。tools/ac/local.env（git に入れない）に GAME_PC=<ホスト名> と書いておける
[ -f "$ROOT/tools/ac/local.env" ] && . "$ROOT/tools/ac/local.env"
GAME_PC=${GAME_PC:?GAME_PC にゲーム PC の ssh ホスト名を入れてください（tools/ac/local.env でもよい）}
D='Documents\kanachu-validation'   # ゲーム PC のホームからの相対（ssh の作業フォルダはホーム）
OUT=$ROOT/export/ac/$T
O="-o BatchMode=yes -o ConnectTimeout=10"
# ゲーム PC 側で「acs が動いていなければ backup-$T から戻して SHA256 を照合する」（launch.ps1 -RestoreTag）
restore_remote() { echo "$GAME_PC: backup-$T から戻します（acs が動いていなければ）"; ssh $O $GAME_PC "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $D\\launch.ps1 -RestoreTag $T" 2>&1 | LC_ALL=C tr -d '\r' | tail -5; }
ps() { ssh $O $GAME_PC "powershell.exe -NoProfile -Command \"$1\"" 2>/dev/null | LC_ALL=C tr -d '\r'; }
# 承認制の試走を古い build や壊れた build で使わない（転送の前に検査する）
[ "$CAR" != kanachu_route_bus ] || python3 "$ROOT/tools/validate.py" || { echo "STOP: validate.py が NG です（python3 tools/assemble.py で組み直してください）"; exit 1; }
[ "$CAR" != kanachu_route_bus ] || [ -d "$ROOT/build/kanachu_route_bus" ] || { echo "STOP: build/kanachu_route_bus がありません（python3 tools/assemble.py）"; exit 1; }
st=$(ps "if(Get-Process acs -EA 0){'BUSY'}else{'idle'}" | tail -1)
if [ "$st" != "idle" ]; then echo "STOP: AC is in use"; exit 1; fi
TMP=$(mktemp -d) || exit 1
trap 'rm -rf "$TMP"' EXIT
[ "$CAR" = kanachu_route_bus ] && { (cd "$ROOT/build" && zip -qr "$TMP/car.zip" kanachu_route_bus) || exit 1; }
(cd "$ROOT/tools/ac" && zip -qr "$TMP/KanachuProbe.zip" KanachuProbe) || exit 1
ps "New-Item -ItemType Directory -Force $D | Out-Null" >/dev/null
scp -q "$TMP"/*.zip "$ROOT/tools/ac/launch.ps1" "$GAME_PC:Documents/kanachu-validation/" || { echo "STOP: scp 失敗"; exit 1; }
LOUT=$(ssh $O $GAME_PC "powershell.exe -NoProfile -ExecutionPolicy Bypass -File $D\\launch.ps1 -Tag $T -Track $TRACK -Layout ${LAYOUT:-NONE} -Mode $MODE -Duration $DUR -Car $CAR -NoProbe $NOPROBE ${SKIN:+-Skin $SKIN} -Night ${NIGHT:-0}" 2>&1 | LC_ALL=C tr -d '\r')
echo "$LOUT" | tail -5
if ! echo "$LOUT" | grep -q "^started $T"; then
  echo "STOP: launch が始まっていません（上の出力を確認）。ssh が途中で切れた場合は launch.ps1 が戻していないので、こちらから戻します。"
  restore_remote
  echo "      $D\\launchfail-$T.txt があれば見てください。"
  exit 1
fi
FOUND=0
for i in $(seq 1 $(( (DUR + 400) / 5 ))); do
  sleep 5
  r=$(ps "if(Test-Path $D\\restored-$T.txt){'DONE'}" | tail -1)
  [ "$r" = "DONE" ] && { FOUND=1; break; }
done
ps "Unregister-ScheduledTask -TaskName Kanachu-Probe-$T -Confirm:\`\$false" >/dev/null
mkdir -p "$OUT"
for f in "log-$T.txt" "log-$T.csv" "aclog-$T.txt" "csplog-$T.txt" "error-$T.txt" "restored-$T.txt"; do scp -q "$GAME_PC:Documents/kanachu-validation/$f" "$OUT/" 2>/dev/null; done
scp -q "$GAME_PC:Documents/kanachu-validation/cap_${T}_*.png" "$OUT/" 2>/dev/null
echo "DONE $T → $OUT"; ls "$OUT"; cat "$OUT/restored-$T.txt" 2>/dev/null
R="$OUT/restored-$T.txt"
if [ "$FOUND" != 1 ] || [ ! -s "$R" ]; then
  echo "WARNING: restored-$T.txt がありません。ゲーム PC の race.ini / video.ini が戻っていない可能性があります。"
  restore_remote
  echo "         戻らなかった場合はゲーム PC の $D\\backup-$T から手で戻してください。"
  exit 2
fi
if grep -q "restored=False" "$R" || grep -q "lua_app_in_apps=True" "$R" || grep -q "acs_running=True" "$R"; then
  echo "WARNING: 戻し処理が不完全です（restored=False、Lua アプリが残っている、または戻した時点で acs が動いていました）。ゲーム PC の設定を確認してください。"
  exit 2
fi
exit 0
