from controller.decide import band_counts, expected_lift
from controller.store import connect

HOURS = list(range(9, 21))


def test_expected_lift_is_positive_when_weight_moves_toward_good_hours():
    hmap = {h: (100, 35 if h < 13 else 22) for h in HOURS}
    w = {h: 2.0 if h < 13 else 0.5 for h in HOURS}
    assert expected_lift(hmap, w, HOURS) > 0.03
    assert expected_lift(hmap, {h: 1.0 for h in HOURS}, HOURS) == 0.0


def test_band_counts_uses_attempt_one_only(tmp_path):
    conn = connect(str(tmp_path / "t.db"))
    with conn:
        conn.executemany("INSERT INTO agg_hour VALUES (?,?,?,?,?,?,?,?,?)", [
            ("w", 9, "hi", "1", "60+", "low", 1, 10, 4),
            ("w", 9, "ta", "2", "60+", "low", 1, 5, 1),
            ("w", 9, "hi", "1", "60+", "low", 2, 99, 99)])
    assert band_counts(conn, "w") == {"60+": {9: (15, 5)}}