"""SQLite store. One file, WAL mode. Multi-row changes go in a single transaction."""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    lang TEXT, city_tier TEXT, age_band TEXT, value_band TEXT
);
CREATE TABLE IF NOT EXISTS agg_variant (
    workflow_id TEXT NOT NULL,
    day INTEGER NOT NULL,              -- simulated day index: 0 = D0, negative = history
    lang TEXT NOT NULL, city_tier TEXT NOT NULL, age_band TEXT NOT NULL, value_band TEXT NOT NULL,
    welcome TEXT NOT NULL, voice TEXT NOT NULL, caller_id TEXT NOT NULL, prompt TEXT NOT NULL,
    dials INTEGER NOT NULL DEFAULT 0,
    connected INTEGER NOT NULL DEFAULT 0,
    engaged INTEGER NOT NULL DEFAULT 0,
    halluc INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, day, lang, city_tier, age_band, value_band,
                 welcome, voice, caller_id, prompt)
);
CREATE TABLE IF NOT EXISTS agg_hour (
    workflow_id TEXT NOT NULL,
    hour INTEGER NOT NULL,
    lang TEXT NOT NULL, city_tier TEXT NOT NULL, age_band TEXT NOT NULL, value_band TEXT NOT NULL,
    attempt INTEGER NOT NULL,          -- 1, 2, or 3 meaning "3 or more"
    dials INTEGER NOT NULL DEFAULT 0,
    connected INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, hour, lang, city_tier, age_band, value_band, attempt)
);
-- Every config version the simulator tells us about, including supervisor edits.
CREATE TABLE IF NOT EXISTS config_log (
    workflow_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,               -- supervisor | controller_approved | controller_auto
    changed_dims TEXT NOT NULL,        -- JSON list
    proposal_id TEXT,
    approval_id TEXT,
    event_id INTEGER NOT NULL,
    PRIMARY KEY (workflow_id, version)
);
-- Approver decisions as reported by the simulator.
CREATE TABLE IF NOT EXISTS approval_log (
    approval_id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL,
    status TEXT NOT NULL,              -- approved | rejected | expired
    reasons TEXT NOT NULL,             -- JSON list
    ts TEXT NOT NULL,
    event_id INTEGER NOT NULL
);
-- Our own decisions: what we noticed, proposed, applied, rolled back, and why.
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sim_ts TEXT NOT NULL,
    workflow_id TEXT NOT NULL,
    kind TEXT NOT NULL,                -- detect | propose | apply | verify | rollback | skip ...
    summary TEXT NOT NULL,
    detail TEXT NOT NULL               -- JSON: evidence, numbers, ids (proposal_id, approval_id)
);
CREATE INDEX IF NOT EXISTS decisions_wf ON decisions(workflow_id, sim_ts);
"""


def connect(path: str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")   # a lost last txn just means that chunk is re-ingested
    conn.executescript(SCHEMA)
    return conn


def get_meta(conn: sqlite3.Connection, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )