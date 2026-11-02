"""Fix round 1 (R23, "nothing lost"): theatre drug lines stay correctable, and every reader puts the correction where
the original stood, so a correction written after the patient left theatre still belongs to the theatre stay."""

from __future__ import annotations

import pytest

from app.journey import discharge_draft, theatre
from conftest import pdf_text
from tests.test_correct import _correct
from tests.test_discharge_draft import DOCTOR, NURSE, _draft, _ok, _stay, _url
from tests.test_care_demo import _client
from tests.test_flow_states import ADMIT_CHECKS
from tests.test_intake import FIXTURE


def _events(client, eid):
    return client.app.state.morning.events(eid)


def _last(client, eid, kind):
    return [e for e in _events(client, eid) if e["event_type"] == kind][-1]


def _in_theatre(client) -> str:
    eid = client.post("/journey/intake", json=FIXTURE).json()["episode_id"]
    move = lambda to, **extra: _ok(client.post(_url(eid, "state"), json={"to": to, "by": DOCTOR, **extra}))
    move("ward", checklist=ADMIT_CHECKS)
    move("theatre", procedure="hernia-repair")
    _ok(client.post(_url(eid, "theatre/drug"), data={"text": "lignocaine two percent, five ml, local infiltration", "by": DOCTOR}))
    return eid


def test_drug_corrected_after_theatre_shows_in_the_draft_and_pdf(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)  # lignocaine 5 ml confirmed in theatre, then back to the ward
    given = _last(client, eid, "drug.given")
    res = _correct(client, eid, given["id"], {"amount": 8}, by=DOCTOR)
    assert res.status_code == 200, res.text
    fixed = _last(client, eid, "drug.given")
    assert fixed["supersedes_id"] == given["id"] and fixed["payload"]["draft_id"] == given["payload"]["draft_id"]
    assert fixed["payload"]["by"] == DOCTOR and fixed["payload"]["amount"] == 8
    [drug] = discharge_draft.build(_events(client, eid))["drugs_given"]
    assert (drug["name"], drug["amount"], drug["unit"]) == ("lignocaine", 8, "ml")
    _ok(_draft(client, eid))
    text = pdf_text(_ok(client.get(_url(eid, "discharge.pdf"))).content)
    assert "8 ml" in text and "5 ml" not in text


def test_a_drug_correction_stays_in_the_theatre_stay(tmp_path):
    """Written after the move to the ward, it still stands where the original stood: not in the ward stay."""
    client = _client(tmp_path)
    eid = _stay(client)
    given = _last(client, eid, "drug.given")
    assert _correct(client, eid, given["id"], {"amount": 8}, by=DOCTOR).status_code == 200
    events = _events(client, eid)
    assert not [e for e in theatre.placed_stay(events) if e["event_type"] == "drug.given"]  # the ward stay has no drug
    up_to_ward = events[: max(i for i, e in enumerate(events) if e["event_type"] == "patient.state")]
    placed = theatre.placed_stay(events[: len(up_to_ward)] + [events[-1]])  # the theatre stay plus the late correction
    assert [e["payload"]["amount"] for e in placed if e["event_type"] == "drug.given"] == [8]


def test_context_card_facts_read_the_corrected_amount(tmp_path):
    client = _client(tmp_path)
    eid = _in_theatre(client)
    heard = _last(client, eid, "druglog.parsed")
    _ok(client.post(_url(eid, f"theatre/drug/{heard['id']}/confirm"), json={"by": DOCTOR}))
    given = _last(client, eid, "drug.given")
    assert _correct(client, eid, given["id"], {"amount": 8}, by=DOCTOR).status_code == 200
    events = _events(client, eid)
    facts = theatre.facts(events, theatre.placed_stay(events), given["ts_ms"] + 60_000)
    assert any("lignocaine 8 ml" in f for f in facts) and not any("5 ml" in f for f in facts)
    [row] = theatre.panel(events, False)["drugs"]
    assert row["given"]["by"] == DOCTOR and row["amount"] == 8  # the row shows the dose given, as corrected
    assert row["given"]["id"] == _last(client, eid, "drug.given")["id"]  # the line to correct is the newest one


def test_correcting_a_heard_line_before_confirm_changes_what_confirm_writes(tmp_path):
    client = _client(tmp_path)
    eid = _in_theatre(client)
    heard = _last(client, eid, "druglog.parsed")
    assert _correct(client, eid, heard["id"], {"amount": 8, "route": "iv"}, by=DOCTOR).status_code == 200
    fixed = _last(client, eid, "druglog.parsed")
    [row] = theatre.panel(_events(client, eid), False)["drugs"]
    assert row["id"] == fixed["id"] and row["amount"] == 8 and row["given"] is None
    assert client.post(_url(eid, f"theatre/drug/{heard['id']}/confirm"), json={"by": DOCTOR}).status_code == 404
    _ok(client.post(_url(eid, f"theatre/drug/{fixed['id']}/confirm"), json={"by": DOCTOR}))
    given = _last(client, eid, "drug.given")
    assert (given["payload"]["amount"], given["payload"]["route"]) == (8, "iv")


def test_a_confirmed_heard_line_is_corrected_on_the_drug_given(tmp_path):
    client = _client(tmp_path)
    eid = _in_theatre(client)
    heard = _last(client, eid, "druglog.parsed")
    _ok(client.post(_url(eid, f"theatre/drug/{heard['id']}/confirm"), json={"by": DOCTOR}))
    assert _correct(client, eid, heard["id"], {"amount": 8}, by=DOCTOR).status_code == 409


@pytest.mark.parametrize("payload", [{"by": NURSE}, {"draft_id": "x"}, {"confirmed": False}, {"generic": "x"},
                                     {"amount": 0}, {"amount": "five"}, {"unit": "bucket"}, {"route": "ear"}])
def test_drug_correction_checks_the_fields(tmp_path, payload):
    client = _client(tmp_path)
    eid = _stay(client)
    given = _last(client, eid, "drug.given")
    assert _correct(client, eid, given["id"], payload, by=DOCTOR).status_code == 422


def test_dose_given_stays_refused(tmp_path):
    client = _client(tmp_path)
    eid = _stay(client)
    old = client.app.state.morning.append(eid, "dose.given", {"key": "p", "name": "P", "amount": "1 g", "by": NURSE}, ts_ms=1)
    assert _correct(client, eid, old["id"], {"amount": "2 g"}).status_code == 409
