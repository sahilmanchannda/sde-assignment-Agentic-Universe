"""Caller-ID health detector. Pure functions: counts in, findings out.

No event flags a bad number, so we compare each ID's recent pickup with its own earlier
pickup, standardised to a common age-band mix so a shift in who was dialled isn't mistaken
for a degraded number.
"""
from __future__ import annotations

from controller.stats import two_prop_test

MIN_DIALS = 300     # dials on the recent day before we trust a reading
MIN_DROP = 0.05     # absolute pickup drop worth acting on
ALPHA = 0.01        # one-sided, per ID


def standardized(by_band: dict, mix: dict) -> tuple[float, float, int]:
    """by_band: {band: (dials, connected)}. Returns (pickup, effective_dials, dials)
    weighting each band by its share in `mix` (the workflow-wide dial mix)."""
    rate, var, total = 0.0, 0.0, 0
    for band, share in mix.items():
        d, k = by_band.get(band, (0, 0))
        total += d
        if d == 0:
            continue
        p = k / d
        rate += share * p
        var += share * share * p * (1 - p) / d
    if var <= 0:
        return rate, 0.0, total
    pooled_p = min(max(rate, 1e-6), 1 - 1e-6)
    return rate, pooled_p * (1 - pooled_p) / var, total


def check_caller_ids(recent: dict, baseline: dict, mix: dict, *, min_dials=MIN_DIALS,
                     min_drop=MIN_DROP, alpha=ALPHA) -> list[dict]:
    """recent/baseline: {caller_id: {band: (dials, connected)}}.
    Returns one row per caller ID with enough data, flagged when it degraded."""
    out = []
    for cid, rb in recent.items():
        base = baseline.get(cid)
        if not base:
            continue
        p_new, n_new, d_new = standardized(rb, mix)
        p_old, n_old, d_old = standardized(base, mix)
        if d_new < min_dials or d_old < min_dials or n_new <= 0 or n_old <= 0:
            out.append({"caller_id": cid, "flagged": False, "insufficient": True,
                        "dials": d_new})
            continue
        # one-sided test that the OLD rate is higher: reuse the two-proportion z-test
        # on effective sample sizes
        t = two_prop_test(round(p_old * n_old), round(n_old), round(p_new * n_new), round(n_new))
        drop = p_old - p_new
        out.append({"caller_id": cid, "recent": round(p_new, 4), "baseline": round(p_old, 4),
                    "drop": round(drop, 4), "p": t["p"], "dials": d_new,
                    "flagged": bool(t["p"] < alpha and drop >= min_drop)})
    return out


def healthy_ids(rows: list[dict], options: list[str], current: dict) -> list[str]:
    """IDs we could shift traffic to: in the workflow's options, not flagged, and either
    currently used (known healthy) or never flagged."""
    bad = {r["caller_id"] for r in rows if r["flagged"]}
    return [o for o in options if o not in bad]