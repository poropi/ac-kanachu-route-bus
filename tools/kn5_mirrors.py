"""バックミラーの鏡面を AC の鏡にする（kn5 を書き出した後の仕上げ）。

AC の決まり（nix_suzuki_swift_sport_ht81s で確認）:
- 鏡面のメッシュのマテリアルは名前 `mirror`（ksPerPixel、テクスチャ無し）。
- data/mirrors.ini に `[MIRROR_n] NAME=<メッシュ名>` で並べる。
- 鏡面の UV は面全体で 0〜1（そこに後ろの景色が貼られる。Swift の主鏡は u 0〜1、v −1〜0）。
- CSP の本物の鏡は extension/ext_config.ini の `[REAL_MIRROR_n]`（n は mirrors.ini の順）。

外装のミラーは鏡面が 5 枚（`Mirror_*_Surface`、元は chrome）。並びは運転席側（右）から。
"""
import numpy as np

# (メッシュ名, CSP の視野 FOV°)。右＝Starboard（運転席側）、左＝Port。kn5 の +x は車の左。
MIRRORS = [
    ("Mirror_Starboard_Main_Surface", 18),       # 右の後写鏡
    ("Mirror_Starboard_Crossview_Surface", 40),  # 右の直前直左確認鏡（下向き・凸面）
    ("Mirror_Port_Long_Surface", 18),            # 左の後写鏡
    ("Mirror_Port_Upper_Surface", 24),           # 左の上の補助鏡
    ("Mirror_Port_Crossview_Surface", 40),       # 左の直前確認鏡（下向き・凸面）
]
NAMES = [n for n, _ in MIRRORS]
MATERIAL = "mirror"


def _local_mats(root):
    """メッシュ名 -> そのメッシュの親までの世界行列（4x4、kn5 は転置して持つ）。"""
    out = {}

    def walk(n, M):
        if n.cls == 1 and n.matrix is not None:
            M = M @ np.array(n.matrix, "f8").reshape(4, 4).T
        if n.cls != 1:
            out.setdefault(n.name, M)
        for c in n.children:
            walk(c, M)
    walk(root, np.eye(4))
    return out


def mirror_uv(pos, normal, up_world=(0.0, 1.0, 0.0)):
    """鏡面の頂点 pos（N×3、世界の向きにそろえた座標）と面の法線 normal から UV（N×2）を作る。
    鏡を正面から見て（視線 = -normal）左→右が u 0→1、上→下が v −1→0（Swift の主鏡と同じ範囲）。"""
    n = np.asarray(normal, "f8"); n = n / np.linalg.norm(n)
    up = np.asarray(up_world, "f8"); up = up - n * (up @ n); up = up / np.linalg.norm(up)
    right = np.cross(-n, up)          # 視線 × 上 = 見る人の右（kn5 は +x が左、+z が前）
    u = pos @ right; v = pos @ up
    u = (u - u.min()) / max(u.max() - u.min(), 1e-9)
    v = (v - v.min()) / max(v.max() - v.min(), 1e-9)
    return np.c_[u, v - 1.0]          # 上端 v=0、下端 v=-1


def apply(root, mirror_matid):
    """MIRRORS のメッシュのマテリアルを mirror にし、UV を貼り直す。見つからない名前のリストを返す。"""
    mats = _local_mats(root)
    found = set()

    def walk(n):
        if n.cls != 1 and n.name in NAMES and len(n.vertices):
            V = np.frombuffer(n.vertices, "<f4").reshape(-1, 11).astype("f8").copy()
            R = mats[n.name][:3, :3]
            P = (R @ V[:, :3].T).T
            Nw = (R @ V[:, 3:6].T).T.mean(0)
            V[:, 6:8] = mirror_uv(P, Nw)
            n.vertices = V.astype("<f4").tobytes()
            n.matid = mirror_matid
            found.add(n.name)
        for c in n.children:
            walk(c)
    walk(root)
    return [x for x in NAMES if x not in found]


def mirrors_ini():
    return "\n".join("[MIRROR_%d]\nNAME=%s\n" % (i, n) for i, n in enumerate(NAMES))


def real_mirrors_ext():
    """CSP の本物の鏡。ROTATION 0,0 は鏡面の向きどおりに映す。FLIP は映りが左右逆ならゲームで直す。"""
    return "\n".join("[REAL_MIRROR_%d]\n; %s\nROTATION=0,0\nFOV=%d\nASPECT_MULT=1.0\nIS_MONITOR=0\nFLIP=0\n" % (i, n, f)
                     for i, (n, f) in enumerate(MIRRORS))
