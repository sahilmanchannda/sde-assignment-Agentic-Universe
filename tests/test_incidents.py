"""Hallucination incident response: detect -> validate revert -> propose with evidence -> verify.
Fails safe: an unexpected API response is logged, never guessed at."""
from __future__ import annotations

import copy
import json
from datetime import date

from controller.audit import log_decision
from controller.governance import in_send_window
from controller.halluc import check_prompts
from controller.store import get_meta, set_meta
from controller.validation import affordable_n, cost


def prompt_counts(conn, wf, first_day, last_day):
    return {p: (c, h) for p, c, h in conn.execute(
        "SELECT prompt, SUM(connected), SUM(halluc) FROM agg_variant "
        "WHERE workflow_id=? AND day BETWEEN ? AND ? GROUP BY prompt",
        (wf, first_day, last_day))}


def pick_reference(recent, history, previous_prompt):
    """Reference rate per prompt: its own history, else the previous prompt's."""
    ref = dict(history)
    for p in recent:
        if ref.get(p, (0, 0))[0] == 0 and previous_prompt in history:
            ref[p] = history[previous_prompt]
    return ref


def _prompt_of(cfg):
    return cfg.get("prompt_version")


def _log(conn, ts, wf, kind, note, detail=None):
    with conn:
        log_decision(conn, ts, wf, kind, note, detail or {})


def incident_step(conn, client, gov, st):
    ts, day = st["ts"], st["ts"][:10]
    today = (date.fromisoformat(day) - date.fromisoformat(get_meta(conn, "d0"))).days
    for w in client.workflows():
        wf = w["workflow_id"]
        if get_meta(conn, f"inc_day_{wf}") == day or gov.in_flight(wf):
            continue
        detail = client.workflow(wf)
        pol = detail["governance"]
        if not in_send_window(pol, ts):
            continue
        with conn:
            set_meta(conn, f"inc_day_{wf}", day)
        cur = client.config(wf)
        current = _prompt_of(cur["config"])
        recent = prompt_counts(conn, wf, today - 1, today - 1)
        history = prompt_counts(conn, wf, -14, today - 2)
        prev = conn.execute(
            "SELECT prompt FROM agg_variant WHERE workflow_id=? AND prompt!=? "
            "ORDER BY day DESC LIMIT 1", (wf, current)).fetchone()
        ref = pick_reference({current: recent.get(current, (0, 0))}, history,
                             prev[0] if prev else None)
        rows = check_prompts({current: recent.get(current, (0, 0))}, ref)
        if not rows or not rows[0]["flagged"]:
            continue
        _respond(conn, client, gov, wf, cur, current, prev[0] if prev else None,
                 rows[0], detail, pol, ts)


def _validate(conn, client, wf, prompt, n, ts, pol):
    try:
        res = client.validate(wf, prompt, n)
    except Exception as e:                        # 402 out of credits, 4xx, network
        _log(conn, ts, wf, "failed", f"validation of {prompt} failed: {e}", {})
        return None
    run_id, rate = res.get("validation_run_id") or res.get("run_id"), res.get("pass_rate")
    if run_id is None or rate is None:
        _log(conn, ts, wf, "failed", "unexpected validation response", {"body": res})
        return None
    ok = rate >= pol.get("min_validation_pass_rate", 0.97)
    _log(conn, ts, wf, "verify", f"validated {prompt}: pass_rate {rate} ({'ok' if ok else 'below threshold'})",
         {"run_id": run_id, "n": n, "pass_rate": rate, "prompt": prompt})
    return {"run_id": run_id, "pass_rate": rate, "ok": ok}


def _respond(conn, client, gov, wf, cur, current, target, row, detail, pol, ts):
    _log(conn, ts, wf, "detect", f"hallucination rate on {current} above reference", {"finding": row})
    credits = client.state()["credits_remaining"]
    spent = 0.0
    candidates = [target] if target else []
    tried = []
    for stage in (0, 1):
        for prompt in candidates:
            n = affordable_n(credits - spent, spent)
            if n == 0:
                _log(conn, ts, wf, "skip", "not enough credit budget to validate", {"spent": spent})
                return
            v = _validate(conn, client, wf, prompt, n, ts, pol)
            spent += cost(n)
            tried.append(prompt)
            if v and v["ok"]:
                new = copy.deepcopy(cur["config"])
                new["prompt_version"] = prompt
                pid, why = gov.propose(
                    wf, cur["version"], new, f"prompt fix: {current} -> {prompt}",
                    f"{current} shows a clearly elevated hallucination flag rate. {prompt} passed "
                    f"validation ({v['pass_rate']}).", ts, pol,
                    diff={"prompt_version": f"{current} -> {prompt}"},
                    affected_leads=conn.execute("SELECT COUNT(*) FROM leads WHERE workflow_id=?",
                                                (wf,)).fetchone()[0],
                    dry_run={"finding": row, "validation": v}, impact_score=0.5,
                    evidence={"validation_run_id": v["run_id"]})
                _log(conn, ts, wf, "propose" if pid else "skip",
                     f"proposed fix to {prompt}" if pid else f"could not send fix: {why}",
                     {"proposal_id": pid})
                return
        if stage == 1:
            break
        # revert target missing or failed: ask the LLM once
        try:
            fixes = client.suggest_fixes(wf, f"{current} has an elevated hallucination rate")
        except Exception as e:
            _log(conn, ts, wf, "failed", f"suggest-fixes failed: {e}", {})
            return
        spent += 3
        raw = fixes.get("fixes") or fixes.get("suggestions") or []
        candidates = [f.get("prompt_version") for f in raw
                      if isinstance(f, dict) and f.get("prompt_version") not in (current, *tried)]
        if not candidates:
            _log(conn, ts, wf, "failed", "no usable fix candidates", {"body": fixes})
            return
    _log(conn, ts, wf, "failed", "no candidate passed validation", {"tried": tried})