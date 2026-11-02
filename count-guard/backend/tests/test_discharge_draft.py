"""Discharge drafted from the timeline (spec §6.8): the DD prescription, drugs given, the count and key moves; the
PDF and the follow-up .ics; Spark wording with the wording check, or the template labelled Prepared (§6.7)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.adapters.spark import SparkAdapter
from app.journey import discharge_draft
from app.main import create_app
from conftest import pdf_text
from tests.test_care_demo import _client
from tests.test_flow_states import ADMIT_CHECKS
from tests.test_intake import FIXTURE
from tests.test_p2_live import _keyed

DOCTOR = "Dr. A. Rao (synthetic)"
NURSE = "Nurse Asha (synthetic)"


def _url(eid, path):
    return f"/journey/episodes/{eid}/{path}"


def _ok(response):
    assert response.status_code == 200, response.text
    return response


def _stay(client) -> str:
    """Tasks 2, 7, 8 in order: the DD admission, theatre with lignocaine confirmed and a person's 20 of 20 count, back to ward."""
    created = client.post("/journey/intake", json=FIXTURE)
    assert created.status_code == 201, created.text
    eid = created.json()["episode_id"]
    move = lambda to, **extra: _ok(client.post(_url(eid, "state"), json={"to": to, "by": DOCTOR, **extra}))
    move("ward", checklist=ADMIT_CHECKS)
    move("theatre", procedure="hernia-repair")
    _ok(client.post(_url(eid, "count"), json={"step": "opened", "quantity": 20, "by": NURSE}))
    _ok(client.post(_url(eid, "surgery"), json={"step": "began", "by": NURSE}))
    _ok(client.post(_url(eid, "theatre/drug"), data={"text": "lignocaine two percent, five ml, local infiltration", "by": DOCTOR}))
    heard = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "druglog.parsed"][-1]
    _ok(client.post(_url(eid, f"theatre/drug/{heard['id']}/confirm"), json={"by": DOCTOR}))
    _ok(client.post(_url(eid, "count"), json={"step": "closing", "returned": 20, "by": NURSE}))
    _ok(client.post(_url(eid, "surgery"), json={"step": "ended", "by": NURSE}))
    move("ward")
    return eid


def _draft(client, eid):
    return client.post(_url(eid, "discharge/draft"), json={"by": DOCTOR})


def test_draft_pulls_rx_drugs_and_count(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)
    view = _ok(_draft(client, eid)).json()
    draft = view["drafts"]["discharge"]
    timeline = draft["timeline"]
    assert [r["name"] for r in timeline["prescription"]["rows"]] == ["Paracetamol", "Pantoprazole"]
    assert timeline["prescription"]["diagnosis"] == ["Left inguinal hernia, for elective repair"]
    [drug] = timeline["drugs_given"]
    assert (drug["name"], drug["amount"], drug["unit"], drug["by"]) == ("lignocaine", 5, "ml", DOCTOR)
    assert "opened 20 / returned 20" in timeline["count"]["text"] and timeline["count"]["by"] == NURSE
    assert [m["to"] for m in timeline["events"]][:3] == ["admitting", "ward", "theatre"]
    assert timeline["follow_up"]["date"] == "2026-11-09"
    assert "lignocaine" in draft["summary"] and "Paracetamol" in draft["summary"]
    # The same build from the record alone (the interface the route uses).
    built = discharge_draft.build(client.app.state.morning.events(eid))
    assert set(built) == {"prescription", "drugs_given", "count", "events", "follow_up"}


def test_ai_or_camera_closing_is_not_the_count(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)
    client.app.state.morning.append(eid, "count.closing", {"opened": 20, "returned": 3, "unaccounted": 17, "by": "Count Guard AI"}, ts_ms=10**7)
    count = discharge_draft.build(client.app.state.morning.events(eid))["count"]
    assert "returned 20" in count["text"] and count["by"] == NURSE


def test_pdf_contains_drug_and_count(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)
    assert client.get(_url(eid, "discharge.pdf")).status_code == 404  # nothing drafted yet
    _ok(_draft(client, eid))
    pdf = _ok(client.get(_url(eid, "discharge.pdf")))
    assert pdf.headers["content-type"] == "application/pdf"
    text = pdf_text(pdf.content)
    assert "lignocaine" in text and "Opened 20. Returned 20." in text
    assert "Paracetamol 650 mg" in text and "Follow-up" in text
    assert not list(tmp_path.glob("*.pdf"))  # written under the data dir's reports, never beside the repo
    assert list((tmp_path / "reports" / "journey").glob("*.pdf"))


def test_ics_has_follow_up_date(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)
    assert client.get(_url(eid, "follow-up.ics")).status_code == 404
    _ok(_draft(client, eid))
    ics = _ok(client.get(_url(eid, "follow-up.ics")))
    assert ics.headers["content-type"].startswith("text/calendar")
    assert "DTSTART:20261109T" in ics.text and "BEGIN:VEVENT" in ics.text


def test_draft_refused_before_ward(tmp_path):
    client = _client(tmp_path)
    eid = client.post("/journey/intake", json=FIXTURE).json()["episode_id"]  # admitting
    refused = _draft(client, eid)
    assert refused.status_code == 409 and "ward" in refused.json()["detail"]
    assert client.post(_url("missing", "discharge/draft"), json={"by": DOCTOR}).status_code == 404


def test_dictation_amends_the_draft_and_sign_uses_the_latest(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)
    first = _ok(_draft(client, eid)).json()["drafts"]["discharge"]
    said = {"text": "Follow-up: wound check in clinic on day 7.", "by": DOCTOR}
    amended = _ok(client.post(_url(eid, "dictate/discharge"), data=said)).json()["drafts"]["discharge"]
    assert amended["id"] != first["id"] and amended["amends"] == first["id"]
    assert amended["timeline"] == first["timeline"] and amended["summary"] == first["summary"]
    assert amended["sections"]
    stale = {"summary": "Old.", "by": DOCTOR, "draft_id": first["id"]}
    assert client.post(_url(eid, "discharge/sign"), json=stale).status_code == 409
    signed = {"summary": "Recovered well after hernia repair.", "by": DOCTOR, "draft_id": amended["id"]}
    assert _ok(client.post(_url(eid, "discharge/sign"), json=signed)).json()["state"] == "discharging"
    assert "Recovered well after hernia repair." in pdf_text(_ok(client.get(_url(eid, "discharge.pdf"))).content)


def test_discharge_card_in_patient_view(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)
    draft = _ok(_draft(client, eid)).json()["drafts"]["discharge"]
    body = {"summary": draft["summary"], "by": DOCTOR, "draft_id": draft["id"]}
    view = _ok(client.post(_url(eid, "discharge/sign"), json=body)).json()
    card = view["card"]
    assert card["title"] and card["by"] == DOCTOR
    assert [row["medicine"] for row in card["schedule"]][:1] == ["Paracetamol 650 mg"]
    [drafted] = [i for i in view["timeline"] if i["type"] == "discharge.drafted"]
    assert drafted["patient"] == "" and drafted["plain"] == f"{DOCTOR} drafted the discharge from the record (draft, not signed)."
    assert not any(m["capability"] == "discharge" for m in view["ai_moments"])  # a timeline draft is not a voice moment


def test_discharge_wording_live_and_template_fallback(tmp_path, monkeypatch):
    # Off (no key, demo-check): the template text, labelled prepared.
    client = _client(tmp_path / "off")
    eid = _stay(client)
    off = _ok(_draft(client, eid)).json()["drafts"]["discharge"]
    assert off["wording"] == "template" and off["source"] == "prepared" and off["calls"] == []
    assert off["summary"] == "\n".join(line["text"] for line in off["lines"])

    # Live: Spark rewords; kept only when it passes the wording check (no new number, drug or advice).
    prompts = []
    reply = {"text": "M. Fernandes had a hernia repair. Lignocaine 5 ml was given in theatre. The swab count was 20 of 20."}
    monkeypatch.setattr(SparkAdapter, "write", lambda self, prompt: prompts.append(prompt) or reply["text"])
    live = TestClient(create_app(_keyed(tmp_path / "on")), client=("127.0.0.1", 50000))   # loopback: intake
    eid = _stay(live)
    got = _ok(_draft(live, eid)).json()["drafts"]["discharge"]
    assert len(prompts) == 1 and "Do not add any fact" in prompts[0]
    assert got["wording"] == "muse-spark-1.3" and got["source"] == "muse-spark-1.3"
    assert got["summary"] == reply["text"] and got["calls"][0]["source"] == "muse-spark-1.3"

    reply["text"] = "Give ondansetron 4 mg at home."  # advice, a new drug and a new number: the check refuses it
    bad = _ok(_draft(live, eid)).json()["drafts"]["discharge"]
    assert bad["wording"] == "template" and bad["source"] == "prepared" and bad["model_note"]
    assert bad["summary"] == "\n".join(line["text"] for line in bad["lines"]) and "ondansetron" not in bad["summary"]
    assert bad["calls"][0]["source"] == "failed"


def test_follow_up_ics_from_a_card_alone(tmp_path):
    client = _client(tmp_path)
    eid = client.post("/journey/intake", json=FIXTURE).json()["episode_id"]
    assert client.get(_url(eid, "follow-up.ics")).status_code == 404
    _ok(client.post(_url(eid, "discharge-card"), json={"template": "hernia-repair", "by": DOCTOR}))
    assert "DTSTART:20261109T" in _ok(client.get(_url(eid, "follow-up.ics"))).text
    assert client.get(_url(eid, "discharge.pdf")).status_code == 404  # a PDF needs a draft or a signed discharge


def _pdf_follow_up(client, eid) -> str:
    text = pdf_text(_ok(client.get(_url(eid, "discharge.pdf"))).content)
    return text.split("Follow-up visit: ")[1].split("\n")[0]


def test_follow_up_date_does_not_drift_with_later_events(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)
    draft = _ok(_draft(client, eid)).json()["drafts"]["discharge"]
    before = _pdf_follow_up(client, eid)
    assert before == "Mon 9 Nov (2026-11-09)."
    two_days = 2 * 24 * 3_600_000
    client.app.state.morning.append(eid, "checkin.recorded", {"day": 3, "feels": "ok", "by": "patient"}, ts_ms=draft["at_ms"] + two_days)
    assert _pdf_follow_up(client, eid) == before
    assert "DTSTART:20261109T" in _ok(client.get(_url(eid, "follow-up.ics"))).text


def test_draft_after_dictation_keeps_the_dictated_sections(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)
    said = {"text": "Follow-up: wound check in clinic on day 7.", "by": DOCTOR}
    dictated = _ok(client.post(_url(eid, "dictate/discharge"), data=said)).json()["drafts"]["discharge"]
    drafted = _ok(_draft(client, eid)).json()["drafts"]["discharge"]
    assert drafted["sections"] == dictated["sections"] and drafted["amends"] == dictated["id"]
    assert drafted["timeline"]["count"] is not None
    text = pdf_text(_ok(client.get(_url(eid, "discharge.pdf"))).content)
    assert "wound check in clinic" in text.lower()  # point 4: the PDF prints the dictated sections under the summary


def test_closing_before_incision_is_not_the_count(tmp_path):
    client = _client(tmp_path)
    created = client.post("/journey/intake", json=FIXTURE).json()["episode_id"]
    move = lambda to, **extra: _ok(client.post(_url(created, "state"), json={"to": to, "by": DOCTOR, **extra}))
    move("ward", checklist=ADMIT_CHECKS)
    move("theatre", procedure="hernia-repair")
    _ok(client.post(_url(created, "count"), json={"step": "opened", "quantity": 20, "by": NURSE}))
    _ok(client.post(_url(created, "count"), json={"step": "closing", "returned": 20, "by": NURSE}))  # before incision
    assert discharge_draft.build(client.app.state.morning.events(created))["count"] is None
    _ok(client.post(_url(created, "surgery"), json={"step": "began", "by": NURSE}))
    assert discharge_draft.build(client.app.state.morning.events(created))["count"] is None
