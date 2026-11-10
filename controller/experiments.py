"""Variant experiments on voice and welcome message. Winners are picked by the tests in
stats.py, never by judgement. State lives in the database, so a restart resumes exactly.

Lifecycle: none -> proposed -> running -> closing -> monitoring -> (rolling_back ->) done

Supervisor edits: if a client supervisor changes a dimension we are testing, that dimension is
dropped from the experiment (its comparison is contaminated) and we never write it again.
"""
from __future__ import annotations

import copy
import json
from datetime import date

from controller.audit import log_decision
from controller.governance import in_send_window
from controller.stats import benjamini_hochberg, diff_ci, two_prop_test
from controller.store import get_meta, set_meta

DIMS = {"welcome_message": "welcome", "voice": "voice"}   # config key -> agg_variant column
ARMS = 3             # control plus at most 2 candidates per dimension
MAX_ATTEMPTS = 3     # start requests per workflow
MIN_N = 300          # observations per arm before a result counts
MIN_EFFECT = 0.02    # absolute lift worth an approver's attention
Q = 0.025            # stricter than 0.05 because we look once a day
MAX_DAYS = 5         # complete days of data before we give up and revert
HOLDBACK = 0.10      # share of traffic left on the old option after a promotion
HOLD_MIN_N = 100     # holdback observations needed before the monitor may decide
ROLLBACK_CONF = 0.8  # two-sided 80% interval = one-sided 90% bound

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


def final_config(cfg: dict, arms: dict, winners: dict, holdback: float = 0.0) -> dict:
    """Winners get 1-holdback, the old option keeps `holdback`. No winner: back to control.
    Only dimensions in `arms` are written; everything else is left exactly as it is live."""
    new = copy.deepcopy(cfg)
    d = new["allocations"].setdefault("default", {})
    for dim, a in arms.items():
        w = winners.get(dim)
        if w and holdback > 0:
            d[dim] = {w: round(1 - holdback, 4), a["control"]: round(holdback, 4)}
        else:
            d[dim] = {(w or a["control"]): 1.0}
    return new


def supervisor_dims(log_rows, owned=DIMS) -> set:
    """log_rows: [(actor, changed_dims_json)] for config changes after the experiment started.
    Returns the dimensions we own that a supervisor changed."""
    out: set = set()
    for actor, dims_json in log_rows:
        if actor == "supervisor":
            out |= set(json.loads(dims_json)) & set(owned)
    return out


def guardrail(objective: dict):
    for k, v in (objective.get("guardrail") or {}).items():
        if k.endswith("_max_drop"):
            return k[: -len("_max_drop")], v
    return None


def find_winners(counts: dict, arms: dict, primary: str, guard, recent: dict | None = None, *,
                 min_n=MIN_N, min_effect=MIN_EFFECT, q=Q):
    """counts: {dim: {arm: (dials, connected, engaged)}} over all complete days.
    recent: the same for the latest complete day only; a winner must not be behind there.
    Returns (rows, {dim: best arm})."""
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
                    guard_ok = False    # unknown guardrail: fail closed
                else:
                    gx, gn = METRICS[gname](arm)
                    gcx, gcn = METRICS[gname](ctl)
                    if gn and gcn:
                        worse = two_prop_test(gcx, gcn, gx, gn)["p"] < 0.05
                        guard_ok = (gx / gn - gcx / gcn) > -drop and not worse
            recent_ok, recent_diff = True, None
            if recent is not None:
                rc = recent.get(dim, {})
                rx, rn = pm(rc.get(cand, (0, 0, 0)))
                rcx, rcn = pm(rc.get(a["control"], (0, 0, 0)))
                if rn == 0 or rcn == 0:
                    recent_ok = False    # no recent evidence: fail closed
                else:
                    recent_diff = rx / rn - rcx / rcn
                    recent_ok = recent_diff >= 0
            enough = n >= min_n and nc >= min_n
            rows.append({"dim": dim, "arm": cand, "control": a["control"], "diff": t["diff"],
                         "p": t["p"] if enough else 1.0, "n": n, "n_control": nc,
                         "guard_ok": guard_ok, "enough": enough,
                         "recent_ok": recent_ok, "recent_diff": recent_diff})
    keep = benjamini_hochberg([r["p"] for r in rows], q)
    winners: dict = {}
    for r, k in zip(rows, keep):
        r["wins"] = bool(k and r["enough"] and r["guard_ok"] and r["recent_ok"]
                         and r["diff"] >= min_effect)
        if r["wins"] and (r["dim"] not in winners or r["diff"] > winners[r["dim"]][1]):
            winners[r["dim"]] = (r["arm"], r["diff"])
    return rows, {d: v[0] for d, v in winners.items()}


def monitor_check(counts: dict, winners: dict, arms: dict, primary: str,
                  hold_min_n: int = HOLD_MIN_N, conf: float = ROLLBACK_CONF,
                  min_effect: float = MIN_EFFECT):
    """Compare each promoted option with its holdback. A dimension is 'decayed' only when the
    interval on the lift lies entirely below the minimum worthwhile effect."""
    pm = METRICS[primary]
    rows, decayed = [], []
    for dim, win in winners.items():
        c = counts.get(dim, {})
        xw, nw = pm(c.get(win, (0, 0, 0)))
        xc, nc = pm(c.get(arms[dim]["control"], (0, 0, 0)))
        if nw == 0 or nc < hold_min_n:
            rows.append({"dim": dim, "arm": win, "decided": False, "n": nw, "n_holdback": nc})
            continue
        diff = xw / nw - xc / nc
        lo, hi = diff_ci(xw, nw, xc, nc, conf)
        bad = hi < min_effect
        rows.append({"dim": dim, "arm": win, "decided": True, "diff": diff, "ci": [lo, hi],
                     "n": nw, "n_holdback": nc, "decayed": bad})
        if bad:
            decayed.append(dim)
    return rows, decayed


# ---------- state and database ----------
def arm_counts(conn, wf, col, first_day, last_day):
    q = (f"SELECT {col}, SUM(dials), SUM(connected), SUM(engaged) FROM agg_variant "
         "WHERE workflow_id=? AND day BETWEEN ? AND ? GROUP BY " + col)   # col is from DIMS
    return {a: (d, k, e) for a, d, k, e in conn.execute(q, (wf, first_day, last_day))}


def _load(conn, wf):
    raw = get_meta(conn, f"exp_{wf}")
    return json.loads(raw) if raw else {"state": "none", "attempts": 0}


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


def _guard(conn, wf, exp, ts) -> bool:
    """Drop any dimension a supervisor changed since the experiment began. Returns True if the
    experiment has nothing left to test (it is closed here, with no proposal)."""
    row = conn.execute("SELECT ts FROM config_log WHERE workflow_id=? AND proposal_id=?",
                       (wf, exp.get("start_pid"))).fetchone()
    since = row[0] if row else exp.get("started_ts")
    if since is None:
        return False
    log = conn.execute("SELECT actor, changed_dims FROM config_log WHERE workflow_id=? AND ts>?",
                       (wf, since)).fetchall()
    touched = supervisor_dims(log) & set(exp.get("arms", {}))
    if not touched:
        return False
    for d in touched:
        exp["arms"].pop(d, None)
        exp.get("winners", {}).pop(d, None)
    note = (f"supervisor changed {', '.join(sorted(touched))} during the experiment; "
            "leaving it exactly as the supervisor set it and dropping it from the comparison")
    if not exp["arms"]:
        exp["state"] = "done"
        note += "; nothing left to test, experiment closed"
    _commit(conn, wf, exp, ts, "skip", note, {"touched": sorted(touched)})
    return not exp["arms"]


# ---------- the per-tick step ----------
def experiment_step(conn, client, gov, st):
    ts, day = st["ts"], st["ts"][:10]
    today = (date.fromisoformat(day) - date.fromisoformat(get_meta(conn, "d0"))).days
    for w in client.workflows():
        wf = w["workflow_id"]
        exp = _load(conn, wf)
        s = exp["state"]
        if s in ("proposed", "closing", "rolling_back"):
            _follow(conn, wf, exp, ts, today)
        elif s == "none":
            _start(conn, client, gov, wf, exp, ts, day)
        elif s == "running":
            _review(conn, client, gov, wf, exp, ts, today)
        elif s == "monitoring":
            _monitor(conn, client, gov, wf, exp, ts, today)


def _follow(conn, wf, exp, ts, today):
    ps = _pstate(conn, exp["pid"])
    if ps in (None, "drafted", "submitted", "approved"):
        return   # still in flight
    s = exp["state"]
    if s == "proposed":
        if ps == "applied":
            exp.update(state="running", start_day=today + 1, started_ts=ts)
            note = f"experiment live; counting complete days from day {today + 1}"
        else:
            exp.update(state="none", attempts=exp["attempts"] + 1)
            note = f"start request ended as {ps}; will retry"
    elif s == "closing":
        if ps == "applied" and exp.get("winners"):
            exp.update(state="monitoring", mon_day=today + 1)
            note = (f"promotion live with a {HOLDBACK:.0%} holdback; "
                    f"monitoring from day {today + 1}")
        elif ps == "applied":
            exp["state"], note = "done", "reverted to control; experiment closed"
        else:
            exp["state"], note = "running", f"closing request ended as {ps}; back to review"
    else:   # rolling_back
        if ps == "applied":
            exp["winners"] = exp.pop("after_rollback", {})
            exp.update(state="monitoring" if exp["winners"] else "done", mon_day=today + 1)
            note = "rollback live"
        else:
            exp.pop("after_rollback", None)
            exp["state"], note = "monitoring", f"rollback request ended as {ps}; will re-check"
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
        return   # cap or window: retry on a later tick
    exp.update(state="proposed", pid=pid, start_pid=pid, arms=arms, last_try_day=day)
    _commit(conn, wf, exp, ts, "experiment", f"proposed experiment: {desc}", {"proposal_id": pid})


def _review(conn, client, gov, wf, exp, ts, today):
    days = today - exp["start_day"]   # complete days of data so far
    if days < 1 or exp.get("last_eval_day") == today or gov.in_flight(wf):
        return
    detail = client.workflow(wf)
    pol = detail["governance"]
    if not in_send_window(pol, ts):
        return
    if _guard(conn, wf, exp, ts):
        return
    primary = detail["objective"]["primary"]
    guard = guardrail(detail["objective"])
    counts = {dim: arm_counts(conn, wf, DIMS[dim], exp["start_day"], today - 1)
              for dim in exp["arms"]}
    recent = {dim: arm_counts(conn, wf, DIMS[dim], today - 1, today - 1) for dim in exp["arms"]}
    rows, confirmed = find_winners(counts, exp["arms"], primary, guard, recent)
    exp["last_eval_day"] = today
    ev = {"days_of_data": days, "primary": primary, "guardrail": guard, "rows": rows,
          "confirmed": confirmed}
    if not confirmed and days < MAX_DAYS:
        _commit(conn, wf, exp, ts, "verify", f"day {days}: no confirmed winner yet", ev)
        return
    cur = client.config(wf)
    final = final_config(cur["config"], exp["arms"], confirmed, HOLDBACK)
    lift = round(sum(r["diff"] for r in rows if confirmed.get(r["dim"]) == r["arm"]), 4)
    what = (", ".join(f"{d}={a}" for d, a in confirmed.items()) if confirmed
            else "no winner by the deadline: revert to control")
    pid, why = gov.propose(
        wf, cur["version"], final, f"close experiment: {what}",
        f"After {days} complete days, {what}. Chosen by one-sided two-proportion tests with "
        f"Benjamini-Hochberg (q={Q}), lift >= {MIN_EFFECT}, guardrail respected, and the latest "
        f"complete day not behind control. Winners keep a {HOLDBACK:.0%} holdback on the old "
        "option so decay can be detected. Only dimensions still under test are changed.",
        ts, pol,
        diff={f"allocations.default.{d}": "winner (with holdback) or back to control" for d in exp["arms"]},
        affected_leads=_n_leads(conn, wf),
        dry_run={"evidence": rows, "confirmed": confirmed, "primary": primary},
        impact_score=lift)
    if pid is None:
        exp["last_eval_day"] = None   # retry on a later tick
        _commit(conn, wf, exp, ts, "verify", f"ready to close but could not send: {why}", ev)
        return
    exp.update(state="closing", pid=pid, winners=confirmed)
    ev["proposal_id"] = pid
    _commit(conn, wf, exp, ts, "experiment", f"proposed closing: {what}", ev)


def _monitor(conn, client, gov, wf, exp, ts, today):
    n_days = today - exp["mon_day"]
    if n_days < 1 or exp.get("last_eval_day") == today or gov.in_flight(wf):
        return
    detail = client.workflow(wf)
    pol = detail["governance"]
    if not in_send_window(pol, ts):
        return
    if _guard(conn, wf, exp, ts) or not exp.get("winners"):
        if exp.get("state") != "done":
            exp["state"] = "done"
            _commit(conn, wf, exp, ts, "verify", "no promoted dimension left to monitor", {})
        return
    primary = detail["objective"]["primary"]
    counts = {dim: arm_counts(conn, wf, DIMS[dim], exp["mon_day"], today - 1)
              for dim in exp["winners"]}
    rows, decayed = monitor_check(counts, exp["winners"], exp["arms"], primary)
    ev = {"monitor_days": n_days, "primary": primary, "rows": rows, "decayed": decayed}
    if not decayed:
        exp["last_eval_day"] = today
        _commit(conn, wf, exp, ts, "verify", f"monitor day {n_days}: promotion holds or undecided", ev)
        return
    remaining = {d: a for d, a in exp["winners"].items() if d not in decayed}
    cur = client.config(wf)
    owned = {d: exp["arms"][d] for d in exp["winners"]}      # only what we still own
    back = final_config(cur["config"], owned, remaining, HOLDBACK)
    what = ", ".join(f"{d}: back to {exp['arms'][d]['control']}" for d in decayed)
    pid, why = gov.propose(
        wf, cur["version"], back, f"rollback: {what}",
        f"After {n_days} complete days, the promoted option's lift over its holdback is clearly "
        f"below {MIN_EFFECT} (80% interval entirely below). Reverting to the old option.",
        ts, pol,
        diff={f"allocations.default.{d}": "back to control" for d in decayed},
        affected_leads=_n_leads(conn, wf),
        dry_run={"evidence": rows, "primary": primary},
        impact_score=0.0)
    if pid is None:
        _commit(conn, wf, exp, ts, "verify", f"decay detected but could not send: {why}", ev)
        return   # retry on a later tick
    exp.update(state="rolling_back", pid=pid, after_rollback=remaining, last_eval_day=today)
    ev["proposal_id"] = pid
    _commit(conn, wf, exp, ts, "experiment", f"proposed rollback: {what}", ev)