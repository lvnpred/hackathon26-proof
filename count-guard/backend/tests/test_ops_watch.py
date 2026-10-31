"""Ops watcher: the rules that decide that work is needed, once per input."""

from __future__ import annotations

import re

import pytest

from app.ops import watch
from app.ops.policy import FILE_AFTER_MS, LEVELS

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")
DOTTED = re.compile(r"\b[a-z]+\.[a-z_]+\b")
DR = "Dr. A. Rao (synthetic)"
MONITOR = {"sbp": 118, "dbp": 76, "hr": 80}


def _ev(type, payload, id, ts=0, supersedes=None):
    return {"id": id, "episode_id": "e1", "ts_ms": ts, "wall_clock": "", "event_type": type,
            "payload": payload, "supersedes_id": supersedes, "tier": "documentation"}


def _state(to, id, ts=0, frm="clinic"):
    return _ev("patient.state", {"from": frm, "to": to, "by": DR}, id, ts)


def _order(id="o1", ts=100):
    return _ev("order.signed", {"by": DR, "items": []}, id, ts)


def _task(id, order_id="o1", ts=110):
    return _ev("task.created", {"order_id": order_id, "title": "Obs", "kind": "obs", "mode": "round",
                                "proof": "monitor", "every_h": 4, "due_ms": ts + 1000}, id, ts)


def _opened(item, id="w1", ts=0):
    return _ev("work.opened", {"kind": item.kind, "reason": item.reason, "inputs": list(item.inputs),
                               "owner_role": item.owner_role, "level": LEVELS[item.kind],
                               "key": item.key}, id, ts)


def _kinds(items):
    return [i.kind for i in items]


def _ward_obs(t=1000):
    """A ward stay with an open obs task and a monitor read of it."""
    return [_state("admitting", "s1", 10), _state("ward", "s2", 20, "admitting"), _order(),
            _ev("order.acknowledged", {"order_id": "o1", "by": "Nurse"}, "k0", 105), _task("t1"), _ev("task.assigned", {"task_id": "t1", "to": "Nurse Meena (synthetic)"}, "a1", 120),
            _ev("proof.checked", {"photo_id": "p1", "task_id": "t1", "values_read": MONITOR}, "c1", t)]


def _theatre(count_unaccounted=None):
    evs = [_state("theatre", "s1", 10, "ward"), _ev("surgery.began", {}, "u1", 11),
           _ev("surgery.ended", {}, "u2", 12)]
    if count_unaccounted is not None:
        evs += [_ev("count.pack_opened", {"quantity": 10}, "k1", 13),
                _ev("count.closing", {"opened": 10, "returned": 10 - count_unaccounted,
                                      "unaccounted": count_unaccounted}, "k2", 14)]
    return evs


def test_orders_rule_waits_for_admission():
    evs = [_order()]
    assert watch.watch(evs, 500) == []
    evs.append(_state("admitting", "s1", 200))
    got = watch.watch(evs, 500)
    assert _kinds(got) == ["ack_order"] and got[0].inputs == ("o1",)
    assert got[0].owner_role == "nurse" and got[0].rule == "orders_unacknowledged"
    assert got[0].key == "orders_unacknowledged:ack_order:o1"
    assert "Dr. A. Rao signed orders at" in got[0].reason and "not acknowledged yet" in got[0].reason
    evs.append(_ev("order.acknowledged", {"order_id": "o1", "by": "Nurse"}, "k1", 300))
    assert watch.watch(evs, 500) == []


def _fixtures():
    nudge = _ev("nudge.raised", {"kind": "obs_overdue", "key": "obs-due:x", "says": "s"}, "n1", 50)
    card = _ev("discharge.card", {"warning_signs": ["a"], "wound_care": "w"}, "d1", 40)
    ask = _ev("question.asked", {"to": "doctor", "text": "q", "by": "R. Kumar"}, "q1", 60)
    return {
        "orders_unacknowledged": [_order(), _state("admitting", "s1", 200)],
        "task_unassigned": [_task("t1")],
        "obs_overdue": [nudge],
        "question_waiting": [ask],
        "read_unfiled": _ward_obs(),
        "move_ready": _theatre(0),
    }


@pytest.mark.parametrize("rule", watch.RULES)
def test_each_rule_fires_once(rule):
    evs = _fixtures()[rule]
    at = 10_000_000
    got = [i for i in watch.watch(evs, at) if i.rule == rule]
    assert got, rule
    for item in got:
        assert not ADVICE.search(item.reason) and not SNAKE.search(item.reason) and not DOTTED.search(item.reason)
    opened = [_opened(item, f"w{n}", at) for n, item in enumerate(got)]
    assert [i for i in watch.watch(evs + opened, at) if i.rule == rule] == []


def test_rules_tuple_names_every_rule():
    assert set(watch.RULES) == set(_fixtures())


def test_tasks_grouped_per_order():
    evs = [_task("t1"), _task("t2"), _task("t3")]
    got = watch.watch(evs, 500)
    assert _kinds(got) == ["assign_task"] and got[0].inputs == ("t1", "t2", "t3")
    assert got[0].key == "task_unassigned:assign_task:o1"
    evs.append(_ev("task.assigned", {"task_id": "t2", "to": "Nurse Meena (synthetic)"}, "a1", 120))
    assert watch.watch(evs, 500)[0].inputs == ("t1", "t3")
    other = evs + [_task("t4", "o2")]
    assert [i.key for i in watch.watch(other, 500)] == [
        "task_unassigned:assign_task:o1", "task_unassigned:assign_task:o2"]


def test_question_routes_and_drafts_only_with_card():
    ask = _ev("question.asked", {"to": "doctor", "text": "q", "by": "R. Kumar"}, "q1", 60)
    got = watch.watch([ask], 500)
    assert _kinds(got) == ["route_question"] and got[0].owner_role == "doctor"
    assert got[0].inputs == ("q1",)
    card = _ev("discharge.card", {"warning_signs": ["a"], "wound_care": "w"}, "d1", 40)
    got = watch.watch([card, ask], 500)
    assert _kinds(got) == ["route_question", "draft_answer"]
    assert got[1].owner_role == "doctor" and got[1].inputs == ("q1", "d1")
    bot = _ev("question.asked", {"to": "bot", "text": "q", "by": "R. Kumar"}, "q2", 60)
    assert watch.watch([card, bot], 500) == []
    routed = _ev("question.routed", {"question_id": "q1", "to": DR}, "r1", 70)
    assert _kinds(watch.watch([card, ask, routed], 500)) == ["draft_answer"]
    answered = _ev("question.answered", {"question_id": "q1", "answer": "a", "by": DR}, "x1", 80)
    assert watch.watch([card, ask, routed, answered], 500) == []


def test_read_unfiled_grace_and_saved():
    evs = _ward_obs(1000)
    assert watch.watch(evs, 1000 + FILE_AFTER_MS - 1) == []
    got = watch.watch(evs, 1000 + FILE_AFTER_MS)
    assert _kinds(got) == ["file_read"] and got[0].inputs == ("c1",)
    assert got[0].key == "read_unfiled:file_read:c1" and got[0].owner_role == "nurse"
    assert got[0].reason == "The read was not saved within 5 minutes."
    saved = evs + [_ev("task.done", {"task_id": "t1", "by": "N", "via": "tap", "note": "", "proof_id": "p1"}, "d1", 2000)]
    assert watch.watch(saved, 10_000_000) == []
    strip = [e for e in evs if e["event_type"] != "proof.checked"] + [
        _ev("proof.checked", {"photo_id": "p2", "task_id": "t1", "match": "match"}, "c2", 1000)]
    assert watch.watch(strip, 10_000_000) == []


def test_read_unfiled_never_for_a_camera_count():
    """Ruling F-I3: the AI files monitor reads only. A swab closing is always saved by a person."""
    evs = _theatre() + [_ev("count.pack_opened", {"quantity": 10}, "k1", 13),
                        _ev("swabs.counted", {"count": 10, "opened": 10, "evidence_id": "ev1"}, "c1", 20)]
    for at in (20 + FILE_AFTER_MS, 20 + 5 * FILE_AFTER_MS, 10_000_000):
        assert [i for i in watch.watch(evs, at) if i.kind == "file_read"] == []
        assert watch.read_unfiled(evs, at, set()) == []


def test_move_ready_only_theatre_to_ward():
    ward = [_state("ward", "s1", 10, "admitting")]
    assert watch.watch(ward, 500) == []  # moving to theatre needs a procedure
    got = watch.watch(_theatre(0), 500)
    assert _kinds(got) == ["propose_move"] and got[0].owner_role == "nurse"
    assert got[0].key == "move_ready:propose_move:ward:s1"
    assert watch.watch(_theatre(1), 500) == []  # count open
    began = [_state("theatre", "s1", 10, "ward"), _ev("surgery.began", {}, "u1", 11)]
    assert watch.watch(began, 500) == []


def test_stale_codes():
    ask = _ev("question.asked", {"to": "doctor", "text": "q", "by": "R"}, "q1", 60)
    work = _ev("work.opened", {"kind": "draft_answer", "inputs": ["q1", "d1"], "owner_role": "doctor",
                               "level": "L1", "key": "k", "reason": "r"}, "w1", 61)
    prop = _ev("work.proposed", {"work_id": "w1", "level": "L1"}, "p1", 62)
    assert watch.stale([ask, work, prop]) == []
    answered = _ev("question.answered", {"question_id": "q1", "answer": "a", "by": DR}, "x1", 80)
    got = watch.stale([ask, work, prop, answered])
    assert [(w, c) for w, c, _ in got] == [("w1", "done_by_person")]
    assert not SNAKE.search(got[0][2])

    base = _theatre(0)
    move = _ev("work.opened", {"kind": "propose_move", "inputs": ["s1"], "owner_role": "nurse",
                               "level": "L1", "key": "m", "reason": "r"}, "w2", 30)
    mprop = _ev("work.proposed", {"work_id": "w2", "level": "L1"}, "p2", 31)
    assert watch.stale(base + [move, mprop]) == []
    ward = _state("ward", "s9", 40, "theatre")
    assert [(w, c) for w, c, _ in watch.stale(base + [move, mprop, ward])] == [("w2", "done_by_person")]
    reopened = _ev("count.closing", {"opened": 10, "returned": 9, "unaccounted": 1}, "k9", 41)
    got = watch.stale(base + [move, mprop, reopened])
    assert [(w, c) for w, c, _ in got] == [("w2", "no_longer_allowed")]
    assert not ADVICE.search(got[0][2]) and not SNAKE.search(got[0][2])
    pack = _ev("count.pack_opened", {"quantity": 10}, "k8", 40)  # a new count started after the proposal (I2)
    got = watch.stale(base + [move, mprop, pack])
    assert [(w, c) for w, c, _ in got] == [("w2", "no_longer_allowed")]
    no_pack = _theatre() + [move, mprop]
    assert watch.stale(no_pack) == [] and watch.stale(no_pack + [pack]) != []
    done = _ev("work.dropped", {"work_id": "w2", "by": "x", "reason": "r", "code": "rejected"}, "z", 50)
    assert watch.stale(base + [move, mprop, reopened, done]) == []


def test_move_ready_never_with_a_started_count_unclosed():
    started = _theatre() + [_ev("count.pack_opened", {"quantity": 10}, "k1", 13)]
    assert watch.watch(started, 500) == []
    got = watch.watch(_theatre(), 500)  # no pack at all
    assert _kinds(got) == ["propose_move"]
    assert got[0].reason == "Surgery has ended; no swab count was started."
    assert not ADVICE.search(got[0].reason)
    closed = watch.watch(_theatre(0), 500)
    assert "the count is closed" in closed[0].reason


def test_tasks_skip_done_and_closed():
    one_off = _ev("task.created", {"order_id": "o1", "title": "Dose", "kind": "dose", "mode": "tap",
                                   "proof": "none", "every_h": 0, "due_ms": 1000}, "t1", 110)
    done = _ev("task.done", {"task_id": "t1", "by": "N", "via": "tap", "note": ""}, "d1", 200)
    assert _kinds(watch.watch([one_off], 500)) == ["assign_task"]
    assert watch.watch([one_off, done], 500) == []
    recurring_done = [_task("t2"), _ev("task.done", {"task_id": "t2", "by": "N", "via": "tap", "note": ""}, "d2", 200)]
    assert _kinds(watch.watch(recurring_done, 500)) == ["assign_task"]  # every_h task is open again
    home = [_task("t3"), _state("home", "s9", 300, "discharging")]
    assert watch.watch(home, 500) == []
