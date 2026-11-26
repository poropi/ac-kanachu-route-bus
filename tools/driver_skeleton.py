"""運転手の骨組みの定義（骨名の唯一の出どころ）。

kn5 書き出し・座った姿勢（knh）・ハンドルの腕の動き（ksanim）は、すべてここの BONES を使う。
名前と親子は AC 標準の運転手（refs/kunos_driver/driver.kn5）に合わせるための識別子で、
形・行列・動きは写していない。kn5 から自動生成せず、文字で書いてある（kn5 は試験で照合するだけ）。

骨の選び方: 種類 1（ダミー）のノードのうち、
  - 根の `DRIVER:DRIVER`、
  - 名前が `DRIVER:RIG_` で始まるもの（胴・頭・腕・肩・脚）、
  - 名前が `DRIVER:HAND_` で始まるもの（指）
だけを骨とする。`DRIVER:HELMET*`・`DRIVER:GEO_Driver_FACE`・`DRIVER:COLLARE_HANS`・`DRIVER:Gloves`・
`DRIVER:suit` は骨ではなく、メッシュを載せるための入れ物なので含めない。
親は「骨だけをたどった祖先」（kn5 の根 `FBX: ...` は親にしない）。順は親が先。
"""

BONES = [
    ('DRIVER:DRIVER', None),
    ('DRIVER:RIG_Center', 'DRIVER:DRIVER'),
    ('DRIVER:RIG_Hips', 'DRIVER:RIG_Center'),
    ('DRIVER:RIG_Cest', 'DRIVER:RIG_Hips'),
    ('DRIVER:RIG_Nek', 'DRIVER:RIG_Cest'),
    ('DRIVER:RIG_Head', 'DRIVER:RIG_Nek'),
    ('DRIVER:RIG_Clave_L', 'DRIVER:RIG_Cest'),
    ('DRIVER:RIG_Arm_L', 'DRIVER:RIG_Clave_L'),
    ('DRIVER:RIG_ForeArm_L', 'DRIVER:RIG_Arm_L'),
    ('DRIVER:RIG_ForeArm_END_L', 'DRIVER:RIG_ForeArm_L'),
    ('DRIVER:RIG_HAND_L', 'DRIVER:RIG_ForeArm_END_L'),
    ('DRIVER:HAND_L_Thumb1', 'DRIVER:RIG_HAND_L'),
    ('DRIVER:HAND_L_Thumb2', 'DRIVER:HAND_L_Thumb1'),
    ('DRIVER:HAND_L_Thumb3', 'DRIVER:HAND_L_Thumb2'),
    ('DRIVER:HAND_Index1', 'DRIVER:RIG_HAND_L'),
    ('DRIVER:HAND_Index2', 'DRIVER:HAND_Index1'),
    ('DRIVER:HAND_Index3', 'DRIVER:HAND_Index2'),
    ('DRIVER:HAND_Middle1', 'DRIVER:RIG_HAND_L'),
    ('DRIVER:HAND_Middle2', 'DRIVER:HAND_Middle1'),
    ('DRIVER:HAND_Middle3', 'DRIVER:HAND_Middle2'),
    ('DRIVER:HAND_Ring1', 'DRIVER:RIG_HAND_L'),
    ('DRIVER:HAND_Ring2', 'DRIVER:HAND_Ring1'),
    ('DRIVER:HAND_Ring3', 'DRIVER:HAND_Ring2'),
    ('DRIVER:HAND_Pinkie1', 'DRIVER:RIG_HAND_L'),
    ('DRIVER:HAND_Pinkie2', 'DRIVER:HAND_Pinkie1'),
    ('DRIVER:HAND_Pinkie3', 'DRIVER:HAND_Pinkie2'),
    ('DRIVER:RIG_Shoulder_L', 'DRIVER:RIG_Clave_L'),
    ('DRIVER:RIG_Clave_R', 'DRIVER:RIG_Cest'),
    ('DRIVER:RIG_Arm_R', 'DRIVER:RIG_Clave_R'),
    ('DRIVER:RIG_ForeArm_R', 'DRIVER:RIG_Arm_R'),
    ('DRIVER:RIG_ForeArm_END_R', 'DRIVER:RIG_ForeArm_R'),
    ('DRIVER:RIG_HAND_R', 'DRIVER:RIG_ForeArm_END_R'),
    ('DRIVER:HAND_R_Thumb1', 'DRIVER:RIG_HAND_R'),
    ('DRIVER:HAND_R_Thumb2', 'DRIVER:HAND_R_Thumb1'),
    ('DRIVER:HAND_R_Thumb3', 'DRIVER:HAND_R_Thumb2'),
    ('DRIVER:HAND_Index4', 'DRIVER:RIG_HAND_R'),
    ('DRIVER:HAND_Index5', 'DRIVER:HAND_Index4'),
    ('DRIVER:HAND_Index6', 'DRIVER:HAND_Index5'),
    ('DRIVER:HAND_Middle4', 'DRIVER:RIG_HAND_R'),
    ('DRIVER:HAND_Middle5', 'DRIVER:HAND_Middle4'),
    ('DRIVER:HAND_Middle6', 'DRIVER:HAND_Middle5'),
    ('DRIVER:HAND_Ring4', 'DRIVER:RIG_HAND_R'),
    ('DRIVER:HAND_Ring5', 'DRIVER:HAND_Ring4'),
    ('DRIVER:HAND_Ring6', 'DRIVER:HAND_Ring5'),
    ('DRIVER:HAND_Pinkie4', 'DRIVER:RIG_HAND_R'),
    ('DRIVER:HAND_Pinkie5', 'DRIVER:HAND_Pinkie4'),
    ('DRIVER:HAND_Pinkie6', 'DRIVER:HAND_Pinkie5'),
    ('DRIVER:RIG_Shoulder_R', 'DRIVER:RIG_Clave_R'),
    ('DRIVER:RIG_Leg_L', 'DRIVER:RIG_Center'),
    ('DRIVER:RIG_Shin_L', 'DRIVER:RIG_Leg_L'),
    ('DRIVER:RIG_Hill_L', 'DRIVER:RIG_Shin_L'),
    ('DRIVER:RIG_Foot_L', 'DRIVER:RIG_Hill_L'),
    ('DRIVER:RIG_Leg_R', 'DRIVER:RIG_Center'),
    ('DRIVER:RIG_Shin_R', 'DRIVER:RIG_Leg_R'),
    ('DRIVER:RIG_Hill_R', 'DRIVER:RIG_Shin_R'),
    ('DRIVER:RIG_Foot_R', 'DRIVER:RIG_Hill_R'),
]

# 頭の骨 `DRIVER:RIG_Head` に骨で親子付けする固定メッシュ（運転席の視点から隠す対象）
HEAD_MESHES = ("DRIVER:GEO_Driver_FACE", "DRIVER:HAIR", "DRIVER:CAP")
# 骨で動くメッシュ（Armature モディファイアと、骨名の頂点グループを持つ）
SKINNED_MESHES = ("DRIVER:BODY", "DRIVER:GLOVES")
# 首の肌（2026-11-26、ユーザー判断）: NECK_SOURCE のうちマテリアル名が NECK_MATERIAL_PREFIX で始まる面を、書き出しで骨で動くメッシュから外し、
# 頭の骨に付いた固定メッシュ NECK_MESH（種類 2。複数マテリアルなら種類 1 + _SUBn）にする。driver3d.ini の HIDE_OBJECT は骨で動く
# メッシュ（種類 3、前の DRIVER:BODY_SUB3）を隠せなかった（試走のユーザーの画面）ので、頭と同じ固定メッシュにして運転席の視点から隠す。
# .blend の作り（首の肌は DRIVER:BODY の一部で、重みは RIG_Cest・RIG_Nek）は変えない。
NECK_SOURCE = "DRIVER:BODY"
NECK_MATERIAL_PREFIX = "driver_neck"
NECK_MESH = "DRIVER:NECK"

# AC が driver3d.ini の [HEAD_MOVEMENT] で回す首の骨と、その子の頭の骨のレストの向き（2026-11-26、ユーザー判断）。
# AC は DRIVER:RIG_Nek をそのローカルの軸のまわりに回す（Y = ヨー、Z = 前、X = +x = 運転手の左。Kunos の運転手は首が Y 上・Z 前、
# 頭がほぼ単位）。Blender の骨はローカル Y が骨の向きなので、そのままでは AC の「ヨー」が首の左右の傾きになった（試走で確認）。
# そこで kn5 の書き出し（tools/driver_to_kn5.py）で 2 本とも世界の回転を単位行列にする（位置はそのまま）。
# 座った姿勢では首は上体と一緒に前傾するので、ヨーの軸は鉛直から前傾の分（約 5°）だけ前へ倒れる（Kunos の首の約 14° を足すより鉛直に近い）。逆バインド行列・子の骨の相対行列・頭のメッシュの頂点は
# この向きから計算するので、どの姿勢でも頂点の世界位置は変わらない（knh・ksanim は世界の向きの差で解くので自動でこの向きに合う）。
AC_AXES_BONES = ("DRIVER:RIG_Nek", "DRIVER:RIG_Head")
