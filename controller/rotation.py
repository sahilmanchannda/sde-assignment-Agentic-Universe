"""Caller-ID rotation: detect a degraded ID, then move its traffic to healthy IDs.

No event flags a bad number, so detection is a pickup drop against the ID's own earlier days
(health.py). Once flagged, an ID's baseline is frozen at the days before the first flag and the
ID is remembered as bad. Traffic only ever moves to IDs with real history that are not bad."""
from __future__ import annotations

import copy
import json
from datetime import date

from controller.audit import log_decision
from controller.governance import can_auto_apply, in_send_window
from controller.health import check_caller_ids
from controller.store import get_meta, set_meta

MIN_HISTORY = 300        # dials an ID needs in its baseline before it may receive traffic
SHIFT_MARGIN = 0.001     # stay this far under max_shift: weights are rounded to 4 places
NOTHING = "nothing to move"


# ---------- pure logic (unit-tested) ----------
def plan_shift(alloc: dict, bad: set, healthy: set, cap: float | None = None):
    """alloc: {cohort: {caller_id: weight}}. Move weight off `bad` IDs onto healthy ones.
    cap limits how much moves per cohort (total-variation distance). Returns (new_alloc, moves)
    or (None, reason)."""
    new, moves = copy.deepcopy(alloc), {}
    for cohort, dist in alloc.items():
        bw = sum(w for i, w in dist.items() if i in bad)
        if bw <= 1e-9:
            continue
        targets = [i for i in dist if i not in bad and i in healthy]
        targets = targets or sorted(i for i in healthy if i not in bad)
        if not targets:
            return None, f"no healthy caller ID with history to receive traffic in cohort {cohort}"
        moved = bw if cap is None else min(bw, max(cap, 0.0))
        if moved <= 1e-9:
            continue
        frac = moved / bw
        out = {i: (w * (1 - frac) if i in bad else w) for i, w in dist.items()}
        base = {t: dist.get(t, 0.0) for t in targets}
        tot = sum(base.values())
        for t in targets:
            share = base[t] / tot if tot > 0 else 1 / len(targets)
            out[t] = out.get(t, 0.0) + moved * share
        new[cohort] = {i: round(w, 4) for i, w in out.items() if w > 1e-6}
        moves[cohort] = round(moved, 4)
    return (new, moves) if moves else (None, NOTHING)


def band_mix(counts: dict) -> dict:
    tot: dict = {}
    for bands in counts.values():
        for b, (d, _) in bands.items():
            tot[b] = tot.get(b, 0) + d
    s = sum(tot.values())
    return {b: d / s for b, d in tot.items()} if s else {}


# ---------- database ----------
def id_band_counts(conn, wf, first_day, last_day):
    out: dict = {}
    for cid, band, d, k in conn.execute(
            "SELECT caller_id, age_band, SUM(dials), SUM(connected) FROM agg_variant "
            "WHERE workflow_id=? AND day BETWEEN ? AND ? GROUP BY caller_id, age_band",
            (wf, first_day, last_day)):
        out.setdefault(cid, {})[band] = (d, k)
    return out


def _log(conn, ts, wf, kind, note, detail=None):
    with conn:
        log_decision(conn, ts, wf, kind, note, detail or {})


def rotation_step(conn, client, gov, st):
    ts, day = st["ts"], st["ts"][:10]
    d0 = date.fromisoformat(get_meta(conn, "d0"))
    today = (date.fromisoformat(day) - d0).days
    for w in client.workflows():
        wf = w["workflow_id"]
        if today < 1 or get_meta(conn, f"rot_day_{wf}") == day or gov.in_flight(wf):
            continue
        detail = client.workflow(wf)
        pol = detail["governance"]
        auto = can_auto_apply(pol, ["caller_id"])
        if not auto and not in_send_window(pol, ts):
            continue                                   # approval path: wait for the window
        cur = client.config(wf)
        first_bad = json.loads(get_meta(conn, f"did_bad_{wf}") or "{}")
        end_base = min([today - 2] + [d - 1 for d in first_bad.values()])
        recent = id_band_counts(conn, wf, today - 1, today - 1)
        base = id_band_counts(conn, wf, -14, end_base)
        rows = check_caller_ids(recent, base, band_mix(base))
        fresh = [r for r in rows if r.get("flagged") and r["caller_id"] not in first_bad]
        for r in fresh:
            first_bad[r["caller_id"]] = today - 1
            _log(conn, ts, wf, "detect",
                 f"caller ID {r['caller_id']} pickup fell {r['drop']:.3f} vs its own baseline",
                 {"finding": r})
        if fresh:
            with conn:
                set_meta(conn, f"did_bad_{wf}", json.dumps(first_bad, sort_keys=True))
        with conn:
            set_meta(conn, f"rot_day_{wf}", day)       # evaluated for today
        if not first_bad:
            continue
        alloc = {c: d["caller_id"] for c, d in cur["config"].get("allocations", {}).items()
                 if d.get("caller_id")}
        healthy = {c for c, bands in base.items() if c not in first_bad
                   and sum(d for d, _ in bands.values()) >= MIN_HISTORY}
        cap = pol["auto_apply"]["max_shift"] - SHIFT_MARGIN if auto else None
        new_alloc, info = plan_shift(alloc, set(first_bad), healthy, cap)
        if new_alloc is None:
            if info != NOTHING:
                _log(conn, ts, wf, "skip", f"caller ID {sorted(first_bad)} is bad but: {info}", {})
            continue
        new_cfg = copy.deepcopy(cur["config"])
        for cohort, dist in new_alloc.items():
            new_cfg["allocations"][cohort]["caller_id"] = dist
        bad_txt = ", ".join(sorted(first_bad))
        summary = f"move traffic off degraded caller ID {bad_txt}"
        by_id = {r["caller_id"]: r for r in rows if "recent" in r}
        rationale = (f"{bad_txt} pickup is far below its own earlier level "
                     + "; ".join(f"{c}: {r['recent']:.3f} vs {r['baseline']:.3f}"
                                 for c, r in by_id.items() if c in first_bad)
                     + f". Moving {info} of traffic per cohort to healthy IDs with history.")
        if auto:
            pid, why = gov.auto_apply(wf, cur["version"], new_cfg, cur["config"], summary,
                                      rationale, ts, pol)
        else:
            good = [r["recent"] for c, r in by_id.items() if c not in first_bad]
            badp = [r["recent"] for c, r in by_id.items() if c in first_bad]
            gain = (max(good) - min(badp)) if good and badp else 0.0
            impact = round(min(1.0, max(0.0, max(info.values()) * gain)), 4)
            n_leads = conn.execute("SELECT COUNT(*) FROM leads WHERE workflow_id=?", (wf,)).fetchone()[0]
            pid, why = gov.propose(
                wf, cur["version"], new_cfg, summary, rationale, ts, pol,
                diff={"allocations.caller_id": f"move {info} off {bad_txt}"},
                affected_leads=n_leads,
                dry_run={"method": "own pickup per caller ID, last complete day vs frozen baseline",
                         "pickup_by_id": {c: [r["recent"], r["baseline"]] for c, r in by_id.items()},
                         "moves": info},
                impact_score=impact)
        if pid is None:
            _log(conn, ts, wf, "skip", f"caller-ID move not sent: {why}", {"moves": info})