from controller.halluc import check_prompts


def test_a_prompt_with_a_clear_excess_is_flagged():
    rows = check_prompts({"P2": (600, 36)}, {"P2": (6000, 36)})      # 6% vs 0.6%
    assert rows[0]["flagged"]


def test_normal_noise_is_not_flagged():
    rows = check_prompts({"P1": (600, 5)}, {"P1": (6000, 40)})       # 0.8% vs 0.7%
    assert not rows[0]["flagged"]


def test_small_excess_is_ignored_even_if_significant():
    rows = check_prompts({"P1": (20000, 260)}, {"P1": (20000, 160)})  # 1.3% vs 0.8%: 0.5 pts
    assert not rows[0]["flagged"]


def test_thin_data_is_insufficient_not_healthy():
    rows = check_prompts({"P2": (50, 10)}, {"P2": (6000, 36)})
    assert rows[0]["insufficient"] and not rows[0]["flagged"]


def test_unknown_reference_is_insufficient():
    rows = check_prompts({"P2": (600, 36)}, {})
    assert rows[0]["insufficient"]

def test_day6_p1_noise_is_not_flagged_but_p2_incident_is():
    assert not check_prompts({"P1": (781, 21)}, {"P1": (4000, 60)})[0]["flagged"]
    assert check_prompts({"P2": (608, 26)}, {"P2": (4000, 60)})[0]["flagged"]