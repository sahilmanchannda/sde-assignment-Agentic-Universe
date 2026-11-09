"""Variant experiments on voice and welcome message. Winners are picked by the tests in
stats.py, never by judgement. State lives in the database, so a restart resumes exactly."""
from __future__ import annotations

import copy
import json
from datetime import date

from controller.audit import log_decision
from controller.governance import in_send_window
from controller.stats import benjamini_hochberg, two_prop_test
from controller.store import get_meta, set_meta

DIMS = {"welcome_message": "welcome", "voice": "voice"}   # config key -> agg_variant column
ARMS = 3             # control plus at most 2 candidates per dimension
MAX_ATTEMPTS = 3     # start requests per workflow
MIN_N = 300          # observations per arm before a result counts
MIN_EFFECT = 0.02    # absolute lift worth an approver's attention
Q = 0.025            # stricter than 0.05 because we look once a day
STREAK = 2           # consecutive daily checks a winner must survive
MAX_DAYS = 5         # complete days of data before we give up and revert

# counts tuple is (dials, connected, engaged) -> (successes, trials)
METRICS = {"pickup_rate": lambda t: (t[1], t[0]),
           "engagement_rate": lambda t: (t[2], t[1])}


# ---------- pure logic (unit-tested) ----------
def plan_arms(default_alloc: dict, options: dict, max_arms: int = ARMS) -> dict:
    arms = {}
    for dim in DIMS:
        opts = options.get(dim, [])
        cur = default_alloc.get(dim) or {}
        if len(opts) < 2 or len(cur) != 1:      # nothing to test, or already a mix: leave alone
            continue
        control = next(iter(cur))
        arms[dim] = {"control": control,
                     "candidates": [o for o in opts if o != control][: max_arms - 1]}
    return arms


def split_config(cfg: dict, arms: dict) -> dict:
    new = copy.deepcopy(cfg)
    d = new["allocations"].setdefault("default", {})
    for dim, a in arms.items():
        names = [a["control"], *a["candidates"]]
        d[dim] = {n: round(1 / len(names), 4) for n in names}
    return new


def final_config(cfg: dict, arms: dict, winners: dict) -> dict:
    new = copy.deepcopy(cfg)
    d = new["allocations"].setdefault("default", {})
    for dim, a in arms.items():
        d[dim] = {winners.get(dim, a["control"]): 1.0}
    return new


def guardrail(objective: dict):
    for k, v in (objective.get("guardrail") or {}).items():
        if k.endswith("_max_drop"):
            return k[: -len("_max_drop")], v
    return None


def find_winners(counts: dict, arms: dict, primary: str, guard, *, min_n=MIN_N,
                 min_effect=MIN_EFFECT, q=Q):
    """counts: {dim: {arm: (dials, connected, engaged)}}. Returns (rows, {dim: best arm})."""
    pm = METRICS[primary]
    rows = []
    for dim, a in arms.items():
        c = counts.get(dim, {})
        ctl = c.get(a["control"], (0, 0, 0))
        xc, nc = pm(ctl)
        for cand in a["candidates"]:
            arm = c.get(cand, (0, 0, 0))
            x, n = pm(arm)
            t = two_prop_test(x, n, xc, nc)
            guard_ok = True
            if guard:
                gname, drop = guard
                if gname not in METRICS:
                    guard_ok = False                      # unknown guardrail: fail closed
                else:
                    gx, gn = METRICS[gname](arm)
                    gcx, gcn = METRICS[gname](ctl)
                    if gn and gcn:
                        worse = two_prop_test(gcx, gcn, gx, gn)["p"] < 0.05
                        guard_ok = (gx / gn - gcx / gcn) > -drop and not worse
            enough = n >= min_n and nc >= min_n
            rows.append({"dim": dim, "arm": cand, "control": a["control"], "diff": t["diff"],
                         "p": t["p"] if enough else 1.0, "n": n, "n_control": nc,
                         "guard_ok": guard_ok, "enough": enough})
    keep = benjamini_hochberg([r["p"] for r in rows], q)
    winners: dict = {}
    for r, k in zip(rows, keep):
        r["wins"] = bool(k and r["enough"] and r["guard_ok"] and r["diff"] >= min_effect)
        if r["wins"] and (r["dim"] not in winners or r["diff"] > winners[r["dim"]][1]):
            winners[r["dim"]] = (r["arm"], r["diff"])
    return rows, {d: v[0] for d, v in winners.items()}


# ---------- state and database ----------
def arm_counts(conn, wf, col, first_day, last_day):
    q = (f"SELECT {col}, SUM(dials), SUM(connected), SUM(engaged) FROM agg_variant "
         "WHERE workflow_id=? AND day BETWEEN ? AND ? GROUP BY " + col)   # col is from DIMS
    return {a: (d, k, e) for a, d, k, e in conn.execute(q, (wf, first_day, last_day))}


def _load(conn, wf):
    raw = get_meta(conn, f"exp_{wf}")
    return json.loads(raw) if raw else {"state": "none", "attempts": 0, "streak": {}}


def _commit(conn, wf, exp, ts, kind, note, detail=None):
    """Experiment state and its audit record commit together."""
    with conn:
        set_meta(conn, f"exp_{wf}", json.dumps(exp, sort_keys=True))
        log_decision(conn, ts, wf, kind, note, detail or {})


def _pstate(conn, pid):
    row = conn.execute("SELECT state FROM proposals WHERE proposal_id=?", (pid,)).fetchone()
    return row[0] if row else None


def _n_leads(conn, wf):
    return conn.execute("SELECT COUNT(*) FROM leads WHERE workflow_id=?", (wf,)).fetchone()[0]


# ---------- the per-tick step ----------
def experiment_step(conn, client, gov, st):
    ts, day = st["ts"], st["ts"][:10]
    today = (date.fromisoformat(day) - date.fromisoformat(get_meta(conn, "d0"))).days
    for w in client.workflows():
        wf = w["workflow_id"]
        exp = _load(conn, wf)
        if exp["state"] in ("proposed", "closing"):
            _follow(conn, wf, exp, ts, today)
        elif exp["state"] == "none":
            _start(conn, client, gov, wf, exp, ts, day)
        elif exp["state"] == "running":
            _review(conn, client, gov, wf, exp, ts, today)


def _follow(conn, wf, exp, ts, today):
    ps = _pstate(conn, exp["pid"])
    if ps in (None, "drafted", "submitted", "approved"):
        return                                           # still in flight
    if exp["state"] == "proposed":
        if ps == "applied":
            exp.update(state="running", start_day=today + 1, streak={})
            note = f"experiment live; counting complete days from day {today + 1}"
        else:
            exp.update(state="none", attempts=exp["attempts"] + 1)
            note = f"start request ended as {ps}; will retry"
    elif ps == "applied":
        exp["state"], note = "done", "final allocation live; experiment closed"
    else:
        exp["state"], note = "running", f"closing request ended as {ps}; back to review"
    _commit(conn, wf, exp, ts, "verify", note, {"proposal_id": exp["pid"], "proposal_state": ps})


def _start(conn, client, gov, wf, exp, ts, day):
    if exp["attempts"] >= MAX_ATTEMPTS or exp.get("last_try_day") == day or gov.in_flight(wf):
        return
    detail = client.workflow(wf)
    pol = detail["governance"]
    if not in_send_window(pol, ts):
        return
    if detail.get("mid_flight") != "allowed":
        exp.update(state="done", last_try_day=day)
        _commit(conn, wf, exp, ts, "skip",
                "no experiment: mid_flight locks allocations per campaign, so old campaigns "
                "would sit only in control and confound the comparison", {})
        return
    cur = client.config(wf)
    arms = plan_arms(cur["config"].get("allocations", {}).get("default", {}), detail["options"])
    if not arms:
        exp.update(state="done", last_try_day=day)
        _commit(conn, wf, exp, ts, "skip", "no testable dimension (single option or already a mix)", {})
        return
    new = split_config(cur["config"], arms)
    desc = "; ".join(f"{d}: {a['control']} vs {', '.join(a['candidates'])}" for d, a in arms.items())
    pid, why = gov.propose(
        wf, cur["version"], new, f"experiment: {desc}",
        "Equal-weight randomised test. Effects of these options are unknown (history only used "
        "the defaults). Winners are chosen by a pre-set statistical test, with a guardrail check.",
        ts, pol,
        diff={f"allocations.default.{d}": "split equally across control and candidates" for d in arms},
        affected_leads=_n_leads(conn, wf),
        dry_run={"design": arms, "method": "per-dial random split, equal weights",
                 "estimate": "none: this is a test, the effect is unknown"},
        impact_score=0.0)
    if pid is None:
        return                                           # cap or window: retry on a later tick
    exp.update(state="proposed", pid=pid, arms=arms, last_try_day=day)
    _commit(conn, wf, exp, ts, "experiment", f"proposed experiment: {desc}", {"proposal_id": pid})


def _review(conn, client, gov, wf, exp, ts, today):
    days = today - exp["start_day"]                      # complete days of data so far
    if days < 1 or exp.get("last_eval_day") == today or gov.in_flight(wf):
        return
    detail = client.workflow(wf)
    pol = detail["governance"]
    if not in_send_window(pol, ts):
        return
    primary = detail["objective"]["primary"]
    guard = guardrail(detail["objective"])
    counts = {dim: arm_counts(conn, wf, DIMS[dim], exp["start_day"], today - 1)
              for dim in exp["arms"]}
    rows, winners = find_winners(counts, exp["arms"], primary, guard)
    streak = {}
    for r in rows:
        k = f"{r['dim']}:{r['arm']}"
        streak[k] = (exp["streak"].get(k, 0) + 1) if r["wins"] else 0
    confirmed = {d: a for d, a in winners.items() if streak.get(f"{d}:{a}", 0) >= STREAK}
    exp.update(streak=streak, last_eval_day=today)
    ev = {"days_of_data": days, "primary": primary, "guardrail": guard, "rows": rows,
          "confirmed": confirmed}
    if not confirmed and days < MAX_DAYS:
        _commit(conn, wf, exp, ts, "verify", f"day {days}: no confirmed winner yet", ev)
        return
    cur = client.config(wf)
    final = final_config(cur["config"], exp["arms"], confirmed)
    lift = round(sum(r["diff"] for r in rows if confirmed.get(r["dim"]) == r["arm"]), 4)
    what = (", ".join(f"{d}={a}" for d, a in confirmed.items()) if confirmed
            else "no winner by the deadline: revert to control")
    pid, why = gov.propose(
        wf, cur["version"], final, f"close experiment: {what}",
        f"After {days} complete days, {what}. Chosen by one-sided two-proportion tests with "
        f"Benjamini-Hochberg (q={Q}), lift >= {MIN_EFFECT}, guardrail respected, held on "
        f"{STREAK} consecutive checks.",
        ts, pol,
        diff={f"allocations.default.{d}": "set to the winner or back to control" for d in exp["arms"]},
        affected_leads=_n_leads(conn, wf),
        dry_run={"evidence": rows, "confirmed": confirmed, "primary": primary},
        impact_score=lift)
    if pid is None:
        _commit(conn, wf, exp, ts, "verify", f"ready to close but could not send: {why}", ev)
        return
    exp.update(state="closing", pid=pid)
    ev["proposal_id"] = pid
    _commit(conn, wf, exp, ts, "experiment", f"proposed closing: {what}", ev)