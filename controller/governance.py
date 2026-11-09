"""Governance client: every change is a persisted proposal moving through a state machine.

Write-ahead: a proposal is saved as 'drafted' BEFORE any network call. After a crash we look
the proposal_id up on the simulator instead of blindly re-sending, so nothing is duplicated.
Only one change per workflow is in flight at a time: an auto-apply would make a pending or
approved request stale, and a stale approval just lapses.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

import httpx

from controller.api import SimError
from controller.audit import log_decision

IN_FLIGHT = ("drafted", "submitted", "approved")
ALLOC_DIMS = ("welcome_message", "voice", "caller_id")


def changed_dims(old: dict, new: dict) -> list[str]:
    """Which dimensions differ between two configs, named like the simulator names them."""
    dims = [d for d in ("cohorts", "prompt_version", "schedule") if old.get(d) != new.get(d)]
    oa, na = old.get("allocations", {}), new.get("allocations", {})
    for d in ALLOC_DIMS:
        if any((oa.get(c) or {}).get(d) != (na.get(c) or {}).get(d) for c in set(oa) | set(na)):
            dims.append(d)
    return dims


def can_auto_apply(gov: dict, dims: list[str]) -> bool:
    aa = gov["auto_apply"]
    return bool(dims) and aa["enabled"] and set(dims) <= set(aa["allowed_dims"])


def in_send_window(gov: dict, ts: str) -> bool:
    """Send only when a decision (up to max latency later) still lands inside approver hours."""
    t = datetime.fromisoformat(ts)
    start, end = gov["approver_hours"]
    latest = end * 60 - gov["approver_latency_minutes"][1]
    return start * 60 <= t.hour * 60 + t.minute <= latest


class Governance:
    def __init__(self, conn, client):
        self.conn, self.client = conn, client

    # ---- queries ----
    def in_flight(self, wf: str):
        return self.conn.execute(
            "SELECT proposal_id, state FROM proposals WHERE workflow_id=? AND state IN (?,?,?)",
            (wf, *IN_FLIGHT)).fetchone()

    def _requests_last_24h(self, wf: str, ts: str) -> int:
        since = (datetime.fromisoformat(ts) - timedelta(hours=24)).isoformat()
        return self.conn.execute(
            "SELECT COUNT(*) FROM proposals WHERE workflow_id=? AND kind='approval' "
            "AND state!='failed' AND created_ts>?", (wf, since)).fetchone()[0]

    def _detail(self, pid: str) -> dict:
        return json.loads(self.conn.execute(
            "SELECT detail FROM proposals WHERE proposal_id=?", (pid,)).fetchone()[0])

    # ---- state changes: the row and its audit record commit together ----
    def _set(self, pid, wf, ts, state, summary, extra=None, approval_id=None):
        d = self._detail(pid)
        d.update(extra or {})
        with self.conn:
            self.conn.execute(
                "UPDATE proposals SET state=?, updated_ts=?, detail=?, "
                "approval_id=COALESCE(?, approval_id) WHERE proposal_id=?",
                (state, ts, json.dumps(d, sort_keys=True), approval_id, pid))
            log_decision(self.conn, ts, wf, state, summary,
                         {"proposal_id": pid, "approval_id": approval_id, **(extra or {})})

    def _draft(self, kind, wf, base, config, summary, rationale, ts, request) -> str:
        digest = hashlib.sha1(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]
        prefix = f"{wf}-v{base}-{digest}"
        n = self.conn.execute("SELECT COUNT(*) FROM proposals WHERE proposal_id LIKE ?",
                              (prefix + "-%",)).fetchone()[0]
        pid = f"{prefix}-{n + 1}"
        request = {**request, "proposal_id": pid, "workflow_id": wf, "base_version": base,
                   "proposed_config": config, "change_summary": summary, "rationale": rationale}
        with self.conn:
            self.conn.execute("INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?)",
                              (pid, wf, kind, base, "drafted", None, ts, ts,
                               json.dumps({"request": request}, sort_keys=True)))
            log_decision(self.conn, ts, wf, "propose", summary,
                         {"proposal_id": pid, "kind": kind, "rationale": rationale})
        return pid

    # ---- entry points ----
    def propose(self, wf, base, config, summary, rationale, ts, gov, *, diff, affected_leads,
                dry_run, impact_score):
        """Queue an approval request. Returns (proposal_id | None, reason_if_none)."""
        if self.in_flight(wf):
            return None, "another change is already in flight"
        if not in_send_window(gov, ts):
            return None, "outside the window in which a decision can land in approver hours"
        if self._requests_last_24h(wf, ts) >= gov["max_requests_per_24h"]:
            return None, "request cap for the last 24h reached"
        pid = self._draft("approval", wf, base, config, summary, rationale, ts, {
            "diff": diff, "affected_leads": affected_leads, "dry_run": dry_run,
            "impact_score": impact_score, "expires_in_hours": gov["proposal_ttl_hours"]})
        self._submit(pid, wf, ts)
        return pid, ""

    def auto_apply(self, wf, base, config, old_config, summary, rationale, ts, gov):
        """Apply without approval, only when the policy allows exactly these dimensions."""
        dims = changed_dims(old_config, config)
        if not can_auto_apply(gov, dims):
            return None, f"policy does not allow auto-apply for {dims}"
        if self.in_flight(wf):
            return None, "another change is already in flight"
        pid = self._draft("auto", wf, base, config, summary, rationale, ts, {})
        self._put(pid, wf, ts)
        return pid, ""

    def sync(self, ts: str) -> None:
        """Advance every in-flight proposal one step. Call once per tick."""
        rows = self.conn.execute(
            "SELECT proposal_id, workflow_id, kind, state, approval_id FROM proposals "
            "WHERE state IN (?,?,?) ORDER BY created_ts", IN_FLIGHT).fetchall()
        for pid, wf, kind, state, aid in rows:
            if kind == "auto":
                self._put(pid, wf, ts)
            elif state == "drafted":
                self._submit(pid, wf, ts)
            else:
                self._poll(pid, wf, aid, ts)

    # ---- network steps (each safe to repeat after a crash) ----
    def _submit(self, pid, wf, ts):
        found = next((a for a in self.client.approvals(wf) if a["proposal_id"] == pid), None)
        if found is None:
            try:
                found = self.client.submit_approval(self._detail(pid)["request"])
            except SimError as e:
                self._set(pid, wf, ts, "failed", f"simulator refused the request ({e.status})",
                          {"status": e.status, "body": e.body})
                return
            except httpx.TransportError:
                return                       # unknown outcome: next tick finds it by listing
        self._set(pid, wf, ts, "submitted", f"sent as {found['approval_id']}, "
                  f"expires {found.get('expires_at')}", {"expires_at": found.get("expires_at")},
                  approval_id=found["approval_id"])

    def _poll(self, pid, wf, aid, ts):
        a = self.client.approval(aid)
        st = a["status"]
        if st == "pending":
            return
        if st in ("rejected", "expired", "lapsed", "applied"):
            self._set(pid, wf, ts, st, f"simulator reports {st}", {"reasons": a.get("reasons")})
            return
        if st == "approved":
            self._set(pid, wf, ts, "approved", "approved, applying now",
                      {"apply_by": a.get("apply_by")})
            try:
                res = self.client.apply(wf, aid)
            except SimError as e:
                if e.status == 409:
                    self._set(pid, wf, ts, "stale", "base version moved; must re-propose",
                              {"body": e.body})
                elif e.status == 410:
                    self._set(pid, wf, ts, "lapsed", "apply window missed", {"body": e.body})
                else:
                    self._set(pid, wf, ts, "failed", f"apply refused ({e.status})",
                              {"body": e.body})
            except httpx.TransportError:
                return                       # next tick: GET will say applied or still approved
            else:
                self._set(pid, wf, ts, "applied", f"live as v{res['version']}",
                          {"version": res["version"], "dims": res["changed_dims"]})

    def _put(self, pid, wf, ts):
        hist = self.client.config_history(wf)
        done = next((h for h in hist if h.get("proposal_id") == pid), None)
        if done is None:
            req = self._detail(pid)["request"]
            try:
                done = self.client.put_config(wf, {k: req[k] for k in
                    ("proposal_id", "base_version", "proposed_config", "rationale")})
            except SimError as e:
                self._set(pid, wf, ts, "stale" if e.status == 409 else "failed",
                          f"auto-apply refused ({e.status})", {"body": e.body})
                return
            except httpx.TransportError:
                return
        self._set(pid, wf, ts, "applied", f"auto-applied as v{done['version']}",
                  {"version": done["version"]})