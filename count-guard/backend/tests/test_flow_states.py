"""Patient states: guarded moves, the theatre count rule, and plain now/next wording."""

from __future__ import annotations

import re

from tests.test_care_demo import _client

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
ADMIT_CHECKS = {"band": True, "allergies": True, "baseline_obs": True, "consent": True}
DISCHARGE_CHECKS = {"card_given": True, "medicines_handed": True, "reminders_set": True}


def _new(tmp_path):
    client = _client(tmp_path)
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    return client, eid


def _move(client, eid, to, **extra):
    body = {"to": to, "by": "Dr. A. Rao (synthetic)", "at_ms": 0, **extra}
    return client.post(f"/journey/episodes/{eid}/state", json=body)


def _view(client, eid):
    return client.get(f"/journey/episodes/{eid}").json()


def _to_ward(client, eid):
    assert _move(client, eid, "admitting", reason="Hernia repair").status_code == 200
    assert _move(client, eid, "ward", checklist=ADMIT_CHECKS).status_code == 200


def _to_theatre(client, eid):
    _to_ward(client, eid)
    assert _move(client, eid, "theatre", procedure="hernia-repair").status_code == 200


def _surgery(client, eid, step):
    return client.post(f"/journey/episodes/{eid}/surgery", json={"step": step, "by": "Nurse Asha (synthetic)", "at_ms": 0})


def test_new_episode_is_in_clinic(tmp_path):
    client, eid = _new(tmp_path)
    view = _view(client, eid)
    assert view["state"] == "clinic"
    assert {m["to"] for m in view["allowed"]} == {"admitting", "clinic_done"}
    assert view["procedures"] == {"hernia-repair": "Open inguinal hernia repair"}


def test_admit_needs_reason(tmp_path):
    client, eid = _new(tmp_path)
    assert _move(client, eid, "admitting", reason="").status_code == 409
    r = _move(client, eid, "admitting", reason="Hernia repair")
    assert r.status_code == 200
    assert r.json()["state"] == "admitting"
    assert "admission" in r.json()["now_next"]["next"]


def test_disallowed_move_is_409_and_writes_nothing(tmp_path):
    client, eid = _new(tmp_path)
    before = len(_view(client, eid)["timeline"])
    r = _move(client, eid, "theatre", procedure="hernia-repair")
    assert r.status_code == 409
    assert "clinic" in r.json()["detail"]
    assert len(_view(client, eid)["timeline"]) == before


def test_admission_checklist_must_be_complete(tmp_path):
    client, eid = _new(tmp_path)
    _move(client, eid, "admitting", reason="Hernia repair")
    assert _move(client, eid, "ward", checklist={**ADMIT_CHECKS, "consent": False}).status_code == 409
    assert _move(client, eid, "ward", checklist={"band": True, "allergies": True, "baseline_obs": True}).status_code == 409
    assert _move(client, eid, "ward", checklist=ADMIT_CHECKS).json()["state"] == "ward"


def test_theatre_needs_procedure_and_surgery_end(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    assert _move(client, eid, "theatre").status_code == 409
    assert _move(client, eid, "theatre", procedure="hernia-repair").json()["state"] == "theatre"
    assert _view(client, eid)["procedure"]["key"] == "hernia-repair"
    assert _move(client, eid, "ward").status_code == 409
    assert _surgery(client, eid, "ended").status_code == 409
    assert _surgery(client, eid, "began").status_code == 200
    assert _surgery(client, eid, "ended").status_code == 200
    assert _move(client, eid, "ward").json()["state"] == "ward"


def test_surgery_only_in_theatre(tmp_path):
    client, eid = _new(tmp_path)
    assert _surgery(client, eid, "began").status_code == 409


def test_open_count_needs_reason(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    base = f"/journey/episodes/{eid}"
    by = {"by": "Nurse Asha (synthetic)", "at_ms": 0}
    client.post(f"{base}/count", json={"step": "opened", "quantity": 20, **by})
    client.post(f"{base}/count", json={"step": "closing", "returned": 19, **by})
    _surgery(client, eid, "began")
    _surgery(client, eid, "ended")
    r = _move(client, eid, "ward", reason="")
    assert r.status_code == 409
    assert "count" in r.json()["detail"]
    assert _move(client, eid, "ward", reason="X-ray ordered").status_code == 200
    state_event = [e for e in _view(client, eid)["timeline"] if e["type"] == "patient.state"][-1]
    assert "X-ray ordered" in state_event["plain"]


def test_closed_count_needs_no_reason(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    base = f"/journey/episodes/{eid}"
    by = {"by": "Nurse Asha (synthetic)", "at_ms": 0}
    client.post(f"{base}/count", json={"step": "opened", "quantity": 20, **by})
    client.post(f"{base}/count", json={"step": "closing", "returned": 20, **by})
    _surgery(client, eid, "began")
    _surgery(client, eid, "ended")
    assert _move(client, eid, "ward").status_code == 200


def test_discharging_needs_signed_event_and_home_is_final(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    assert _move(client, eid, "discharging").status_code == 409
    store = client.app.state.morning
    store.append(eid, "discharge.signed", {"by": "Dr. A. Rao (synthetic)"}, ts_ms=1000)
    assert _move(client, eid, "discharging").json()["state"] == "discharging"
    assert _move(client, eid, "home", checklist={**DISCHARGE_CHECKS, "card_given": False}).status_code == 409
    assert _move(client, eid, "home", checklist=DISCHARGE_CHECKS).json()["state"] == "home"
    assert _view(client, eid)["allowed"] == []
    for to in ("clinic", "ward", "discharging", "home"):
        assert _move(client, eid, to, reason="again", checklist=DISCHARGE_CHECKS).status_code == 409


def test_no_advice_words_in_now_next(tmp_path):
    client, eid = _new(tmp_path)
    seen = [_view(client, eid)]
    _to_theatre(client, eid)
    seen.append(_view(client, eid))
    _surgery(client, eid, "began")
    _surgery(client, eid, "ended")
    seen.append(_move(client, eid, "ward").json())
    client.app.state.morning.append(eid, "discharge.signed", {"by": "x"}, ts_ms=2000)
    seen.append(_move(client, eid, "discharging").json())
    seen.append(_move(client, eid, "home", checklist=DISCHARGE_CHECKS).json())
    for view in seen:
        assert not ADVICE.search(view["now_next"]["now"] + " " + view["now_next"]["next"])
    assert len(seen) == 5
