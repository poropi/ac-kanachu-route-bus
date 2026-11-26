"""Fit the four fixed, square-pixel photo cameras in native image coordinates."""
import json
import math
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares


def solve(data):
    width, height = data['size']
    controls = data.get('calibration_points',data['points'])
    xyz = np.float64([p[1] for p in controls])
    uv = np.float64([p[2] for p in controls])
    def intrinsic(focal):
        return np.array([[focal, 0., width / 2], [0., focal, height / 2], [0., 0., 1.]])
    def residual(params):
        xy, _ = cv2.projectPoints(xyz, params[:3], params[3:6], intrinsic(math.exp(params[6])), None)
        return (xy[:, 0] - uv).ravel()
    lo, hi = data['focal_bounds']
    limits = ([-np.inf]*6+[math.log(lo)], [np.inf]*6+[math.log(hi)])
    best = None
    for focal in np.geomspace(lo*1.001, hi*.999, 8):
        ok, rot, trans = cv2.solvePnP(xyz, uv, intrinsic(focal), None, flags=cv2.SOLVEPNP_SQPNP)
        if not ok:
            continue
        fit = least_squares(residual, np.r_[rot.ravel(), trans.ravel(), math.log(focal)],
                            bounds=limits, x_scale='jac', ftol=1e-12, xtol=1e-12, gtol=1e-12)
        rotation = cv2.Rodrigues(fit.x[:3])[0]
        depth = (rotation @ xyz.T).T[:,2] + fit.x[5]
        if min(depth)>0 and (best is None or fit.cost < best.cost):
            best = fit
    if best is None:
        raise ValueError('カメラの前方に対応点が収まりません')
    rotation = cv2.Rodrigues(best.x[:3])[0]
    center = -rotation.T @ best.x[3:6]
    world = np.eye(4)
    world[:3,:3] = rotation.T @ np.diag([1., -1., -1.])
    world[:3,3] = center
    f = math.exp(best.x[6])
    def offsets(points):
        world_points = np.float64([p[1] for p in points])
        image_points = np.float64([p[2] for p in points])
        xy, _ = cv2.projectPoints(world_points,best.x[:3],best.x[3:6],intrinsic(f),None)
        return xy[:,0]-image_points
    errors = offsets(data['points'])
    return dict(world=world.tolist(), focal_px=f, lens_mm=36*f/width,
                delta_before=offsets(data.get('points_before',data['points'])).tolist(),
                delta_px=errors.tolist(), rms=float(np.sqrt(np.mean(np.sum(errors**2, axis=1)))))


if __name__ == '__main__':
    import sys
    for path in sorted(Path(__file__).parent.glob('match_*.json')):
        data = json.loads(path.read_text())
        fit = solve(data)
        key = path.stem.removeprefix('match_')
        print(key, 'f', round(fit['focal_px']), 'C', np.round(np.array(fit['world'])[:3,3],2),
              'RMS', round(fit['rms'],2), np.round(np.linalg.norm(fit['delta_px'],axis=1),1))
        if len(sys.argv)>1:
            (Path(sys.argv[1]) / (key+'.json')).write_text(json.dumps({**data, **fit},ensure_ascii=False,indent=1))
