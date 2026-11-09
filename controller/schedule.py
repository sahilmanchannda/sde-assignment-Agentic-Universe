"""Per-cohort call-time planner. Pure functions: counts in, proposed config out.

Only age-band cohorts for now. A cohort gets its own hour table only when its best slot
beats its worst slot significantly; otherwise it stays on the flat default table.
"""
from __future__ import annotations

import copy

from controller.cohorts import Cohort
from controller.stats import benjamini_hochberg, two_prop_test

SLOTS = (("morning", 0, 13), ("midday", 13, 17), ("evening", 17, 24))
CAP = (0.5, 2.0)


def slot_of(hour: int) -> str:
    return next(n for n, lo, hi in SLOTS if lo <= hour < hi)


def plan(by_band: dict, hours: list[int], *, prior: int = 200, min_dials: int = 300,
         q: float = 0.05) -> dict:
    """by_band: {band: {hour: (dials, connected)}} using attempt-1 calls only.
    Returns {band: {"weights": {hour: w}, "evidence": {...}}} for bands worth a table."""
    cands = []
    for band, hmap in by_band.items():
        slots = {n: [0, 0] for n, _, _ in SLOTS}
        for h in hours:
            d, k = hmap.get(h, (0, 0))
            s = slots[slot_of(h)]
            s[0] += d
            s[1] += k
        used = {n: v for n, v in slots.items() if v[0] > 0}
        if len(used) < 2 or any(v[0] < min_dials for v in used.values()):
            continue                                   # not enough data: say nothing
        nall = sum(v[0] for v in used.values())
        pall = sum(v[1] for v in used.values()) / nall
        rate = {n: v[1] / v[0] for n, v in used.items()}
        best, worst = max(rate, key=rate.get), min(rate, key=rate.get)
        t = two_prop_test(used[best][1], used[best][0], used[worst][1], used[worst][0])
        cands.append((band, used, pall, rate, best, worst, min(1.0, t["p"] * 3)))
    keep = benjamini_hochberg([c[-1] for c in cands], q)
    out = {}
    for (band, used, pall, rate, best, worst, p), ok in zip(cands, keep):
        if not ok or pall <= 0:
            continue
        w = {}
        for n, v in used.items():
            shrunk = (v[1] + prior * pall) / (v[0] + prior)
            w[n] = round(min(CAP[1], max(CAP[0], shrunk / pall)), 2)
        weights = {h: w.get(slot_of(h), 1.0) for h in hours}
        out[band] = {"weights": weights,
                     "evidence": {"best": best, "worst": worst, "p_adj": p,
                                  "rates": {n: round(r, 3) for n, r in rate.items()}}}
    return out


def build_config(config: dict, planned: dict, hours: list[int]):
    """Return (new_config, reason). Refuses to touch workflows that already have cohorts."""
    if not planned:
        return None, "no age band shows a significant time-of-day preference"
    if config.get("cohorts"):
        return None, "workflow already has cohorts; merging is not implemented"
    new = copy.deepcopy(config)
    tables = {"default": {str(h): 1 for h in hours}}
    cohorts = []
    for band in sorted(planned):
        c = Cohort.make({"age_band": [band]})
        cohorts.append(c.to_config())
        tables[c.id] = {str(h): w for h, w in planned[band]["weights"].items()}
    new["cohorts"] = cohorts
    new.setdefault("schedule", {})["hour_weights"] = tables
    new["schedule"].setdefault("lead_preferred_hour", {})
    return new, ""