"""Correction moved into the care app (spec §9 "morning correction route"): a person corrects a reading by superseding it.

Only a typed observation set and the theatre drug lines (test_correct_drugs.py) are correctable. Everything the
hard stop, the photo gate, the ward list or the dose nudges read is refused with 409, so a correction can never
change what those decide.
"""

from __future__ import annotations

import pytest

from test_care_demo import _client
from test_stream import _patient

NURSE = "Nurse A. Iyer (synthetic)"
OBS = {"sbp": 85, "dbp": 60, "hr": 80, "by": NURSE}


def _store(client):
    return client.app.state.morning


def _obs(client, eid) -> dict:
    assert client.post(f"/journey/episodes/{eid}/obs", json=OBS).status_code == 200
    return [e for e in _store(client).events(eid) if e["event_type"] == "obs.recorded"][-1]


def _correct(client, eid, event_id, payload, by=NURSE):
    return client.post(f"/journey/episodes/{eid}/correct", json={"event_id": event_id, "payload": payload, "by": by})


def test_correct_supersedes(tmp_path):
    client = _client(tmp_path)
    eid = _patient(client)
    old = _obs(client, eid)
    res = _correct(client, eid, old["id"], {"sbp": 118}, by="Nurse B. Das (synthetic)")
    assert res.status_code == 200, res.text
    assert res.json()["episode"]["id"] == eid  # the whole chart view, like every care action
    new = [e for e in _store(client).events(eid) if e["event_type"] == "obs.recorded"][-1]
    assert new["supersedes_id"] == old["id"]
    assert new["ts_ms"] == old["ts_ms"]  # the reading keeps its own time
    assert new["payload"] == {**old["payload"], "sbp": 118, "by": "Nurse B. Das (synthetic)"}


def test_a_corrected_reading_closes_its_past_limit_nudge(tmp_path):
    from app.journey.nudges import open_nudges
    client = _client(tmp_path)
    eid = _patient(client)
    orders = {"doses": [], "obs_every_h": 4, "limits": {"sbp_min": 90}, "by": "Dr. Test"}
    _store(client).append(eid, "ward.orders_set", orders, ts_ms=0)
    old = _obs(client, eid)
    assert any(n["payload"]["kind"] == "obs_past_limit" for n in open_nudges(_store(client).events(eid)))
    assert _correct(client, eid, old["id"], {"sbp": 118}).status_code == 200
    assert not any(n["payload"]["kind"] == "obs_past_limit" for n in open_nudges(_store(client).events(eid)))


@pytest.mark.parametrize("kind", ["count.closing", "count.pack_opened", "surgery.began", "surgery.ended", "patient.state"])
def test_correct_refuses_count_and_state(tmp_path, kind):
    client = _client(tmp_path)
    eid = _patient(client)
    old = _store(client).append(eid, kind, {"by": NURSE, "to": "ward", "returned": 20}, ts_ms=1)
    before = len(_store(client).events(eid))
    res = _correct(client, eid, old["id"], {"returned": 20})
    assert res.status_code == 409
    assert len(_store(client).events(eid)) == before  # nothing written


def test_a_real_move_is_refused(tmp_path):
    client = _client(tmp_path)
    eid = _patient(client)
    move = [e for e in _store(client).events(eid) if e["event_type"] == "patient.state"]
    assert not move  # a new patient starts in clinic without a move; make one
    assert client.post(f"/journey/episodes/{eid}/state", json={"to": "admitting", "by": NURSE, "reason": "x"}).status_code == 200
    move = [e for e in _store(client).events(eid) if e["event_type"] == "patient.state"][-1]
    res = _correct(client, eid, move["id"], {"to": "ward"})
    assert res.status_code == 409 and res.json()["detail"] == "A patient move is recorded as a new move, not corrected here."


@pytest.mark.parametrize("kind", [
    "check.photo", "check.override", "photo.added", "proof.checked",  # the photo gate (U9) reads these
    "camera.advice", "camera.closed", "swabs.counted",  # camera output is advice; never relabelled as a person's
    "patient.registered", "bed.changed", "rx.ordered",  # the ward list, the bed, and Doctor Dictation's record
    "dose.given", "vitals.reading",  # dose-gap nudges and the strip read these in write order
    "task.done", "work.done", "nudge.raised", "order.signed",
])
def test_correct_refuses_anything_but_a_typed_observation(tmp_path, kind):
    client = _client(tmp_path)
    eid = _patient(client)
    old = _store(client).append(eid, kind, {"by": NURSE}, ts_ms=1)
    assert _correct(client, eid, old["id"], {"by": NURSE}).status_code == 409


@pytest.mark.parametrize("by", ["AI (on behalf of Nurse A)", "Count Guard AI", "  count   guard ai "])
def test_correct_needs_a_person(tmp_path, by):
    client = _client(tmp_path)
    eid = _patient(client)
    old = _obs(client, eid)
    assert _correct(client, eid, old["id"], {"sbp": 118}, by=by).status_code == 422


def test_correct_refuses_an_event_already_corrected(tmp_path):
    client = _client(tmp_path)
    eid = _patient(client)
    old = _obs(client, eid)
    assert _correct(client, eid, old["id"], {"sbp": 118}).status_code == 200
    res = _correct(client, eid, old["id"], {"sbp": 119})
    assert res.status_code == 409


@pytest.mark.parametrize("payload", [{}, {"sbp": 5}, {"sbp": 118, "note": "x"}, {"by": "Someone"}, {"evidence_id": "x"}])
def test_correct_checks_the_values(tmp_path, payload):
    client = _client(tmp_path)
    eid = _patient(client)
    old = _obs(client, eid)
    assert _correct(client, eid, old["id"], payload).status_code == 422


def test_correct_needs_the_event_on_this_episode(tmp_path):
    client = _client(tmp_path)
    eid = _patient(client)
    other = _patient(client, "L. Rao (synthetic)")
    old = _obs(client, other)
    assert _correct(client, eid, old["id"], {"sbp": 118}).status_code == 404
    assert _correct(client, eid, "missing", {"sbp": 118}).status_code == 404
    assert _correct(client, "nope", old["id"], {"sbp": 118}).status_code == 404


def test_correct_takes_the_demo_time_like_every_care_action(tmp_path):
    client = _client(tmp_path)
    eid = _patient(client)
    old = _obs(client, eid)
    body = {"event_id": old["id"], "payload": {"hr": 72}, "by": NURSE, "at_ms": old["ts_ms"] + 60_000}
    assert client.post(f"/journey/episodes/{eid}/correct", json=body).status_code == 200
    assert client.post(f"/journey/episodes/{eid}/correct", json={**body, "extra": 1}).status_code == 422
