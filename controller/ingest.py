"""Idempotent ingestion: a chunk's effects and the cursor commit in one transaction."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import TYPE_CHECKING

from controller.store import get_meta, set_meta

if TYPE_CHECKING:                      # keeps this module importable (and testable) without httpx
    from controller.api import SimClient

UPSERT_VARIANT = """
INSERT INTO agg_variant (workflow_id, day, lang, city_tier, age_band, value_band,
                         welcome, voice, caller_id, prompt,
                         dials, connected, engaged, halluc)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(workflow_id, day, lang, city_tier, age_band, value_band,
            welcome, voice, caller_id, prompt)
DO UPDATE SET dials = dials + excluded.dials,
              connected = connected + excluded.connected,
              engaged = engaged + excluded.engaged,
              halluc = halluc + excluded.halluc
"""

UPSERT_HOUR = """
INSERT INTO agg_hour (workflow_id, hour, lang, city_tier, age_band, value_band,
                      attempt, dials, connected)
VALUES (?,?,?,?,?,?,?,?,?)
ON CONFLICT(workflow_id, hour, lang, city_tier, age_band, value_band, attempt)
DO UPDATE SET dials = dials + excluded.dials,
              connected = connected + excluded.connected
"""


class Ingestor:
    def __init__(self, conn, client: "SimClient", d0: date):
        self.conn = conn
        self.client = client
        self.d0 = d0
        self._feat: dict[str, tuple] = {}   # lead_id -> (lang, city_tier, age_band, value_band)

    def _features(self, lead_id: str):
        f = self._feat.get(lead_id)
        if f is None:
            row = self.conn.execute(
                "SELECT lang, city_tier, age_band, value_band FROM leads WHERE lead_id=?",
                (lead_id,),
            ).fetchone()
            if row:
                f = tuple(row)
                self._feat[lead_id] = f
        return f

    def _day(self, ts: str) -> int:
        return (date.fromisoformat(ts[:10]) - self.d0).days

    def ingest_chunk(self, kind: str, chunk_no: int) -> int:
        """Apply one chunk atomically. Returns the number of new events applied."""
        last_event = int(get_meta(self.conn, "last_event_id", "0"))
        newest, applied = last_event, 0
        leads: list[tuple] = []
        cfg_rows: list[tuple] = []
        appr_rows: list[tuple] = []
        agg_v = defaultdict(lambda: [0, 0, 0, 0])   # dials, connected, engaged, halluc
        agg_h = defaultdict(lambda: [0, 0])         # dials, connected
        for ev in self.client.chunk_events(chunk_no):
            eid = ev["event_id"]
            if eid <= last_event:
                continue                      # already applied (defence in depth)
            newest = eid
            applied += 1
            t = ev["type"]
            if t == "lead":
                f = ev["features"]
                row = (f["lang"], f["city_tier"], f["age_band"], f["value_band"])
                self._feat[ev["lead_id"]] = row
                leads.append((ev["lead_id"], ev["workflow_id"], ev["person_id"], *row))
            elif t == "call":
                f = self._features(ev["lead_id"])
                if f is None:
                    continue                  # call for a lead we never saw: skip, don't crash
                wf = ev["workflow_id"]
                v = ev["variant"]
                qa = ev.get("qa") or {}
                connected = 1 if ev["connected"] else 0
                a = agg_v[(wf, self._day(ev["ts"]), *f, v["welcome_message"], v["voice"],
                           v["caller_id"], v["prompt_version"])]
                a[0] += 1
                a[1] += connected
                a[2] += 1 if ev["engaged"] else 0
                a[3] += 1 if qa.get("hallucination_flag") else 0
                b = agg_h[(wf, int(ev["ts"][11:13]), *f, min(ev["attempt_no"], 3))]
                b[0] += 1
                b[1] += connected
            elif t == "config_changed":
                cfg_rows.append((ev["workflow_id"], ev["version"], ev["ts"], ev["actor"],
                                 json.dumps(ev.get("changed_dims", [])),
                                 ev.get("proposal_id"), ev.get("approval_id"), eid))
            elif t == "approval_decided":
                appr_rows.append((ev["approval_id"], ev["workflow_id"], ev["status"],
                                  json.dumps(ev.get("reasons", [])), ev["ts"], eid))
        with self.conn:                       # ONE transaction: data + cursor together
            self.conn.executemany("INSERT OR IGNORE INTO leads VALUES (?,?,?,?,?,?,?)", leads)
            self.conn.executemany(UPSERT_VARIANT, [k + tuple(v) for k, v in agg_v.items()])
            self.conn.executemany(UPSERT_HOUR, [k + tuple(v) for k, v in agg_h.items()])
            self.conn.executemany(
                "INSERT OR IGNORE INTO config_log VALUES (?,?,?,?,?,?,?,?)", cfg_rows)
            self.conn.executemany(
                "INSERT OR IGNORE INTO approval_log VALUES (?,?,?,?,?,?)", appr_rows)
            set_meta(self.conn, "last_event_id", newest)
            set_meta(self.conn, f"last_chunk_{kind}", chunk_no)
        return applied

    def ingest_new(self, kind: str) -> int:
        """Ingest every chunk of this kind not yet applied, in order."""
        cursor = get_meta(self.conn, f"last_chunk_{kind}")
        after = int(cursor) if cursor is not None else None
        total = 0
        for ch in sorted(self.client.chunks(kind, after=after), key=lambda c: c["chunk"]):
            total += self.ingest_chunk(kind, ch["chunk"])
        return total