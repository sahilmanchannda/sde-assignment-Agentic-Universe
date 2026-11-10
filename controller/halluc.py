"""Hallucination incident detector. Pure functions: counts in, findings out.

The automated flag is imperfect, so we never act on single flags. We test whether a prompt's
flag rate per connected call is clearly above a reference rate (its own history, or the
previous prompt's if it is new).
"""
from __future__ import annotations

from controller.stats import two_prop_test

MIN_CONNECTED = 200    # connected calls on the recent day before we trust a reading
# MIN_EXCESS = 0.01      # absolute rate increase worth responding to
# ALPHA = 0.01
MIN_EXCESS = 0.02
ALPHA = 0.0001

def check_prompts(recent: dict, reference: dict, *, min_connected=MIN_CONNECTED,
                  min_excess=MIN_EXCESS, alpha=ALPHA) -> list[dict]:
    """recent / reference: {prompt: (connected, flagged)}.
    reference for a prompt is its own history, or the previous prompt's if it has none."""
    out = []
    for prompt, (n, x) in recent.items():
        n0, x0 = reference.get(prompt, (0, 0))
        if n < min_connected or n0 < min_connected:
            out.append({"prompt": prompt, "flagged": False, "insufficient": True,
                        "connected": n, "reference_connected": n0})
            continue
        t = two_prop_test(x, n, x0, n0)
        out.append({"prompt": prompt, "recent": round(x / n, 4), "reference": round(x0 / n0, 4),
                    "excess": round(x / n - x0 / n0, 4), "p": t["p"], "connected": n,
                    "flagged": bool(t["p"] < alpha and x / n - x0 / n0 >= min_excess)})
    return out