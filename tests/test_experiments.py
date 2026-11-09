from controller.experiments import final_config, find_winners, plan_arms, split_config

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