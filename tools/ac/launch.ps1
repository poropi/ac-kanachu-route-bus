param([string]$Tag,[string]$Track,[string]$Layout='',[string]$Mode='drive',[int]$Duration=30,[string]$Car='kanachu_route_bus',[int]$NoProbe=0,[string]$Skin='',[int]$Night=0,[string]$RestoreTag='')
$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'
if ($Layout -eq 'NONE') { $Layout='' }
$dir=Join-Path $env:USERPROFILE 'Documents\kanachu-validation'
$ac='C:\Program Files (x86)\Steam\steamapps\common\assettocorsa'
$cfg=Join-Path $env:USERPROFILE 'Documents\Assetto Corsa\cfg'
$car=$Car; $ownCar=($Car -eq 'kanachu_route_bus')
if ($RestoreTag) {
  # Cleanup called from run.sh: if acs is not running, restore from backup-$RestoreTag and check SHA256
  $b="$dir\backup-$RestoreTag"
  if (-not (Test-Path $b)) { "RESTORE: backup-$RestoreTag is not there (nothing to restore)"; exit 0 }
  if (Get-Process acs -ErrorAction SilentlyContinue) { "RESTORE SKIPPED: acs is running; restore $b by hand after AC exits"; exit 3 }
  Stop-ScheduledTask -TaskName "Kanachu-Probe-$RestoreTag" -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName "Kanachu-Probe-$RestoreTag" -Confirm:$false -ErrorAction SilentlyContinue
  Copy-Item "$b\race.ini","$b\video.ini" $cfg -Force
  if (Test-Path "$ac\apps\lua\KanachuProbe") { Remove-Item "$ac\apps\lua\KanachuProbe" -Recurse -Force }
  $ok=@(foreach($f in 'race.ini','video.ini'){ (Get-FileHash "$cfg\$f" -Algorithm SHA256).Hash -eq (Get-FileHash "$b\$f" -Algorithm SHA256).Hash }) -notcontains $false
  "RESTORE restored=$ok lua_app_in_apps=$(Test-Path "$ac\apps\lua\KanachuProbe")"
  if ($ok -and -not (Test-Path "$dir\restored-$RestoreTag.txt")) { @("restored by run.sh (RestoreTag)","race.ini restored=True","video.ini restored=True") | Set-Content "$dir\restored-$RestoreTag.txt" }
  exit $(if($ok){0}else{1})
}
$backup="$dir\backup-$Tag"; $backedUp=$false
try {
if (Get-Process acs -ErrorAction SilentlyContinue) {throw 'AC is already running'}
# Refuse to start while a previous run is unrestored (backup-* without restored-* or launchfail-*): the modified ini would become the new backup
$unrestored=@(Get-ChildItem $dir -Directory -Filter 'backup-*' -ErrorAction SilentlyContinue | Where-Object { $n=$_.Name.Substring(7); -not (Test-Path "$dir\restored-$n.txt") -and -not (Test-Path "$dir\launchfail-$n.txt") } | ForEach-Object { $_.FullName })
if ($unrestored.Count -gt 0) { throw ("previous run is not restored; refusing to start. Restore race.ini/video.ini from these backups by hand (or run launch.ps1 -RestoreTag <tag>): "+($unrestored -join ', ')) }
if (Test-Path $backup) {throw 'Backup already exists'}
New-Item -ItemType Directory $backup | Out-Null
Copy-Item "$cfg\race.ini","$cfg\video.ini" $backup
$backedUp=$true
if ($ownCar) {
  # our car folder is deleted and recreated each run (only this folder is touched under content\cars)
  if (Test-Path "$ac\content\cars\$car") { Remove-Item "$ac\content\cars\$car" -Recurse -Force }
  Expand-Archive "$dir\car.zip" "$ac\content\cars" -Force
  if (-not (Test-Path "$ac\content\cars\$car\$car.kn5")) { throw 'car was not installed' }
  # our driver model: overwrite only this one file under content\driver (it may stay installed after the run)
  if (-not (Test-Path "$dir\kanachu_driver.kn5")) { throw 'kanachu_driver.kn5 was not sent' }
  New-Item -ItemType Directory -Force "$ac\content\driver" | Out-Null
  Copy-Item "$dir\kanachu_driver.kn5" "$ac\content\driver\kanachu_driver.kn5" -Force
  if ((Get-Item "$ac\content\driver\kanachu_driver.kn5").Length -ne (Get-Item "$dir\kanachu_driver.kn5").Length) { throw 'driver kn5 was not installed' }
  # first skin folder by name (0_new2023) unless -Skin names one
  $first=Get-ChildItem "$ac\content\cars\$car\skins" -Directory -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -First 1
  if ($Skin) { if (-not (Test-Path "$ac\content\cars\$car\skins\$Skin")) { throw "skin $Skin was not found in $car" }; $skin=$Skin }
  elseif ($first) { $skin=$first.Name } else { throw "no skin folder in $car" }
} else {
  # an existing car, read-only: use its first skin folder
  $first=Get-ChildItem "$ac\content\cars\$car\skins" -Directory -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -First 1
  if (-not $first) { throw "car $car or its skins were not found" }
  $skin=$first.Name
}
if (-not $NoProbe) {
  if (Test-Path "$ac\apps\lua\KanachuProbe") { Remove-Item "$ac\apps\lua\KanachuProbe" -Recurse -Force }
  Expand-Archive "$dir\KanachuProbe.zip" "$ac\apps\lua" -Force
  # the probe writes its logs to this run folder: fill in the @OUTPUT@ placeholder with the real path
  $lua="$ac\apps\lua\KanachuProbe\KanachuProbe.lua"
  [IO.File]::WriteAllText($lua, ([IO.File]::ReadAllText($lua).Replace('@OUTPUT@', ($dir -replace '\\','/') + '/')), (New-Object Text.UTF8Encoding($false)))
}
Set-Content "$dir\tag.txt" $Tag
Set-Content "$dir\mode.txt" $Mode
Set-Content "$dir\duration.txt" $Duration
Set-Content "$dir\night.txt" $Night
function Set-Key([string]$text,[string]$section,[string]$key,[string]$value) {
  $pattern='(?ms)(^\['+[regex]::Escape($section)+'\]\s*\r?\n)(.*?)(?=^\[|\z)'
  $m=[regex]::Match($text,$pattern)
  if(-not $m.Success){ throw "section [$section] not found; refusing to edit" }
  $body=$m.Groups[2].Value; $kp='(?m)^'+[regex]::Escape($key)+'=.*$'
  if([regex]::IsMatch($body,$kp)){$body=[regex]::Replace($body,$kp,$key+'='+$value)}else{$body=$body.TrimEnd()+"`r`n$key=$value`r`n`r`n"}
  return $text.Substring(0,$m.Index)+$m.Groups[1].Value+$body+$text.Substring($m.Index+$m.Length)
}
$t=Get-Content "$cfg\race.ini" -Raw
$t=Set-Key $t 'WEATHER' 'NAME' 'sol_01_clear'
$t=Set-Key $t 'LIGHTING' '__CM_WEATHER_TYPE' '15'
if ($Night) { $t=Set-Key $t 'LIGHTING' 'SUN_ANGLE' '120.00' }   # CSP sun angle: (hour - 13) x 15 deg, so 21:00 = 120 (the user's race.ini has -29.38 at about 11:00)
$t=Set-Key $t 'CAR_0' 'MODEL' $car
$t=Set-Key $t 'CAR_0' 'SKIN' $skin
$t=Set-Key $t 'RACE' 'MODEL' $car
$t=Set-Key $t 'RACE' 'SKIN' $skin
$t=Set-Key $t 'RACE' 'TRACK' $Track
$t=Set-Key $t 'RACE' 'CONFIG_TRACK' $Layout
if ($t -notmatch ('(?m)^TRACK='+[regex]::Escape($Track)+'\r?$') -or $t -notmatch '(?m)^__CM_WEATHER_TYPE=15\r?$' -or $t -notmatch ('(?m)^CONFIG_TRACK='+[regex]::Escape($Layout)+'\r?$') -or $t -notmatch ('(?m)^MODEL='+$car+'\r?$')) { Copy-Item "$backup\race.ini","$backup\video.ini" $cfg -Force; throw 'race.ini was not set as expected; AC not started' }
[IO.File]::WriteAllText("$cfg\race.ini",$t)
$v=Get-Content "$cfg\video.ini" -Raw
$v=Set-Key $v 'VIDEO' 'FULLSCREEN' '0'; $v=Set-Key $v 'VIDEO' 'WIDTH' '1920'; $v=Set-Key $v 'VIDEO' 'HEIGHT' '1080'
[IO.File]::WriteAllText("$cfg\video.ini",$v)
$t0=(Get-Date).Ticks
function Q([string]$s) { return $s.Replace("'","''") }   # double single quotes in values embedded in the here-string
$qDir=Q $dir; $qAc=Q $ac; $qCfg=Q $cfg; $qTag=Q $Tag; $qCar=Q $Car; $qSkin=Q $skin
$body=@"
`$dir='$qDir'; `$ac='$qAc'; `$cfg='$qCfg'; `$tag='$qTag'; `$tag_car='$qCar'; `$skin_used='$qSkin'; `$t0=[long]$t0; `$crash=`$null; `$noprobe=$NoProbe; `$running=`$false; `$killed=`$false; `$runAt=`$null
`$lg=Join-Path (Split-Path `$cfg) 'logs\log.txt'
function Stop-Wer([int]`$id) { Get-CimInstance Win32_Process -Filter "Name='WerFault.exe'" -ErrorAction SilentlyContinue | Where-Object { `$_.CommandLine -match ('-p '+`$id+'\b') } | ForEach-Object { Stop-Process -Id `$_.ProcessId -Force -ErrorAction SilentlyContinue } }
[IO.File]::WriteAllText("`$dir\watching-`$tag.txt",(Get-Date).ToString('o'))
function Read-Shared([string]`$f) { `$fs=[IO.File]::Open(`$f,'Open','Read','ReadWrite,Delete'); try { `$r=New-Object IO.StreamReader(`$fs); return `$r.ReadToEnd() } finally { `$fs.Dispose() } }
try {
  `$env:SteamAppId='244210'
  `$p=Start-Process "`$ac\acs.exe" -WorkingDirectory `$ac -PassThru
  `$deadline=(Get-Date).AddSeconds($(if($NoProbe){$Duration+60}else{$Duration+400}))
  while(-not `$p.HasExited -and (Get-Date) -lt `$deadline -and -not (Test-Path "`$dir\`$tag.complete")) {
    Start-Sleep -Seconds 1; `$p.Refresh()
    try {
      if((Test-Path `$lg) -and (Get-Item `$lg).LastWriteTime.Ticks -gt `$t0) {
        `$ls=(Read-Shared `$lg) -split "`r?`n"; `$i=[array]::IndexOf(`$ls,(`$ls | Where-Object { `$_ -like 'CRASH in:*' } | Select-Object -First 1))
        if(`$i -ge 0) { `$crash=(`$ls[`$i..([Math]::Min(`$i+4,`$ls.Count-1))] -join ' | '); break }
        if(`$noprobe -and -not `$running -and (`$ls | Where-Object { `$_ -like '*SESSION INFO RECEIVED*' } | Select-Object -First 1)) { `$running=`$true; `$runAt=Get-Date }
      }
    } catch {}
    if(`$running -and (Get-Date) -ge `$runAt.AddSeconds(20)) { break }
  }
  if(`$crash) {
    Stop-Wer `$p.Id
    Stop-Process -Id `$p.Id -Force -ErrorAction SilentlyContinue; `$p.WaitForExit(10000) | Out-Null
  }
  elseif(-not `$p.HasExited) { `$p.CloseMainWindow() | Out-Null; if(-not `$p.WaitForExit(15000)) { `$killed=`$true; `$p.Kill(); `$p.WaitForExit(10000) | Out-Null } }
  # WerFault can appear only after acs is gone: keep looking for 5 s
  if(`$crash -or `$killed) { for(`$k=0;`$k -lt 5;`$k++){ Stop-Wer `$p.Id; Start-Sleep -Seconds 1 } }
} catch { `$_ | Out-String | Set-Content "`$dir\error-`$tag.txt" }
finally {
  # restore only after acs has exited (AC may write cfg after a restore made while it runs)
  foreach(`$a in @(Get-Process acs -ErrorAction SilentlyContinue)) { if(-not `$a.WaitForExit(30000)) { try { `$a.Kill() } catch {}; `$a.WaitForExit(10000) | Out-Null } }
  Copy-Item "`$dir\backup-`$tag\race.ini","`$dir\backup-`$tag\video.ini" `$cfg -Force
  if (Test-Path "`$ac\apps\lua\KanachuProbe") { Move-Item "`$ac\apps\lua\KanachuProbe" "`$dir\KanachuProbe-removed-`$tag" -Force }
  Copy-Item (Join-Path (Split-Path `$cfg) 'logs\log.txt') "`$dir\aclog-`$tag.txt" -Force -ErrorAction SilentlyContinue
  Copy-Item (Join-Path (Split-Path `$cfg) 'logs\custom_shaders_patch.log') "`$dir\csplog-`$tag.txt" -Force -ErrorAction SilentlyContinue
  `$o=@()
  foreach(`$f in 'race.ini','video.ini'){ `$a=(Get-FileHash "`$cfg\`$f" -Algorithm SHA256).Hash; `$b=(Get-FileHash "`$dir\backup-`$tag\`$f" -Algorithm SHA256).Hash; `$o+="`$f restored=`$(`$a -eq `$b) sha256=`$a backup=`$b" }
  `$o+="probe=`$(-not `$noprobe)"; if(`$noprobe){ `$o+="reached_running=`$running" }
  `$o+="car=`$tag_car skin=`$skin_used"
  `$o+="crashed=`$([bool]`$crash)"; if(`$crash){ `$o+="crash_line=`$crash" }
  `$o+="lua_app_in_apps=`$(Test-Path "`$ac\apps\lua\KanachuProbe")"
  `$o+="acs_running=`$([bool](Get-Process acs -ErrorAction SilentlyContinue))"
  `$o | Set-Content "`$dir\restored-`$tag.txt"
}
"@
$encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($body))
$action=New-ScheduledTaskAction -Execute conhost.exe -Argument ('--headless powershell.exe -NoProfile -NonInteractive -EncodedCommand '+$encoded)
$principal=New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "Kanachu-Probe-$Tag" -Action $action -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName "Kanachu-Probe-$Tag"
# Wait up to 20 s for the watching task to start (it writes watching-$Tag.txt first); otherwise the catch restores.
# Keep this file ASCII-only: Windows PowerShell 5.1 reads a BOM-less file as CP932, and a Japanese comment there
# swallowed the next line (run 20261126_104406: the wait loop vanished and the launch failed at once).
$w=0; while (-not (Test-Path "$dir\watching-$Tag.txt") -and $w -lt 20) { Start-Sleep -Seconds 1; $w++ }
if (-not (Test-Path "$dir\watching-$Tag.txt")) { throw 'the watching task did not start within 20 s (user not logged on? bad script?)' }
"started $Tag"
} catch {
  # anything before the scheduled task took over: put everything back and fail loudly
  $err=$_ | Out-String
  if ($backedUp) { try { Copy-Item "$backup\race.ini","$backup\video.ini" $cfg -Force } catch {} }
  try { if ($backedUp -and (Test-Path "$ac\apps\lua\KanachuProbe")) { Remove-Item "$ac\apps\lua\KanachuProbe" -Recurse -Force } } catch {}
  try { Stop-ScheduledTask -TaskName "Kanachu-Probe-$Tag" -ErrorAction SilentlyContinue } catch {}
  try { Unregister-ScheduledTask -TaskName "Kanachu-Probe-$Tag" -Confirm:$false -ErrorAction SilentlyContinue } catch {}
  # Stopping the task kills conhost but not its powershell child (run 20261126_104406: the watcher still started AC);
  # the .complete file makes a running watcher close AC and restore again.
  try { Set-Content "$dir\$Tag.complete" "launch failed" } catch {}
  try {
    $same=$true
    if ($backedUp) { $same=@(foreach($f in 'race.ini','video.ini'){ (Get-FileHash "$cfg\$f" -Algorithm SHA256).Hash -eq (Get-FileHash "$backup\$f" -Algorithm SHA256).Hash }) -notcontains $false }
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    @("launch failed before AC started","backed_up=$backedUp","restored=$same","lua_app_in_apps=$(Test-Path "$ac\apps\lua\KanachuProbe")","error=$err") | Set-Content "$dir\launchfail-$Tag.txt"
  } catch {}
  Write-Output "LAUNCH FAILED: $err"
  exit 1
}
