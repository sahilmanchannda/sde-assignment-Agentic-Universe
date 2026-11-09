from controller.schedule import build_config, plan

HOURS = list(range(9, 21))


def band(rates):
    """250 dials in each hour; rates = (morning, midday, evening)."""
    out = {}
    for h in HOURS:
        r = rates[0] if h < 13 else rates[1] if h < 17 else rates[2]
        out[h] = (250, round(250 * r))
    return out


DATA = {"60+": band((0.35, 0.27, 0.22)), "31-45": band((0.28, 0.28, 0.28))}


def test_only_the_band_with_a_real_preference_gets_a_table():
    p = plan(DATA, HOURS)
    assert list(p) == ["60+"]
    w = p["60+"]["weights"]
    assert w[10] > 1.0 > w[19] and 0.5 <= w[19] and w[10] <= 2.0


def test_every_table_lists_every_hour_because_missing_hours_mean_zero():
    cfg, _ = build_config({"cohorts": [], "schedule": {"hour_weights": {}}}, plan(DATA, HOURS), HOURS)
    for table in cfg["schedule"]["hour_weights"].values():
        assert sorted(table, key=int) == [str(h) for h in HOURS]
    assert cfg["cohorts"][0]["id"] == "age_band_60plus"


def test_thin_data_proposes_nothing():
    thin = {"60+": {h: (5, 2) for h in HOURS}}
    assert plan(thin, HOURS) == {}


def test_existing_cohorts_are_never_overwritten():
    cfg, why = build_config({"cohorts": [{"id": "x", "where": {"lang": ["ta"]}}]},
                            plan(DATA, HOURS), HOURS)
    assert cfg is None and "already has cohorts" in why
    