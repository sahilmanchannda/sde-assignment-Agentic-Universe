"""Sizing and budgeting for validation runs. Pure functions."""
from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()

N_DEFAULT = 300
N_MIN, N_MAX = 50, 2000
RESERVE = 60          # credits always kept for later incidents
PER_INCIDENT = 40     # most one incident may spend


def cost(n: int) -> int:
    return math.ceil(n / 100)


def p_clears(true_rate: float, n: int, threshold: float) -> float:
    """Chance a run with n conversations measures at least `threshold` (normal approximation)."""
    if true_rate >= 1.0:
        return 1.0
    se = math.sqrt(true_rate * (1 - true_rate) / n)
    return 1 - _N.cdf((threshold - true_rate) / se)


def affordable_n(credits: float, spent_this_incident: float, want: int = N_DEFAULT) -> int:
    """Largest n <= want we can afford while keeping the reserve and the per-incident cap.
    Returns 0 if even the minimum run is not affordable."""
    room = min(credits - RESERVE, PER_INCIDENT - spent_this_incident)
    n = min(want, int(room) * 100)
    return n if n >= N_MIN else 0