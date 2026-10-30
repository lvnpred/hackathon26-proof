"""Task 9: the brown bag. A day plan built only from the prescription, a record rule for medicines, doctor-only marks."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.adapters import spark as spark_mod
from app.journey.medicines import day_plan, match_medicines
from app.journey.record import medicine_answer, record_lines
from app.journey.rx import document_for, from_document
from app.journey.schedule import build, schedule_text
from app.main import create_app
from tests.test_care_demo import _client
from tests.test_flow_states import ADVICE
from tests.test_flow_tasks import DOC, _url
from tests.test_p2_live import _keyed
from tests.test_p4_ask import PNG, _ask, _events, _home, _patients, no_network  # noqa: F401  (no_network is autouse)
from tests.test_p4_medicines import KUMAR_STRIPS

RX = from_document(document_for("R. Kumar, 58 M (synthetic)"), source="demo")
RX_EVENT = [{"id": "rx", "episode_id": "e", "event_type": "rx.ordered", "ts_ms": 0, "payload": RX}]


def _read():
    strips = [{"name_as_read": s["name"], "strength": s["strength"]} for s in KUMAR_STRIPS]
    rows = match_medicines(strips, RX)["rows"]
    regions = [{"bbox": [0, i / 4, 1, 0.2], "label": r["read"], "value": r["read"], "row": i} for i, r in enumerate(rows)]
    return {"rows": rows, "regions": regions, "photo_id": "p", "evidence_id": "e" * 32}


def test_match_rows_carry_name_key_and_rx_strength():
    rows = _read()["rows"]
    assert [r["name"] for r in rows] == ["Metoprolol", "Amlodipine", "Pantoprazole", "Cetirizine"]
    assert [r["key"] for r in rows][:2] == ["metoprolol", "amlodipine"]
    assert rows[0]["rx_strength"] and rows[3]["rx_strength"] == ""


def test_day_plan_slots_quote_schedule_text():
    plan = day_plan(RX, _read())
    built = {r["key"]: r for r in build(RX)}
    assert [i["key"] for i in plan["slots"]["morning"]] == ["metoprolol", "amlodipine", "pantoprazole"]
    assert [i["key"] for i in plan["slots"]["night"]] == ["metoprolol"] and plan["slots"]["afternoon"] == []
    assert [i["key"] for i in plan["as_needed"]] == ["paracetamol"]
    for item in plan["slots"]["morning"] + plan["as_needed"]:
        assert item["text"] == schedule_text(built[item["key"]])
    assert plan["slots"]["morning"][0]["region"] == 0 and plan["as_needed"][0]["region"] is None
    assert plan["not_prescribed"] == [{"name": "Cetirizine", "read": "Cetirizine 10 mg", "region": 3}]
    assert plan["photo_id"] == "p" and plan["evidence_id"] == "e" * 32


def test_day_plan_unreadable_dose_is_as_written():
    rx = {**RX, "rows": [{**RX["rows"][0], "dose": "1 tab thrice", "duration": "5 days"}]}
    plan = day_plan(rx, None)
    assert plan["as_written"][0]["text"] == "1 tab thrice; After food; for 5 days" and plan["as_needed"] == []
    assert day_plan(None, None) is None


def test_medicine_rule_quotes_the_row():
    lines = record_lines(RX_EVENT)
    out = medicine_answer("When do I take amlodipine?", lines, [])
    amlo = next(line for line in lines if line.get("key") == "amlodipine")
    assert out == {"answer": "Here is what your record says.", "sources": [amlo], "found": True}
    assert schedule_text({r["key"]: r for r in build(RX)}["amlodipine"]) in amlo["text"]
    assert all(("key" in line) == line["text"].startswith("Prescription from") for line in lines)


def test_medicine_rule_is_key_equality():
    lines = record_lines(RX_EVENT)
    assert medicine_answer("What about amlo?", lines, []) is None
    assert medicine_answer("What about amlodipines?", lines, []) is None


def test_medicine_rule_not_prescribed():
    lines = record_lines(RX_EVENT)
    out = medicine_answer("Can I take the cetirizine?", lines, _read()["rows"])
    assert out == {"answer": "Cetirizine is not on your prescription. Ask Dr. Rao.", "sources": [], "found": False}


def test_bot_answers_a_medicine_question_with_no_model_call(tmp_path, monkeypatch):
    def refuse(self, prompt):
        raise AssertionError("the model was called")

    monkeypatch.setattr(spark_mod.SparkAdapter, "write", refuse)
    client = TestClient(create_app(_keyed(tmp_path)))
    kumar = _patients(client)["4"]
    _home(client, kumar)
    got = _ask(client, kumar, "When do I take amlodipine?").json()["ask"]["questions"][-1]["answer"]
    assert got["source"] == "rules" and got["found"] and got["text"] == "Here is what your record says."
    event = [e for e in _events(client, kumar) if e["event_type"] == "question.answered"][-1]
    assert event["payload"]["calls"] == []


def _meds(client, eid):
    r = client.post(_url(eid, "ask/medicines"), files={"file": ("meds-kumar.png", PNG, "image/png")}, data={"at_ms": "3000"})
    assert r.status_code == 200
    return r.json()["ask"]["medicines"][-1]["id"]


def _mark(client, eid, read_id, **body):
    return client.post(_url(eid, f"medicines/{read_id}/mark"), json={"at_ms": 4000, **body})


def test_mark_is_doctor_only(tmp_path):
    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    _home(client, kumar)
    read_id = _meds(client, kumar)
    nurse = _mark(client, kumar, read_id, row=3, mark="discuss", by="Nurse Meena (synthetic)")
    assert nurse.status_code == 403 and nurse.json()["detail"] == "Only the doctor marks medicines from home."
    assert _mark(client, kumar, "nope", row=3, mark="discuss", by=DOC).status_code == 404
    assert _mark(client, kumar, read_id, row=9, mark="discuss", by=DOC).json()["detail"] == "No such row in that photo."
    assert _mark(client, kumar, read_id, row=9, mark="discuss", by=DOC).status_code == 422
    assert _mark(client, kumar, read_id, row=3, mark="maybe", by=DOC).status_code == 422
    done = _mark(client, kumar, read_id, row=3, mark="discuss", by=DOC)
    assert done.status_code == 200
    marks = done.json()["ask"]["medicines"][0]["marks"]
    assert [(m["row"], m["mark"], m["by"]) for m in marks] == [(3, "discuss", DOC)]
    assert any(t["patient"] == "Dr. A. Rao will talk to you about Cetirizine." for t in done.json()["timeline"])
    again = _mark(client, kumar, read_id, row=3, mark="noted", by=DOC).json()
    assert [m["mark"] for m in again["ask"]["medicines"][0]["marks"]] == ["noted"]
    assert any(t["patient"] == "Dr. A. Rao noted Cetirizine 10 mg." for t in again["timeline"])
    assert any(t["plain"] == f"{DOC} marked Cetirizine 10 mg: noted." for t in again["timeline"])


def test_mark_in_another_episode_is_404(tmp_path):
    client = _client(tmp_path)
    ids = _patients(client)
    _home(client, ids["4"])
    read_id = _meds(client, ids["4"])
    assert _mark(client, ids["9"], read_id, row=0, mark="noted", by=DOC).status_code == 404


def test_view_carries_day_plan(tmp_path):
    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    _home(client, kumar)
    assert client.get(_url(kumar, "")[:-1]).json()["day_plan"]["not_prescribed"] == []
    _meds(client, kumar)
    plan = client.get(_url(kumar, "")[:-1]).json()["day_plan"]
    assert plan["not_prescribed"][0]["name"] == "Cetirizine" and plan["slots"]["morning"]


def test_brownbag_copy_has_no_advice():
    rows = _read()["rows"]
    lines = record_lines(RX_EVENT)
    said = [medicine_answer(q, lines, rows) for q in ("When do I take amlodipine?", "Can I take the cetirizine?")]
    texts = [s["answer"] for s in said] + [line["text"] for s in said for line in s["sources"]]
    plan = day_plan(RX, _read())
    texts += [i["text"] for slot in plan["slots"].values() for i in slot] + [i["text"] for i in plan["as_needed"]]
    written = day_plan({**RX, "rows": [{**RX["rows"][0], "dose": "1 tab thrice", "duration": "5 days"}]}, None)
    texts += [i["text"] for i in written["as_written"]] + [i["text"] for i in plan["as_written"]]
    assert written["as_written"]
    for text in texts:
        assert not ADVICE.search(text), text
