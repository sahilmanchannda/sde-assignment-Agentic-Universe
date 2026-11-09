from controller.validation import affordable_n, cost, p_clears
from controller.incidents import pick_reference


def test_cost_is_per_hundred_rounded_up():
    assert cost(50) == 1 and cost(300) == 3 and cost(301) == 4


def test_a_safe_prompt_clears_the_threshold_but_a_borderline_one_does_not_reliably():
    assert p_clears(0.99, 300, 0.97) > 0.95
    assert 0.4 < p_clears(0.97, 300, 0.97) < 0.6


def test_budget_keeps_the_reserve():
    assert affordable_n(200, 0) == 300
    assert affordable_n(63, 0) == 300
    assert affordable_n(62, 0) == 200
    assert affordable_n(60, 0) == 0


def test_one_incident_cannot_overspend():
    assert affordable_n(200, 38) == 200
    assert affordable_n(200, 40) == 0

def test_fresh_prompt_borrows_the_previous_prompts_history():
    ref = pick_reference({"P2": (600, 36)}, {"P1": (6000, 36)}, "P1")
    assert ref["P2"] == (6000, 36)


def test_a_prompt_with_its_own_history_keeps_it():
    ref = pick_reference({"P1": (600, 5)}, {"P1": (6000, 40), "P3": (100, 1)}, "P3")
    assert ref["P1"] == (6000, 40)