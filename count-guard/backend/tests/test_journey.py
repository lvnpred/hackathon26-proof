"""Doctor, nurse and patient stories. Each nudge sets a recorded fact beside a recorded intent."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.agent.verifier import ADVICE
from app.config import Settings
from app.journey import nudges as rules
from app.journey import rx as rxmod
from app.journey.rx import DEMO_DOCUMENT, from_document
from app.journey.schedule import build, days, reminders_ics, slots
from app.main import create_app

H = 3_600_000
ORDERS = {
    "doses": [{"name": "Paracetamol", "amount": "1 g IV", "every_h": 6}],
    "obs_every_h": 1,
    "limits": {"sbp_min": 90, "hr_max": 110},
    "by": "Dr. Test",
}
# Words that would turn a nudge into an instruction about care.
INSTRUCTION = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)


def _client(tmp_path, *, dd_base="http://127.0.0.1:9"):
    settings = Settings(
        data_dir=tmp_path,
        meta_api_key="",
        meta_base="https://api.meta.ai/v1",
        sam_model="sam-3.1",
        voice_model="muse-voice-transcribe-1.0",
        spark_model="muse-spark-1.3",
        baseten_api_key="",
        spark_open_base="https://inference.baseten.co/v1",
        spark_open_model="meta-models/muse-spark-open-1026",
        low_confidence=0.45,
        unannounced_window_ms=30_000,
        lost_after_frames=4,
        sam_fps=2,
        dd_base=dd_base,
    )
    return TestClient(create_app(settings))


def _episode(api) -> str:
    return api.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]


def _kinds(view: dict) -> list[str]:
    return [nudge["kind"] for nudge in view["nudges"]]


# --- schedule ---------------------------------------------------------------

def test_dose_codes_become_slots_and_as_needed_has_none():
    assert slots("1-0-1") == {"morning": "1", "afternoon": "", "night": "1"}
    assert slots("SOS") is None
    assert days("14 days") == 14 and days("2 weeks") == 14 and days("") is None


def test_reminders_skip_as_needed_and_repeat_for_the_prescribed_days():
    rows = build(from_document(DEMO_DOCUMENT, source="demo"))
    ics = reminders_ics(rows, "R. Kumar")
    assert ics.count("BEGIN:VEVENT") == 4  # metoprolol x2, amlodipine, pantoprazole; paracetamol SOS has none
    assert "RRULE:FREQ=DAILY;COUNT=30" in ics and "Paracetamol" not in ics


# --- the rules --------------------------------------------------------------

def test_strip_with_another_strength_nudges_the_patient(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    api.post(f"/journey/episodes/{eid}/rx/demo", json={})
    view = api.post(
        f"/journey/episodes/{eid}/strips",
        json={"strips": [{"name": "amlodipine", "strength": "10 mg"}, {"name": "metoprolol", "strength": "25 mg"}]},
    ).json()
    assert _kinds(view) == ["strip_strength_differs"]
    nudge = view["nudges"][0]
    assert nudge["to"] == "patient" and "10 mg" in nudge["says"] and "5 mg" in nudge["says"]


def test_strip_not_on_the_prescription_nudges_the_patient(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    api.post(f"/journey/episodes/{eid}/rx/demo", json={})
    view = api.post(f"/journey/episodes/{eid}/strips", json={"strips": [{"name": "aspirin", "strength": "75 mg"}]}).json()
    assert _kinds(view) == ["strip_not_prescribed"]


def test_overdue_dose_is_raised_once_and_only_after_the_interval(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    base = f"/journey/episodes/{eid}"
    api.post(f"{base}/orders", json={**ORDERS, "at_ms": 0})
    api.post(f"{base}/dose", json={"name": "Paracetamol", "amount": "1 g", "by": "Nurse A", "at_ms": H})
    assert _kinds(api.post(f"{base}/tick", json={"at_ms": 7 * H}).json()) == []  # due at 7 h, grace 30 min
    view = api.post(f"{base}/tick", json={"at_ms": 8 * H}).json()
    assert _kinds(view) == ["dose_overdue"]
    assert "every 6 h" in view["nudges"][0]["says"] and "7 h ago" in view["nudges"][0]["says"]
    assert _kinds(api.post(f"{base}/tick", json={"at_ms": 9 * H}).json()) == ["dose_overdue"]  # not twice


def test_a_dose_logged_too_soon_or_without_an_order_nudges_the_nurse(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    base = f"/journey/episodes/{eid}"
    api.post(f"{base}/orders", json={**ORDERS, "at_ms": 0})
    api.post(f"{base}/dose", json={"text": "paracetamol 1 g iv", "by": "Nurse A", "at_ms": H})
    api.post(f"{base}/dose", json={"name": "Paracetamol", "by": "Nurse B", "at_ms": 2 * H})
    view = api.post(f"{base}/dose", json={"text": "ondansetron 4 mg iv", "by": "Nurse B", "at_ms": 2 * H + 1})
    assert sorted(_kinds(view.json())) == ["dose_logged_early", "dose_not_ordered"]


def test_a_reading_past_the_doctors_limit_nudges_the_nurse(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    base = f"/journey/episodes/{eid}"
    api.post(f"{base}/orders", json={**ORDERS, "at_ms": 0})
    inside = {"sbp": 120, "dbp": 80, "hr": 80, "spo2": 98, "temp": 37.0, "by": "Nurse A"}
    assert _kinds(api.post(f"{base}/obs", json={**inside, "at_ms": H}).json()) == []
    view = api.post(f"{base}/obs", json={**inside, "sbp": 86, "hr": 118, "at_ms": 2 * H}).json()
    says = sorted(nudge["says"] for nudge in view["nudges"])
    assert says == [
        "Heart rate 118 is above the limit of 110 set by Dr. Test.",
        "Systolic BP 86 is below the limit of 90 set by Dr. Test.",
    ]


def test_observation_round_starts_at_the_first_ward_set_and_stops_at_discharge(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    base = f"/journey/episodes/{eid}"
    api.post(f"{base}/orders", json={"obs_every_h": 1, "by": "Dr. Test", "at_ms": 0})
    assert _kinds(api.post(f"{base}/tick", json={"at_ms": 5 * H}).json()) == []  # in theatre: no set yet
    api.post(f"{base}/obs", json={"sbp": 120, "dbp": 80, "hr": 80, "by": "Nurse A", "at_ms": 6 * H})
    api.post(f"{base}/discharge-card", json={"by": "Dr. Test", "at_ms": 6 * H + 60_000})
    assert _kinds(api.post(f"{base}/tick", json={"at_ms": 20 * H}).json()) == []  # gone home


def test_help_and_a_ticked_discharge_sign_reach_the_nurse(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    base = f"/journey/episodes/{eid}"
    card = api.post(f"{base}/discharge-card", json={"by": "Dr. Test"}).json()["card"]
    api.post(f"{base}/checkin", json={"day": 2, "feels": "warm", "signs": [card["warning_signs"][0], "not on the list"]})
    view = api.post(f"{base}/help", json={"says": "The dressing is wet."}).json()
    assert _kinds(view) == ["warning_sign_ticked", "help_requested"]
    assert all(nudge["to"] == "nurse" for nudge in view["nudges"])


def test_answering_a_nudge_closes_it_and_keeps_it_in_the_audit(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    base = f"/journey/episodes/{eid}"
    nudge = api.post(f"{base}/help", json={"says": "Pain"}).json()["nudges"][0]
    view = api.post(f"{base}/nudges/{nudge['id']}/seen", json={"by": "Nurse A", "note": "Called back"}).json()
    assert view["nudges"] == []
    rows = api.get(f"{base}/audit").json()["rows"]
    assert [row["type"] for row in rows] == ["help.requested", "nudge.raised", "nudge.seen"]
    assert api.post(f"{base}/nudges/nope/seen", json={"by": "x"}).status_code == 404


def test_no_nudge_in_the_demo_tells_anyone_what_to_do_clinically(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    api.post(f"/journey/episodes/{eid}/play")
    rows = api.get(f"/journey/episodes/{eid}/audit").json()["rows"]
    raised = [row["what"] for row in rows if row["type"] == "nudge.raised"]
    assert len(raised) == 8  # strip, count, BP, early dose, overdue dose, obs round, sign, help
    for text in raised:
        assert not ADVICE.search(text), text
        assert not INSTRUCTION.search(text), text


def test_the_demo_completes_all_three_stories_with_corrections_kept(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    view = api.post(f"/journey/episodes/{eid}/play").json()
    assert [(s["who"], s["done"], s["total"]) for s in view["stories"]] == [
        ("Doctor", 4, 4), ("Nurse", 5, 5), ("Patient", 4, 4),
    ]
    assert sorted(_kinds(view)) == ["help_requested", "warning_sign_ticked"]
    assert view["ics_url"] == f"/journey/episodes/{eid}/reminders.ics"  # kept after a reload
    assert [s["strength"] for s in view["strips"] if s["generic"] == "amlodipine"] == ["5 mg"]
    rows = api.get(f"/journey/episodes/{eid}/audit").json()["rows"]
    replaced = [row for row in rows if row["replaced_by"]]
    assert {row["type"] for row in replaced} == {"brownbag.med_found", "count.closing"}


# --- option A: Doctor Dictation stays its own app -----------------------------

DD_DOCUMENT = {
    "document_id": 7,
    "structured": {
        "patientName": "R. Kumar",
        "diagnosis": ["Hernia"],
        "rx": [
            {"form": "Tab.", "name": "Metoprolol", "strength": "25 mg", "dose": "1-0-1",
             "timing": "After food", "duration": "30 days", "instructions": ""},
            {"form": "", "name": "", "strength": "", "dose": "", "timing": "", "duration": "", "instructions": ""},
        ],
        "advice": [],
        "review": "In 2 weeks",
    },
    "author": {"doctor_name": "Dr. Rao"},
}


def test_import_reads_a_doctor_dictation_document(tmp_path, monkeypatch):
    seen = {}

    def fake_fetch(base, document_id, **_):
        seen["call"] = (base, document_id)
        return DD_DOCUMENT

    monkeypatch.setattr("app.journey.api.fetch_document", fake_fetch)
    api = _client(tmp_path, dd_base="http://dd.local")
    eid = _episode(api)
    view = api.post(f"/journey/episodes/{eid}/rx/import", json={"document_id": 7}).json()
    assert seen["call"] == ("http://dd.local", 7)
    assert view["rx"]["source"] == "doctor-dictation" and view["rx"]["by"] == "Dr. Rao"
    assert [row["key"] for row in view["rx"]["rows"]] == ["metoprolol"]  # the empty row is dropped


def test_import_says_when_doctor_dictation_is_not_running(tmp_path):
    api = _client(tmp_path, dd_base="http://127.0.0.1:9")
    eid = _episode(api)
    response = api.post(f"/journey/episodes/{eid}/rx/import", json={"document_id": 1})
    assert response.status_code == 502 and "127.0.0.1:9" in response.json()["detail"]
    assert api.post(f"/journey/episodes/{eid}/rx/import", json={"document_id": 0}).status_code == 422


def test_fetch_document_maps_404_to_lookup_error(monkeypatch):
    class Reply:
        status_code = 404

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get(self, url):
            assert url == "http://dd.local/api/v1/documents/3"
            return Reply()

    monkeypatch.setattr(rxmod.httpx, "Client", Client)
    try:
        rxmod.fetch_document("http://dd.local/", 3)
    except LookupError as exc:
        assert "3" in str(exc)
    else:
        raise AssertionError("expected LookupError")


# --- boundaries -------------------------------------------------------------

def test_inputs_are_checked_at_the_boundary(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    base = f"/journey/episodes/{eid}"
    assert api.post(f"{base}/obs", json={"sbp": 400, "dbp": 80, "hr": 80, "by": "x"}).status_code == 422
    assert api.post(f"{base}/orders", json={"doses": [{"name": "X", "every_h": 0}], "by": "x"}).status_code == 422
    assert api.post(f"{base}/dose", json={"by": "x"}).status_code == 422
    assert api.post(f"{base}/strips", json={"strips": []}).status_code == 422
    assert api.post(f"{base}/discharge-card", json={"template": "nope", "by": "x"}).status_code == 404
    assert api.post(f"{base}/reminders", json={}).status_code == 409
    assert api.post("/journey/episodes/missing/play").status_code == 404


def test_strip_photo_is_refused_without_a_model_key(tmp_path):
    api = _client(tmp_path)
    eid = _episode(api)
    response = api.post(f"/journey/episodes/{eid}/strips/photo", files={"file": ("s.jpg", b"x", "image/jpeg")})
    assert response.status_code == 409


def test_rule_functions_are_pure_over_events():
    events = [
        {"id": "o", "event_type": "ward.orders_set", "ts_ms": 0, "payload": {**ORDERS, "doses": [
            {**ORDERS["doses"][0], "key": "paracetamol"}]}},
    ]
    assert rules.evaluate(events, 6 * H) == []
    assert [n["kind"] for n in rules.evaluate(events, 7 * H)] == ["dose_overdue"]


# --- shift handover (Muse Spark 1.3 may reword, never add) --------------------

def _ward(api) -> tuple[str, str]:
    eid = _episode(api)
    base = f"/journey/episodes/{eid}"
    api.post(f"{base}/orders", json={**ORDERS, "at_ms": 0})
    api.post(f"{base}/dose", json={"name": "Paracetamol", "amount": "1 g", "by": "Nurse A", "at_ms": H})
    api.post(f"{base}/obs", json={"sbp": 86, "dbp": 50, "hr": 80, "by": "Nurse A", "at_ms": 2 * H})
    return eid, base


def _handover(api, base, **extra):
    body = {"from_nurse": "Nurse A", "to_nurse": "Nurse B", "at_ms": 3 * H, **extra}
    return api.post(f"{base}/handover", json=body).json()["handover"]


def test_handover_template_lists_recorded_facts_with_their_events(tmp_path):
    api = _client(tmp_path)
    _, base = _ward(api)
    handover = _handover(api, base)
    texts = [line["text"] for line in handover["lines"]]
    assert "Day 0 10:00: Paracetamol 1 g logged by Nurse A." in texts
    assert "Paracetamol is ordered every 6 h; by that order the next is due Day 0 16:00." in texts
    assert "Still open: Systolic BP 86 is below the limit of 90 set by Dr. Test." in texts
    assert all(line["evidence"] for line in handover["lines"])
    assert handover["wording"] == "template" and handover["model_note"] == "no Meta Model API key"


def test_handover_keeps_a_spark_rewording_that_adds_nothing(tmp_path):
    api = _client(tmp_path)
    _, base = _ward(api)
    seen = {}

    def write(prompt):
        seen["prompt"] = prompt
        return "Paracetamol 1 g was logged at Day 0 10:00 by Nurse A. Systolic BP 86 is below the limit of 90."

    api.app.state.handover_write = write
    handover = _handover(api, base)
    assert "Do not add any fact" in seen["prompt"] and "Paracetamol 1 g logged" in seen["prompt"]
    assert handover["wording"] == "muse-spark-1.3" and handover["text"].startswith("Paracetamol 1 g")


def test_handover_rejects_a_rewording_with_a_new_number_or_advice(tmp_path):
    api = _client(tmp_path)
    _, base = _ward(api)
    for reply, why in [
        ("Paracetamol 2 g was logged by Nurse A.", "added a number, a medicine or an instruction"),
        ("We recommend a fluid bolus for the BP of 86.", "advice wording"),
        ("Ondansetron was logged by Nurse A.", "added a number, a medicine or an instruction"),
    ]:
        api.app.state.handover_write = lambda prompt, reply=reply: reply
        handover = _handover(api, base)
        assert handover["wording"] == "template" and handover["text"] is None
        assert handover["model_note"] == why, reply


def test_handover_falls_back_when_the_model_call_fails(tmp_path):
    api = _client(tmp_path)
    _, base = _ward(api)

    def broken(prompt):
        raise RuntimeError("down")

    api.app.state.handover_write = broken
    handover = _handover(api, base)
    assert handover["wording"] == "template" and handover["model_note"] == "model call failed (RuntimeError)"


def test_accepting_a_handover_completes_the_nurse_story(tmp_path):
    api = _client(tmp_path)
    eid, base = _ward(api)
    handover = _handover(api, base)
    view = api.post(f"{base}/handover/{handover['id']}/accept", json={"by": "Nurse B"}).json()
    assert view["handover"]["accepted_by"] == "Nurse B"
    nurse = next(story for story in view["stories"] if story["id"] == "nurse")
    assert next(step for step in nurse["steps"] if step["id"] == "handover")["done"] is True
    assert api.post(f"{base}/handover/nope/accept", json={"by": "x"}).status_code == 404
    second = _handover(api, base, at_ms=5 * H)
    assert second["since"] == "Day 0 12:00"  # starts where the last handover ended


def test_handover_after_discharge_drops_ward_due_times(tmp_path):
    api = _client(tmp_path)
    _, base = _ward(api)
    api.post(f"{base}/discharge-card", json={"by": "Dr. Test", "at_ms": 2 * H + 1})
    texts = [line["text"] for line in _handover(api, base)["lines"]]
    assert not any("next is due" in text for text in texts)
