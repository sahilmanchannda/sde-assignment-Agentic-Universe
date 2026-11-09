"""Decision log and audit queries. Depends only on sqlite3, so it is easy to test.

    python -m controller.audit why nw_renewal --at 2027-01-06T14:00
    python -m controller.audit timeline nw_renewal
"""
from __future__ import annotations

import argparse
import json
import sqlite3

from controller.store import connect

IST = "+05:30"   # all simulator timestamps are IST


def log_decision(conn: sqlite3.Connection, sim_ts: str, workflow_id: str, kind: str,
                 summary: str, detail: dict | None = None) -> int:
    """Record one decision. Call it inside the same transaction as the action it describes,
    so the log can never disagree with what actually happened."""
    cur = conn.execute(
        "INSERT INTO decisions(sim_ts, workflow_id, kind, summary, detail) VALUES (?,?,?,?,?)",
        (sim_ts, workflow_id, kind, summary, json.dumps(detail or {}, sort_keys=True)),
    )
    return cur.lastrowid


def _dicts(cur: sqlite3.Cursor) -> list[dict]:
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _norm(ts: str) -> str:
    """Accept 2027-01-06T14:00, 2027-01-06T14:00:00 or a full timestamp with offset."""
    if len(ts) == 16:
        return ts + ":00" + IST
    if len(ts) == 19:
        return ts + IST
    return ts


def why(conn: sqlite3.Connection, workflow_id: str, at_ts: str) -> dict:
    """Answer: which config change was live at `at_ts`, who made it, who approved it,
    what we decided around it, and what happened next."""
    at_ts = _norm(at_ts)
    rows = _dicts(conn.execute(
        "SELECT * FROM config_log WHERE workflow_id=? AND ts<=? ORDER BY version DESC LIMIT 1",
        (workflow_id, at_ts)))
    change = rows[0] if rows else None
    out = {"workflow_id": workflow_id, "at": at_ts, "change": change,
           "approval": None, "decisions": [], "after": [], "next_change": None}
    if change is None:
        return out
    if change["approval_id"]:
        a = _dicts(conn.execute("SELECT * FROM approval_log WHERE approval_id=?",
                                (change["approval_id"],)))
        out["approval"] = a[0] if a else None
    if change["proposal_id"]:
        out["decisions"] = _dicts(conn.execute(
            "SELECT * FROM decisions WHERE workflow_id=? "
            "AND json_extract(detail, '$.proposal_id')=? ORDER BY id",
            (workflow_id, change["proposal_id"])))
    nxt = _dicts(conn.execute(
        "SELECT * FROM config_log WHERE workflow_id=? AND version>? ORDER BY version LIMIT 1",
        (workflow_id, change["version"])))
    out["next_change"] = nxt[0] if nxt else None
    upper = nxt[0]["ts"] if nxt else "9999"
    out["after"] = _dicts(conn.execute(
        "SELECT * FROM decisions WHERE workflow_id=? AND sim_ts>? AND sim_ts<=? "
        "ORDER BY id LIMIT 20", (workflow_id, change["ts"], upper)))
    return out


def format_why(res: dict) -> str:
    c = res["change"]
    if c is None:
        return f"No config change recorded for {res['workflow_id']} at or before {res['at']}."
    lines = [f"{res['workflow_id']} was on config v{c['version']} at {res['at']}",
             f"  changed at {c['ts']} by {c['actor']}, dims {c['changed_dims']}"]
    if c["actor"] == "supervisor":
        lines.append("  (client supervisor edit: not initiated by the controller)")
    a = res["approval"]
    if a:
        lines.append(f"  approval {a['approval_id']}: {a['status']} at {a['ts']}, reasons {a['reasons']}")
    elif c["approval_id"]:
        lines.append(f"  approval {c['approval_id']}: decision not recorded")
    if c["proposal_id"]:
        lines.append(f"  proposal {c['proposal_id']} - our reasoning:")
        for d in res["decisions"]:
            lines.append(f"    [{d['sim_ts']}] {d['kind']}: {d['summary']}")
        if not res["decisions"]:
            lines.append("    (no decision records linked to this proposal)")
    lines.append("  what happened next:")
    for d in res["after"]:
        lines.append(f"    [{d['sim_ts']}] {d['kind']}: {d['summary']}")
    if not res["after"]:
        lines.append("    (no decisions recorded after this change)")
    n = res["next_change"]
    lines.append(f"  next config change: v{n['version']} at {n['ts']} by {n['actor']}"
                 if n else "  next config change: none")
    return "\n".join(lines)


def timeline(conn: sqlite3.Connection, workflow_id: str) -> list[dict]:
    return _dicts(conn.execute(
        "SELECT * FROM config_log WHERE workflow_id=? ORDER BY version", (workflow_id,)))


def main() -> None:
    ap = argparse.ArgumentParser(description="Query the controller's audit trail")
    ap.add_argument("command", choices=["why", "timeline"])
    ap.add_argument("workflow_id")
    ap.add_argument("--at", help="simulated time, e.g. 2027-01-06T14:00")
    ap.add_argument("--db", default="data/controller.db")
    a = ap.parse_args()
    conn = connect(a.db)
    if a.command == "why":
        if not a.at:
            ap.error("why needs --at")
        print(format_why(why(conn, a.workflow_id, a.at)))
    else:
        for r in timeline(conn, a.workflow_id):
            print(f"v{r['version']}  {r['ts']}  {r['actor']}  {r['changed_dims']}  "
                  f"proposal={r['proposal_id']} approval={r['approval_id']}")


if __name__ == "__main__":
    main()