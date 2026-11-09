"""The controller's main loop. Crash-safe: all progress lives in the SQLite cursor."""
from __future__ import annotations

import argparse
import time

import httpx

from controller.api import SimClient, SimError
from controller.runtime import open_run

from controller.decide import schedule_step
from controller.governance import Governance

STEP_MINUTES = 15


def advance_safely(client: SimClient, minutes: int) -> dict:
    """Advance time once. If the outcome is unknown (timeout, 5xx), ask the
    simulator what happened instead of retrying, because a retry could advance twice."""
    try:
        client.advance(minutes)
    except SimError as e:
        if e.status == 409:                  # already finished
            return client.state()
        if e.status < 500:
            raise
        print(f"advance returned {e.status}; checking state instead of retrying", flush=True)
    except httpx.TransportError as e:
        print(f"advance failed ({type(e).__name__}); checking state instead of retrying", flush=True)
    return client.state()


def run(url: str, db_path: str, step: int = STEP_MINUTES) -> None:
    client, conn, ing = open_run(url, db_path)
    gov = Governance(conn, client)
    t0 = time.perf_counter()
    total = ing.ingest_new("history")
    last_day = None
    while True:
        total += ing.ingest_new("events")    # catch up first: covers a crash right after an advance
        st = client.state()
        if st["finished"]:
            break
        day = st["ts"][:10]
        if day != last_day:
            last_day = day
            print(f"{st['ts']}  events this run={total:,}  credits={st['credits_remaining']}"
                  f"  elapsed={time.perf_counter() - t0:.0f}s", flush=True)
        gov.sync(st["ts"])
        schedule_step(conn, client, gov, st)
        advance_safely(client, step)
    print(f"finished at {st['ts']}: {total:,} events ingested in {time.perf_counter() - t0:.0f}s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8700")
    ap.add_argument("--db", default="data/controller.db")
    ap.add_argument("--step", type=int, default=STEP_MINUTES)
    a = ap.parse_args()
    run(a.url, a.db, a.step)


if __name__ == "__main__":
    main()