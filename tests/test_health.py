from controller.health import check_caller_ids, healthy_ids, standardized

MIX = {"18-30": 0.3, "31-45": 0.4, "60+": 0.3}


def band(rate, dials_per_band=400):
    return {b: (dials_per_band, round(dials_per_band * rate)) for b in MIX}


def test_a_clearly_degraded_id_is_flagged():
    rows = check_caller_ids({"D1": band(0.15)}, {"D1": band(0.27)}, MIX)
    assert rows[0]["flagged"] and rows[0]["drop"] > 0.1


def test_a_healthy_id_is_not_flagged():
    rows = check_caller_ids({"D1": band(0.27)}, {"D1": band(0.268)}, MIX)
    assert not rows[0]["flagged"]


def test_a_small_drop_is_ignored_even_if_significant():
    rows = check_caller_ids({"D1": band(0.245, 4000)}, {"D1": band(0.27, 4000)}, MIX)
    assert not rows[0]["flagged"]


def test_thin_data_says_nothing():
    assert check_caller_ids({"D1": band(0.05, 20)}, {"D1": band(0.27, 400)}, MIX) == []


def test_a_change_in_age_mix_is_not_mistaken_for_degradation():
    # same per-band pickup, but the recent day happened to dial mostly low-pickup 60+ leads
    base = {"18-30": (400, 120), "31-45": (400, 120), "60+": (400, 80)}
    recent = {"18-30": (100, 30), "31-45": (100, 30), "60+": (1000, 200)}
    assert not check_caller_ids({"D1": recent}, {"D1": base}, MIX)[0]["flagged"]


def test_healthy_ids_excludes_flagged():
    rows = [{"caller_id": "D1", "flagged": True}, {"caller_id": "D2", "flagged": False}]
    assert healthy_ids(rows, ["D1", "D2", "D3"], {}) == ["D2", "D3"]


def test_standardized_ignores_missing_bands_gracefully():
    p, n, d = standardized({"60+": (100, 25)}, MIX)
    assert d == 100 and 0 < p < 1