"""Reproduces the false-winner-rate and power figures quoted in SUBMISSION.md.

    python scripts/power_table.py

Pure simulation: it never touches the simulator. Fixed seed, so the output is repeatable.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from controller.stats import benjamini_hochberg, required_n, two_prop_test

RNG = np.random.default_rng(2027)


def run_family(arms, n, p_control, effects, q=0.05):
    """One experiment: `arms` candidates vs one shared control. Returns, per arm, 'declared winner'."""
    control = int(RNG.binomial(n, p_control))
    xs = [int(RNG.binomial(n, p_control + effects.get(i, 0.0))) for i in range(arms)]
    ps = [two_prop_test(x, n, control, n)["p"] for x in xs]
    return benjamini_hochberg(ps, q)


def main():
    print("FALSE-WINNER RATE under the null (no candidate is truly better), BH q=0.05, 4000 runs each")
    for m in (1, 4, 12, 45):
        for n in (150, 600):
            fw = sum(any(run_family(m, n, 0.5, {})) for _ in range(4000)) / 4000
            print(f"  m={m:2d} comparisons, n={n:4d}/arm -> P(any false winner) = {fw:.3f}")

    print("\nPOWER to find ONE true winner among m=12 candidates (BH q=0.05), 1500 runs each, baseline 50%")
    print("  n/arm :   150    300    600   1200")
    for delta in (0.05, 0.10, 0.15):
        row = []
        for n in (150, 300, 600, 1200):
            ok = sum(run_family(12, n, 0.5, {0: delta})[0] for _ in range(1500)) / 1500
            row.append(f"{ok:5.2f}")
        print(f"  +{int(delta * 100):2d} pts: " + "  ".join(row))

    print("\nPER-ARM SAMPLE NEEDED for 90% power at +10 pts, baseline 50% (one-sided)")
    for m in (1, 12, 45):
        print(f"  family size {m:2d}: ~{required_n(0.5, 0.10, alpha=0.05 / m, power=0.9)} per arm"
              " (Bonferroni approx.)")

    print("\nDAYS TO REACH that sample, nw_renewal, using history volumes (~934 connected calls/day)")
    need = required_n(0.5, 0.10, alpha=0.05 / 12, power=0.9)
    print(f"  (needs ~{need} connected calls per arm)")
    for label, share in (("whole workflow", 1.0), ("age 60+ (15%)", 0.152), ("Tamil (20%)", 0.20)):
        for arms in (2, 4):
            per_day = 934 * share / arms
            print(f"  {label:16s} {arms} arms: {per_day:6.0f} connected/arm/day -> {need / per_day:5.1f} days")


if __name__ == "__main__":
    main()