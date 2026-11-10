"""Sizing and budgeting for validation runs. Pure functions."""
from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()

N_DEFAULT = 300
N_MIN, N_MAX = 50, 2000
RESERVE = 60          # credits always kept for later incidents
PER_INCIDENT = 40     # most one incident may spend
MARGIN = 0.01   # a prompt must clear the threshold by this much, validation is noisy


def acceptable(pass_rate: float, threshold: float, margin: float = MARGIN) -> bool:
    return pass_rate >= threshold + margin


def in_cooldown(days_since_change: int | None, excess: float,
                cooldown: int = 2, override: float = 0.03) -> bool:
    """After our own prompt change, ignore small excesses for a couple of days."""
    return days_since_change is not None and days_since_change < cooldown and excess < override

def cost(n: int) -> int:
    return math.ceil(n / 100)


def p_clears(true_rate: float, n: int, threshold: float) -> float:
    """Chance a run with n conversations measures at least `threshold` (normal approximation)."""
    if true_rate <= 0.0:
        return 0.0
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