-- Kanachu bus probe (temporary; removed after each run). Active only when car 0 is kanachu_route_bus.
-- mode.txt: drive (autopilot) / accel (autopilot on drag400) / circle (full steering lock at ~10 km/h via ac.overrideCarControls)
--           / skidpad (20 m steady circle, speed ramp until the limit; design §8-5)
--           / circleramp (circle, then the speed ramps at full lock until the limit; stand-in for §8-5 on 'drift').
-- Logs t,x,y,z,kmh,rpm,gear,roll,pitch at 10 Hz from the very start (still phase included) to log-<tag>.csv.
-- Screenshots (chase / side / cockpit) while still, every 30 s of driving, and at the end.
local enabled = ac.getCarID(0) == 'kanachu_route_bus'
local SHOT_TIMEOUT = 8   -- seconds; a screenshot job never blocks driving or finishing longer than this
local output = '@OUTPUT@'   -- launch.ps1 replaces this with the run folder (<user>/Documents/kanachu-validation/) when it installs the app
local function readLine(name, default)
  local f = io.open(output..name,'r'); if not f then return default end
  local l = f:read('*l'); f:close(); return l and l:gsub('%s+$','') or default
end
local runTag = readLine('tag.txt','run')
local mode = readLine('mode.txt','drive')
local duration = tonumber(readLine('duration.txt','30')) or 30
local night = readLine('night.txt','0') == '1'
-- drive mode also checks the turn signals: hazards on from the start, and every shot waits (up to 1.5 s) for the lamps' on-phase.
local hazards = (mode == 'drive')
local WAIT = 5
local elapsed, started, done, driveStart = 0, false, false, 0
local cockpitPos
local lastHaz
local lastDbg, lastFlags, lastLights
local lastLog, nextShot, shotJob, grabbed, endShot = 0, nil, nil, nil, false
local function record(t) local f=io.open(output..'log-'..runTag..'.txt','a'); if f then f:write(t..'\n'); f:close() end end
local function csv(t) local f=io.open(output..'log-'..runTag..'.csv','a'); if f then f:write(t..'\n'); f:close() end end
local function finish() done=true; if grabbed then pcall(function() grabbed:dispose() end) end
  record('complete'); local f=io.open(output..runTag..'.complete','w'); if f then f:write('ok'); f:close() end end
if enabled then
  record('loaded '..runTag..' mode='..mode..' track='..tostring(ac.getTrackID())..' car='..tostring(ac.getCarID(0)))
  record('layout='..tostring(select(2, pcall(ac.getTrackLayout)))..' physics.allowed='..tostring(select(2, pcall(physics.allowed))))
  csv('t,x,y,z,kmh,rpm,gear,roll,pitch,gas,brake,clutch,handbrake,req_gear,engaged_gear,steer_deg,front_steer_deg,cam_x,cam_y,cam_z,'
    ..'w0_kmh,w0_slipratio,w0_slipangle,w0_load,w1_kmh,w1_slipratio,w1_slipangle,w1_load,'
    ..'w2_kmh,w2_slipratio,w2_slipangle,w2_load,w3_kmh,w3_slipratio,w3_slipangle,w3_load')
end
function script.windowMain() ui.text('Kanachu probe') end

local CAMS = {'chase','side','front34','cockpit','drvhands','drvfront','drvwindow','drvaisle'}   -- cockdown: eye position looking 35 deg down, shows the steering wheel and hands
-- eyedown: the same pose as cockdown, but with the driver's face / hair / cap hidden while it is taken, i.e. what the real cockpit view
-- (driver3d.ini HIDE_OBJECT) would see looking down. The grabbed camera does not apply HIDE_OBJECT, so the probe hides the nodes itself.
local DRV_SHOTS = {'drvhands', 'drvwindow', 'drvaisle', 'cockpit', 'eyedown'}   -- circle mode: at steer 0 (still), +90 (steer90), -90 (steerm90)
-- AC's own cameras (not grabbed): cockpit, acchase1/2 = F1 chase / chase far (global distance, user: covers the screen), f6_3/4 = the rear F6 cameras in cameras.ini (AC reads at most 6)
local NATIVE = {cockpit = true, acchase1 = true, acchase2 = true, f6_3 = true, f6_4 = true}
-- External views use our own grabbed camera (the bus is 10.4 x 2.5 x 3.1 m; AC's chase camera ends up inside it).
-- c.position is the car's model origin; the target is 1.5 m above it. "left" = +c.side: c.side points to the car's LEFT
-- (run 091041: with left = -c.side the "side" shot showed the right, door-less side of the bus).
local function viewPose(name, c)
  local centre = c.position + vec3(0, 1.5, 0)
  local left = c.side
  local pos
  if name == 'chase' then pos = c.position - c.look * 16 + vec3(0, 5, 0)
  elseif name == 'side' then pos = c.position + left * 12 + vec3(0, 1.8, 0)
  else pos = c.position + c.look * 8.5 + left * 8.5 + vec3(0, 3, 0) end      -- front34: 12 m away, ahead-left
  return pos, centre
end
local function setCamera(name, c)
  if name == 'cockpit' then ac.setCurrentCamera(ac.CameraMode.Cockpit)
  elseif name == 'acchase1' or name == 'acchase2' then
    ac.setCurrentCamera(ac.CameraMode.Drivable)
    ac.setCurrentDrivableCamera(name == 'acchase1' and ac.DrivableCamera.Chase or ac.DrivableCamera.Chase2)
  elseif name:sub(1, 3) == 'f6_' then
    local sm = ac.getSim(); local n = tonumber(name:sub(4))
    if sm.cameraMode ~= ac.CameraMode.Car then ac.setCurrentCamera(ac.CameraMode.Car) elseif sm.carCameraIndex ~= n then ac.setCurrentCarCamera(n) end
  elseif not grabbed then grabbed = ac.grabCamera('kanachu probe') end
end
-- The camera basis is set explicitly (AC: +x right, +y up, +z forward): look = target - pos, side = up_world x look, up = look x side.
-- (Run 090152: mat4x4.look(pos, dir, up) gave upside-down images, so it is only a fallback now.)
local function cross(a, b) return {a[2]*b[3]-a[3]*b[2], a[3]*b[1]-a[1]*b[3], a[1]*b[2]-a[2]*b[1]} end
local function norm(a) local l = math.sqrt(a[1]*a[1]+a[2]*a[2]+a[3]*a[3]); return {a[1]/l, a[2]/l, a[3]/l} end
-- Driver eye in world space, recomputed every frame from car.ini [GRAPHICS] DRIVEREYES (kn5 coords: +x = car's left = c.side).
-- (Run circle_drift_094555: reusing the world position of the last cockpit shot left the camera 1.6 m behind the eye once the bus
-- had moved, and the cockpit camera itself once came out 5.6 m behind the bus.)  Checked against run 094256: eye = 3.39 m ahead, 0.63 m right, 1.98 m up.
local EYE = {-0.642, 1.815, 3.83}   -- = tools/spec.json eye_x/y/z (2026-11-26: the driver model's eye inside the head; was DRIVER_EYE -0.642, 1.985, 3.407)
-- F6 cameras 3/4 as written to data/cameras.ini (kn5 car space: +x = c.side, +y = up, +z = c.look); read from the car if CSP allows, else these copies
local F6CAM = {[3] = {p = {0, 4.905, -13.48}, f = {0, -0.21914, 0.97569}}, [4] = {p = {0, 6.305, -18.48}, f = {0, -0.23213, 0.97268}}}
pcall(function()
  local ini = ac.INIConfig.carData(0, 'cameras.ini')
  for n = 3, 4 do
    local p = ini:get('CAMERA_'..n, 'POSITION', vec3(0, -99, 0)); local f = ini:get('CAMERA_'..n, 'FORWARD', vec3(0, 0, 0))
    if p and p.y ~= -99 then F6CAM[n] = {p = {p.x, p.y, p.z}, f = {f.x, f.y, f.z}}; record(string.format('F6 camera %d from car data: %.3f,%.3f,%.3f', n, p.x, p.y, p.z)) end
  end
end)
-- centres of the rear-view mirror faces in kn5 car space (build/kanachu_route_bus.kn5: Mirror_Starboard_Main_Surface, Mirror_Port_Long_Surface)
-- cameras aimed at the driver (kn5 car space: +x = car's left, +y up, +z forward; driver seat ~(-0.64, 1.7, 3.7), bus front at z ~4.95)
local CARCAM = {
  drvfront  = {p = {-0.9, 2.3, 7.0},  t = {-0.64, 1.75, 3.75}, fov = 35},   -- 2 m ahead of the bus, through the windshield
  drvwindow = {p = {-3.2, 2.0, 3.9},  t = {-0.64, 1.75, 3.70}, fov = 35},   -- outside the driver's (right) side window
  drvaisle  = {p = {0.45, 1.95, 2.3}, t = {-0.60, 1.55, 3.85}, fov = 55},   -- inside, from the aisle behind-left
  drvhands  = {p = {-0.85, 2.15, 4.75}, t = {-0.64, 1.45, 4.00}, fov = 50}, -- inside the windshield, looking down at both hands on the wheel
}
local MIRROR_AT = {mirrorR = {-1.327, 2.031, 4.508}, mirrorL = {1.263, 1.997, 5.124}}
local function eyeWorld(c) return c.position + c.side * EYE[1] + c.up * EYE[2] + c.look * EYE[3] end
local function externalCam(name, c)
  if not grabbed then return end
  local pos, centre, look
  if CARCAM[name] then   -- fixed camera in car space aimed at the driver (original driver, Task 8)
    local cc = CARCAM[name]
    pos = c.position + c.side * cc.p[1] + c.up * cc.p[2] + c.look * cc.p[3]
    local tgt = c.position + c.side * cc.t[1] + c.up * cc.t[2] + c.look * cc.t[3]
    look = norm({tgt.x - pos.x, tgt.y - pos.y, tgt.z - pos.z})
    centre = tgt
  elseif name == 'mirrorR' or name == 'mirrorL' then   -- from the driver's eye, zoomed on the right (driver side) / left rear-view mirror
    local m = MIRROR_AT[name]
    pos = eyeWorld(c)
    local tgt = c.position + c.side * m[1] + c.up * m[2] + c.look * m[3]
    look = norm({tgt.x - pos.x, tgt.y - pos.y, tgt.z - pos.z})
    centre = tgt
  elseif name:sub(1, 4) == 'f6g_' then  -- replica of F6 camera N: same car-space position / forward / fov as data/cameras.ini, through the grabbed camera
    local n = tonumber(name:sub(5)); local cp = F6CAM[n]
    pos = c.position + c.side * cp.p[1] + c.up * cp.p[2] + c.look * cp.p[3]
    look = norm({c.side.x*cp.f[1] + c.up.x*cp.f[2] + c.look.x*cp.f[3], c.side.y*cp.f[1] + c.up.y*cp.f[2] + c.look.y*cp.f[3], c.side.z*cp.f[1] + c.up.z*cp.f[2] + c.look.z*cp.f[3]})
    centre = vec3(pos.x + look[1], pos.y + look[2], pos.z + look[3])
  elseif name == 'cockdown' or name == 'eyedown' then   -- from the driver's eye position, car heading, pitched 35 deg down (shows the steering wheel)
    pos = eyeWorld(c)
    local cp, sp = math.cos(math.rad(35)), math.sin(math.rad(35))
    look = norm({c.look.x*cp - c.up.x*sp, c.look.y*cp - c.up.y*sp, c.look.z*cp - c.up.z*sp})
    centre = vec3(pos.x + look[1], pos.y + look[2], pos.z + look[3])
  else
    pos, centre = viewPose(name, c)
    look = norm({centre.x-pos.x, centre.y-pos.y, centre.z-pos.z})
  end
  local side = norm(cross({0, 1, 0}, look))
  local up = cross(look, side)
  local t = grabbed.transform
  local ok = pcall(function()
    t.position:set(pos); t.look:set(vec3(look[1], look[2], look[3]))
    t.side:set(vec3(side[1], side[2], side[3])); t.up:set(vec3(up[1], up[2], up[3]))
    grabbed.transform = t
  end)
  if not ok then grabbed.transform = mat4x4.look(pos, centre - pos, vec3(0, 1, 0)) end
  grabbed.fov = (CARCAM[name] and CARCAM[name].fov) or (name == 'cockdown' or name == 'eyedown') and 70 or ((name == 'mirrorR' or name == 'mirrorL') and 20 or 60)   -- 60 = FOV of F6 cameras 3/4
  local ok2, tt = pcall(function() local m = grabbed.transform
    return {look=m.look, up=m.up, side=m.side} end)
  return pos, (ok2 and tt or nil), look, up
end
local function releaseCamera() if grabbed then pcall(function() grabbed:dispose() end); grabbed = nil end end
-- Hide the same driver nodes as driver3d.ini HIDE_OBJECT for the 'eyedown' shot (CSP scene API: ac.findNodes / ac.findMeshes return an
-- ac.SceneReference with :size() and :setVisible()). ':' may be read as a filter key by CSP, so '?' (single-character wildcard, which hit
-- in an earlier CSP Lua probe where '*' did not) is tried as well; the multi-material head meshes are kind-1 nodes with _SUBn meshes.
-- Every attempt and its count is logged; nothing found or no API -> HIDE_UNAVAILABLE. Visibility is restored right after the shot.
local HIDE_NAMES = {'GEO_Driver_FACE', 'HAIR', 'CAP', 'NECK'}   -- the same list as tools/driver.py HIDE. Face/hair/cap are kind-1 nodes with kind-2 meshes <name>_SUB0, _SUB1; NECK (neck skin) is a single kind-2 mesh under RIG_Head (was the skinned BODY_SUB3, which HIDE_OBJECT could not hide)
local HIDE_MAX = 8                                        -- more matches than this for one filter are logged, not hidden
local hiddenRefs = nil
local function hideDriverHead(hide)
  if hide then
    if hiddenRefs then return end
    hiddenRefs = {}
    local notes, total = {}, 0
    local function try(label, finder)
      local ok, ref = pcall(finder)
      local cnt = 0
      if ok and ref then pcall(function() cnt = ref:size() end) end
      if cnt > HIDE_MAX then notes[#notes + 1] = string.format('%s=%d TOO_MANY_NOT_HIDDEN', label, cnt); return end   -- a filter read differently could match the whole scene
      if cnt > 0 and pcall(function() ref:setVisible(false) end) then hiddenRefs[#hiddenRefs + 1] = ref; total = total + cnt end
      notes[#notes + 1] = string.format('%s=%s', label, ok and tostring(cnt) or 'err')
    end
    for _, n in ipairs(HIDE_NAMES) do
      for _, pat in ipairs({'DRIVER:'..n, 'DRIVER?'..n}) do
        try('nodes('..pat..')', function() return ac.findNodes(pat) end)
        try('meshes('..pat..')', function() return ac.findMeshes(pat) end)
        try('meshes('..pat..'_SUB?)', function() return ac.findMeshes(pat..'_SUB?') end)
      end
    end
    if total == 0 then      -- not found in the global search: search under the car's own root
      for _, n in ipairs(HIDE_NAMES) do
        local pat = 'DRIVER?'..n
        try('car.nodes('..pat..')', function() return ac.findNodes('carRoot:0'):findNodes(pat) end)
        try('car.meshes('..pat..'_SUB?)', function() return ac.findNodes('carRoot:0'):findMeshes(pat..'_SUB?') end)
      end
    end
    record('eyedown hide found='..total..' refs='..#hiddenRefs..(total == 0 and ' HIDE_UNAVAILABLE' or '')..' '..table.concat(notes, ' '))
  else
    if not hiddenRefs then return end
    local n = 0
    for _, ref in ipairs(hiddenRefs) do if pcall(function() ref:setVisible(true) end) then n = n + 1 end end
    record(string.format('eyedown restore %d/%d', n, #hiddenRefs)); hiddenRefs = nil
  end
end
local function startShots(label, cams) if not shotJob then shotJob = {label=label, cams=cams or CAMS, single=(cams ~= nil and #cams == 1), i=0, wait=0, pending=false, age=0} end end
local function stepShots(dt, c)
  local j = shotJob; if not j then return end
  j.age = j.age + dt
  if j.age > SHOT_TIMEOUT * #j.cams then record('shots aborted '..j.label); hideDriverHead(false); releaseCamera(); shotJob = nil; return end
  if j.pending then return end
  if not j.cam then
    j.i = j.i + 1
    if j.i > #j.cams then releaseCamera(); shotJob = nil; return end
    j.cam = j.cams[j.i]; j.wait = 0.6; j.phaseWait = 0; j.camPos = nil; j.camTT = nil; j.camLook = nil; j.camUp = nil
    local ok, err = pcall(setCamera, j.cam, c); if not ok then record('camerr '..j.cam..' '..tostring(err)) end
    if j.cam == 'eyedown' then local okh, errh = pcall(hideDriverHead, true); if not okh then record('eyedown hide err '..tostring(errh)..' HIDE_UNAVAILABLE') end end
  end
  if not NATIVE[j.cam] then local ok, pos, tt, lk, upv = pcall(externalCam, j.cam, c); if ok and pos then j.camPos = pos; j.camTT = tt; j.camLook = lk; j.camUp = upv end end
  if hiddenRefs then for _, ref in ipairs(hiddenRefs) do pcall(function() ref:setVisible(false) end) end end   -- re-apply every frame in case AC restores visibility
  j.wait = j.wait - dt
  -- run circleramp_drift_20261126_104809: setCurrentCarCamera right after switching the mode stayed at index 0, so keep re-applying while waiting
  if j.wait > 0 then if NATIVE[j.cam] and j.cam ~= 'cockpit' then pcall(setCamera, j.cam, c) end; return end
  if hazards and not c.turningLightsActivePhase and j.phaseWait < 1.5 then j.phaseWait = j.phaseWait + dt; return end
  j.pending = true
  local name = j.single and j.label or string.format('%s_%s', j.label, j.cam)
  local camName = j.cam
  local ok, err = pcall(ac.makeScreenshot, output..'cap_'..runTag..'_'..name..'.png', {format=ac.ScreenshotFormat.PNG, accumulation=false}, function(e)
    local cp = j.camPos or ac.getCameraPosition()
    local extra = string.format(' steer_deg=%.1f', (ac.getCar(0) or c).steer)
    if hazards then pcall(function() local cc = ac.getCar(0) or c; extra = extra..string.format(' hazard=%s phase=%s', tostring(cc.hazardLights), tostring(cc.turningLightsActivePhase)) end) end
    if NATIVE[camName] then pcall(function() local sm = ac.getSim(); extra = extra..string.format(' mode=%s car_cam=%s drv_cam=%s car_cams=%s', tostring(sm.cameraMode), tostring(sm.carCameraIndex), tostring(sm.driveableCameraMode), tostring((ac.getCar(0) or c).carCamerasCount)) end) end
    if camName == 'cockpit' then cockpitPos = vec3(cp.x, cp.y, cp.z)
      local d = (cockpitPos - eyeWorld(ac.getCar(0) or c)):length()
      extra = extra..string.format(' eye_off=%.2f%s', d, d > 0.5 and ' WARN_NOT_COCKPIT' or '') end
    if j.camLook then extra = extra..string.format(' set_look=%.3f,%.3f,%.3f set_up=%.3f,%.3f,%.3f', j.camLook[1], j.camLook[2], j.camLook[3], j.camUp[1], j.camUp[2], j.camUp[3]) end
    if j.camTT then pcall(function() extra = extra..string.format(' got_look=%.3f,%.3f,%.3f got_up=%.3f,%.3f,%.3f', j.camTT.look.x, j.camTT.look.y, j.camTT.look.z, j.camTT.up.x, j.camTT.up.y, j.camTT.up.z) end) end
    record(string.format('saved %s err=%s cam=%.2f,%.2f,%.2f car=%.2f,%.2f,%.2f%s', name, tostring(e), cp.x, cp.y, cp.z, c.position.x, c.position.y, c.position.z, extra))
    if camName == 'eyedown' then pcall(hideDriverHead, false) end
    if not NATIVE[camName] then releaseCamera() end      -- AC's own camera shots must not be taken through the grabbed camera
    j.pending = false; j.cam = nil end)
  if not ok then
    record('shoterr '..name..' '..tostring(err))
    if camName == 'eyedown' then pcall(hideDriverHead, false) end
    if not NATIVE[camName] then releaseCamera() end
    j.pending = false; j.cam = nil
  end
end

-- Gear convention (CSP): car.gear 0 = neutral, -1 = reverse, 1 = first (does not pass through 0 on sequential shifts);
-- car.engagedGear is the same numbering but does pass through 0 while shifting. reqGear is what this probe last asked for (gear +/- 1).
local reqGear = 0
local function wheelCols(w, tyreSign)
  local ok, str = pcall(function()
    return string.format('%.3f,%.4f,%.3f,%.0f', w.angularSpeed * w.tyreRadius * 3.6, w.slipRatio, w.slipAngle, w.load) end)
  return ok and str or 'nan,nan,nan,nan'
end
local function frontSteerDeg(c)   -- actual front wheel yaw relative to the car body (deg, + = to the left of travel), mean of both front wheels
  local function yaw(v) return math.atan2(v.x, v.z) end
  local d = 0
  for i = 0, 1 do
    local a = yaw(c.wheels[i].look) - yaw(c.look)
    a = math.atan2(math.sin(a), math.cos(a)); d = d + a
  end
  return math.deg(d / 2)
end

local function sample(c, t)
  local roll = math.deg(math.atan2(c.side.y, c.up.y))
  local pitch = math.deg(math.asin(math.max(-1, math.min(1, c.look.y))))
  local base = string.format('%.2f,%.3f,%.3f,%.3f,%.2f,%.0f,%d,%.3f,%.3f', t, c.position.x, c.position.y, c.position.z, c.speedKmh, c.rpm, c.gear, roll, pitch)
  local okx, ext = pcall(function()
    local cam = ac.getCameraPosition()
    return string.format('%.3f,%.3f,%.3f,%.3f,%d,%d,%.2f,%.2f,%.2f,%.2f,%.2f', c.gas, c.brake, c.clutch, c.handbrake, reqGear, c.engagedGear, c.steer, frontSteerDeg(c), cam.x, cam.y, cam.z)
  end)
  if not okx then ext = 'nan,nan,nan,nan,0,0,nan,nan,nan,nan,nan' end
  return base..','..ext..','..wheelCols(c.wheels[0])..','..wheelCols(c.wheels[1])..','..wheelCols(c.wheels[2])..','..wheelCols(c.wheels[3])
end

-- Manual driving for accel / circle (run 7 showed the autopilot holds the brake at 1.0 and overrides gas, so it cannot measure the car).
local lastPulse = -10
local function shiftLogic(ctl, c, upRpm)
  if elapsed - lastPulse < 0.8 then return end
  if c.gear < 1 then ctl.gearUp = true; reqGear = c.gear + 1; lastPulse = elapsed
  elseif c.rpm > upRpm and c.gear < 6 then ctl.gearUp = true; reqGear = c.gear + 1; lastPulse = elapsed
  elseif c.rpm < 900 and c.gear > 1 and c.speedKmh > 1 then ctl.gearDown = true; reqGear = c.gear - 1; lastPulse = elapsed end
end
local function accelControl(c)
  local ctl = ac.overrideCarControls(0); if not ctl then return end
  ctl.combineAxis = false
  ctl.steer = 0; ctl.gas = 1.0; ctl.brake = 0
  shiftLogic(ctl, c, 2300)
end
-- circle: phase A = straight full-throttle run to 45 km/h (gives 0-40 km/h time and rpm), phase B = slow down to ~10 km/h, then full lock.
-- phase Z (first, standing still with the brake on): steer 0, hold 2.5 s, shoot 'still' (DRV_SHOTS). The generic 'still' shots are not
-- taken in circle mode: they ran into phase S and were logged at steer_deg=90 (run circle_drift_20261126_152034).
-- phase S (then, still braked): steer 0.1 = 90 deg of wheel to the right, hold 2.5 s, shoot 'steer90' (DRV_SHOTS).
-- Full lock is 900 deg = 2.5 turns, which looks the same either way round, so the wheel's direction is judged from this shot
-- (steer > 0 turns right: run 100217 front_steer_deg = -52.4 at steer 900; the wheel must then turn clockwise as the driver sees it).
local phase = 'Z'
local phaseBT
local sShot = false
local sT = 0
local function circleControl(c)
  local ctl = ac.overrideCarControls(0)
  if not ctl then return end
  ctl.combineAxis = false
  local kmh = c.speedKmh
  if phase == 'Z' then
    ctl.steer = 0; ctl.gas = 0; ctl.brake = 1
    if not sShot and not shotJob and elapsed - driveStart >= 2.5 then sShot = true; startShots('still', DRV_SHOTS)
    elseif sShot and not shotJob then phase = 'S'; sT = elapsed; driveStart = elapsed; sShot = false; record('phase Z done') end
    return
  end
  if phase == 'S' then
    ctl.steer = 0.1; ctl.gas = 0; ctl.brake = 1
    if not sShot and not shotJob and elapsed - sT >= 2.5 then sShot = true; startShots('steer90', DRV_SHOTS)
    elseif sShot and not shotJob then phase = 'S2'; sT = elapsed; driveStart = elapsed; sShot = false; record('phase S done') end
    return
  end
  -- S2: the same at 90 deg to the LEFT (steer -0.1), so the driver's hands can be judged at 0 / +90 / -90 (original driver, Task 8)
  if phase == 'S2' then
    ctl.steer = -0.1; ctl.gas = 0; ctl.brake = 1
    if not sShot and not shotJob and elapsed - sT >= 2.5 then sShot = true; startShots('steerm90', DRV_SHOTS)
    elseif sShot and not shotJob then phase = 'A'; driveStart = elapsed; record('phase S2 done') end
    return
  end
  if phase == 'A' and (kmh >= 45 or elapsed - driveStart > 25) then phase = 'B'; phaseBT = elapsed; record('phase B at '..string.format('%.1f', elapsed - driveStart)) end
  if phase == 'A' then
    ctl.steer = 0; ctl.gas = 1.0; ctl.brake = 0
  else
    ctl.steer = (kmh < 13) and 1.0 or 0           -- full lock only once slow (the steer value is -1..1)
    ctl.gas = kmh < 10 and 0.35 or 0
    ctl.brake = kmh > 12 and 0.5 or 0
  end
  shiftLogic(ctl, c, 2300)
end

-- skidpad (design §8-5, second half): hold a 20 m radius with steering feedback while the target speed rises 1 km/h every 3 s,
-- until the bus slides (measured radius > 1.25 x 20 m for 2 s), an inner wheel unloads (< 500 N) or it rolls > 8 deg.
-- Every 0.5 s a 'skid' line logs speed, measured radius (v / yaw rate), lateral g (v x yaw rate / g), steer and the smallest wheel load.
-- steer > 0 turns right (run 100217); feedforward 0.28 = atan(5.3 / 20) / 52.4 deg (front wheel angle at full lock).
-- Run skidpad_nevadadrift_102630: a right-hand circle from the pit spot ran into the platform kerb and bollards on the right.
-- So: drive straight 25 m first, then circle LEFT (SKID_DIR -1); the circle then stays ahead-left of the start spot.
local SKID_R, SKID_DIR, SKID_STRAIGHT = 20, -1, 25
local skid = {straight = true, target = 12, lastUp = 0, slideT = 0, done = false, lastLog = -1, peak = 0, peakAt = ''}
-- yaw rate from the change of heading (c.look), smoothed over ~0.3 s; independent of which angular-velocity fields CSP exposes
local lastYaw, yawRateS = nil, 0
local function yawRate(c, dt)
  local y = math.atan2(c.look.x, c.look.z)
  if lastYaw and dt > 0 then
    local d = math.atan2(math.sin(y - lastYaw), math.cos(y - lastYaw)) / dt
    local a = math.min(1, dt / 0.3); yawRateS = yawRateS + a * (d - yawRateS)
  end
  lastYaw = y
  return yawRateS
end
local function skidpadControl(c, dt)
  local ctl = ac.overrideCarControls(0); if not ctl then return end
  ctl.combineAxis = false
  local v = c.speedKmh / 3.6
  local w = math.abs(yawRate(c, dt))
  local rMeas = (w > 0.02 and v > 1) and v / w or 999
  local latg = v * w / 9.81
  local minLoad = math.huge
  for i = 0, 3 do minLoad = math.min(minLoad, c.wheels[i].load) end
  local roll = math.abs(math.deg(math.atan2(c.side.y, c.up.y)))
  if skid.done then ctl.steer = 0; ctl.gas = 0; ctl.brake = 0.6; return end
  skid.p0 = skid.p0 or vec3(c.position.x, c.position.y, c.position.z)
  if skid.straight then
    ctl.steer = 0; ctl.gas = c.speedKmh < 12 and 0.5 or 0.2; ctl.brake = 0; shiftLogic(ctl, c, 2300)
    if (c.position - skid.p0):length() >= SKID_STRAIGHT then skid.straight = false; record('skid circle start') end
    return
  end
  -- steering: feedforward + feedback on curvature error
  local k = 1 / SKID_R - ((rMeas < 900) and 1 / rMeas or 0)
  ctl.steer = SKID_DIR * math.max(0, math.min(1, 0.28 + 6.0 * k))
  -- speed: ramp the target, P control on gas/brake
  if elapsed - skid.lastUp >= 3 and math.abs(c.speedKmh - skid.target) < 2 then skid.target = skid.target + 1; skid.lastUp = elapsed end
  local e = skid.target - c.speedKmh
  ctl.gas = math.max(0, math.min(1, 0.25 + 0.15 * e)); ctl.brake = e < -3 and 0.2 or 0
  shiftLogic(ctl, c, 2300)
  if v > 4 and rMeas < 900 then
    if latg > skid.peak and math.abs(rMeas - SKID_R) < 0.25 * SKID_R then skid.peak = latg; skid.peakAt = string.format('%.1f km/h R=%.1f', c.speedKmh, rMeas) end
  end
  if v > 4 and math.abs(rMeas - SKID_R) < 0.25 * SKID_R then skid.locked = true end   -- slide is judged only after the circle has settled once
  skid.slideT = (skid.locked and rMeas > 1.25 * SKID_R and v > 4) and skid.slideT + dt or 0
  local why = (skid.slideT > 2 and 'slide') or (v > 4 and minLoad < 500 and 'wheel_unloaded') or (roll > 8 and 'roll') or nil
  if elapsed - skid.lastLog >= 0.5 or why then skid.lastLog = elapsed
    record(string.format('skid t=%.1f kmh=%.1f target=%d R=%.1f latg=%.3f steer=%.3f minload=%.0f roll=%.2f', elapsed - driveStart, c.speedKmh, skid.target, rMeas, latg, ctl.steer, minLoad, roll)) end
  if why then skid.done = true; record(string.format('skid limit %s peak_latg=%.3f at %s', why, skid.peak, skid.peakAt)) end
end

-- circleramp (user decision 2026-11-26, stand-in for design §8-5 second half): no safe 20 m pad was found, so on 'drift' the proven
-- circle route is kept (straight, slow down, full lock right) and, 12 s after full lock, the target speed rises 1 km/h every 3 s
-- until the bus slides (radius > 1.25 x the radius at ramp start for 2 s), an inner wheel unloads (< 500 N) or it rolls > 8 deg.
-- The CG radius at full lock is ~5.8 m, not 20 m: this measures the lateral limit at a much smaller radius.
local ramp = {target = 10, lastUp = 0, slideT = 0, unloadT = 0, done = false, lastLog = -1, peak = 0, peakAt = '', r0 = nil, t0 = nil}
local function rampControl(c, dt)
  local ctl = ac.overrideCarControls(0); if not ctl then return end
  ctl.combineAxis = false
  local v = c.speedKmh / 3.6
  local w = math.abs(yawRate(c, dt))
  local rMeas = (w > 0.02 and v > 1) and v / w or 999
  local latg = v * w / 9.81
  local minLoad = math.huge
  for i = 0, 3 do minLoad = math.min(minLoad, c.wheels[i].load) end
  local roll = math.abs(math.deg(math.atan2(c.side.y, c.up.y)))
  if ramp.done then ctl.steer = 1; ctl.gas = 0; ctl.brake = 0.6; return end
  ctl.steer = 1
  -- run 104809: R0 taken on the first frame was 126 m (yaw-rate filter not settled); take it after 2 s of holding the circle
  ramp.t0 = ramp.t0 or elapsed
  if not ramp.r0 then
    ctl.gas = c.speedKmh < 10 and 0.35 or 0; ctl.brake = 0
    if elapsed - ramp.t0 >= 2 and rMeas < 900 then ramp.r0 = rMeas; ramp.lastUp = elapsed; record(string.format('ramp start R0=%.2f', ramp.r0)) end
    return
  end
  if elapsed - ramp.lastUp >= 3 and math.abs(c.speedKmh - ramp.target) < 1.5 then ramp.target = ramp.target + 1; ramp.lastUp = elapsed end
  local e = ramp.target - c.speedKmh
  ctl.gas = math.max(0, math.min(1, 0.3 + 0.15 * e)); ctl.brake = e < -3 and 0.2 or 0
  shiftLogic(ctl, c, 2300)
  local onCircle = rMeas < 1.25 * ramp.r0
  if v > 2 and onCircle and latg > ramp.peak then ramp.peak = latg; ramp.peakAt = string.format('%.1f km/h R=%.2f', c.speedKmh, rMeas) end
  ramp.slideT = (not onCircle and v > 2) and ramp.slideT + dt or 0
  -- a single-sample zero load is a kerb hit on 'drift' (run 104809); an inner wheel counts as lifted only after 0.5 s below 500 N
  ramp.unloadT = (v > 2 and minLoad < 500) and ramp.unloadT + dt or 0
  local why = (ramp.slideT > 2 and 'slide') or (ramp.unloadT > 0.5 and 'wheel_unloaded') or (roll > 8 and 'roll') or nil
  if elapsed - ramp.lastLog >= 0.5 or why then ramp.lastLog = elapsed
    record(string.format('skid t=%.1f kmh=%.1f target=%d R=%.2f latg=%.3f steer=%.3f minload=%.0f roll=%.2f', elapsed - driveStart, c.speedKmh, ramp.target, rMeas, latg, ctl.steer, minLoad, roll)) end
  if why then ramp.done = true; record(string.format('skid limit %s peak_latg=%.3f at %s', why, ramp.peak, ramp.peakAt)) end
end

function script.update(dt)
  if not enabled or done then return end
  elapsed = elapsed + dt
  local c = ac.getCar(0)
  if not c then return end
  if elapsed > duration + WAIT + 180 then record('timeout'); finish(); return end   -- standing phases (Z, S, S2) and the end shots need ~90 s on top of duration
  if elapsed - lastLog >= 0.1 then lastLog = elapsed
    local ok, line = pcall(sample, c, elapsed); csv(ok and line or ('err,'..tostring(line)))
  end
  if elapsed - (lastDbg or -1) >= 0.5 then lastDbg = elapsed
    pcall(function() local w2, w0 = c.wheels[2], c.wheels[0]
      record(string.format('dbg %.1f gas=%.2f brk=%.2f clu=%.2f hb=%.2f rr_slip=%.3f rr_w=%.1f fr_w=%.1f rr_load=%.0f fr_load=%.0f brkT=%.0f',
        elapsed, c.gas, c.brake, c.clutch, c.handbrake, w2.slipRatio, w2.angularSpeed, w0.angularSpeed, w2.load, w0.load, w2.brakeTemperature)) end) end
  if elapsed - (lastFlags or -9) >= 2 then lastFlags = elapsed
    pcall(function() record(string.format('flags %.1f pitLimiter=%s inPitlane=%s engLimiterOn=%s autoClutch=%s speedLimiter=%s userLimiter=%s gear=%d engaged=%d headlights=%s lowBeams=%s hour=%s hazard=%s',
      elapsed, tostring(c.speedLimiterInAction), tostring(c.isInPitlane), tostring(c.isEngineLimiterOn), tostring(c.autoClutch), tostring(c.speedLimiter), tostring(c.userSpeedLimiterEnabled), c.gear, c.engagedGear, tostring(c.headlightsActive), tostring(c.lowBeams), tostring((ac.getSim() or {}).timeHours), tostring(c.hazardLights))) end) end
  if night and elapsed - (lastLights or -9) >= 1 and not c.headlightsActive then lastLights = elapsed; pcall(ac.setHeadlights, true) end
  if hazards and elapsed - (lastHaz or -9) >= 1 and not c.hazardLights then lastHaz = elapsed
    local ok, err = pcall(function() ac.setTurningLights(ac.TurningLights.Hazards) end); if not ok then record('hazard err '..tostring(err)) end end
  if not started then
    local circleMode = (mode == 'circle' or mode == 'circleramp')     -- circle mode shoots 'still' itself at steer 0 (phase Z)
    if elapsed > 3 and not nextShot and not circleMode then nextShot = 'still'; startShots('still') end
    if elapsed > WAIT then
      started = true; driveStart = elapsed; nextShot = 30
      ac.tryToStart(true)
      if mode == 'drive' then local ok, err = pcall(function() physics.setCarAutopilot(true) end); record('autopilot '..tostring(ok)..' '..tostring(err)) end
    end
    stepShots(dt, c); return
  end
  if mode == 'circle' or mode == 'circleramp' then
    local f = (mode == 'circleramp' and phase == 'B' and phaseBT and elapsed - phaseBT >= 12) and rampControl or circleControl
    local ok, err = pcall(f, c, dt); if not ok then record('ctlerr '..tostring(err)) end
  end
  if mode == 'accel' then local ok, err = pcall(accelControl, c); if not ok then record('ctlerr '..tostring(err)) end end
  if mode == 'skidpad' then local ok, err = pcall(skidpadControl, c, dt); if not ok then record('ctlerr '..tostring(err)) end end
  stepShots(dt, c)
  local t = elapsed - driveStart    -- read after the controls: circle resets driveStart after each standing phase (Z, S, S2), so the 30 s shots and the end never start while standing
  if not shotJob and not endShot and t >= nextShot and t < duration then startShots(string.format('t%03d', nextShot)); nextShot = nextShot + 30 end
  if t > duration and not shotJob then
    if not endShot then endShot = true; startShots('end') else finish() end
  end
end
