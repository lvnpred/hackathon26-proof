"""Task 1: two-way threads. The check-in list in the ask view and the nurse's idempotent Seen."""

from __future__ import annotations

import httpx
import pytest

from tests.test_care_demo import _client, _seed
from tests.test_flow_states import ADVICE
from tests.test_flow_tasks import _url
from tests.test_p4_ask import _home


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


NURSE, OTHER = "Nurse Meena (synthetic)", "Nurse Asha (synthetic)"


def _kumar_home(tmp_path):
    client = _client(tmp_path)
    eid = {p["bed"]: p["id"] for p in _seed(client)}["4"]
    _home(client, eid)
    return client, eid


def _checkin(client, eid):
    body = {"day": 3, "feels": "Better", "signs": [], "note": "", "at_ms": 5000}
    assert client.post(_url(eid, "checkin"), json=body).status_code == 200
    return client.get(f"/journey/episodes/{eid}").json()["ask"]["checkins"][0]["id"]


def test_checkin_seen_is_idempotent_per_nurse(tmp_path):
    client, eid = _kumar_home(tmp_path)
    cid = _checkin(client, eid)
    for _ in range(2):
        assert client.post(_url(eid, f"checkins/{cid}/seen"), json={"by": NURSE, "at_ms": 6000}).status_code == 200
    client.post(_url(eid, f"checkins/{cid}/seen"), json={"by": OTHER, "at_ms": 7000})
    seen = client.get(f"/journey/episodes/{eid}").json()["ask"]["checkins"][0]["seen"]
    assert seen == [{"by": NURSE, "at_ms": 6000}, {"by": OTHER, "at_ms": 7000}]
    rows = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "checkin.seen"]
    assert len(rows) == 2


def test_checkin_seen_unknown_or_foreign_is_404(tmp_path):
    client, eid = _kumar_home(tmp_path)
    other = {p["bed"]: p["id"] for p in _seed(client)}["7"]
    cid = _checkin(client, eid)
    assert client.post(_url(other, f"checkins/{cid}/seen"), json={"by": NURSE}).status_code == 404
    assert client.post(_url(eid, "checkins/nope/seen"), json={"by": NURSE}).status_code == 404
    assert client.post(_url(eid, f"checkins/{cid}/seen"), json={"by": ""}).status_code == 422


def test_checkin_view_fields(tmp_path):
    client, eid = _kumar_home(tmp_path)
    cid = _checkin(client, eid)
    row = client.get(f"/journey/episodes/{eid}").json()["ask"]["checkins"][0]
    assert row == {"id": cid, "at_ms": 5000, "day": 3, "feels": "Better", "signs": [], "note": "", "seen": []}


def test_thread_view_holds_record_and_doctor_asks(tmp_path):
    client, eid = _kumar_home(tmp_path)
    client.post(_url(eid, "ask/bot"), json={"text": "When is my wound check?", "at_ms": 1000})
    client.post(_url(eid, "ask/doctor"), json={"text": "Is the swelling normal?", "at_ms": 2000})
    ask = client.get(f"/journey/episodes/{eid}").json()["ask"]
    assert [(q["to"], q["answer"] is not None) for q in ask["questions"]] == [("bot", True), ("doctor", False)]


def test_seen_lines_have_no_advice():
    from app.journey.stories import patient_line, plain

    e = {"event_type": "checkin.seen", "payload": {"checkin_id": "c", "by": NURSE}}
    assert plain(e) == f"{NURSE} saw a check-in."
    assert patient_line(e, {}) == "Nurse Meena saw your check-in."
    for s in (plain(e), patient_line(e, {})):
        assert not ADVICE.search(s)
