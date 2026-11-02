"""Coverage the archived morning, camera-case and play tests held, now driven from the care app (Task 16 fix round 1).

- The fact card and the other decision-tier events stay off the discharge sheet, in both tiers.
- The care discharge PDF and the camera count sheet survive text Helvetica cannot draw.
- The seeded demo's nudges tell nobody what to do clinically.
"""

from __future__ import annotations

import re

import pytest

from app.agent.verifier import ADVICE
from app.journey.api import raise_nudges
from app.journey.rx import DEMO_DOCUMENT, from_document, key_of
from app.journey.stories import CARE_TEMPLATES, audit_rows
from app.morning.brownbag import read_strip
from app.morning.store import MorningStore
from app.morning.discharge import DECISION_TYPES, fold
from conftest import pdf_text
from tests.test_care_demo import _client
from tests.test_count_gate_paths import NURSE, _begin_with_pack, _camera, _new_patient, _post_json
from tests.test_flow_states import _count, _move, _surgery, _to_theatre
from tests.test_theatre_api import _drop_with_context, _of

DOCTOR = "Dr. A. Rao (synthetic)"
INSTRUCTION = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
CARD_ADVICE = re.compile(r"\b(give|consider|should|recommend(?:ed|s)?|advise[sd]?|administer|increase|reduce)\b", re.I)
ODD = "— “Ré” ✓"  # an em dash, curly quotes, an accent and a tick: none of them in Helvetica's Latin-1 except é


def _event(i: int, kind: str, payload: dict, tier: str = "documentation") -> dict:
    return {"id": f"e{i}", "event_type": kind, "payload": payload, "tier": tier, "ts_ms": i, "supersedes_id": None}


def test_fold_drops_the_card_and_every_decision_event():
    events = [
        _event(1, "vitals.reading", {"systolic": 86}),
        _event(2, "vitals.card", {"text": "BP 86/50, down 28% in 4 min."}, "decision"),
        _event(3, "vitals.change", {"drop_pct": 28}, "decision"),
        _event(4, "brownbag.same_drug_twice", {"generic": "metoprolol"}, "decision"),
        _event(5, "brownbag.med_found", {"generic": "metoprolol"}),
        _event(6, "druglog.given", {"name": "lignocaine"}, "decision"),  # any decision-tier line, whatever its kind
    ]
    sheet = fold(events)
    assert sheet["readings"] == [{"systolic": 86}] and sheet["opd"] == [{"generic": "metoprolol"}]
    assert sheet["drugs"] == []
    assert "28%" not in repr(sheet) and "same_drug_twice" not in repr(sheet)
    assert DECISION_TYPES == {"vitals.card", "vitals.change", "brownbag.same_drug_twice"}


def _ward_after_theatre(client, eid, *, tier: bool) -> None:
    _to_theatre(client, eid)
    assert client.post(f"/journey/episodes/{eid}/theatre/tier", json={"on": tier}).status_code == 200
    assert _surgery(client, eid, "began").status_code == 200
    _drop_with_context(client, eid)  # metoprolol strip, 20 swabs opened, lignocaine given, the BP drop
    assert _count(client, eid, "closing", returned=20).status_code == 200
    assert _surgery(client, eid, "ended").status_code == 200
    assert _move(client, eid, "ward").status_code == 200


def _drafted_pdf(client, eid) -> tuple[str, str]:
    r = client.post(f"/journey/episodes/{eid}/discharge/draft", json={"by": DOCTOR})
    assert r.status_code == 200, r.text
    summary = r.json()["drafts"]["discharge"]["summary"]
    pdf = client.get(f"/journey/episodes/{eid}/discharge.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    return summary, pdf_text(pdf.content)


@pytest.mark.parametrize("tier", [False, True])
def test_care_discharge_has_no_card_or_advice_in_both_tiers(tmp_path, tier):
    client = _client(tmp_path)
    eid = client.post("/journey/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    _ward_after_theatre(client, eid, tier=tier)
    cards = _of(client, eid, "vitals.card")
    assert len(cards) == (1 if tier else 0)
    summary, text = _drafted_pdf(client, eid)
    assert "lignocaine" in text and "Opened 20. Returned 20." in text
    for words in (summary, text):
        assert "down 28%" not in words and "in 4 min" not in words  # the card's sentence; the readings are facts
        assert not CARD_ADVICE.search(words), words  # verifier.ADVICE would hit the sheet's own "does not state a treatment"


def test_care_discharge_pdf_survives_non_latin1_text(tmp_path):
    client = _client(tmp_path)
    label = f"Synthetic demo, A. Das {ODD} (synthetic)"
    eid = client.post("/journey/episodes", json={"label": label}).json()["id"]
    _ward_after_theatre(client, eid, tier=False)
    _, text = _drafted_pdf(client, eid)
    assert 'A. Das - "Ré"' in text  # the label, drawn with Latin-1 stand-ins rather than a 500


def test_camera_count_sheet_survives_a_non_latin1_reason(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    advice = _camera(client, eid, "clip2")["camera"]["advice"]
    open_rows = [row for row in advice if not row.get("resolved")]
    assert open_rows
    for row in open_rows:
        r = _post_json(client, eid, f"/camera/advice/{row['id']}/resolve", {"by": NURSE, "reason": f"Found under drape {ODD}"})
        assert r.status_code == 200, r.text
    assert _post_json(client, eid, "/camera/close", {"by": NURSE}).status_code == 200
    got = client.get(f"/journey/episodes/{eid}/camera/count-sheet.pdf")
    assert got.status_code == 200 and got.content[:4] == b"%PDF"
    assert 'Found under drape - "Ré"' in pdf_text(got.content)


H, M = 3_600_000, 60_000
LIMITS = {"sbp_min": 90, "sbp_max": 160, "hr_max": 110, "spo2_min": 94, "temp_max": 38.0}


def _three_stories(store, eid) -> None:
    """The facts the archived three-act play recorded, written straight to the record; the shipped rules raise the nudges."""
    def put(kind, payload, at, **extra):
        event = store.append(eid, kind, payload, ts_ms=at, **extra)
        raise_nudges(store, eid, at)
        return event

    def obs(sbp, dbp, hr, at):
        put("obs.recorded", {"sbp": sbp, "dbp": dbp, "hr": hr, "spo2": 97, "temp": 37.0, "by": "Nurse M"}, at)

    def dose(name, amount, at):
        put("dose.given", {"key": key_of(name), "name": name, "amount": amount, "by": "Nurse M", "source": "spoken"}, at)

    put("rx.ordered", from_document(DEMO_DOCUMENT, source="demo"), 0)
    put("brownbag.med_found", {**read_strip("metoprolol", "25 mg"), "by": "patient", "source": "typed"}, 10 * H)
    put("brownbag.med_found", {**read_strip("amlodipine", "10 mg"), "by": "patient", "source": "typed"}, 10 * H + M)
    doses = [{"name": "Paracetamol", "amount": "1 g IV", "every_h": 6}, {"name": "Ondansetron", "amount": "4 mg IV", "every_h": 8}]
    put("ward.orders_set", {"doses": [{**d, "key": key_of(d["name"])} for d in doses], "obs_every_h": 1,
                            "limits": LIMITS, "by": DOCTOR}, 22 * H)
    put("count.pack_opened", {"item_type": "swab", "quantity": 20, "source": "spoken", "by": "Nurse P"}, 24 * H)
    put("count.closing", {"opened": 20, "returned": 19, "unaccounted": 1, "detail": "1 swab unaccounted.", "by": "Nurse P"},
        24 * H + 50 * M)
    obs(128, 80, 84, 26 * H)
    dose("Paracetamol", "1 g IV", 26 * H + 5 * M)
    obs(86, 54, 96, 28 * H)
    dose("Ondansetron", "4 mg IV", 28 * H + 30 * M)
    dose("Ondansetron", "4 mg IV", 29 * H)
    raise_nudges(store, eid, 33 * H + 30 * M)  # the ward clock check: a dose and an obs set overdue
    template = CARE_TEMPLATES["hernia-repair"]
    put("discharge.card", {"template": "hernia-repair", "warning_signs": template["warning_signs"], "by": DOCTOR}, 35 * H)
    put("checkin.recorded", {"day": 2, "feels": "Sore", "signs": [template["warning_signs"][0]], "note": "", "by": "patient"},
        73 * H)
    put("help.requested", {"says": "The dressing is wet.", "by": "patient"}, 73 * H + 30 * M)


def test_the_three_stories_nudges_are_advice_free(tmp_path):
    """The sweep the archived play test ran (archive/tests/test_journey.py), on the same facts without the play route."""
    store = MorningStore(tmp_path / "m.db")
    eid = store.create_episode("Synthetic demo, R. Kumar")["id"]
    _three_stories(store, eid)
    raised = [e["payload"] for e in store.events(eid) if e["event_type"] == "nudge.raised"]
    assert {n["kind"] for n in raised} == {"strip_strength_differs", "count_open", "obs_past_limit", "dose_logged_early",
                                           "dose_overdue", "obs_overdue", "warning_sign_ticked", "help_requested"}
    rows = [row["what"] for row in audit_rows(store.events(eid)) if row["type"] == "nudge.raised"]
    for text in rows + [n["says"] for n in raised] + [n["says_staff"] for n in raised]:
        assert not ADVICE.search(text), text
        assert not INSTRUCTION.search(text), text


def test_seeded_demo_nudges_are_advice_free(tmp_path):
    """The seeded ward and a day of its clock."""
    client = _client(tmp_path)
    seeded = client.post("/journey/demo/seed").json()
    ids = [p["id"] for p in seeded["patients"]]
    for hours in (2, 6, 12, 24):
        assert client.post("/journey/clock", json={"ms": hours * 3_600_000}).status_code == 200
        for eid in ids:
            client.post(f"/journey/episodes/{eid}/tick", json={"at_ms": hours * 3_600_000})
    raised = [row["what"] for eid in ids for row in client.get(f"/journey/episodes/{eid}/audit").json()["rows"]
              if row["type"] == "nudge.raised"]
    assert raised, "the seeded ward raised no nudge"
    for text in raised:
        assert not ADVICE.search(text), text
        assert not INSTRUCTION.search(text), text
