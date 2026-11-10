from controller.rotation import band_mix, confirm_flags, plan_shift

ALLOC = {"default": {"D1": 0.5, "D2": 0.5}}


def test_capped_step_moves_only_the_allowed_share():
    new, moves = plan_shift(ALLOC, {"D2"}, {"D1", "D2"}, cap=0.199)
    assert moves == {"default": 0.199}
    assert abs(new["default"]["D2"] - 0.301) < 1e-3 and abs(new["default"]["D1"] - 0.699) < 1e-3


def test_uncapped_move_takes_everything_off_the_bad_id():
    new, _ = plan_shift(ALLOC, {"D2"}, {"D1"})
    assert new["default"] == {"D1": 1.0}


def test_repeated_capped_steps_reach_zero_in_three_days():
    alloc, steps = ALLOC, 0
    while True:
        new, info = plan_shift(alloc, {"D2"}, {"D1"}, cap=0.199)
        if new is None:
            break
        alloc, steps = new, steps + 1
    assert steps == 3 and alloc["default"] == {"D1": 1.0}


def test_no_healthy_receiver_means_no_move():
    new, why = plan_shift({"default": {"D1": 1.0}}, {"D1"}, set())
    assert new is None and "no healthy" in why


def test_a_bad_id_already_at_zero_is_nothing_to_do():
    assert plan_shift({"default": {"D1": 1.0}}, {"D2"}, {"D1"})[0] is None


def test_unused_id_with_history_can_receive_when_no_healthy_id_is_in_use():
    new, _ = plan_shift({"default": {"D2": 1.0}}, {"D2"}, {"D1"})
    assert new["default"] == {"D1": 1.0}


def test_band_mix_sums_to_one():
    m = band_mix({"D1": {"60+": (100, 25)}, "D2": {"60+": (100, 20), "18-30": (200, 50)}})
    assert abs(sum(m.values()) - 1) < 1e-9 and abs(m["18-30"] - 0.5) < 1e-9

def test_flag_needs_a_clearly_better_id_on_the_same_day():
    assert confirm_flags(["D2"], {"D1": 0.242, "D2": 0.103}) == ["D2"]


def test_lone_id_that_slid_after_taking_all_traffic_is_not_confirmed():
    assert confirm_flags(["D1"], {"D1": 0.185}) == []
    assert confirm_flags(["D1"], {"D1": 0.20, "D2": 0.21}) == []