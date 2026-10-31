"""Final review fixes: undo stays off people's records, theatre is never left on an open count, a paused agent shows."""

from __future__ import annotations

import threading

import pytest

from app.journey.nudges import hours
from app.morning.discharge import visible_events
from app.morning.store import MorningStore
from app.ops import gate, run as ops_run, site, watch
from app.ops.items import Action, WorkItem, work_items
from app.ops.policy import AI_BY
from tests.test_ops_api import MEENA, _propose_move, _proposal, _undo
from tests.test_ops_gate import ASHA, _kumar_in_clinic, _of, _ops_client, _store, _url
from tests.test_ops_watch import _ev, _theatre

DR = "Dr. A. Rao (synthetic)"
ADVICE = r"\b(give|take|stop|increase|reduce|start|administer|consider)\b"


def _store_ep(tmp_path):
    store = MorningStore(tmp_path / "m.db")
    return store, store.create_episode("R. Kumar (synthetic)")["id"]


def _route_item():
    return WorkItem("route_question", "r", ("q",), "doctor", "question_waiting", "k")


def _routed(store, ep, at_ms=10):
    """An L2 routing the AI did, with a person's vitals landing inside the gate's before/after window (the probe)."""
    w = store.append(ep, "work.opened", {"kind": "route_question", "inputs": ["q"], "owner_role": "doctor",
                                         "level": "L2", "key": "k", "reason": "r"}, ts_ms=1)
    return w["id"]


# --- I1: the gate keeps only the AI's own events ---

def test_person_event_during_execute_is_not_wrote_and_survives_undo(tmp_path, monkeypatch):
    store, ep = _store_ep(tmp_path)
    wid = _routed(store, ep)
    orig = gate._DO["route_question"]

    def racing(store, episode_id, action, level, item, at_ms):
        orig(store, episode_id, action, level, item, at_ms)
        store.append(episode_id, "vitals.reading", {"by": MEENA, "sbp": 120}, ts_ms=at_ms)  # another thread's write

    monkeypatch.setitem(gate._DO, "route_question", racing)
    out = gate.apply(store, ep, wid, _route_item(), Action("route_question", {"question_id": "q", "to": DR}, "Sent"),
                     10, level="L2")
    wrote = out[0]["payload"]["wrote"]
    kinds = {e["id"]: e["event_type"] for e in store.events(ep)}
    assert [kinds[i] for i in wrote] == ["question.routed"]
    gate.undo(store, ep, wid, MEENA, 20)
    shown = visible_events(store.events(ep))
    assert any(e["event_type"] == "vitals.reading" for e in shown)
    assert not any(e["event_type"] == "question.routed" for e in shown)


def test_revert_skips_an_id_that_is_not_the_ais(tmp_path):
    """Even a `wrote` list recorded before the fix never supersedes a person's event."""
    store, ep = _store_ep(tmp_path)
    wid = _routed(store, ep)
    routed = store.append(ep, "question.routed", {"question_id": "q", "to": DR, "by": AI_BY}, ts_ms=10)
    person = store.append(ep, "vitals.reading", {"by": MEENA, "sbp": 120}, ts_ms=10)
    store.append(ep, "work.done", {"work_id": wid, "level": "L2", "by": AI_BY, "reason": "r", "summary": "s",
                                   "inputs": ["q"], "wrote": [routed["id"], person["id"]], "undo_until_ms": 600_010},
                 ts_ms=10)
    gate.undo(store, ep, wid, MEENA, 20)
    undone = next(e for e in store.events(ep) if e["event_type"] == "work.undone")["payload"]
    assert undone["reverted"] == [routed["id"]]
    assert person["id"] in {e["id"] for e in visible_events(store.events(ep))}


def test_ack_keeps_the_orders_tasks_in_wrote(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    client.post(_url(eid, "state"), json={"to": "admitting", "by": DR, "at_ms": 1000, "reason": "Hernia repair"})
    done = next(e for e in _of(client, eid, "work.done") if e["payload"]["summary"].startswith("Acknowledged"))
    kinds = {e["id"]: e["event_type"] for e in _store(client).events(eid)}
    assert sorted(kinds[i] for i in done["payload"]["wrote"]) == ["order.acknowledged", "task.created", "task.created"]


def test_ours_test():
    task = {"event_type": "task.created", "payload": {"order_id": "o1"}}
    assert gate.ours(task, "o1") and not gate.ours(task, "o2") and not gate.ours(task, None)
    assert gate.ours({"event_type": "x", "payload": {"by": AI_BY}}, None)
    assert not gate.ours({"event_type": "vitals.reading", "payload": {"by": MEENA}}, "o1")


# --- M7: a person's supersede of an AI write blocks undo ---

def test_undo_refused_when_a_person_superseded_what_the_ai_wrote(tmp_path):
    store, ep = _store_ep(tmp_path)
    wid = _routed(store, ep)
    out = gate.apply(store, ep, wid, _route_item(), Action("route_question", {"question_id": "q", "to": DR}, "Sent"),
                     10, level="L2")
    routed = out[0]["payload"]["wrote"][0]
    store.append(ep, "question.routed", {"question_id": "q", "to": "Dr. B (synthetic)", "by": MEENA}, ts_ms=12,
                 supersedes_id=routed)
    before = len(store.events(ep))
    with pytest.raises(gate.OpsError) as err:
        gate.undo(store, ep, wid, MEENA, 20)
    assert err.value.status == 409 and err.value.detail == gate.PERSON_ACTED
    assert len(store.events(ep)) == before


# --- M8: the undo cascade never takes back a person's approval ---

def test_cascade_skips_an_approved_row(tmp_path):
    store, ep = _store_ep(tmp_path)
    wid = _routed(store, ep)
    out = gate.apply(store, ep, wid, _route_item(), Action("route_question", {"question_id": "q", "to": DR}, "Sent"),
                     10, level="L2")
    routed = out[0]["payload"]["wrote"][0]
    other = store.append(ep, "work.opened", {"kind": "draft_answer", "inputs": [routed], "owner_role": "doctor",
                                             "level": "L1", "key": "k2", "reason": "r"}, ts_ms=11)
    answer = store.append(ep, "question.answered", {"question_id": "q2", "answer": "a", "by": DR}, ts_ms=12)
    store.append(ep, "work.done", {"work_id": other["id"], "level": "L1", "by": DR, "approved_by": DR, "reason": "r",
                                   "inputs": [routed], "summary": "s", "wrote": [answer["id"]]}, ts_ms=12)
    gate.undo(store, ep, wid, MEENA, 20)
    rows = {r["id"]: r["status"] for r in work_items(store.events(ep))}
    assert rows[wid] == "undone" and rows[other["id"]] == "done"
    assert answer["id"] in {e["id"] for e in visible_events(store.events(ep))}


# --- I2: a proposal to leave theatre goes stale when a count is started, and approve re-checks ---

def test_stale_drops_back_to_ward_after_a_pack_is_opened():
    move = _ev("work.opened", {"kind": "propose_move", "inputs": ["s1"], "owner_role": "nurse", "level": "L1",
                               "key": "m", "reason": "r"}, "w2", 30)
    prop = _ev("work.proposed", {"work_id": "w2", "level": "L1"}, "p2", 31)
    pack = _ev("count.pack_opened", {"quantity": 10}, "k1", 40)
    evs = _theatre() + [move, prop]
    assert watch.stale(evs) == []
    got = watch.stale(evs + [pack])
    assert [(w, c) for w, c, _ in got] == [("w2", "no_longer_allowed")]


def test_approve_refuses_when_a_count_was_started(tmp_path):
    import re
    client = _ops_client(tmp_path)
    eid = _propose_move(client)
    wi = _proposal(client, eid, "propose_move")
    _store(client).append(eid, "count.pack_opened", {"quantity": 15, "by": ASHA}, ts_ms=45)  # no settle yet
    before = len(_store(client).events(eid))
    r = client.post(_url(eid, f"ops/work/{wi}/approve"), json={"by": MEENA, "at_ms": 50})
    assert r.status_code == 409 and r.json()["detail"] == "A swab count was started and is not closed."
    assert not re.search(ADVICE, r.json()["detail"], re.I)
    assert len(_store(client).events(eid)) == before
    assert _of(client, eid, "patient.state")[-1]["payload"]["to"] == "theatre"


def test_pack_opened_through_the_route_drops_the_proposal(tmp_path):
    client = _ops_client(tmp_path)
    eid = _propose_move(client)
    wi = _proposal(client, eid, "propose_move")
    client.post(_url(eid, "count"), json={"step": "opened", "quantity": 15, "by": ASHA, "at_ms": 45})
    drop = next(e for e in _of(client, eid, "work.dropped") if e["payload"]["work_id"] == wi)["payload"]
    assert drop["code"] == "no_longer_allowed"
    r = client.post(_url(eid, f"ops/work/{wi}/approve"), json={"by": MEENA, "at_ms": 50})
    assert r.status_code == 409


# --- I4: a paused agent shows what it has not done ---

def test_paused_view_shows_not_done_only_while_paused(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    site.set_paused(_store(client), True, "Charge nurse", 0)
    view = client.post(_url(eid, "state"), json={"to": "admitting", "by": DR, "at_ms": 1000,
                                                 "reason": "Hernia repair"}).json()
    rows = view["ops"]["open"]
    assert rows and all(r["paused_note"] == "Paused · not done" for r in rows)
    assert {r["kind"] for r in rows} == {"ack_order"}

    running = _ops_client(tmp_path / "running")
    other = _kumar_in_clinic(running)
    site.set_level(_store(running), "ack_order", "L0", "Owner", 0)  # observe only: the item stays open, not paused
    view = running.post(_url(other, "state"), json={"to": "admitting", "by": DR, "at_ms": 1000,
                                                    "reason": "Hernia repair"}).json()
    assert view["ops"]["open"] and all("paused_note" not in r for r in view["ops"]["open"])


# --- I5: one lock per episode ---

def test_episode_locks_are_per_episode():
    assert ops_run.episode_lock("a") is ops_run.episode_lock("a")
    assert ops_run.episode_lock("a") is not ops_run.episode_lock("b")
    assert not hasattr(ops_run, "_LOCK")


def test_a_held_episode_does_not_stall_another(tmp_path):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    other = "0" * 36
    finished = threading.Event()
    with ops_run.episode_lock(other):
        worker = threading.Thread(target=lambda: (client.post(_url(eid, "state"), json={
            "to": "admitting", "by": DR, "at_ms": 1000, "reason": "Hernia repair"}), finished.set()))
        worker.start()
        assert finished.wait(10), "a write on one episode waited for another episode's lock"
    worker.join()
    assert _of(client, eid, "order.acknowledged")[0]["payload"]["by"] == AI_BY


def test_undo_route_uses_the_episode_lock(tmp_path, monkeypatch):
    client = _ops_client(tmp_path)
    eid = _kumar_in_clinic(client)
    client.post(_url(eid, "state"), json={"to": "admitting", "by": DR, "at_ms": 1000, "reason": "Hernia repair"})
    wi = next(e for e in _of(client, eid, "work.done") if e["payload"]["summary"].startswith("Acknowledged"))
    asked = []
    real = ops_run.episode_lock
    import app.ops.api as ops_api
    monkeypatch.setattr(ops_api, "episode_lock", lambda e: asked.append(e) or real(e))
    assert _undo(client, eid, wi["payload"]["work_id"], 2000).status_code == 200
    assert asked == [eid]


# --- M3: overdue intervals below an hour read in minutes ---

def test_hours_reads_minutes_below_an_hour():
    assert [hours(v) for v in (0.25, 0.5, 1, 1.5, 4, 6.0)] == ["15 min", "30 min", "1 h", "1.5 h", "4 h", "6 h"]
