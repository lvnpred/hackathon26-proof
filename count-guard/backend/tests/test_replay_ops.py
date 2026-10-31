"""Replay evaluation: proposal precision, undo rate and the eligibility bar (spec section 8)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval"))

import replay_ops  # noqa: E402
from app.morning.store import MorningStore  # noqa: E402
from tests.test_ops_gate import _admit, _events, _kumar_in_clinic, _ops_client, _store  # noqa: E402


def _ev(i, etype, **payload):
    return {"id": f"e{i}", "event_type": etype, "payload": payload, "ts_ms": i, "supersedes_id": None, "tier": "documentation"}


def _day(rate_undone=0):
    return {"ack_order": {"proposed": 0, "agreed": 0, "precision": None, "l2": 10, "undone": 0, "undo_rate": rate_undone},
            "propose_move": {"proposed": 10, "agreed": 9, "precision": 0.9, "l2": 0, "undone": 0, "undo_rate": None}}


def test_metrics_counts_done_by_person_as_agreed():
    events = [_ev(1, "work.opened", kind="propose_move"), _ev(2, "work.opened", kind="propose_move"),
              _ev(3, "work.proposed", work_id="e1"), _ev(4, "work.proposed", work_id="e2"),
              _ev(5, "work.done", work_id="e1", level="L1", approved_by="Dr"),
              _ev(6, "work.dropped", work_id="e2", code="done_by_person")]
    row = replay_ops.metrics(events)["propose_move"]
    assert (row["proposed"], row["agreed"], row["precision"]) == (2, 2, 1.0)


def test_undo_rate():
    events = [_ev(i, "work.opened", kind="ack_order") for i in range(10)]
    events += [_ev(20 + i, "work.done", work_id=f"e{i}", level="L2") for i in range(10)]
    events.append(_ev(40, "work.undone", work_id="e0"))
    row = replay_ops.metrics(events)["ack_order"]
    assert row["l2"] == 10 and row["undone"] == 1 and row["undo_rate"] == 0.1
    assert row["precision"] is None


def test_eligible_needs_three_days_and_thresholds():
    assert not any(replay_ops.eligible([_day(), _day()]).values())
    assert all(replay_ops.eligible([_day(), _day(), _day()]).values())
    bad = replay_ops.eligible([_day(), _day(0.06), _day()])
    assert bad["ack_order"] is False and bad["propose_move"] is True


def _recorded_flow(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    _admit(client, eid, 1000)
    return client, eid


def test_replay_reproduces_agent_on_a_recorded_flow(tmp_path):
    client, eid = _recorded_flow(tmp_path)
    events = _events(client, eid)
    recorded = [(e["payload"]["kind"], e["payload"]["created_by_rule"]) for e in events if e["event_type"] == "work.opened"]
    assert recorded
    label = _store(client).get_episode(eid)["label"]
    assert replay_ops.replay(events, replay_ops._settings(tmp_path), label) == recorded


def test_cli_prints_table(tmp_path):
    client, eid = _recorded_flow(tmp_path)
    db = _store(client).path
    out = subprocess.run([sys.executable, str(ROOT / "eval" / "replay_ops.py"), "--db", str(db)],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    assert "eligible:" in out.stdout and "same: " in out.stdout
    n, m = out.stdout.split("same: ")[1].split()[0].split("/")
    assert n == m and int(m) > 0
