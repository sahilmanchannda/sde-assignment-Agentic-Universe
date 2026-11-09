"""Opening a run: connect, detect a database from another world, and set up ingestion."""
from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from controller.api import SimClient
from controller.ingest import Ingestor
from controller.store import connect, get_meta, set_meta


def _archive(db_path: str) -> None:
    stamp = int(time.time())
    for suffix in ("", "-wal", "-shm"):
        p = Path(db_path + suffix)
        if p.exists():
            p.rename(f"{db_path}{suffix}.stale-{stamp}")


def open_run(url: str, db_path: str):
    """Return (client, conn, ingestor). A database that belongs to a different simulator
    world is archived and replaced, so a new scenario never inherits old state."""
    client = SimClient(url)
    st = client.state()
    hist = client.chunks("history")
    world = f"{st['scenario']}|{hist[-1]['last_event_id'] if hist else 0}"
    conn = connect(db_path)
    known = get_meta(conn, "world")
    ahead = int(get_meta(conn, "last_event_id", "0")) > st["last_event_id"]
    if (known is not None and known != world) or ahead:
        conn.close()
        _archive(db_path)
        print(f"WARNING: {db_path} was from another simulator world; archived it, starting fresh",
              file=sys.stderr)
        conn = connect(db_path)
    if get_meta(conn, "world") is None:
        d0 = (datetime.fromisoformat(st["ts"]) - timedelta(minutes=st["sim_minute"])).date()
        with conn:
            set_meta(conn, "world", world)
            set_meta(conn, "d0", d0.isoformat())
    return client, conn, Ingestor(conn, client, date.fromisoformat(get_meta(conn, "d0")))