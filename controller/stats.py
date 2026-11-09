"""Statistics for deciding winners. Pure functions, no I/O: deterministic and unit-testable.

An LLM may suggest what to try; only these functions decide what won.
"""
from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()


def two_prop_test(x1: int, n1: int, x2: int, n2: int) -> dict:
    """Compare arm 1 (candidate) against arm 2 (control).

    Returns diff = p1 - p2, the z statistic, and the ONE-SIDED p-value for
    'the candidate is better than the control' (pooled two-proportion z-test).
    """
    if n1 <= 0 or n2 <= 0:
        return {"diff": 0.0, "z": 0.0, "p": 1.0}
    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return {"diff": p1 - p2, "z": 0.0, "p": 1.0}
    z = (p1 - p2) / se
    return {"diff": p1 - p2, "z": z, "p": 0.5 * math.erfc(z / math.sqrt(2))}


def benjamini_hochberg(pvalues: list[float], q: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg: controls the false discovery rate at q across many comparisons.
    Returns, in the original order, which hypotheses are rejected (declared winners)."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    cutoff = 0
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= q * rank / m:
            cutoff = rank
    keep = [False] * m
    for rank, i in enumerate(order, start=1):
        if rank <= cutoff:
            keep[i] = True
    return keep


def required_n(p0: float, delta: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """Per-arm sample size needed to detect an absolute lift `delta` over a baseline rate p0
    (one-sided test)."""
    p1 = min(p0 + delta, 0.999)
    pbar = (p0 + p1) / 2
    za, zb = _N.inv_cdf(1 - alpha), _N.inv_cdf(power)
    num = (za * math.sqrt(2 * pbar * (1 - pbar))
           + zb * math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))) ** 2
    return math.ceil(num / (p1 - p0) ** 2)


def diff_ci(x1: int, n1: int, x2: int, n2: int, conf: float = 0.95) -> tuple[float, float]:
    """Wald confidence interval for p1 - p2."""
    if n1 <= 0 or n2 <= 0:
        return (-1.0, 1.0)
    p1, p2 = x1 / n1, x2 / n2
    se = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    z = _N.inv_cdf(0.5 + conf / 2)
    return (p1 - p2 - z * se, p1 - p2 + z * se)