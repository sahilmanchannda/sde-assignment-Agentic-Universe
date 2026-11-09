"""Measures the caller-ID detector: how often it cries wolf on a healthy ID, and how often it
catches a degraded one. Pure simulation, fixed seed.

    python scripts/health_power.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from controller.health import check_caller_ids

RNG = np.random.default_rng(2027)
MIX = {"18-30": 0.3, "31-45": 0.4, "46-60": 0.2, "60+": 0.1}
RATES = {"18-30": 0.27, "31-45": 0.28, "46-60": 0.27, "60+": 0.25}


def sample(dials, drop=0.0):
    """One period for one caller ID: dials split by MIX, pickup = band rate minus `drop`."""
    out = {}
    for band, share in MIX.items():
        n = int(RNG.binomial(dials, share))
        out[band] = (n, int(RNG.binomial(n, max(RATES[band] - drop, 0.0))))
    return out


def rate(runs, recent_dials, base_dials, drop):
    hit = thin = 0
    for _ in range(runs):
        rows = check_caller_ids({"D1": sample(recent_dials, drop)},
                                {"D1": sample(base_dials)}, MIX)
        hit += bool(rows and rows[0]["flagged"])
        thin += bool(rows and rows[0].get("insufficient"))
    rate.thin = thin / runs
    return hit / runs


def main():
    print("FALSE ALARMS on a healthy ID (no drop), 3000 runs each")
    for recent in (300, 800, 2400):
        for base in (3000, 20000):
            print(f"  recent={recent:5d} dials, baseline={base:6d} dials -> "
                  f"P(flag) = {rate(3000, recent, base, 0.0):.3f}")
    print("\nDETECTION of a degraded ID, baseline 20000 dials, 1000 runs each")
    print("  recent dials:   300    800   2400")
    for drop in (0.05, 0.10, 0.15):
        row = []
        for n in (300, 800, 2400):
            row.append(f"{rate(1000, n, 20000, drop):5.2f}")
            if n == 300:
                print(f"  drop {int(drop * 100):2d} pts: thin-day share at 300 dials = {rate.thin:.2f}")
        print(f"  drop {int(drop * 100):2d} pts:  " + "  ".join(row))
    print("\nA FALSE ALARM EVERY DAY for 10 days, at the 800-dial rate: "
          "1 - (1 - p)^10 where p is the 800/20000 figure above")


if __name__ == "__main__":
    main()