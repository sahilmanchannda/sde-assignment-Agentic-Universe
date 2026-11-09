from datetime import date

import pytest

from controller import ingest as ingest_mod
from controller.audit import format_why, log_decision, timeline, why
from controller.ingest import Ingestor
from controller.store import connect, get_meta


class FakeClient:
    """Stands in for SimClient: serves canned chunks, no network."""

    def __init__(self, chunks):
        self._chunks = chunks            # {chunk_no: (kind, [events])}

    def chunks(self, kind, after=None):
        return [{"chunk": n} for n, (k, _) in sorted(self._chunks.items())
                if k == kind and (after is None or n > after)]

    def chunk_events(self, n):
        return iter(self._chunks[n][1])


def lead(eid, lead_id="w:l1"):
    return {"type": "lead", "event_id": eid, "ts": "2027-01-04T08:00:00+05:30",
            "workflow_id": "w", "campaign_id": "w:c1", "lead_id": lead_id, "person_id": "w:p1",
            "features": {"lang": "hi", "city_tier": "1", "age_band": "60+", "value_band": "low"}}


def call(eid, lead_id="w:l1", connected=True, engaged=False, hour=9):
    return {"type": "call", "event_id": eid, "ts": f"2027-01-04T{hour:02d}:15:00+05:30",
            "workflow_id": "w", "lead_id": lead_id, "attempt_no": 1, "config_version": 1,
            "cohort_id": "default",
            "variant": {"welcome_message": "W1", "voice": "V1", "caller_id": "D1",
                        "prompt_version": "P1"},
            "connected": connected, "engaged": engaged,
            "qa": {"hallucination_flag": False, "flow_adherence": 0.9}}


def config_changed(eid, version=2, actor="controller_approved", proposal="p-1", approval="apr_00001"):
    return {"type": "config_changed", "event_id": eid, "ts": "2027-01-04T11:00:00+05:30",
            "workflow_id": "w", "version": version, "actor": actor,
            "changed_dims": ["voice"], "proposal_id": proposal, "approval_id": approval}


def approval_decided(eid):
    return {"type": "approval_decided", "event_id": eid, "ts": "2027-01-04T11:00:00+05:30",
            "approval_id": "apr_00001", "workflow_id": "w", "status": "approved", "reasons": []}


CHUNKS = {1: ("events", [lead(1), call(2), call(3, connected=False),
                         config_changed(4), approval_decided(5)])}


@pytest.fixture
def conn(tmp_path):
    return connect(str(tmp_path / "t.db"))


def make(conn, chunks=CHUNKS):
    return Ingestor(conn, FakeClient(chunks), date(2027, 1, 4))


def scalar(conn, sql):
    return conn.execute(sql).fetchone()[0]


def test_ingest_records_calls_and_governance_events(conn):
    assert make(conn).ingest_new("events") == 5
    assert conn.execute("SELECT SUM(dials), SUM(connected) FROM agg_variant").fetchone() == (2, 1)
    assert conn.execute("SELECT SUM(dials) FROM agg_hour").fetchone()[0] == 2
    assert conn.execute("SELECT actor, proposal_id FROM config_log").fetchall() == [
        ("controller_approved", "p-1")]
    assert conn.execute("SELECT status FROM approval_log").fetchall() == [("approved",)]


def test_ingest_is_idempotent_across_restarts(conn):
    make(conn).ingest_new("events")
    restarted = make(conn)                       # new process, same database
    assert restarted.ingest_chunk("events", 1) == 0      # chunk re-offered: nothing re-applied
    assert restarted.ingest_new("events") == 0           # cursor says we're done
    assert scalar(conn, "SELECT SUM(dials) FROM agg_variant") == 2
    assert scalar(conn, "SELECT COUNT(*) FROM config_log") == 1


def test_crash_inside_transaction_rolls_back_data_and_cursor(conn, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("killed mid-transaction")

    monkeypatch.setattr(ingest_mod, "set_meta", boom)
    with pytest.raises(RuntimeError):
        make(conn).ingest_new("events")
    assert scalar(conn, "SELECT COUNT(*) FROM agg_variant") == 0
    assert scalar(conn, "SELECT COUNT(*) FROM config_log") == 0
    assert get_meta(conn, "last_event_id") is None
    monkeypatch.undo()
    assert make(conn).ingest_new("events") == 5          # restart applies the chunk exactly once
    assert scalar(conn, "SELECT SUM(dials) FROM agg_variant") == 2


def test_supervisor_edit_is_recorded_with_its_actor(conn):
    chunks = {1: ("events", [config_changed(1, version=2, actor="supervisor",
                                            proposal=None, approval=None)])}
    make(conn, chunks).ingest_new("events")
    assert [r["actor"] for r in timeline(conn, "w")] == ["supervisor"]


def test_why_answers_who_approved_and_what_happened_next(conn):
    make(conn).ingest_new("events")
    log_decision(conn, "2027-01-04T10:00:00+05:30", "w", "propose", "try V2", {"proposal_id": "p-1"})
    log_decision(conn, "2027-01-04T12:00:00+05:30", "w", "verify", "no harm seen", {"proposal_id": "p-1"})
    log_decision(conn, "2027-01-04T20:00:00+05:30", "w", "detect", "nothing unusual", {})
    conn.commit()
    res = why(conn, "w", "2027-01-04T14:00")             # short form is accepted
    assert res["change"]["actor"] == "controller_approved"
    assert res["approval"]["status"] == "approved"
    assert [d["kind"] for d in res["decisions"]] == ["propose", "verify"]
    assert [d["kind"] for d in res["after"]] == ["verify", "detect"]
    assert res["next_change"] is None
    text = format_why(res)
    assert "controller_approved" in text and "try V2" in text


def test_why_before_any_change_says_so(conn):
    make(conn).ingest_new("events")
    res = why(conn, "w", "2027-01-04T09:00")
    assert res["change"] is None
    assert "No config change recorded" in format_why(res)