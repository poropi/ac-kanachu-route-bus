import json
import pytest
import spec

def test_spec_values():
    s = spec.load()
    assert s["length"] == 10.430 and s["wheelbase"] == 5.300
    assert s["track_f"] == 2.065 and s["track_r"] == 1.820
    assert s["mass_vehicle"] == 9790
    d = spec.derived(s)
    assert d["tyre_radius"] == pytest.approx(0.4783, abs=1e-4)
    assert d["steer_angle_deg"] == pytest.approx(39.68, abs=0.05)
    assert d["axle_z_front"] == pytest.approx(2.65) and d["axle_z_rear"] == pytest.approx(-2.65)
    assert d["rear_overhang"] == 2.83

def test_every_value_has_src():
    raw = json.load(open(spec.PATH))
    assert raw
    for k, e in raw.items():
        assert e["src"] in ("isuzu_A", "isuzu_kiseki", "calc", "assumption"), k
        assert "v" in e
    for k in ("driver_mass", "hub_mass_f", "hub_mass_r", "brake_split_f", "brake_split_r", "cg_front"):
        assert raw[k]["src"] == "assumption"
