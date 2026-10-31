"""Task 1 (v4 UX): the AI moments of the chart view (contract C1), built from hand-made events."""

from __future__ import annotations

import re

import httpx
import pytest

from app.journey.ai_moments import line_of, moments, visual_finding
from app.journey.rx import document_for, from_document
from tests.test_care_demo import _client, _seed

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
EID = "e" * 32
ASHA, RAO = "Nurse Asha (synthetic)", "Dr. A. Rao (synthetic)"
SAM = {"model": "sam", "model_id": "sam-3.1", "source": "prepared", "ms": None}
VOICE = {"model": "voice", "model_id": "muse-voice-transcribe-1.0", "source": "prepared", "ms": None}
DOSE = {"kind": "dose", "name": "Paracetamol", "amount": "1 g", "every_h": 6, "text": "Paracetamol 1 g every 6 h"}
OBS = {"kind": "obs", "every_h": 4, "text": "Observations every 4 h"}
KUMAR_SAID = " ".join(f"w{i}" for i in range(25))


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _ev(eid, etype, ts, **payload):
    return {"id": eid, "event_type": etype, "ts_ms": ts, "payload": payload, "episode_id": "e1", "supersedes_id": None}


def _rx(eid="r1", ts=1):
    return {**_ev(eid, "rx.ordered", ts), "payload": from_document(document_for("R. Kumar, 58 M (synthetic)"), source="demo")}


def _one(rows):
    assert len(rows) == 1, rows
    return rows[0]


def _check_text(m):
    return [m["finding"]] + ([m["patient_finding"]] if m["patient_finding"] else [])


def test_tray_check_is_a_flagged_visual_moment():
    rows = [{"concept": "needle holder", "planned": 3, "seen": 2}, {"concept": "retractor", "planned": 2, "seen": 2}]
    m = _one(moments([_ev("t1", "tray.checked", 10, rows=rows, match="mismatch", why="w", media="video",
                         source="prepared", calls=[SAM], by=ASHA, evidence_id=EID, frame_ids=[])]))
    assert (m["kind"], m["capability"], m["status"], m["owner"], m["filter"]) == ("visual", "tray", "flagged", "doctor", "video")
    assert m["finding"] == "Saw 2 of 3 needle holders."
    assert m["evidence_id"] == EID and m["calls"] == [SAM]
    assert m["patient_finding"] == "The tray was checked by camera before your surgery."


def test_visual_finding_twins_the_viewer_sentence():
    full = [{"concept": "retractor", "planned": 10, "seen": 10}, {"concept": "clamp", "planned": 5, "seen": 5}]
    assert visual_finding(full) == "Saw every planned item: 15 of 15."
    assert visual_finding([{"concept": "clamp", "planned": 5, "seen": 0}]) == "Nothing seen in the clip."
    assert visual_finding([{"concept": "clamp", "planned": 5, "seen": None}]) == "Nothing seen in the clip."


def test_order_draft_is_open_until_signed():
    drafted = _ev("d1", "order.drafted", 10, items=[DOSE, OBS], transcript=KUMAR_SAID, heard_by="prepared", source="rules",
                  calls=[VOICE], by=RAO)
    assert _one(moments([drafted]))["status"] == "open"
    m = _one(moments([drafted, _ev("s1", "order.signed", 20, items=[DOSE, OBS], draft_id="d1", by=RAO)]))
    assert m["finding"] == "2 orders drafted from 25 words."
    assert m["status"] == "recorded" and [w["type"] for w in m["written"]] == ["order.drafted", "order.signed"]
    assert m["refs"]["signed_items"] == [DOSE, OBS] and m["patient_finding"] is None


def test_nudge_moment_links_intent_and_fact():
    rx = _rx()
    strip = _ev("m1", "brownbag.med_found", 2, name_as_read="Amlodipine", strength="10 mg")
    nudge = _ev("n1", "nudge.raised", 3, key="k", kind="strip_strength_differs", to="patient", says="a", says_staff="b",
                intent_id="r1", fact_id="m1", at_ms=3)
    m = _one(moments([rx, strip, nudge]))
    assert (m["kind"], m["capability"], m["status"], m["owner"], m["finding"]) == ("rule", "nudge", "open", "patient", "b")
    assert m["refs"]["intent"]["id"] == "r1" and m["refs"]["fact"]["id"] == "m1" and m["refs"]["fact"]["plain"]
    assert m["patient_finding"] == "a" and m["refs"]["rule"].startswith("The strength read from a strip")
    seen = _ev("n2", "nudge.seen", 4, nudge_id="n1", by="patient", note="ok")
    assert _one(moments([rx, strip, nudge, seen]))["status"] == "recorded"


def test_nudge_closed_by_a_correction_reads_recorded():
    fact = _ev("c1", "count.closing", 1, returned=14, opened=15, unaccounted=1)
    fixed = {**_ev("c2", "count.closing", 2, returned=15, opened=15, unaccounted=0), "supersedes_id": "c1"}
    nudge = _ev("n1", "nudge.raised", 3, key="k", kind="count_open", to="nurse", says="x", says_staff="x",
                intent_id=None, fact_id="c1", at_ms=3)
    m = _one(moments([fact, fixed, nudge]))
    assert m["status"] == "recorded" and m["owner"] == "nurse" and m["patient_finding"] is None


def test_record_bot_answer_cites_lines():
    asked = _ev("q1", "question.asked", 1, to="bot", text="When is my review?", by="p")
    answered = _ev("a1", "question.answered", 2, question_id="q1", answer="x", sources=[{"id": "L1", "text": "Review day 7"}],
                   found=True, source="rules", by="Record bot", calls=[])
    m = _one(moments([asked, answered]))
    assert m["finding"] == "Answered from 1 record line."
    assert m["patient_finding"] == "Answered from 1 line of your record."
    assert m["calls"] == [] and m["refs"]["question"] == "When is my review?"
    nothing = _ev("a2", "question.answered", 3, question_id="q1", answer="", sources=[], found=False, source="rules", calls=[])
    assert _one(moments([asked, nothing]))["finding"] == "Not found in the record."


def test_handover_lines_keep_evidence():
    dose = _ev("g1", "dose.given", 1, name="Paracetamol", amount="1 g", by=ASHA, key="paracetamol")
    draft = _ev("h1", "handover.drafted", 5, **{"from": ASHA, "to": "Nurse Kavya (synthetic)", "lines": [
        {"text": "Dose logged.", "evidence": ["g1"]}], "text": None, "wording": "template", "calls": [], "by": ASHA})
    m = _one(moments([dose, draft]))
    assert m["refs"]["lines"][0]["evidence"][0]["id"] == "g1"
    assert (m["status"], m["owner"], m["finding"]) == ("open", "nurse", "Handover of 1 line from 1 recorded event.")
    took = _ev("h2", "handover.accepted", 6, handover_id="h1", by="Nurse Kavya (synthetic)")
    assert _one(moments([dose, draft, took]))["status"] == "recorded"


def test_day_plan_moment_id():
    rx = _rx()
    read = _ev("m1", "medicines.read", 2, photo_id="p1", rows=[], match="none", why="w", source="prepared", calls=[])
    rows = moments([rx, read])
    assert [m["capability"] for m in rows] == ["medicines", "day_plan"]
    m = _one([m for m in rows if m["capability"] == "day_plan"])
    assert m["id"] == "dayplan:r1" and m["kind"] == "draft" and m["capability"] == "day_plan"
    k = len(rx["payload"]["rows"])
    assert m["calls"] == [] and m["patient_finding"] == f"Your day plan lists {k} medicines."
    assert m["finding"] == f"Day plan of {k} medicines; 0 matched to the medicines photo."
    assert [w["type"] for w in m["written"]] == ["rx.ordered", "medicines.read"]


def test_reference_photo_is_a_record_row():
    ref = _ev("p1", "photo.added", 1, purpose="reference", by="p", path="x")
    m = _one(moments([ref, _ev("p2", "photo.added", 2, purpose="frame", video="tray", by="p", path="y")]))
    assert (m["finding"], m["filter"], m["kind"], m["photo_id"]) == ("Reference photo.", "photos", "record", "p1")


def test_old_check_without_evidence_is_still_a_moment():
    rows = [{"concept": "clamp", "planned": 2, "seen": 2}]
    m = _one(moments([_ev("t1", "setup.checked", 1, rows=rows, match="ok", why="w", source="prepared", by=ASHA, frame_ids=[])]))
    assert m["evidence_id"] is None and m["finding"] == "Saw every planned item: 2 of 2." and m["status"] == "matches"
    assert m["owner"] == "nurse"


def test_findings_have_no_advice_and_no_model_text():
    proof = _ev("c1", "proof.checked", 1, photo_id="p1", task_id="t", read="Zzzdrug 5 mg", match="mismatch",
                why="The strip reads Zzzdrug 5 mg", source="prepared", calls=[SAM])
    mon = _ev("c2", "proof.checked", 2, photo_id="p2", task_id="t", read="88/54", match="ok", why="w", source="prepared",
              values_read={"sbp": 88, "dbp": 54, "hr": 112}, calls=[SAM])
    rows = moments([proof, mon])
    by_cap = {m["capability"]: m for m in rows}
    assert by_cap["dose_strip"]["finding"] == "Strip photo does not match the task."
    assert "Zzzdrug" not in str(_check_text(by_cap["dose_strip"]))
    assert by_cap["monitor"]["finding"] == "Read SBP 88, DBP 54, HR 112."
    assert all(not ADVICE.search(t) for m in rows for t in _check_text(m))


def test_staff_only_moments_have_no_patient_finding():
    voice = _ev("d1", "order.drafted", 1, items=[DOSE], transcript="a b", heard_by="typed", source="rules", calls=[], by=RAO)
    typed = _ev("s1", "order.signed", 2, items=[DOSE, OBS], by=RAO)
    hand = _ev("h1", "handover.drafted", 3, lines=[], text=None, wording="template", calls=[], by=ASHA)
    nudge = _ev("n1", "nudge.raised", 4, key="k", kind="dose_overdue", to="nurse", says="s", says_staff="s", intent_id=None,
                fact_id=None, at_ms=4)
    task = _ev("k1", "task.done", 5, task_id="t", by=ASHA, via="voice", transcript="done it", heard_by="prepared", calls=[VOICE])
    rows = moments([voice, typed, hand, nudge, task])
    assert {m["capability"] for m in rows} == {"orders", "typed_orders", "handover", "nudge", "task_voice"}
    assert all(m["patient_finding"] is None for m in rows)
    assert [m["finding"] for m in rows if m["capability"] == "typed_orders"] == ["2 orders signed."]


def test_moments_newest_first():
    a = _ev("a", "photo.added", 5, purpose="reference", by="p", path="x")
    b = _ev("b", "photo.added", 5, purpose="wound", by="p", path="x")
    c = _ev("c", "photo.added", 9, purpose="wound", by="p", path="x")
    assert [m["id"] for m in moments([a, b, c])] == ["c", "b", "a"]


def test_strip_photo_batch_is_one_moment_with_calls_on_the_first_row():
    rx = _rx()
    rows = [_ev(f"m{i}", "brownbag.med_found", 2 + i, name_as_read=n, generic=n.lower(), strength=s, photo_id="p1",
                evidence_id=EID, source="prepared", **({"calls": [SAM]} if i == 0 else {}))
            for i, (n, s) in enumerate([("Amlodipine", "10 mg"), ("Ibuprofen", "400 mg")])]
    typed = _ev("m9", "brownbag.med_found", 9, name_as_read="Zinc", generic="zinc", strength="")
    by_cap = {m["capability"]: m for m in moments([rx, *rows, typed])}
    m = by_cap["strips"]
    assert m["id"] == "m0" and m["calls"] == [SAM] and m["status"] == "flagged" and m["owner"] is None
    assert m["finding"] == "Read 2 strips: 1 differs from the prescription, 1 not on the prescription."
    assert [w["event_id"] for w in m["written"]] == ["m0", "m1"]


def test_line_of_is_a_citable_line():
    line = line_of(_ev("g1", "dose.given", 0, name="Paracetamol", amount="1 g", by=ASHA))
    assert set(line) == {"id", "type", "when", "by", "plain"} and line["when"] == "Day 0 09:00" and line["by"] == ASHA


def test_view_has_ai_moments(tmp_path):
    client = _client(tmp_path)
    patients = _seed(client)
    body = client.get(f"/journey/episodes/{patients[0]['id']}").json()
    assert isinstance(body["ai_moments"], list)
