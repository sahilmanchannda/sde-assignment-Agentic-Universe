import numpy as np
import pytest

from controller.stats import benjamini_hochberg, diff_ci, required_n, two_prop_test


def test_required_n_matches_the_textbook_figure():
    # 5-point lift over a 50% baseline, one-sided alpha 0.05, 80% power: about 1,233 per arm
    assert 1200 < required_n(0.5, 0.05) < 1300


def test_two_prop_test_detects_a_clear_difference():
    r = two_prop_test(600, 1000, 500, 1000)
    assert r["diff"] == pytest.approx(0.1)
    assert r["z"] == pytest.approx(4.5, abs=0.05)
    assert r["p"] < 1e-4


def test_two_prop_test_is_one_sided_in_the_candidates_favour():
    assert two_prop_test(500, 1000, 600, 1000)["p"] > 0.99           # candidate is WORSE
    assert two_prop_test(500, 1000, 500, 1000)["p"] == pytest.approx(0.5)


def test_degenerate_inputs_do_not_crash():
    assert two_prop_test(0, 0, 5, 10)["p"] == 1.0
    assert two_prop_test(0, 10, 0, 10)["p"] == 1.0
    assert two_prop_test(10, 10, 10, 10)["p"] == 1.0


def test_benjamini_hochberg_textbook_example():
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205]
    assert benjamini_hochberg(p, 0.05) == [True, True, False, False, False, False, False, False]


def test_benjamini_hochberg_keeps_the_original_order_and_handles_empty():
    assert benjamini_hochberg([0.5, 0.001]) == [False, True]
    assert benjamini_hochberg([]) == []


def test_diff_ci_contains_the_estimate_and_narrows_with_more_data():
    lo1, hi1 = diff_ci(60, 100, 50, 100)
    lo2, hi2 = diff_ci(600, 1000, 500, 1000)
    assert lo1 < 0.1 < hi1 and lo2 < 0.1 < hi2
    assert (hi2 - lo2) < (hi1 - lo1)


def run_family(rng, arms, n, p_control, effects, q=0.05):
    """One experiment: `arms` candidates vs one shared control; returns which arms were declared winners."""
    control = int(rng.binomial(n, p_control))
    xs = [int(rng.binomial(n, p_control + effects.get(i, 0.0))) for i in range(arms)]
    ps = [two_prop_test(x, n, control, n)["p"] for x in xs]
    return benjamini_hochberg(ps, q)


def test_false_winner_rate_under_the_null_is_controlled():
    # 12 candidates, none truly better. How often do we declare ANY winner? Target: about 5% or less.
    rng = np.random.default_rng(7)
    runs = 3000
    false_runs = sum(any(run_family(rng, 12, 200, 0.5, {})) for _ in range(runs))
    assert false_runs / runs < 0.08


def test_a_real_effect_is_found_when_there_is_enough_data():
    # 12 candidates, candidate 0 is truly +10 points. The correction for 12 comparisons costs power:
    # a lone winner must reach p <= 0.05/12, so 600 per arm finds it only ~80% of the time,
    # and about 800 per arm is needed to find it ~90% of the time.
    rng = np.random.default_rng(11)
    runs = 400
    found = sum(run_family(rng, 12, 800, 0.5, {0: 0.10})[0] for _ in range(runs))
    assert found / runs > 0.85