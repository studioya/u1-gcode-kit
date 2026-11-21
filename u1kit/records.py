"""Load printer, spool and material records into writer objects.

records/
  printer/u1.yaml          measured machine values (feed factors, offsets checks, shaper)
  spools/<id>.yaml         one physical spool: brand, lot, measured diameter, weighed g/m, density
  materials/<id>.yaml      tuned settings for a material+brand(+colour); points at a spool
  pairs/<a>__<b>.yaml      what we learned about printing two materials together
"""
from __future__ import annotations
import os
import yaml

from .writer import Material

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "records")


def _load(sub, name):
    path = os.path.join(ROOT, sub, f"{name}.yaml")
    with open(path) as f:
        return yaml.safe_load(f) or {}


def printer():
    return _load("printer", "u1")


def feed_factors():
    heads = (printer().get("heads") or {})
    out = {}
    for t, h in heads.items():
        ff = (h or {}).get("feed_factor")
        out[int(t)] = float(ff) if ff else 1.0
    return out


def material(mat_id: str) -> Material:
    d = _load("materials", mat_id)
    s = d.get("settings", {}) or {}
    m = Material(name=d.get("name", mat_id), type=d.get("type", "PLA"),
                 colour=d.get("colour", "#FFFFFF"))
    for k, v in s.items():
        if v is not None and hasattr(m, k):
            setattr(m, k, v)
    spool_id = d.get("spool")
    if spool_id:
        sp = _load("spools", spool_id)
        meas = sp.get("measured", {}) or {}
        if meas.get("density_g_cm3"):
            m.density = float(meas["density_g_cm3"])
        if meas.get("diameter_mean_mm"):
            m.diameter = float(meas["diameter_mean_mm"])
        if meas.get("linear_density_g_m"):
            m.linear_density = float(meas["linear_density_g_m"])
    return m
