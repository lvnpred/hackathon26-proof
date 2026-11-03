"""Discharge and task dictation open in every state where the patient is admitted (clarity §4.4, C5).

A 409 with the reason stays for clinic, clinic_done and home, where there is no stay to attach the words to.
"""

from __future__ import annotations

import pytest

from app.journey import media_api
from tests.test_flow_states import DISCHARGE_CHECKS, _move, _new, _to_theatre, _to_ward

DOC = "Dr. A. Rao (synthetic)"
ADMITTED = ("admitting", "ward", "theatre", "discharging")
NOT_ADMITTED = ("clinic", "clinic_done", "home")
SAID = {"dictate/discharge": "Follow-up in one week.", "dictate/task": "Paracetamol given"}


def test_admitted_states_are_pinned():
    """The frontend's visibility.js ADMITTED list is this tuple's twin; a change here must change both."""
    assert media_api.ADMITTED == ADMITTED


def _in(tmp_path, state):
    client, eid = _new(tmp_path)
    if state == "clinic_done":
        assert _move(client, eid, "clinic_done").status_code == 200
    elif state == "admitting":
        assert _move(client, eid, "admitting", reason="Hernia repair").status_code == 200
    elif state == "ward":
        _to_ward(client, eid)
    elif state == "theatre":
        _to_theatre(client, eid)
    elif state in ("discharging", "home"):
        _to_ward(client, eid)
        client.app.state.morning.append(eid, "discharge.signed", {"by": DOC}, ts_ms=1000)
        assert _move(client, eid, "discharging").status_code == 200
        if state == "home":
            assert _move(client, eid, "home", checklist=DISCHARGE_CHECKS).status_code == 200
    assert client.get(f"/journey/episodes/{eid}").json()["state"] == state
    return client, eid


def _say(client, eid, route):
    return client.post(f"/journey/episodes/{eid}/{route}", data={"by": DOC, "at_ms": 0, "text": SAID[route]})


@pytest.mark.parametrize("route", sorted(SAID))
@pytest.mark.parametrize("state", ADMITTED)
def test_admitted_states_accept_dictation(tmp_path, route, state):
    client, eid = _in(tmp_path, state)
    said = _say(client, eid, route)
    assert said.status_code == 200, said.text
    if route == "dictate/discharge":
        assert said.json()["drafts"]["discharge"] is not None


@pytest.mark.parametrize("route", sorted(SAID))
@pytest.mark.parametrize("state", NOT_ADMITTED)
def test_other_states_refuse_with_the_reason(tmp_path, route, state):
    client, eid = _in(tmp_path, state)
    refused = _say(client, eid, route)
    assert refused.status_code == 409
    detail = refused.json()["detail"]
    assert detail.endswith(f"The patient is in {state}.") and "admitted" in detail
