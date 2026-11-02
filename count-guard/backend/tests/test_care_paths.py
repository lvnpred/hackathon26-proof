"""One test per journey v1 feature the care app now carries. Each calls the route the care component calls."""

from __future__ import annotations

from tests.test_care_demo import _client
from tests.test_care_story import DOCTOR, Ward

H = 3_600_000
MEENA = "Nurse Meena (synthetic)"  # NurseActions WARD_NURSE
KAVYA = "Nurse Kavya (synthetic)"  # Handover.jsx TO


def _ward(tmp_path):
    client = _client(tmp_path)
    kumar = next(p for p in client.post("/journey/demo/seed").json()["patients"] if p["bed"] == "7")
    return client, Ward(client, kumar["id"])


def _home(tmp_path):
    client = _client(tmp_path)
    kumar = next(p for p in client.post("/journey/demo/seed").json()["patients"] if p["bed"] == "4")
    ward = Ward(client, kumar["id"])
    ward.post("rx/demo", {"at_ms": 0})
    ward.post("discharge-card", {"template": "hernia-repair", "by": DOCTOR, "at_ms": H})
    return client, ward


def test_handover_from_nurse_chart(tmp_path):
    _, ward = _ward(tmp_path)
    # Handover.jsx: draft with from/to and use_model, then accept as the taker.
    view = ward.post("handover", {"from_nurse": MEENA, "to_nurse": KAVYA, "use_model": False, "at_ms": 2 * H})
    handover = view["handover"]
    assert handover["wording"] == "template" and handover["lines"] is not None and not handover["accepted_by"]
    view = ward.post(f"handover/{handover['id']}/accept", {"by": KAVYA, "at_ms": 3 * H})
    assert view["handover"]["accepted_by"] == KAVYA


def test_dose_given_from_nurse_chart(tmp_path):
    _, ward = _ward(tmp_path)
    # DoseGiven.jsx: one typed or said line with the nurse's name.
    view = ward.post("dose", {"text": "paracetamol 1 g", "by": MEENA, "at_ms": 2 * H})
    gave = [e for e in view["timeline"] if e["type"] == "dose.given"]
    assert gave and "aracetamol" in gave[-1]["plain"]


def test_reminders_ics_from_patient_view(tmp_path):
    client, ward = _home(tmp_path)
    # legacy Reminders: post, then the file link it returns.
    out = ward.post("reminders", {})
    assert out["ics_url"].endswith("/reminders.ics")
    res = client.get(out["ics_url"])
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in res.text
    assert ward.get()["card"]["title"]  # the discharge card shows in the same patient view


def test_checkin_and_help_from_patient_view(tmp_path):
    _, ward = _home(tmp_path)
    view = ward.post("checkin", {"day": 2, "feels": "A bit sore", "signs": [], "note": "", "at_ms": 30 * H})
    assert any(e["type"] == "checkin.recorded" for e in view["timeline"])
    view = ward.post("help", {"says": "My wound is leaking", "at_ms": 31 * H})
    assert any(e["type"] == "help.requested" for e in view["timeline"])


def test_audit_in_history(tmp_path):
    _, ward = _ward(tmp_path)
    ward.post("dose", {"text": "paracetamol 1 g", "by": MEENA, "at_ms": 2 * H})
    rows = ward.audit("dose.given")  # Chart.jsx: getAudit(episodeId) -> rows -> AuditTable
    assert rows and {"id", "when", "who", "what", "type"} <= set(rows[0])


def test_audit_rows_on_ai_page(tmp_path):
    client, ward = _ward(tmp_path)
    ward.post("handover", {"from_nurse": MEENA, "to_nurse": KAVYA, "use_model": False, "at_ms": 2 * H})
    body = client.get(f"/journey/episodes/{ward.eid}/audit").json()  # AiAudit.jsx: same route, picked patient
    assert body["banner"] and any(r["type"] == "handover.drafted" for r in body["rows"])
