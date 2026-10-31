"""Task 1 (v4 UX): staff wording of strip alerts and the doctor's home next step."""

from __future__ import annotations

import re

from app.journey.nudges import strips_vs_rx
from app.journey.states import now_next

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
RAO = "Dr. A. Rao (synthetic)"
NURSE = "Nurse Meena (synthetic)"


def _ev(eid, kind, ts, **payload):
    return {"id": eid, "event_type": kind, "ts_ms": ts, "payload": payload, "episode_id": "e1", "supersedes_id": None}


def _rx(key, name, strength):
    return _ev("rx", "rx.ordered", 1, by=RAO, source="demo", rows=[{"key": key, "name": name, "strength": strength}])


def _strip(name, strength):
    return _ev("m1", "brownbag.med_found", 2, name_as_read=name, generic=name.lower(), strength=strength)


def _home_events():
    return [_ev("s1", "patient.state", 1, **{"from": "discharging", "to": "home", "by": RAO})]


def _checkin(eid, day):
    return _ev(eid, "checkin.recorded", 5, day=day, feels="Better", signs=[], note="")


def _seen(eid, by):
    return _ev(f"seen-{by}", "checkin.seen", 6, checkin_id=eid, by=by)


def test_strip_nudge_has_staff_wording():
    out = strips_vs_rx([_rx("amlodipine", "Amlodipine", "5 mg"), _strip("Amlodipine", "10 mg")])
    assert out[0]["says_staff"] == "Strip reads amlodipine 10 mg; prescription says 5 mg."
    assert "Show both to your pharmacist or doctor." in out[0]["says"]


def test_unprescribed_strip_staff_wording():
    out = strips_vs_rx([_rx("amlodipine", "Amlodipine", "5 mg"), _strip("Ibuprofen", "400 mg")])
    assert out[0]["says_staff"] == "Strip reads ibuprofen 400 mg; not on the prescription from Dr. A. Rao (synthetic)."
    assert not any(ADVICE.search(n["says_staff"]) for n in out)


def test_other_nudge_kinds_keep_one_wording():
    from app.journey.nudges import _nudge

    assert _nudge("k", "x", "nurse", "same", None, None, 0)["says_staff"] == "same"


def test_home_next_step_names_unseen_checkin():
    events = _home_events() + [_checkin("c1", day=1)]
    assert now_next(events)["next_mine"] == "Day 1 check-in not seen."
    assert now_next(events)["next"] == "Day 1 check-in not seen by the doctor."
    assert now_next(events)["you_next"] == "Dr. Rao has not seen your day 1 check-in yet."
    assert now_next(events)["next_role"] == "doctor"
    assert now_next(events + [_seen("c1", NURSE)])["next_role"] == "doctor"
    assert now_next(events + [_seen("c1", RAO)])["next"] == "The patient is home. No further steps."
    assert now_next(events + [_seen("c1", RAO)])["next_role"] is None
    for key in ("next", "next_mine", "you_next"):
        assert not ADVICE.search(now_next(events)[key])


def test_reviews_and_questions_come_before_checkins():
    base = _home_events() + [_checkin("c1", day=1)]
    review = _ev("rv", "review.requested", 3, photo_id="p", note="", by="R. Kumar, 58 M (synthetic)")
    question = _ev("q", "question.asked", 3, to="doctor", text="Why?", by="R. Kumar, 58 M (synthetic)")
    assert now_next(base + [review])["next_mine"] == "Review the healing photo."
    assert now_next(base + [question])["next_mine"] == "Answer the question."
