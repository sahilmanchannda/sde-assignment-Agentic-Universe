from controller.experiments import (final_config, find_winners, monitor_check, plan_arms,
                                    split_config)

OPTS = {"voice": ["V1", "V2", "V3", "V4"], "welcome_message": ["W1", "W2", "W3"]}
ARMS = {"voice": {"control": "V1", "candidates": ["V2"]}}
GUARD = ("pickup_rate", 0.02)


def run(ctl, cand, guard=GUARD, primary="engagement_rate"):
    return find_winners({"voice": {"V1": ctl, "V2": cand}}, ARMS, primary, guard)


def test_plan_arms_picks_single_valued_dimensions():
    alloc = {"voice": {"V1": 1.0}, "welcome_message": {"W1": 1.0}}
    assert plan_arms(alloc, OPTS) == {
        "voice": {"control": "V1", "candidates": ["V2", "V3"]},
        "welcome_message": {"control": "W1", "candidates": ["W2", "W3"]}}


def test_plan_arms_leaves_an_existing_mix_alone():
    alloc = {"voice": {"V1": 0.5, "V2": 0.5}, "welcome_message": {"W1": 1.0}}
    assert list(plan_arms(alloc, OPTS)) == ["welcome_message"]


def test_clear_winner_is_found():
    rows, w = run((3000, 750, 375), (3000, 750, 450))     # engagement 0.50 vs 0.60
    assert w == {"voice": "V2"} and rows[0]["wins"]


def test_no_effect_is_not_a_winner():
    assert run((3000, 750, 375), (3000, 750, 380))[1] == {}


def test_guardrail_blocks_a_win_that_costs_pickup():
    # engagement wins (0.5 vs 0.6) but pickup falls 0.25 -> 0.20, past the 0.02 limit
    rows, w = run((3000, 750, 375), (3000, 600, 360))
    assert w == {} and not rows[0]["guard_ok"]


def test_thin_data_never_wins():
    assert run((100, 25, 5), (100, 25, 20))[1] == {}


def test_tiny_effect_is_not_worth_an_approval():
    # 0.515 vs 0.50 is statistically clear at this n but below the 2-point minimum
    assert run((80000, 20000, 10000), (80000, 20000, 10300))[1] == {}


def test_split_and_final_config():
    cfg = {"allocations": {"default": {"voice": {"V1": 1.0}, "welcome_message": {"W1": 1.0},
                                       "caller_id": {"D1": 0.5, "D2": 0.5}}}}
    arms = plan_arms(cfg["allocations"]["default"], OPTS)
    d = split_config(cfg, arms)["allocations"]["default"]
    assert abs(sum(d["voice"].values()) - 1) < 1e-3 and d["caller_id"] == {"D1": 0.5, "D2": 0.5}
    f = final_config(cfg, arms, {"voice": "V2"})["allocations"]["default"]
    assert f["voice"] == {"V2": 1.0} and f["welcome_message"] == {"W1": 1.0}
    assert cfg["allocations"]["default"]["voice"] == {"V1": 1.0}     # input untouched

def test_recency_check_blocks_a_winner_whose_latest_day_has_faded():
    pooled = {"V1": (3000, 750, 375), "V2": (3000, 750, 450)}          # 0.50 vs 0.60
    fading = {"V1": (1000, 250, 125), "V2": (1000, 250, 120)}          # latest day: V2 behind
    holding = {"V1": (1000, 250, 125), "V2": (1000, 250, 150)}
    assert find_winners({"voice": pooled}, ARMS, "engagement_rate", GUARD, {"voice": fading})[1] == {}
    assert find_winners({"voice": pooled}, ARMS, "engagement_rate", GUARD, {"voice": holding})[1] == {"voice": "V2"}


def test_recency_check_fails_closed_without_recent_data():
    pooled = {"V1": (3000, 750, 375), "V2": (3000, 750, 450)}
    assert find_winners({"voice": pooled}, ARMS, "engagement_rate", GUARD, {"voice": {}})[1] == {}


def test_monitor_rolls_back_a_clearly_decayed_promotion():
    arms = {"voice": {"control": "V1", "candidates": ["V2"]}}
    decayed = {"voice": {"V2": (3000, 900, 450), "V1": (1000, 300, 180)}}   # 0.50 vs 0.60
    rows, bad = monitor_check(decayed, {"voice": "V2"}, arms, "engagement_rate")
    assert bad == ["voice"] and rows[0]["decided"]


def test_monitor_keeps_a_promotion_that_holds():
    arms = {"voice": {"control": "V1", "candidates": ["V2"]}}
    holds = {"voice": {"V2": (3000, 900, 540), "V1": (1000, 300, 150)}}     # 0.60 vs 0.50
    assert monitor_check(holds, {"voice": "V2"}, arms, "engagement_rate")[1] == []


def test_monitor_waits_for_enough_holdback_data():
    arms = {"voice": {"control": "V1", "candidates": ["V2"]}}
    thin = {"voice": {"V2": (3000, 900, 450), "V1": (160, 50, 30)}}
    rows, bad = monitor_check(thin, {"voice": "V2"}, arms, "engagement_rate")
    assert bad == [] and not rows[0]["decided"]


def test_final_config_with_holdback_keeps_the_old_option_at_ten_percent():
    cfg = {"allocations": {"default": {"voice": {"V1": 0.5, "V2": 0.5}}}}
    arms = {"voice": {"control": "V1", "candidates": ["V2"]}}
    d = final_config(cfg, arms, {"voice": "V2"}, 0.10)["allocations"]["default"]
    assert d["voice"] == {"V2": 0.9, "V1": 0.1}