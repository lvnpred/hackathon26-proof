"""The P4 story with no model key: Kumar, Das and Iyer, prepared files only, explicit at_ms."""

from __future__ import annotations

import re

import httpx
import pytest

from app.journey.doctor_status import free_about
from tests.test_care_demo import _client
from tests.test_flow_states import ADMIT_CHECKS, DISCHARGE_CHECKS, _move
from tests.test_flow_tasks import DOC, _url
from tests.test_p4_ask import PNG, _ask
from tests.test_p4_status import AVAILABLE, THEATRE, _chip

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
H = 3_600_000
MIN = 60_000
NURSE = "Nurse Asha (synthetic)"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _upload(client, eid, tail, name, **data):
    return _ok(client.post(_url(eid, tail), files={"file": (name, PNG, "image/png")}, data=data))


def _sign_discharge(client, eid, at_ms):
    body = {"summary": "Recovering well.", "by": DOC, "at_ms": at_ms}
    _ok(client.post(_url(eid, "discharge/sign"), json=body))


def test_p4_done_when_without_a_key(tmp_path):
    client = _client(tmp_path)
    got = _ok(client.post("/journey/demo/seed"))
    ids = {p["bed"]: p["id"] for p in got["patients"]}
    board = got["board"]
    kumar, iyer, das = ids["4"], ids["7"], ids["9"]
    chip = lambda at: _chip(client, board, ids, at).json()["text"]
    seen = []

    # Kumar: clinic to theatre to home. The chip follows him.
    _ok(client.post(_url(kumar, "rx/demo"), json={"at_ms": 0}))
    _ok(_move(client, kumar, "admitting", reason="Hernia repair", at_ms=0))
    _ok(_move(client, kumar, "ward", checklist=ADMIT_CHECKS, at_ms=H))
    assert chip(H + 30 * MIN) == AVAILABLE
    _ok(_move(client, kumar, "theatre", procedure="hernia-repair", at_ms=2 * H))
    assert chip(2 * H) == THEATRE == _chip(client, board, ids, 2 * H + 20 * MIN).json()["text"]
    assert _chip(client, board, ids, 2 * H).json()["until_ms"] == free_about(2 * H, 31)
    for step, at in (("began", 2 * H + 10 * MIN), ("ended", 2 * H + 40 * MIN)):
        _ok(client.post(_url(kumar, "surgery"), json={"step": step, "by": NURSE, "at_ms": at}))
    _ok(_move(client, kumar, "ward", at_ms=3 * H, reason=""))
    assert chip(3 * H + MIN) == AVAILABLE
    _sign_discharge(client, kumar, 3 * H + 5 * MIN)
    _ok(_move(client, kumar, "home", checklist=DISCHARGE_CHECKS, at_ms=24 * H))

    # Kumar at home: all four Ask actions.
    bot = _ok(_ask(client, kumar, "How do I care for the dressing?", at_ms=25 * H))["ask"]["questions"][-1]["answer"]
    assert bot["found"] and any("Keep the dressing dry" in s["text"] for s in bot["sources"])
    seen.append(bot["text"])
    asked = _ok(_ask(client, kumar, "Is some redness at the wound normal?", "doctor", at_ms=25 * H + MIN))
    qid = asked["ask"]["questions"][-1]["id"]
    body = {"text": "A little redness is expected.", "by": DOC, "at_ms": 26 * H}
    answered = _ok(client.post(_url(kumar, f"questions/{qid}/answer"), json=body))
    reply = answered["ask"]["questions"][-1]["answer"]
    assert reply["via"] == "text" and reply["source"] == "doctor"
    review = _upload(client, kumar, "ask/review", "wound-day3.png", note="Day 3", at_ms="27000000")
    rid = review["ask"]["reviews"][-1]["id"]
    decision = {"decision": "no_visit", "by": DOC, "at_ms": 28 * H}
    decided = _ok(client.post(_url(kumar, f"reviews/{rid}/answer"), json=decision))
    label = decided["ask"]["reviews"][-1]["answer"]["label"]
    assert label == "No visit needed"
    seen += [label, decided["now_next"]["now"], decided["now_next"]["next"]]
    meds = _upload(client, kumar, "ask/medicines", "meds-kumar.png", at_ms="29000000")["ask"]["medicines"][-1]
    rows = meds["rows"]
    assert len(rows) == 4 and sum(r["prescribed"] for r in rows) == 3 and meds["match"] == "mismatch"
    assert all(r["schedule"] for r in rows if r["prescribed"])
    assert [r["read"] for r in rows if r["flag"]] == ["Cetirizine 10 mg"]
    seen += [meds["why"], *(r["why"] for r in rows), *(r["schedule"] for r in rows if r["schedule"])]

    # Das: the bot answers from the prescription line, and only that line.
    _ok(client.post(_url(das, "rx/demo"), json={"at_ms": 0}))
    _ok(_move(client, das, "clinic_done", at_ms=H))
    got_das = _ok(_ask(client, das, "When do I take amlodipine?", at_ms=2 * H))["ask"]["questions"][-1]["answer"]
    assert got_das["found"] and len(got_das["sources"]) == 1
    assert "Amlodipine 5 mg" in got_das["sources"][0]["text"] and got_das["sources"][0]["kind"] == "prescription"
    seen.append(got_das["text"])

    # Iyer: the photo names each strip with its schedule, and flags what is not prescribed.
    _sign_discharge(client, iyer, 2 * H)
    _ok(_move(client, iyer, "home", checklist=DISCHARGE_CHECKS, at_ms=24 * H))
    iyer_meds = _upload(client, iyer, "ask/medicines", "meds-iyer.png", at_ms="90000000")["ask"]["medicines"][-1]
    flagged = {r["read"]: r["flag"] for r in iyer_meds["rows"]}
    assert flagged["Ibuprofen 400 mg"] == "not_prescribed"
    assert [f for f in flagged.values() if f is None] and len([f for f in flagged.values() if f is None]) == 3
    assert all(r["schedule"] for r in iyer_meds["rows"] if r["prescribed"])
    seen += [iyer_meds["why"], *(r["why"] for r in iyer_meds["rows"])]

    # Every string produced here, and the plain lines of the stories.
    for eid in (kumar, das, iyer, board):
        seen += [r["what"] for r in client.get(_url(eid, "audit")).json()["rows"] if r["type"] == "doctor.status"]
    seen.append(chip(2 * H + 20 * MIN))
    for text in seen:
        assert text and not ADVICE.search(text), text
