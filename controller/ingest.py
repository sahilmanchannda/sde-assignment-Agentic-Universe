"""Idempotent ingestion: a chunk's effects and the cursor commit in one transaction."""
from __future__ import annotations

import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from controller.api import SimClient
from controller.store import connect, get_meta, set_meta

UPSERT = """
INSERT INTO call_agg (workflow_id, day, hour, lang, city_tier, age_band, value_band,
                      welcome, voice, caller_id, prompt, attempt_no,
                      dials, connected, engaged, halluc)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(workflow_id, day, hour, lang, city_tier, age_band, value_band,
            welcome, voice, caller_id, prompt, attempt_no)
DO UPDATE SET dials = dials + excluded.dials,
              connected = connected + excluded.connected,
              engaged = engaged + excluded.engaged,
              halluc = halluc + excluded.halluc
"""


class Ingestor:
    def __init__(self, conn, client: SimClient, d0: date):
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
        agg = defaultdict(lambda: [0, 0, 0, 0])
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
                v = ev["variant"]
                qa = ev.get("qa") or {}
                key = (ev["workflow_id"], self._day(ev["ts"]), int(ev["ts"][11:13]), *f,
                       v["welcome_message"], v["voice"], v["caller_id"], v["prompt_version"],
                       ev["attempt_no"])
                a = agg[key]
                a[0] += 1
                a[1] += 1 if ev["connected"] else 0
                a[2] += 1 if ev["engaged"] else 0
                a[3] += 1 if qa.get("hallucination_flag") else 0
        with self.conn:                       # ONE transaction: data + cursor together
            self.conn.executemany("INSERT OR IGNORE INTO leads VALUES (?,?,?,?,?,?,?)", leads)
            self.conn.executemany(UPSERT, [k + tuple(v) for k, v in agg.items()])
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


def main(url: str, db_path: str) -> None:
    client = SimClient(url)
    conn = connect(db_path)
    st = client.state()
    if int(get_meta(conn, "last_event_id", "0")) > st["last_event_id"]:
        sys.exit(f"{db_path} is from a different simulator run. Delete it and retry.")
    if get_meta(conn, "d0") is None:
        d0 = (datetime.fromisoformat(st["ts"]) - timedelta(minutes=st["sim_minute"])).date()
        with conn:
            set_meta(conn, "d0", d0.isoformat())
    ing = Ingestor(conn, client, date.fromisoformat(get_meta(conn, "d0")))

    t0 = time.perf_counter()
    n = ing.ingest_new("history")
    dt = time.perf_counter() - t0
    print(f"applied {n} history events in {dt:.1f}s ({n / max(dt, 1e-9):,.0f} events/s)")

    print("leads:", conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
          "| dials:", conn.execute("SELECT SUM(dials) FROM call_agg").fetchone()[0],
          "| agg rows:", conn.execute("SELECT COUNT(*) FROM call_agg").fetchone()[0])
    rows = conn.execute(
        "SELECT workflow_id, caller_id, SUM(dials), SUM(connected), SUM(engaged) "
        "FROM call_agg GROUP BY workflow_id, caller_id ORDER BY workflow_id, caller_id"
    ).fetchall()
    for wf, cid, d, k, e in rows:
        print(f"{wf} {cid}: dials={d} pickup={k / d:.3f} engage={e / max(k, 1):.3f}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8700",
         sys.argv[2] if len(sys.argv) > 2 else "data/controller.db")