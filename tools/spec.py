"""車の諸元の 1 か所化。値は tools/spec.json（{"v", "src"}）。"""
import json, math
from pathlib import Path

PATH = Path(__file__).resolve().parent / "spec.json"

def load():
    return {k: e["v"] for k, e in json.load(open(PATH)).items()}

def derived(s):
    wb = s["wheelbase"]
    return {
        "tyre_radius": round(s["tyre_diameter"] / 2 + 1e-9, 4),
        "rear_overhang": s["overhang_r"],
        "axle_z_front": wb / 2,
        "axle_z_rear": -wb / 2,
        "steer_angle_deg": math.degrees(math.asin(wb / s["min_turn_radius"])),
    }
