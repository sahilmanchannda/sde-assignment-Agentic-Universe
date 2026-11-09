import httpx
import pytest

from controller.api import SimError
from controller.governance import Governance, can_auto_apply, changed_dims, in_send_window
from controller.store import connect

GOV = {"approver_hours": [10, 19], "approver_latency_minutes": [30, 240],
       "proposal_ttl_hours": 24, "max_requests_per_24h": 3,
       "auto_apply": {"enabled": True, "allowed_dims": ["schedule", "caller_id"], "max_shift": 0.5}}
T = "2027-01-04T10:00:00+05:30"
CFG = {"cohorts": [], "prompt_version": "P1", "allocations": {"default": {"voice": {"V1": 1.0}}},
       "schedule": {"hour_weights": {"default": {"9": 2}}}}
EXTRA = dict(diff={}, affected_leads=100, dry_run={}, impact_score=0.1)


class FakeSim:
    def __init__(self):
        self.apps, self.version, self.posts, self.history = {}, 1, 0, []
        self.down = False

    def approvals(self, wid, status=None):
        return [dict(a) for a in self.apps.values() if a["workflow_id"] == wid]

    def submit_approval(self, body):
        self.posts += 1
        aid = f"apr_{len(self.apps) + 1:05d}"
        self.apps[aid] = {"approval_id": aid, "proposal_id": body["proposal_id"],
                          "workflow_id": body["workflow_id"], "base_version": body["base_version"],
                          "status": "pending"}
        return dict(self.apps[aid])

    def approval(self, aid):
        return dict(self.apps[aid])

    def apply(self, wid, aid):
        if self.down:
            raise httpx.ConnectError("down")
        a = self.apps[aid]
        if a["base_version"] != self.version:
            raise SimError(409, {"error": "stale_base_version"})
        a["status"], self.version = "applied", self.version + 1
        return {"workflow_id": wid, "version": self.version, "changed_dims": ["schedule"]}

    def config_history(self, wid):
        return self.history

    def put_config(self, wid, body):
        self.version += 1
        self.history.append({"version": self.version, "proposal_id": body["proposal_id"]})
        return {"version": self.version, "changed_dims": ["schedule"], "workflow_id": wid}


@pytest.fixture
def env(tmp_path):
    conn, sim = connect(str(tmp_path / "t.db")), FakeSim()
    return conn, sim, Governance(conn, sim)


def state(conn, pid):
    return conn.execute("SELECT state FROM proposals WHERE proposal_id=?", (pid,)).fetchone()[0]


def test_send_window_keeps_decisions_inside_approver_hours():
    f = lambda hhmm: in_send_window(GOV, f"2027-01-04T{hhmm}:00+05:30")
    assert not f("09:00") and f("10:00") and f("15:00") and not f("15:01") and not f("20:00")


def test_dims_and_auto_apply_policy():
    new = {**CFG, "schedule": {"hour_weights": {}}}
    assert changed_dims(CFG, new) == ["schedule"]
    voice = {**CFG, "allocations": {"default": {"voice": {"V2": 1.0}}}}
    assert changed_dims(CFG, voice) == ["voice"]
    assert can_auto_apply(GOV, ["schedule"]) and not can_auto_apply(GOV, ["voice"])
    assert not can_auto_apply(GOV, [])


def test_happy_path_to_applied(env):
    conn, sim, g = env
    pid, why = g.propose("w", 1, CFG, "s", "r", T, GOV, **EXTRA)
    assert pid and state(conn, pid) == "submitted"
    g.sync(T)
    assert state(conn, pid) == "submitted"                   # still pending: nothing happens
    sim.apps["apr_00001"]["status"] = "approved"
    g.sync(T)
    assert state(conn, pid) == "applied" and sim.version == 2


def test_only_one_change_in_flight_per_workflow(env):
    _, _, g = env
    assert g.propose("w", 1, CFG, "s", "r", T, GOV, **EXTRA)[0]
    pid, why = g.propose("w", 1, CFG, "s", "r", T, GOV, **EXTRA)
    assert pid is None and "in flight" in why


def test_crash_after_post_does_not_duplicate_the_request(env):
    conn, sim, g = env
    pid = g._draft("approval", "w", 1, CFG, "s", "r", T, EXTRA)   # drafted, then "crash"
    sim.submit_approval(g._detail(pid)["request"])                # the POST had reached the sim
    Governance(conn, sim).sync(T)                                 # restart
    assert sim.posts == 1 and state(conn, pid) == "submitted"


def test_stale_approval_is_recorded_not_retried(env):
    conn, sim, g = env
    pid, _ = g.propose("w", 1, CFG, "s", "r", T, GOV, **EXTRA)
    sim.apps["apr_00001"]["status"] = "approved"
    sim.version = 2                                           # someone else changed the config
    g.sync(T)
    assert state(conn, pid) == "stale"


def test_network_error_during_apply_leaves_it_approved_for_next_tick(env):
    conn, sim, g = env
    pid, _ = g.propose("w", 1, CFG, "s", "r", T, GOV, **EXTRA)
    sim.apps["apr_00001"]["status"] = "approved"
    sim.down = True
    g.sync(T)
    assert state(conn, pid) == "approved"
    sim.down = False
    g.sync(T)
    assert state(conn, pid) == "applied"


def test_auto_apply_refused_locally_for_disallowed_dims(env):
    _, sim, g = env
    voice = {**CFG, "allocations": {"default": {"voice": {"V2": 1.0}}}}
    pid, why = g.auto_apply("w", 1, voice, CFG, "s", "r", T, GOV)
    assert pid is None and sim.version == 1


def test_auto_apply_crash_after_put_is_reconciled_from_history(env):
    conn, sim, g = env
    new = {**CFG, "schedule": {"hour_weights": {}}}
    pid = g._draft("auto", "w", 1, new, "s", "r", T, {})          # drafted, then "crash"
    sim.put_config("w", g._detail(pid)["request"])                # the PUT had gone through
    g.sync(T)
    assert state(conn, pid) == "applied" and sim.version == 2     # not applied twice