import numpy as np
import pytest

import kn5_axes
import kn5io


def rot_x(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def node(name, M, children=()):
    n = kn5io.Node(1, name, 1, children=list(children))
    n.matrix = tuple(float(x) for x in M.T.ravel())
    return n


def mesh(pts):
    v = np.zeros((len(pts), 11), "<f4")
    v[:, :3] = pts
    v[:, 3:6] = [0, 1, 0]
    v[:, 8:11] = [1, 0, 0]
    n = kn5io.Node(2, "M", 1)
    n.vertices = v.tobytes()
    n.indices = list(range(len(pts)))
    return n


def world(n, M=np.eye(4)):
    if n.cls == 1 and n.matrix is not None:
        M = M @ np.array(n.matrix).reshape(4, 4).T
    if n.cls == 2:
        v = np.frombuffer(n.vertices, "<f4").reshape(-1, 11)
        yield v[:, :3].astype("f8") @ M[:3, :3].T + M[:3, 3]
        yield (v[:, 3:6].astype("f8") @ M[:3, :3].T)
    for c in n.children:
        yield from world(c, M)


def tree(name):
    M = np.eye(4); M[:3, :3] = rot_x(1.0); M[:3, 3] = [0.3, 1.5, 4.4]
    child_m = np.eye(4); child_m[:3, :3] = rot_x(0.4); child_m[:3, 3] = [0.01, 0.02, 0.03]
    pts = np.array([[0, 0, 0], [0.1, 0.02, 0], [0.05, 0.1, 0.01], [0.2, 0.3, 0.5]])
    inner = node("INNER", child_m, [mesh(pts)])
    return node("root", np.eye(4), [node(name, M, [inner, mesh(pts * 2)])])


@pytest.mark.parametrize("name", ["ARROW_SPEED", "ARROW_RPM", "STEER_HR"])
def test_world_unchanged_and_axes_rotated(name):
    a, b = tree(name), tree(name)
    assert kn5_axes.reorient(b) == [name]
    for x, y in zip(world(a), world(b)):
        assert x == pytest.approx(y, abs=1e-5)
    Ma = np.array(a.children[0].matrix).reshape(4, 4).T
    Mb = np.array(b.children[0].matrix).reshape(4, 4).T
    assert np.linalg.det(Mb[:3, :3]) == pytest.approx(1.0)
    if name == "STEER_HR":
        assert Mb[:3, 2] == pytest.approx(Ma[:3, 1])      # 回転軸は古い Y
        assert Mb[:3, 0] == pytest.approx(Ma[:3, 0])
    else:
        assert Mb[:3, 2] == pytest.approx(-Ma[:3, 1])


def test_other_nodes_untouched():
    t = tree("OTHER")
    before = [x.copy() for x in world(t)]
    assert kn5_axes.reorient(t) == []
    for x, y in zip(before, world(t)):
        assert x == pytest.approx(y)
