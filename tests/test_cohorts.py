import pytest

from controller.cohorts import DEFAULT, MAX_COHORTS, Cohort, CohortSet

SENIOR_TA = {"lang": "ta", "city_tier": "2", "age_band": "60+", "value_band": "low"}
YOUNG_HI = {"lang": "hi", "city_tier": "1", "age_band": "18-30", "value_band": "mid"}


def test_id_is_deterministic_and_readable():
    a = Cohort.make({"age_band": ["60+"], "lang": ["ta"]})
    b = Cohort.make({"lang": ["ta"], "age_band": ["60+"]})          # different key order
    assert a.id == b.id == "age_band_60plus__lang_ta"
    assert Cohort.make({"age_band": ["46-60", "60+"]}).id == "age_band_46_60_60plus"


def test_match_is_and_across_features_or_within_a_feature():
    c = Cohort.make({"age_band": ["46-60", "60+"], "lang": ["ta"]})
    assert c.matches(SENIOR_TA)
    assert not c.matches({**SENIOR_TA, "lang": "hi"})                # AND: language must match
    assert not c.matches({**SENIOR_TA, "age_band": "18-30"})         # OR list excludes 18-30


def test_a_lead_belongs_to_the_first_matching_cohort_else_default():
    senior = Cohort.make({"age_band": ["60+"]})
    tamil = Cohort.make({"lang": ["ta"]})
    cs = CohortSet([senior, tamil])
    assert cs.assign(SENIOR_TA) == senior.id                         # matches both: first wins
    assert cs.assign({**SENIOR_TA, "age_band": "18-30"}) == tamil.id
    assert cs.assign(YOUNG_HI) == DEFAULT
    assert cs.ids() == [senior.id, tamil.id, DEFAULT]


def test_config_round_trip_keeps_the_id_the_config_already_uses():
    cfg = [{"id": "senior_ta", "where": {"age_band": ["60+"], "lang": ["ta"]}}]
    cs = CohortSet.from_config(cfg)
    assert cs.ids() == ["senior_ta", DEFAULT]                        # supervisor's name is kept
    assert cs.to_config() == cfg
    assert cs.assign(SENIOR_TA) == "senior_ta"


def test_validation():
    with pytest.raises(ValueError):
        Cohort.make({})
    with pytest.raises(ValueError):
        Cohort.make({"shoe_size": ["9"]})
    with pytest.raises(ValueError):
        Cohort.make({"lang": []})
    c = Cohort.make({"lang": ["ta"]})
    with pytest.raises(ValueError):
        CohortSet([c, c])                                            # duplicate id
    with pytest.raises(ValueError):
        CohortSet([Cohort("default", c.where)])                      # reserved id
    many = [Cohort.make({"lang": [f"l{i}"]}) for i in range(MAX_COHORTS + 1)]
    with pytest.raises(ValueError):
        CohortSet(many)