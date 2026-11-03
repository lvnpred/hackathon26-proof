"""Clarity Task 5, fix 1: a person's save carries what the AI proposed, so the chart can say "Changed by {name}"."""

from __future__ import annotations

from tests.test_count_gate_paths import NURSE, _events, _post_json, _theatre_patient
from tests.test_discharge_draft import DOCTOR, _draft, _ok, _stay, _url
from tests.test_flow_tasks import OBS, _done, _ward_with_tasks

HEARD_5 = "lignocaine two percent, five ml, local infiltration"
SAID_8 = "lignocaine two percent, eight ml, local infiltration"


def _act(view, kind):
    return [a for a in view["acts"] if a["type"] == kind][-1]


def _obs_task(tmp_path):
    client, eid, _, view = _ward_with_tasks(tmp_path, [OBS])
    return client, eid, view["tasks"][0]["id"]


def test_edited_heard_obs_saved_carries_the_proposal_beside_the_saved_values(tmp_path):
    client, eid, tid = _obs_task(tmp_path)
    body = {"via": "voice", "transcript": "BP one twenty over eighty, pulse seventy", "heard_by": "prepared", "edited": True,
            "heard_text": "BP one eighteen over eighty, pulse seventy", "values": {"sbp": 120, "dbp": 80, "hr": 70},
            "proposed_values": {"sbp": 118, "dbp": 80, "hr": 70}}
    r = _done(client, eid, tid, **body)
    assert r.status_code == 200, r.text
    act = _act(r.json(), "task.done")
    assert act["proposed"] == {"values": {"sbp": 118, "dbp": 80, "hr": 70}, "said": "BP one eighteen over eighty, pulse seventy"}
    assert act["value"] == {"values": {"sbp": 120, "dbp": 80, "hr": 70}, "said": "BP one twenty over eighty, pulse seventy"}
    done = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "task.done"][-1]["payload"]
    assert done["via"] == "voice" and done["heard_by"] == "prepared" and done["edited"] is True


def test_unedited_heard_obs_saved_as_proposed_has_equal_proposal_and_value(tmp_path):
    client, eid, tid = _obs_task(tmp_path)
    values = {"sbp": 120, "dbp": 80, "hr": 70}
    r = _done(client, eid, tid, via="voice", transcript="BP one twenty over eighty", heard_by="prepared", values=values,
              proposed_values=values)
    act = _act(r.json(), "task.done")
    assert act["proposed"] == act["value"]


def test_proposed_values_are_checked_at_the_boundary(tmp_path):
    client, eid, tid = _obs_task(tmp_path)
    bad = _done(client, eid, tid, via="voice", transcript="x", heard_by="prepared", values={"sbp": 120, "dbp": 80, "hr": 70},
                proposed_values={"pulse": 70})
    assert bad.status_code == 422


def test_edited_discharge_summary_carries_the_drafted_summary(tmp_path):
    client = _client_for(tmp_path)
    eid = _stay(client)
    draft = _ok(_draft(client, eid)).json()["drafts"]["discharge"]
    signed = {"summary": "Recovered well. Wound check day 7.", "by": DOCTOR, "draft_id": draft["id"], "proposed_summary": "Recovered well."}
    act = _act(_ok(client.post(_url(eid, "discharge/sign"), json=signed)).json(), "discharge.signed")
    assert (act["proposed"], act["value"]) == ("Recovered well.", "Recovered well. Wound check day 7.")


def _client_for(tmp_path):
    from tests.test_care_demo import _client

    return _client(tmp_path)


def _hear(client, eid, text, **extra):
    r = client.post(f"/journey/episodes/{eid}/theatre/drug", data={"by": NURSE, "text": text, **extra})
    assert r.status_code == 200, r.text
    return r


def test_edited_heard_drug_confirmed_carries_the_heard_dose(tmp_path):
    client, eid = _theatre_patient(tmp_path)
    _hear(client, eid, SAID_8, heard_by="prepared", heard_text=HEARD_5)
    [draft] = [e for e in _events(client, eid) if e["event_type"] == "druglog.parsed"]
    assert draft["payload"]["heard_text"] == HEARD_5 and draft["payload"]["heard_by"] == "prepared"
    act = _act(_post_json(client, eid, f"/theatre/drug/{draft['id']}/confirm", {"by": NURSE}).json(), "drug.given")
    assert act["proposed"]["amount"] == 5 and act["value"]["amount"] == 8
    assert (act["proposed"]["said"], act["value"]["said"]) == (HEARD_5, SAID_8)


def test_unedited_heard_drug_and_pack_confirmed_have_equal_proposal_and_value(tmp_path):
    client, eid = _theatre_patient(tmp_path)
    _hear(client, eid, HEARD_5, heard_by="prepared", heard_text=HEARD_5)  # the same text is not an edit
    _hear(client, eid, "opening five swabs", heard_by="prepared")
    events = _events(client, eid)
    [drug] = [e for e in events if e["event_type"] == "druglog.parsed"]
    [pack] = [e for e in events if e["event_type"] == "count.pack_heard"]
    assert "heard_text" not in drug["payload"]
    _post_json(client, eid, f"/theatre/drug/{drug['id']}/confirm", {"by": NURSE})
    view = _post_json(client, eid, f"/theatre/pack/{pack['id']}/confirm", {"by": NURSE}).json()
    for kind in ("drug.given", "count.pack_opened"):
        act = _act(view, kind)
        assert act["proposed"] == act["value"], kind


def test_camera_ack_carries_its_reason():
    from app.journey.acts import person_acts

    ev = lambda eid, reason: {"id": eid, "event_type": "camera.ack", "ts_ms": 1, "episode_id": "e1", "supersedes_id": None,
                              "payload": {"advice_id": eid, "by": NURSE, "reason": reason}}
    assert [a["reason"] for a in person_acts([ev("a1", ""), ev("a2", "Counted by hand")])] == ["", "Counted by hand"]


def test_proposed_values_out_of_range_or_not_finite_are_refused(tmp_path):
    client, eid, tid = _obs_task(tmp_path)
    values = {"sbp": 120, "dbp": 80, "hr": 70}
    for bad in ({"sbp": float("nan")}, {"temp": float("inf")}, {"sbp": 10_000}, {"hr": -5}, {"temp": 99.0}):
        r = client.post(f"/journey/episodes/{eid}/tasks/{tid}/done",
                        content=__import__("json").dumps({"by": NURSE, "via": "voice", "transcript": "x", "heard_by": "prepared",
                                                         "values": values, "proposed_values": bad, "at_ms": 0}),
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 422, (bad, r.text)
    ok = _done(client, eid, tid, via="voice", transcript="x", heard_by="prepared", values=values,
               proposed_values={"sbp": 118, "temp": 37.2})
    assert ok.status_code == 200, ok.text
    done = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "task.done"][-1]["payload"]
    assert done["proposed_values"] == {"sbp": 118, "temp": 37.2}


def test_a_tapped_or_typed_save_keeps_no_proposal(tmp_path):
    client, eid, tid = _obs_task(tmp_path)
    r = _done(client, eid, tid, via="text", transcript="typed", heard_by="prepared", values={"sbp": 120, "dbp": 80, "hr": 70},
              proposed_values={"sbp": 118}, edited=True, heard_text="heard")
    assert r.status_code == 200, r.text
    done = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "task.done"][-1]["payload"]
    assert not {"proposed_values", "edited", "heard_text"} & set(done)
