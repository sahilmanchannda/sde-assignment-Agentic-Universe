"""Decision logic run once per tick. Currently: per-cohort call timing (schedule)."""
from __future__ import annotations

from controller.audit import log_decision
from controller.governance import Governance
from controller.schedule import build_config, plan
from controller.store import get_meta, set_meta

MAX_ATTEMPTS = 3   # approval requests per workflow for this idea, so a rejection is not retried forever


def band_counts(conn, wf: str) -> dict:
    """{age_band: {hour: (dials, connected)}} for attempt-1 calls only."""
    out: dict = {}
    for band, hour, d, k in conn.execute(
            "SELECT age_band, hour, SUM(dials), SUM(connected) FROM agg_hour "
            "WHERE workflow_id=? AND attempt=1 GROUP BY age_band, hour", (wf,)):
        out.setdefault(band, {})[hour] = (d, k)
    return out


def expected_lift(hmap: dict, weights: dict, hours: list[int]) -> float:
    """Estimated pickup change for one band if dialling shifts in proportion to the weights."""
    fd = fk = wd = wk = 0.0
    for h in hours:
        d, k = hmap.get(h, (0, 0))
        w = weights[h]
        fd += d
        fk += k
        wd += d * w
        wk += k * w
    if fd == 0 or wd == 0:
        return 0.0
    return wk / wd - fk / fd


def _mark(conn, wf: str, day: str) -> None:
    with conn:
        set_meta(conn, f"sched_day_{wf}", day)


def schedule_step(conn, client, gov: Governance, st: dict) -> None:
    ts, day = st["ts"], st["ts"][:10]
    for w in client.workflows():
        wf = w["workflow_id"]
        if get_meta(conn, f"sched_day_{wf}") == day or gov.in_flight(wf):
            continue
        tries = conn.execute("SELECT COUNT(*) FROM proposals WHERE workflow_id=? AND kind='approval'",
                             (wf,)).fetchone()[0]
        if tries >= MAX_ATTEMPTS:
            continue
        detail = client.workflow(wf)
        pol = detail["governance"]
        lo, hi = detail["dialling_window"]
        hours = list(range(lo, hi))
        cur = client.config(wf)
        counts = band_counts(conn, wf)
        planned = plan(counts, hours)
        new, why = build_config(cur["config"], planned, hours)
        if new is None:
            with conn:
                log_decision(conn, ts, wf, "skip", f"no timing change: {why}", {})
            _mark(conn, wf, day)
            continue
        bands = sorted(planned)
        est = {b: round(expected_lift(counts[b], planned[b]["weights"], hours), 4) for b in bands}
        q = ",".join("?" * len(bands))
        n_band = dict(conn.execute(
            f"SELECT age_band, COUNT(*) FROM leads WHERE workflow_id=? AND age_band IN ({q}) "
            "GROUP BY age_band", (wf, *bands)).fetchall())
        n_all = conn.execute("SELECT COUNT(*) FROM leads WHERE workflow_id=?", (wf,)).fetchone()[0]
        affected = sum(n_band.values())
        impact = round(sum(est[b] * n_band.get(b, 0) for b in bands) / max(n_all, 1), 4)
        summary = f"per-age-band call timing for {', '.join(bands)}"
        rationale = ("Pickup differs by time of day within these age bands (attempt-1 calls only, "
                     "adjusted for choosing the best of 3 slots, Benjamini-Hochberg across bands). "
                     "Pickup only: engagement by hour is not measured here.")
        pid, reason = gov.propose(
            wf, cur["version"], new, summary, rationale, ts, pol,
            diff={"cohorts": f"add {len(bands)} age-band cohorts", "schedule.hour_weights": "per-cohort tables"},
            affected_leads=affected,
            dry_run={"method": "history counts, dialling shifts in proportion to weights (assumption)",
                     "estimated_pickup_lift_by_band": est,
                     "evidence": {b: planned[b]["evidence"] for b in bands}},
            impact_score=impact)
        if pid:
            _mark(conn, wf, day)
        # otherwise (send window closed, request cap): leave unmarked and retry on a later tick