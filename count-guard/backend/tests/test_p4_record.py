"""P4 Task 1: the patient's record lines, the record bot's checks, and the patients' prescriptions."""

from __future__ import annotations

import json
import string

import httpx
import pytest

from app.journey import record
from app.journey.dictation import ADVICE
from app.journey.record import (
    FOUND, NOT_FOUND, WRAPPERS, answer_from_reply, bot_prompt, record_lines, rules_answer,
)
from app.journey.schedule import build, schedule_text
from app.journey.rx import DEMO_DOCUMENT, IYER_DOCUMENT, from_document
from tests.test_care_demo import _client
from tests.test_flow_states import ADMIT_CHECKS, DISCHARGE_CHECKS, _move, _new, _view
from tests.test_flow_tasks import DOC, NURSE, _ack, _done, _sign, _url

OBS = {"kind": "obs", "text": "BP every 1 h", "every_h": 1, "limits": {"sbp_min": 90}}
SUMMARY = "Right hernia repaired. Wound is clean."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _rows(rx):
    return {row["key"]: row for row in build(rx)}


def _full(tmp_path):
    client, eid = _new(tmp_path)
    assert client.post(_url(eid, "rx/demo"), json={"at_ms": 0}).status_code == 200
    assert _move(client, eid, "admitting", reason="Hernia repair").status_code == 200
    assert _move(client, eid, "ward", checklist=ADMIT_CHECKS).status_code == 200
    order = _sign(client, eid, [OBS]).json()["order_list"][0]
    view = _ack(client, eid, order["id"], 1000).json()
    values = {"sbp": 120, "dbp": 80, "hr": 80, "spo2": 98, "temp": 36.8}
    r = _done(client, eid, view["tasks"][0]["id"], 2000, values=values)
    assert r.status_code == 200, r.text
    body = {"summary": SUMMARY, "by": DOC, "at_ms": 3000}
    assert client.post(_url(eid, "discharge/sign"), json=body).status_code == 200
    assert _move(client, eid, "home", checklist=DISCHARGE_CHECKS).status_code == 200
    return client, eid


def _lines(client, eid):
    return record_lines(client.app.state.morning.events(eid))


def _line(lines, needle):
    return next(line for line in lines if needle in line["text"])


def test_schedule_text():
    rows = _rows(from_document(DEMO_DOCUMENT, source="demo"))
    assert schedule_text(rows["amlodipine"]) == "1 in the morning; After food; for 30 days"
    assert schedule_text(rows["metoprolol"]) == "1 in the morning, 1 at night; After food; for 30 days"
    assert schedule_text(rows["paracetamol"]) == "as needed; As needed for pain; Max 3 times daily"


def test_demo_rx_names_the_episode(tmp_path):
    client = _client(tmp_path)
    label = "A. Das, 47 M (synthetic)"
    eid = client.post("/journey/episodes", json={"label": label}).json()["id"]
    view = client.post(_url(eid, "rx/demo"), json={"at_ms": 0}).json()
    assert view["rx"]["patient"] == label
    assert view["rx"]["advice"] == [] and view["rx"]["review"] == ""
    assert not any("hernia" in d.lower() for d in view["rx"]["diagnosis"])
    kumar = client.post("/journey/episodes", json={"label": "R. Kumar, 58 M (synthetic)"}).json()["id"]
    own = client.post(_url(kumar, "rx/demo"), json={"at_ms": 0}).json()["rx"]
    assert own["advice"] and own["review"] and any("hernia" in d.lower() for d in own["diagnosis"])


def test_seed_iyer_has_her_prescription(tmp_path):
    client = _client(tmp_path)
    seeded = client.post("/journey/demo/seed").json()
    by_bed = {p["bed"]: p for p in seeded["patients"]}
    views = {bed: client.get(f"/journey/episodes/{p['id']}").json() for bed, p in by_bed.items()}
    assert [r["key"] for r in views["7"]["rx"]["rows"]] == ["pantoprazole", "atorvastatin", "paracetamol"]
    assert views["7"]["rx"]["patient"] == "S. Iyer (synthetic)"
    assert views["4"]["rx"] is None and views["9"]["rx"] is None
    assert [row["name"] for row in IYER_DOCUMENT["structured"]["rx"]] == ["Pantoprazole", "Atorvastatin", "Paracetamol"]


def test_record_lines_from_a_full_record(tmp_path):
    client, eid = _full(tmp_path)
    lines = _lines(client, eid)
    assert [line["id"] for line in lines] == [f"L{n}" for n in range(1, len(lines) + 1)]
    assert {"prescription", "order", "task", "discharge", "card", "stay"} <= {line["kind"] for line in lines}
    mine = {e["id"] for e in client.app.state.morning.events(eid)}
    assert all(line["event_id"] in mine and len(line["text"]) <= 300 for line in lines)
    assert _line(lines, "Amlodipine")["text"] == (
        "Prescription from Dr. A. Rao (synthetic): Tab. Amlodipine 5 mg — 1 in the morning; After food; for 30 days."
    )
    assert "Discharge summary from Dr. A. Rao (synthetic): Wound is clean." in {l["text"] for l in lines}
    assert any(l["text"].startswith("Order signed by Dr. A. Rao (synthetic) at 09:00: BP every 1 h") for l in lines)
    assert any(l["kind"] == "task" and l["text"].endswith("done by Nurse Asha (synthetic) at 09:00.") for l in lines)
    assert any(l["text"].startswith("Warning sign on your discharge card: ") for l in lines)


def test_rules_answer_cites_the_prescription_line(tmp_path):
    client, eid = _full(tmp_path)
    lines = _lines(client, eid)
    got = rules_answer("When do I take amlodipine?", lines)
    assert got["found"] and got["answer"] == FOUND
    assert got["sources"] == [_line(lines, "Amlodipine")]


def test_rules_answer_not_found(tmp_path):
    client, eid = _full(tmp_path)
    lines = _lines(client, eid)
    for question in ("What is the capital of France?", "When?", ""):
        got = rules_answer(question, lines)
        assert got == {"answer": NOT_FOUND, "sources": [], "found": False}


def test_advice_seeking_question_gets_no_advice(tmp_path):
    client, eid = _full(tmp_path)
    lines = _lines(client, eid)
    got = rules_answer("Should I stop amlodipine?", lines)
    assert got["sources"] == [_line(lines, "Amlodipine")]
    assert not ADVICE.search(got["answer"])
    assert rules_answer("Can I take two?", lines)["found"] is False


def test_model_reply_checked(tmp_path):
    client, eid = _full(tmp_path)
    lines = _lines(client, eid)
    lid = _line(lines, "Amlodipine")["id"]
    good = "Amlodipine 5 mg, 1 in the morning, after food, for 30 days."

    def reply(answer, sources):
        return json.dumps({"answer": answer, "sources": sources})

    ok = answer_from_reply(reply(good, [lid]), lines)
    assert ok == {"answer": good, "sources": [_line(lines, "Amlodipine")], "found": True}
    for bad in (
        reply(good, ["L99"]),
        reply(good.replace("5 mg", "10 mg"), [lid]),
        reply(good.replace("after", "before"), [lid]),
        reply("Take amlodipine 5 mg in the morning.", [lid]),
        reply(good, []),
        reply("", [lid]),
        "not json",
        None,
    ):
        assert answer_from_reply(bad, lines) is None


def test_wrappers_have_no_advice(tmp_path):
    for name, template in WRAPPERS.items():
        fields = {f for _, f, _, _ in string.Formatter().parse(template) if f}
        assert not ADVICE.search(template.format(**{f: "x" for f in fields})), name
    client, eid = _full(tmp_path)
    for line in _lines(client, eid):
        if line["kind"] == "stay":
            assert not ADVICE.search(line["text"]), line
    assert not ADVICE.search(NOT_FOUND) and not ADVICE.search(FOUND)
    assert "Lines:\nL1: a" in bot_prompt([{"id": "L1", "text": "a"}]) and bot_prompt([]).endswith("\nQuestion: ")
    assert record.BOT == "Record bot"
