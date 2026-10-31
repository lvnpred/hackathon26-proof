"""Ops planner: who and what, by rule, with template text."""

from __future__ import annotations

import re

from app.agent import verifier
from app.journey import seed
from app.ops import plan as planner
from app.ops import watch
from app.ops.items import Action, WorkItem
from app.ops.policy import LEVELS

DEMO = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")
DR = "Dr. A. Rao (synthetic)"
MEENA, ASHA = "Nurse Meena (synthetic)", "Nurse Asha (synthetic)"
SIGNS = ["Fever above 38 °C", "Wound red, swollen or leaking", "Pain not eased by the prescribed medicine",
         "Cannot pass urine", "Vomiting that keeps going"]
MONITOR = {"sbp": 118, "dbp": 76, "hr": 80}


def _ev(type, payload, id, ts=0, supersedes=None):
    return {"id": id, "episode_id": "e1", "ts_ms": ts, "wall_clock": "", "event_type": type,
            "payload": payload, "supersedes_id": supersedes, "tier": "documentation"}


def _state(to, id, ts=0, frm="clinic"):
    return _ev("patient.state", {"from": frm, "to": to, "by": DR}, id, ts)


def _item(kind, *inputs):
    return WorkItem(kind, "r", tuple(inputs), "nurse", "rule", f"rule:{kind}:{inputs[0]}")


def _task(id, order_id="o1", kind="obs", ts=110):
    return _ev("task.created", {"order_id": order_id, "title": "Obs", "kind": kind, "mode": "round",
                                "proof": "monitor", "every_h": 4, "due_ms": ts + 1000}, id, ts)


def _ward():
    return [_state("admitting", "s1", 10), _state("ward", "s2", 20, "admitting"),
            _ev("order.signed", {"by": DR, "items": []}, "o1", 100)]


def _assign(task_id, to, id):
    return _ev("task.assigned", {"task_id": task_id, "to": to}, id, 130)


def _card():
    return _ev("discharge.card", {"warning_signs": SIGNS, "wound_care": "Keep the dressing dry for 48 hours."}, "d1", 40)


def _ask():
    return _ev("question.asked", {"to": "doctor", "text": "q", "by": "R. Kumar, 58 M (synthetic)"}, "q1", 60)


def _theatre(closing=True):
    evs = [_state("theatre", "s1", 10, "ward"), _ev("surgery.began", {}, "u1", 11), _ev("surgery.ended", {}, "u2", 12)]
    if closing:
        evs += [_ev("count.pack_opened", {"quantity": 10}, "k1", 13),
                _ev("count.closing", {"opened": 10, "returned": 10, "unaccounted": 0}, "k2", 14)]
    return evs


def _clean(*texts):
    for text in texts:
        assert not DEMO.search(text) and not verifier.ADVICE.search(text), text
        assert not SNAKE.search(text), text


def test_ack_summary():
    evs = _ward()
    act = planner.plan(_item("ack_order", "o1"), evs)
    assert isinstance(act, Action)
    assert act.summary == "Acknowledged Dr. A. Rao's orders"
    assert act.args == {"order_id": "o1"}


def test_pick_nurses_greedy_with_roster_tiebreak():
    evs = _ward() + [_task("t1"), _task("t2"), _task("t3")]
    got = planner.pick_nurses(evs, ["t1", "t2", "t3"])
    assert list(got.values()) == [MEENA, ASHA, MEENA]
    evs = _ward() + [_task("h1"), _task("h2"), _assign("h1", MEENA, "a1"), _assign("h2", MEENA, "a2"),
                     _task("t1"), _task("t2"), _task("t3")]
    got = planner.pick_nurses(evs, ["t1", "t2", "t3"])
    assert list(got.values()) == [ASHA, ASHA, MEENA]
    act = planner.plan(_item("assign_task", "t1", "t2", "t3"), _ward() + [_task("t1"), _task("t2"), _task("t3")])
    assert act.summary == "Assigned 3 tasks to Nurse Meena, Nurse Asha"
    assert act.args == {"pairs": [["t1", MEENA], ["t2", ASHA], ["t3", MEENA]]}


def test_pick_nurses_ignores_finished_tasks():
    done = _ev("task.done", {"task_id": "h1", "by": "n", "via": "tap", "note": ""}, "d9", 125)
    evs = _ward() + [_task("h1", kind="dose"), _assign("h1", MEENA, "a1"), done, _task("t1")]
    # h1 is a one-off dose? every_h=4 reopens it, so make it finished with every_h 0
    evs[3]["payload"]["every_h"] = 0
    assert planner.pick_nurses(evs, ["t1"]) == {"t1": MEENA}
    assert planner.pick_nurses(_ward() + [_task("h1"), _assign("h1", MEENA, "a1"), _task("t1")], ["t1"]) == {"t1": ASHA}


def test_assign_none_when_no_live_unassigned_task():
    evs = _ward() + [_task("t1"), _assign("t1", MEENA, "a1")]
    assert planner.plan(_item("assign_task", "t1"), evs) is None
    closed = _ward() + [_task("t1"), _state("discharging", "s9", 500, "ward")]
    assert planner.plan(_item("assign_task", "t1"), closed) is None
    one = _ward() + [_task("t1"), _task("t2"), _assign("t1", MEENA, "a1")]
    act = planner.plan(_item("assign_task", "t1", "t2"), one)
    assert act.args == {"pairs": [["t2", ASHA]]}
    assert act.summary == "Assigned 1 task to Nurse Asha"


def test_pick_doctor_available_else_named():
    assert planner.pick_doctor(_ward(), [], 1000) == seed.DOCTOR
    busy = _ev("doctor.status", {"doctor": seed.DOCTOR, "status": "busy", "until_ms": 9_000_000, "by": seed.DOCTOR},
               "b1", 10)
    assert planner.pick_doctor(_ward(), [busy], 1000) == seed.DOCTOR


def test_route_question():
    evs = _ward() + [_ask()]
    act = planner.plan(_item("route_question", "q1"), evs)
    assert act.args == {"question_id": "q1", "to": seed.DOCTOR}
    assert act.summary == "Sent the patient's question to Dr. A. Rao"
    routed = evs + [_ev("question.routed", {"question_id": "q1", "to": seed.DOCTOR}, "r1", 70)]
    assert planner.plan(_item("route_question", "q1"), routed) is None


def test_draft_answer_quotes_card():
    evs = _ward() + [_card(), _ask()]
    act = planner.plan(_item("draft_answer", "q1", "d1"), evs)
    assert act.draft.startswith("Your discharge card lists these warning signs: Fever above 38 °C;")
    assert act.draft.endswith("Keep the dressing dry for 48 hours.")
    assert len(act.cited) == 6
    assert [c["id"] for c in act.cited] == [f"d1:w{i}" for i in range(5)] + ["d1:care"]
    assert all(c["text"] in act.draft for c in act.cited)
    assert act.sentence == "Draft answer to R. Kumar's question"
    assert act.args == {"question_id": "q1"}
    assert [c["text"] for c in planner.cited_card(evs)][-1] == "Keep the dressing dry for 48 hours."


def test_draft_answer_none_without_card():
    assert planner.plan(_item("draft_answer", "q1", "d1"), _ward() + [_ask()]) is None


def test_nudge_names_assignee_else_first_nurse():
    nudge = _ev("nudge.raised", {"kind": "obs_overdue", "key": "k", "says": "Observations are ordered every 4 h."}, "n1", 500)
    evs = _ward() + [_task("t1"), _assign("t1", ASHA, "a1"), nudge]
    act = planner.plan(_item("nudge_obs_overdue", "n1"), evs)
    assert act.args == {"nudge_id": "n1", "nurse": ASHA}
    assert act.summary == "Nudged Nurse Asha: Observations are ordered every 4 h."
    bare = planner.plan(_item("nudge_obs_overdue", "n1"), _ward() + [nudge])
    assert bare.args["nurse"] == seed.NURSE


def test_file_read_monitor_and_swabs():
    task = _task("t1")
    read = _ev("proof.checked", {"photo_id": "p1", "task_id": "t1", "values_read": MONITOR}, "c1", 1000)
    evs = _ward() + [_ev("order.acknowledged", {"order_id": "o1", "by": "n"}, "k0", 105), task, read]
    act = planner.plan(_item("file_read", "c1"), evs)
    assert act.args == {"source": "monitor", "task_id": "t1", "photo_id": "p1", "values": MONITOR}
    assert act.summary == "Filed the monitor read 118/76, pulse 80"
    saved = evs + [_ev("task.done", {"task_id": "t1", "by": "n", "via": "tap", "note": "", "proof_id": "p1"}, "d1", 1200)]
    assert planner.plan(_item("file_read", "c1"), saved) is None

    camera = _ev("swabs.counted", {"count": 9, "opened": 10, "evidence_id": "ev1"}, "k5", 100)
    stay = [_state("theatre", "s1", 10, "ward"), _ev("count.pack_opened", {"quantity": 10}, "k1", 13), camera]
    act = planner.plan(_item("file_read", "k5", "k1"), stay)
    assert act.args == {"source": "swabs", "count": 9, "evidence_id": "ev1"}
    assert act.summary == "Filed the camera count: 9 of 10 swabs back"
    closed = stay + [_ev("count.closing", {"opened": 10, "returned": 9, "unaccounted": 1}, "k9", 200)]
    assert planner.plan(_item("file_read", "k5", "k1"), closed) is None


def test_propose_move():
    evs = _theatre()
    act = planner.plan(_item("propose_move", "s1"), evs)
    assert act.args == {"to": "ward"}
    assert act.sentence.startswith("Back to ward: ")
    open_count = _theatre(closing=False) + [_ev("count.pack_opened", {"quantity": 10}, "k1", 13)]
    assert planner.plan(_item("propose_move", "s1"), open_count) is None
    assert planner.plan(_item("propose_move", "s1"), evs + [_state("ward", "s3", 99, "theatre")]) is None


def test_plan_none_when_done():
    evs = _ward() + [_ev("order.acknowledged", {"order_id": "o1", "by": "n"}, "k0", 105)]
    assert planner.plan(_item("ack_order", "o1"), evs) is None
    answered = _ward() + [_card(), _ask(), _ev("question.answered", {"question_id": "q1", "answer": "a", "by": DR}, "a9", 80)]
    assert planner.plan(_item("draft_answer", "q1", "d1"), answered) is None
    assert planner.plan(_item("route_question", "q1"), answered) is None


def test_plan_handles_every_watched_kind():
    for kind in LEVELS:
        if kind in ("ack_order", "assign_task", "nudge_obs_overdue", "route_question", "file_read",
                    "draft_answer", "propose_move"):
            assert kind in planner._PLANNERS


def test_templates_pass_both_regexes():
    evs = _ward() + [_card(), _ask(), _task("t1"), _task("t2")]
    texts = []
    for item in (_item("ack_order", "o1"), _item("assign_task", "t1", "t2"), _item("route_question", "q1"),
                 _item("draft_answer", "q1", "d1")):
        act = planner.plan(item, evs)
        texts += [act.summary, act.sentence, act.draft]
    move = planner.plan(_item("propose_move", "s1"), _theatre())
    texts += [move.summary, move.sentence]
    texts += list(planner.TEMPLATES.values())
    _clean(*[t for t in texts if t])
