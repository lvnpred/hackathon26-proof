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
        n = view["now_next"]
        assert not ADVICE.search(" ".join((n["now"], n["you_now"], n["next"], n["you_next"])))
    assert len(seen) == 5


def test_corrected_count_closes_its_open_nudge(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    base = f"/journey/episodes/{eid}"
    by = {"by": "Nurse Priya (synthetic)", "at_ms": 0}
    client.post(f"{base}/count", json={"step": "opened", "quantity": 20, **by})
    view = client.post(f"{base}/count", json={"step": "closing", "returned": 19, **by}).json()
    assert [n["kind"] for n in view["nudges"]] == ["count_open"]
    first = next(n["fact_id"] for n in view["nudges"])
    view = client.post(f"{base}/count", json={"step": "closing", "returned": 20, "supersedes_id": first, **by}).json()
    assert view["nudges"] == []


def test_correction_does_not_close_overdue_nudges():
    from app.journey.nudges import open_nudges

    def raised(kind):
        return {"id": f"n-{kind}", "event_type": "nudge.raised", "payload": {"kind": kind, "fact_id": "f1"}}

    events = [raised("dose_overdue"), raised("obs_overdue"), raised("obs_past_limit"), raised("count_open"),
              {"id": "f2", "event_type": "obs.recorded", "supersedes_id": "f1", "payload": {}}]
    assert [e["payload"]["kind"] for e in open_nudges(events)] == ["dose_overdue", "obs_overdue"]


def _open_count_in_theatre(client, eid):
    _to_theatre(client, eid)
    base = f"/journey/episodes/{eid}"
    by = {"by": "Nurse Asha (synthetic)", "at_ms": 0}
    client.post(f"{base}/count", json={"step": "opened", "quantity": 20, **by})
    client.post(f"{base}/count", json={"step": "closing", "returned": 19, **by})
    _surgery(client, eid, "began")
    _surgery(client, eid, "ended")


def _back_to_ward(view):
    return next(m for m in view["allowed"] if m["to"] == "ward")


def test_open_count_makes_the_theatre_exit_the_surgeons(tmp_path):
    client, eid = _new(tmp_path)
    _open_count_in_theatre(client, eid)
    move = _back_to_ward(_view(client, eid))
    assert move["role"] == "doctor"
    assert "reason (count open)" in move["needs"]
    assert _move(client, eid, "ward", reason="").status_code == 409


def test_closed_count_leaves_the_theatre_exit_to_the_nurse(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    base = f"/journey/episodes/{eid}"
    by = {"by": "Nurse Asha (synthetic)", "at_ms": 0}
    client.post(f"{base}/count", json={"step": "opened", "quantity": 20, **by})
    client.post(f"{base}/count", json={"step": "closing", "returned": 20, **by})
    _surgery(client, eid, "began")
    _surgery(client, eid, "ended")
    move = _back_to_ward(_view(client, eid))
    assert move["role"] == "nurse"
    assert move["needs"] == []


def test_needs_list_drops_surgery_once_ended(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    assert "surgery ended" in _back_to_ward(_view(client, eid))["needs"]
    _surgery(client, eid, "began")
    _surgery(client, eid, "ended")
    assert "surgery ended" not in _back_to_ward(_view(client, eid))["needs"]


def test_next_names_the_unacknowledged_orders_and_now_the_latest_event(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    items = [{"kind": "check", "text": "Check wound dressing", "mode": "tick", "proof": "none", "every_h": None}]
    view = client.post(
        f"/journey/episodes/{eid}/orders/sign", json={"items": items, "by": "Dr. A. Rao (synthetic)", "at_ms": 600_000}
    ).json()
    assert view["now_next"]["next"] == "Nurse acknowledges the new orders from Dr. A. Rao (synthetic)."
    assert "signed new orders" in view["now_next"]["now"]
    order = view["order_list"][0]
    view = client.post(
        f"/journey/episodes/{eid}/orders/{order['id']}/ack", json={"by": "Nurse Meena (synthetic)", "at_ms": 900_000}
    ).json()
    assert "acknowledged the orders" in view["now_next"]["now"]
    assert view["now_next"]["next"] == NEXT_WARD
    task = view["tasks"][0]
    view = client.post(
        f"/journey/episodes/{eid}/tasks/{task['id']}/done",
        json={"by": "Nurse Meena (synthetic)", "via": "tap", "at_ms": 1_200_000},
    ).json()
    assert "Check wound dressing" in view["now_next"]["now"]
    for text in (view["now_next"]["now"], view["now_next"]["next"]):
        assert not ADVICE.search(text)


NEXT_WARD = "Doctor sends the patient to theatre or signs the discharge."


def test_state_line_with_no_earlier_state_reads_as_an_admission(tmp_path):
    from app.journey.stories import plain

    event = {
        "id": "x", "event_type": "patient.state", "ts_ms": 0, "supersedes_id": None,
        "payload": {"from": None, "to": "ward", "by": "Dr. A. Rao (synthetic)", "reason": "Admitted the day before (seed)"},
    }
    text = plain(event)
    assert "admitted the patient to the ward" in text
    assert "None" not in text


def test_patient_now_speaks_to_you_for_each_kind_of_event(tmp_path):
    from app.journey.stories import clock

    client, eid = _new(tmp_path)
    assert _view(client, eid)["now_next"]["you_now"] == "You are in clinic."
    _to_ward(client, eid)
    assert _view(client, eid)["now_next"]["you_now"].startswith("Dr. A. Rao moved you to the ward at ")
    items = [{"kind": "check", "text": "Check wound dressing", "mode": "tick", "proof": "none", "every_h": None}]
    view = client.post(
        f"/journey/episodes/{eid}/orders/sign", json={"items": items, "by": "Dr. A. Rao (synthetic)", "at_ms": 600_000}
    ).json()
    assert view["now_next"]["you_now"] == f"Dr. A. Rao signed new orders for you at {clock(600_000)}."
    order = view["order_list"][0]
    view = client.post(
        f"/journey/episodes/{eid}/orders/{order['id']}/ack", json={"by": "Nurse Meena (synthetic)", "at_ms": 900_000}
    ).json()
    assert view["now_next"]["you_now"] == f"Nurse Meena acknowledged your orders at {clock(900_000)}."
    assert view["now_next"]["now"] != view["now_next"]["you_now"]
    task = view["tasks"][0]
    view = client.post(
        f"/journey/episodes/{eid}/tasks/{task['id']}/done",
        json={"by": "Nurse Meena (synthetic)", "via": "tap", "at_ms": 1_200_000},
    ).json()
    assert view["now_next"]["you_now"] == f"Nurse Meena finished Check wound dressing at {clock(1_200_000)}."
    asked = client.post(f"/journey/episodes/{eid}/ask/doctor", json={"text": "Is this normal?", "at_ms": 1_500_000}).json()
    assert asked["now_next"]["you_now"] == f"You sent a question to the doctor at {clock(1_500_000)}."


def test_patient_now_names_the_nurse_who_gave_a_dose(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    dose = {"kind": "dose", "text": "Paracetamol 1 g every 6 h", "name": "Paracetamol", "amount": "1 g", "every_h": 6}
    signed = client.post(
        f"/journey/episodes/{eid}/orders/sign", json={"items": [dose], "by": "Dr. A. Rao (synthetic)", "at_ms": 0}
    ).json()
    view = client.post(
        f"/journey/episodes/{eid}/orders/{signed['order_list'][0]['id']}/ack", json={"by": "Nurse Meena (synthetic)", "at_ms": 0}
    ).json()
    view = client.post(
        f"/journey/episodes/{eid}/tasks/{view['tasks'][0]['id']}/done",
        json={"by": "Nurse Meena (synthetic)", "via": "tap", "at_ms": 60_000},
    ).json()
    assert view["now_next"]["you_now"].startswith("Nurse Meena gave Paracetamol 1 g at ")
    assert view["now_next"]["now"].startswith("Nurse Meena (synthetic) finished ")
    assert not ADVICE.search(view["now_next"]["you_now"])


def test_seed_admission_reads_as_admitted_the_day_before_to_you(tmp_path):
    from app.journey.states import _latest_happening

    event = {
        "id": "x", "event_type": "patient.state", "ts_ms": 0, "supersedes_id": None,
        "payload": {"from": None, "to": "ward", "by": "Dr. A. Rao (synthetic)", "reason": "Admitted the day before (seed)"},
    }
    assert _latest_happening([event], you=True) == "You were admitted to the ward the day before."
    assert _latest_happening([event]) == "Dr. A. Rao (synthetic) admitted the patient to the ward the day before."


def test_patient_next_speaks_to_the_patient(tmp_path):
    client, eid = _new(tmp_path)
    nn = _view(client, eid)["now_next"]
    assert nn["you_next"] == "The doctor admits you or closes the visit."
    assert nn["next"] == "Doctor admits the patient or closes the visit."
    from app.journey.states import NEXT, NEXT_YOU

    assert NEXT_YOU.keys() == NEXT.keys()
    assert NEXT_YOU["home"] == "You are home. No further steps."
    assert not any(ADVICE.search(text) for text in NEXT_YOU.values())
    for text in NEXT_YOU.values():
        assert "the patient" not in text.lower()
