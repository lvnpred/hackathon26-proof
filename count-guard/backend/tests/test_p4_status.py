"""P4 Task 4: the doctor's status chip. Auto from theatre, a hand-set status wins until it expires."""

from __future__ import annotations

import re

import httpx
import pytest

from app.journey import seed
from app.journey.doctor_status import current, free_about, theatre_payload
from app.journey.stories import clock, plain
from tests.test_care_demo import _client
from tests.test_flow_states import ADMIT_CHECKS, _move
from tests.test_flow_tasks import _url

H = 3_600_000
MIN = 60_000
ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
AVAILABLE = "Dr. A. Rao: Available"
THEATRE = "Dr. A. Rao: In theatre with R. Kumar, free about 11:45"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _ward(tmp_path):
    client = _client(tmp_path)
    got = client.post("/journey/demo/seed").json()
    ids = {p["bed"]: p["id"] for p in got["patients"]}
    return client, ids, got["board"]


def _theatre(client, eid, at_ms=2 * H):
    assert _move(client, eid, "admitting", reason="Hernia repair", at_ms=0).status_code == 200
    assert _move(client, eid, "ward", checklist=ADMIT_CHECKS, at_ms=H).status_code == 200
    r = _move(client, eid, "theatre", procedure="hernia-repair", at_ms=at_ms)
    assert r.status_code == 200, r.text


def _chip(client, board, ids, at_ms, **extra):
    params = {"board": board, "ids": ",".join(ids.values()), "at_ms": at_ms, **extra}
    return client.get("/journey/staff/doctor", params=params)


def _set(client, board, ids, status, at_ms, until_ms=None, **extra):
    body = {"board": board, "ids": list(ids.values()), "status": status, "at_ms": at_ms, "until_ms": until_ms, **extra}
    return client.post("/journey/staff/doctor", json=body)


def _events(client, eid):
    return client.app.state.morning.events(eid)


def test_free_about_rounds_up():
    assert clock(free_about(2 * H, 31)) == "Day 0 11:45"
    assert clock(free_about(2 * H, 45)) == "Day 0 11:45"
    assert clock(free_about(2 * H, 46)) == "Day 0 12:00"
    got = theatre_payload("Dr. A. Rao (synthetic)", "R. Kumar, 58 M (synthetic)", 2 * H, 31)
    assert got == {"doctor": "Dr. A. Rao (synthetic)", "status": "in_theatre", "patient": "R. Kumar",
                   "until_ms": free_about(2 * H, 31), "source": "auto"}


def test_chip_flips_when_kumar_enters_theatre(tmp_path):
    client, ids, board = _ward(tmp_path)
    assert _chip(client, board, ids, 0).json()["text"] == AVAILABLE
    _theatre(client, ids["4"])
    got = _chip(client, board, ids, 2 * H).json()
    assert got["text"] == THEATRE and got["source"] == "auto" and got["status"] == "in_theatre"
    assert got["patient"] == "R. Kumar" and got["until_ms"] == free_about(2 * H, 31)
    assert _chip(client, board, ids, H).json()["text"] == AVAILABLE
    status = next(e for e in _events(client, ids["4"]) if e["event_type"] == "doctor.status")
    assert status["payload"]["by"] == "Dr. A. Rao (synthetic)" and status["ts_ms"] == 2 * H
    nurse = "Nurse Asha (synthetic)"
    for step, at in (("began", 2 * H + 10 * MIN), ("opened", 2 * H + 20 * MIN), ("closing", 2 * H + 50 * MIN), ("ended", 3 * H)):
        body = {"step": step, "by": nurse, "at_ms": at, **({"quantity": 20} if step == "opened" else {"returned": 20} if step == "closing" else {})}
        route = "count" if step in ("opened", "closing") else "surgery"
        assert client.post(_url(ids["4"], route), json=body).status_code == 200
    assert _chip(client, board, ids, 3 * H).json()["status"] == "in_theatre"
    assert _move(client, ids["4"], "ward", at_ms=3 * H + MIN, reason="").status_code == 200
    assert _chip(client, board, ids, 4 * H).json()["text"] == AVAILABLE


def test_manual_busy_wins_until_it_expires(tmp_path):
    client, ids, board = _ward(tmp_path)
    _theatre(client, ids["4"])
    r = _set(client, board, ids, "busy", 2 * H, until_ms=2 * H + 30 * MIN)
    assert r.status_code == 200 and r.json()["text"] == "Dr. A. Rao: Busy until 11:30"
    assert r.json()["source"] == "manual"
    assert _chip(client, board, ids, 2 * H + 29 * MIN).json()["text"] == "Dr. A. Rao: Busy until 11:30"
    assert _chip(client, board, ids, 2 * H + 30 * MIN).json()["text"] == THEATRE
    manual = next(e for e in _events(client, board) if e["event_type"] == "doctor.status")
    assert manual["payload"]["by"] == "Dr. A. Rao (synthetic)" and manual["payload"]["source"] == "manual"
    assert not any(e["event_type"] == "doctor.status" and e["payload"]["source"] == "manual"
                   for eid in ids.values() for e in _events(client, eid))
    r = _set(client, board, ids, "available", 2 * H + 31 * MIN, until_ms=2 * H + 60 * MIN)
    assert r.json()["text"] == AVAILABLE and r.json()["source"] == "manual"
    cleared = _set(client, board, ids, "auto", 2 * H + 32 * MIN)
    assert cleared.status_code == 200 and cleared.json()["text"] == THEATRE and cleared.json()["source"] == "auto"


def test_status_refusals(tmp_path, monkeypatch):
    client, ids, board = _ward(tmp_path)
    details = []
    plain_set, plain_chip = _set, _chip

    def collect(call):
        def wrapped(*a, **k):
            r = call(*a, **k)
            details.append(str(r.json().get("detail", "")) if r.status_code >= 400 else "")
            return r
        return wrapped

    monkeypatch.setitem(globals(), "_set", collect(plain_set))
    monkeypatch.setitem(globals(), "_chip", collect(plain_chip))
    before = len(_events(client, board))
    at = 2 * H
    for status, until in (("busy", at), ("busy", at - 1), ("busy", at + 12 * H + 1), ("busy", None),
                          ("available", at + 13 * H), ("auto", at + 1)):
        assert _set(client, board, ids, status, at, until_ms=until).status_code == 422, (status, until)
    many = {str(i): f"id{i}" for i in range(11)}
    assert _set(client, board, many, "auto", at).status_code == 422
    assert _set(client, board, {}, "auto", at).status_code == 422
    assert _set(client, board, ids, "auto", -1).status_code == 422
    assert _set(client, board, ids, "busy", at, until_ms=at + 12 * H).status_code == 200
    assert _set(client, "nope", ids, "auto", at).status_code == 404
    assert _set(client, board, {"x": "nope"}, "auto", at).status_code == 404
    assert _chip(client, board, {"x": "nope"}, at).status_code == 404
    assert _chip(client, board, many, at).status_code == 422
    assert _chip(client, board, ids, -1).status_code == 422
    assert client.get("/journey/staff/doctor", params={"board": board, "ids": "", "at_ms": 0}).status_code == 422
    assert client.get("/journey/staff/doctor", params={"board": board, "ids": "a" * 65, "at_ms": 0}).status_code == 422
    assert len(_events(client, board)) == before + 1
    refusals = [d for d in details if d]
    assert any("Send 1 to 10 patient ids" in d for d in refusals) and len(refusals) >= 10
    assert client.get("/journey/staff/doctor", params={"board": ids["4"], "ids": board, "at_ms": 0}).status_code == 422
    refusals.append(plain_set(client, ids["4"], ids, "auto", 0).json()["detail"])
    for text in refusals:
        assert not ADVICE.search(text), text


def test_staff_routes_refuse_a_patient_as_board(tmp_path):
    client, ids, board = _ward(tmp_path)
    kumar = ids["4"]
    count = len(_events(client, kumar))
    r = _set(client, kumar, ids, "busy", H, until_ms=2 * H)
    assert r.status_code == 422 and r.json()["detail"] == "That is not the ward staff board."
    assert _chip(client, kumar, ids, H).status_code == 422
    assert _set(client, board, {"board": board, **ids}, "auto", H).status_code == 422
    assert len(_events(client, kumar)) == count


def test_seed_returns_board(tmp_path):
    client = _client(tmp_path)
    got = client.post("/journey/demo/seed").json()
    assert [p["bed"] for p in got["patients"]] == ["4", "7", "9"] and set(got) == {"patients", "board"}
    assert got["board"] not in {p["id"] for p in got["patients"]}
    assert _events(client, got["board"]) == []
    view = client.get(f"/journey/episodes/{got['board']}").json()
    assert view["state"] == "clinic" and view["episode"]["label"] == seed.BOARD_LABEL


def test_current_is_pure():
    assert current("Dr. A. Rao (synthetic)", [], [], 0) == {
        "doctor": "Dr. A. Rao (synthetic)", "status": "available", "text": AVAILABLE,
        "until_ms": None, "source": "auto", "patient": None}


def test_status_strings_have_no_advice(tmp_path):
    client, ids, board = _ward(tmp_path)
    _theatre(client, ids["4"])
    texts = [_chip(client, board, ids, t).json()["text"] for t in (0, 2 * H, 3 * H)]
    texts.append(_set(client, board, ids, "busy", 2 * H, until_ms=2 * H + 30 * MIN).json()["text"])
    texts.append(_set(client, board, ids, "available", 2 * H + MIN, until_ms=3 * H).json()["text"])
    texts.append(_set(client, board, ids, "auto", 2 * H + 2 * MIN).json()["text"])
    for eid in (ids["4"], board):
        texts += [plain(e) for e in _events(client, eid) if e["event_type"] == "doctor.status"]
    assert any("set the status: Busy until 11:30." in t for t in texts)
    assert any("is in theatre with R. Kumar, free about 11:45." in t for t in texts)
    assert any("set the status: automatic." in t for t in texts)
    for text in texts:
        assert not ADVICE.search(text), text
