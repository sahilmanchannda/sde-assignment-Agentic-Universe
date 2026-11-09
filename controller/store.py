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
CREATE TABLE IF NOT EXISTS call_agg (
    workflow_id TEXT NOT NULL,
    day INTEGER NOT NULL,              -- simulated day index: 0 = D0, negative = history
    hour INTEGER NOT NULL,
    lang TEXT NOT NULL, city_tier TEXT NOT NULL, age_band TEXT NOT NULL, value_band TEXT NOT NULL,
    welcome TEXT NOT NULL, voice TEXT NOT NULL, caller_id TEXT NOT NULL, prompt TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    dials INTEGER NOT NULL DEFAULT 0,
    connected INTEGER NOT NULL DEFAULT 0,
    engaged INTEGER NOT NULL DEFAULT 0,
    halluc INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (workflow_id, day, hour, lang, city_tier, age_band, value_band,
                 welcome, voice, caller_id, prompt, attempt_no)
);
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