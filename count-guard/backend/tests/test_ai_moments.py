"""Task 1 (v4 UX): the AI moments of the chart view (contract C1), built from hand-made events."""

from __future__ import annotations

import re

import httpx
import pytest

from app.journey.ai_moments import line_of, moments, visual_finding
from app.journey.rx import document_for, from_document
from tests.test_care_demo import _client, _seed
from tests.test_flow_states import _new, _to_theatre
from tests.test_p3_tray import _events, _upload, fake_frames  # noqa: F401  (fixture)

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
    line = line_of(_ev("g1", "dose.given", 0, name="Paracetamol", amount="1 g", by=ASHA), 0)
    assert set(line) == {"id", "type", "when", "at_ms", "by", "plain"} and line["when"] == "09:00" and line["by"] == ASHA


def test_view_has_ai_moments(tmp_path):
    client = _client(tmp_path)
    patients = _seed(client)
    body = client.get(f"/journey/episodes/{patients[0]['id']}").json()
    assert isinstance(body["ai_moments"], list)


def test_handmade_fixture_check_gives_a_handmade_moment(tmp_path, fake_frames):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    assert _upload(client, eid).status_code == 200
    payload = [e for e in _events(client, eid) if e["event_type"] == "tray.checked"][-1]["payload"]
    assert payload["handmade"] is True
    tray = [m for m in client.get(f"/journey/episodes/{eid}").json()["ai_moments"] if m["capability"] == "tray"]
    assert tray[0]["handmade"] is True
    assert _one(moments([_ev("t1", "tray.checked", 1, rows=[], match="none", why="w", source="prepared", by=ASHA,
                              frame_ids=[])]))["handmade"] is False


# Spec Appendix B rows 1-17 (care flow), each as the events that make the moment. Row 18 is the AI activity page,
# built client-side from these moments (frontend ai.test.js `activityRows`); it is not a moment itself.
AUDIT = [
    (1, "orders", "voice", _ev("a1", "order.drafted", 1, items=[DOSE], transcript="a b", heard_by="prepared", source="rules", calls=[VOICE], by=RAO)),
    (2, "discharge", "voice", _ev("a2", "discharge.drafted", 2, sections=[{"title": "t"}], transcript="a b", heard_by="prepared", source="rules", calls=[VOICE], by=RAO)),
    (3, "task_voice", "voice", _ev("a3", "task.done", 3, task_id="t", by=ASHA, via="voice", transcript="done", heard_by="prepared", calls=[VOICE])),
    (4, "answer_voice", "voice", _ev("a4", "question.answered", 4, question_id="q", answer="fine", source="doctor", via="voice", by=RAO, calls=[VOICE])),
    (5, "monitor", "photo_read", _ev("a5", "proof.checked", 5, photo_id="p", task_id="t", match="ok", why="w", source="prepared", values_read={"sbp": 88}, calls=[SAM])),
    (6, "dose_strip", "photo_read", _ev("a6", "proof.checked", 6, photo_id="p", task_id="t", read="x", match="ok", why="w", source="prepared", calls=[SAM])),
    (7, "medicines", "photo_read", _ev("a7", "medicines.read", 7, photo_id="p", rows=[], match="none", why="w", source="prepared", calls=[])),
    (8, "strips", "photo_read", _ev("a8", "brownbag.med_found", 8, name_as_read="Amlodipine", generic="amlodipine", strength="10 mg", photo_id="p", evidence_id=EID, source="prepared", calls=[SAM])),
    (9, "tray", "visual", _ev("a9", "tray.checked", 9, rows=[], match="ok", why="w", source="prepared", by=ASHA, frame_ids=[])),
    (10, "setup", "visual", _ev("a10", "setup.checked", 10, rows=[], match="ok", why="w", source="prepared", by=ASHA, frame_ids=[])),
    (11, "swabs", "visual", _ev("a11", "swabs.counted", 11, rows=[], match="ok", why="w", source="prepared", by=ASHA, frame_ids=[])),
    (12, "healing_photo", "record", _ev("a12", "review.requested", 12, photo_id="p", by="p")),
    (13, "record_bot", "answer", _ev("a13", "question.answered", 13, question_id="q", answer="x", sources=[], found=False, source="rules", calls=[])),
    (14, "nudge", "rule", _ev("a14", "nudge.raised", 14, key="k", kind="dose_overdue", to="nurse", says="s", says_staff="s", intent_id=None, fact_id=None, at_ms=14)),
    (15, "handover", "draft", _ev("a15", "handover.drafted", 15, lines=[], text=None, wording="template", calls=[], by=ASHA)),
    (16, "discharge_card", "draft", _ev("a16", "discharge.card", 16, warning_signs=["w"], schedule=[], wound_care="c")),
]


@pytest.mark.parametrize("row,capability,kind,event", AUDIT, ids=[f"row{r[0]}-{r[1]}" for r in AUDIT])
def test_appendix_b_row_has_a_moment(row, capability, kind, event):
    rows = moments([event])
    got = [m for m in rows if m["capability"] == capability]
    assert got, f"Appendix B row {row}: no {capability} moment from {event['event_type']}"
    assert got[0]["kind"] == kind


def test_appendix_b_row_17_day_plan_has_a_moment():
    read = _ev("m1", "medicines.read", 2, photo_id="p1", rows=[], match="none", why="w", source="prepared", calls=[])
    got = [m for m in moments([_rx(), read]) if m["capability"] == "day_plan"]
    assert got and got[0]["kind"] == "draft"


def _swab_flag(eid="s1", ts=10):
    return _ev(eid, "swabs.counted", ts, rows=[{"concept": "gauze swab", "planned": 15, "seen": 14}], match="mismatch",
               why="w", source="prepared", by=ASHA, frame_ids=[], count=14, opened=15)


def _closing(eid, ts, returned, opened=15):
    return _ev(eid, "count.closing", ts, opened=opened, returned=returned, unaccounted=opened - returned, by=ASHA)


def test_swab_flag_resolves_when_a_closing_count_equals_the_pack():
    open_ = _one([m for m in moments([_swab_flag(), _closing("c1", 11, 14)]) if m["capability"] == "swabs"])
    assert (open_["status"], open_["owner"]) == ("flagged", "nurse")
    fixed = [m for m in moments([_swab_flag(), _closing("c1", 11, 14), _closing("c2", 12, 15)]) if m["capability"] == "swabs"]
    assert (fixed[0]["status"], fixed[0]["owner"]) == ("recorded", None)


def _state(eid, ts, to):
    return _ev(eid, "patient.state", ts, to=to)


def _tray_flag(eid="t1", ts=10):
    rows = [{"concept": "needle holder", "planned": 3, "seen": 2}]
    return _ev(eid, "tray.checked", ts, rows=rows, match="mismatch", why="w", media="video", source="prepared", by=ASHA, frame_ids=[])


def test_tray_flag_is_recorded_after_the_patient_leaves_theatre():
    during = moments([_state("s0", 5, "theatre"), _tray_flag()])
    assert (during[0]["status"], during[0]["owner"]) == ("flagged", "doctor")
    after = moments([_state("s0", 5, "theatre"), _tray_flag(), _state("s1", 20, "ward")])
    assert (after[0]["status"], after[0]["owner"]) == ("recorded", None)


def test_tray_flag_is_recorded_when_a_later_check_matches():
    ok = _ev("t2", "tray.checked", 20, rows=[{"concept": "needle holder", "planned": 3, "seen": 3}], match="ok", why="w",
             media="video", source="prepared", by=ASHA, frame_ids=[])
    rows = {m["id"]: m for m in moments([_state("s0", 5, "theatre"), _tray_flag(), ok])}
    assert rows["t1"]["status"] == "recorded" and rows["t1"]["owner"] is None and rows["t2"]["status"] == "matches"


def test_proof_photo_with_nothing_read_is_a_record_row():
    e = _ev("c9", "proof.checked", 3, photo_id="ph9", task_id="t", read="", match="none", why="w", source="none", calls=[])
    m = _one(moments([e]))
    assert (m["kind"], m["title"], m["photo_id"], m["status"], m["filter"]) == ("record", "Proof photo", "ph9", "recorded", "photos")
    assert m["finding"] == "Proof photo kept, not checked." and not ADVICE.search(m["finding"])


def test_cited_lines_carry_ms():
    from app.journey.ai_moments import line_of

    row = line_of({"id": "e1", "event_type": "obs.recorded", "ts_ms": 90_000, "payload": {"by": "n"}}, 90_000)
    assert row["at_ms"] == 90_000 and row["when"]
