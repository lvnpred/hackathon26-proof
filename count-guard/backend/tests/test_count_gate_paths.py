"""A6 (spec §6.5, §11, U10): the camera, the rules and the AI never close the swab count. All through HTTP.

Patients come from each way a patient is made: a Doctor Dictation push (intake), Sync, and New patient.
"""

from __future__ import annotations

from app.journey import states, sync
from app.journey.stories import CAMERA_BY
from app.ops.policy import AI_BY
from tests.test_care_demo import _client
from tests.test_flow_states import ADMIT_CHECKS
from tests.test_intake import _payload, _post
from tests.test_sync import FakeGet

NURSE = "Nurse Asha (synthetic)"
DOCTOR = "Dr. A. Rao (synthetic)"
PROCEDURE = next(iter(states.PROCEDURES))
SAVE_FIRST = "Save the swab count first."


def _move(client, eid, to, **extra):
    r = client.post(f"/journey/episodes/{eid}/state", json={"to": to, "by": DOCTOR, **extra})
    assert r.status_code == 200, r.text


def _to_theatre(client, eid, *, from_clinic=False):
    if from_clinic:
        _move(client, eid, "admitting", reason="Hernia repair")
    _move(client, eid, "ward", checklist=ADMIT_CHECKS)
    _move(client, eid, "theatre", procedure=PROCEDURE)


def _intake_patient(tmp_path):
    client = _client(tmp_path)
    r = _post(client)
    assert r.status_code == 201, r.text
    eid = r.json()["episode_id"]
    _to_theatre(client, eid)
    return client, eid


def _sync_patient(tmp_path, monkeypatch):
    client = _client(tmp_path)
    monkeypatch.setattr(sync.httpx, "get", FakeGet([_payload()]))
    r = client.post("/journey/sync", json={})
    assert r.status_code == 200 and r.json()["new"] == 1, r.text
    eid = client.get("/journey/ward").json()["patients"][0]["id"]
    _to_theatre(client, eid)
    return client, eid


def _new_patient(tmp_path):
    client = _client(tmp_path)
    r = client.post("/journey/patients", json={"name": "K. Nair (synthetic)", "age_sex": "35 M", "reason": "Lump"})
    assert r.status_code == 201, r.text
    eid = r.json()["episode_id"]
    _to_theatre(client, eid, from_clinic=True)
    return client, eid


def _post_json(client, eid, path, body):
    return client.post(f"/journey/episodes/{eid}{path}", json=body)


def _begin_with_pack(client, eid, quantity=10):
    assert _post_json(client, eid, "/surgery", {"step": "began", "by": NURSE}).status_code == 200
    assert _post_json(client, eid, "/count", {"step": "opened", "quantity": quantity, "by": NURSE}).status_code == 200


def _camera(client, eid, scenario):
    assert _post_json(client, eid, "/camera/case", {"by": NURSE}).status_code == 200
    r = client.post(f"/journey/episodes/{eid}/camera/clip", data={"scenario": scenario, "by": NURSE})
    assert r.status_code == 200, r.text
    return r.json()


def _end(client, eid):
    return _post_json(client, eid, "/surgery", {"step": "ended", "by": NURSE})


def _events(client, eid):
    return client.app.state.morning.events(eid)


def _ai_closing_refused_and_ignored(client, eid):
    """An AI or camera `by` on the count route is refused; one written past the route is ignored by the gate."""
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")
    for by in (AI_BY, CAMERA_BY):
        r = _post_json(client, eid, "/count", {"step": "closing", "returned": 10, "by": by})
        assert r.status_code == 422, r.text
    for by in (AI_BY, CAMERA_BY):
        client.app.state.morning.append(
            eid, "count.closing", {"opened": 10, "returned": 10, "unaccounted": 0, "detail": "", "by": by}, ts_ms=10**9
        )
    assert states.count_gate(_events(client, eid)) == "none"
    r = _end(client, eid)
    assert r.status_code == 409 and r.json()["detail"] == SAVE_FIRST


def test_camera_and_rules_never_close_the_count(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    body = _camera(client, eid, "clip2")  # ten opened, nine back, one left on the field
    assert any(row["rule"] == "R3" for row in body["camera"]["advice"])
    events = _events(client, eid)
    assert states.count_gate(events) == "none"
    assert not [e for e in events if e["event_type"] == "count.closing"]
    assert _end(client, eid).status_code == 409


def test_unacknowledged_advice_with_valid_manual_closing_ends_surgery(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    body = _camera(client, eid, "clip2")
    assert body["camera"]["advice"] and not any(row["acked"] for row in body["camera"]["advice"])
    assert _post_json(client, eid, "/count", {"step": "closing", "returned": 10, "by": NURSE}).status_code == 200
    assert _end(client, eid).status_code == 200  # U10: advice never blocks; acknowledgement is never read


def test_ai_written_closing_never_ok_via_intake_patient(tmp_path):
    client, eid = _intake_patient(tmp_path)
    _ai_closing_refused_and_ignored(client, eid)


def test_ai_written_closing_never_ok_via_sync_patient(tmp_path, monkeypatch):
    client, eid = _sync_patient(tmp_path, monkeypatch)
    _ai_closing_refused_and_ignored(client, eid)


def test_ai_written_closing_never_ok_via_new_patient(tmp_path):
    client, eid = _new_patient(tmp_path)
    _ai_closing_refused_and_ignored(client, eid)


def test_short_manual_count_still_409_with_camera_agreeing(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    body = _camera(client, eid, "clip1")  # the camera sees all ten back
    assert not any(row["rule"] in ("R1", "R3") for row in body["camera"]["advice"])
    short = _post_json(client, eid, "/count", {"step": "closing", "returned": 9, "by": NURSE})
    assert short.status_code == 422  # a short count needs what the team did
    r = _end(client, eid)
    assert r.status_code == 409 and r.json()["detail"] == SAVE_FIRST


def test_camera_never_writes_pack_opened(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    before = [e["id"] for e in _events(client, eid) if e["event_type"].startswith("count.")]
    _camera(client, eid, "demo")
    with client.websocket_connect(f"/journey/episodes/{eid}/camera/live") as socket:
        socket.receive_json()
        socket.send_json({"type": "utterance", "text": "Adding 5 gauze swabs", "media_ts_ms": 1000})
        socket.receive_json()
    after = [e for e in _events(client, eid) if e["event_type"].startswith("count.")]
    assert [e["id"] for e in after] == before
    camera = [e for e in _events(client, eid) if e["event_type"].startswith("camera.") and e["event_type"] != "camera.ack"]
    assert camera and all(e["payload"]["by"] == CAMERA_BY for e in camera)


def test_morning_count_routes_refuse_a_care_theatre_stay(tmp_path):
    """The older morning routes write a pack and a closing with no `by`; on a care stay they would move the count."""
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    assert _post_json(client, eid, "/count", {"step": "closing", "returned": 10, "by": NURSE}).status_code == 200
    case_id = client.post("/cases", json={"label": "Old camera", "item_types": ["lap sponge"]}).json()["id"]
    before = _events(client, eid)
    opened, gate = states.stay_opened(before), states.count_gate(before)
    assert (opened, gate) == (10, "ok")
    base = f"/morning/episodes/{eid}"
    for r in (
        client.post(f"{base}/count/from-case", json={"case_id": case_id}),
        client.post(f"{base}/count/replay"),
        client.post(f"{base}/hear", json={"text": "opening twenty swabs"}),
        client.post(f"{base}/play"),
    ):
        assert r.status_code == 409 and r.json() == {"error": "use the theatre count panel"}, r.text
    after = _events(client, eid)
    assert len(after) == len(before)
    assert (states.stay_opened(after), states.count_gate(after)) == (opened, gate)
    assert _end(client, eid).status_code == 200


def test_ai_label_variants_never_pass_as_a_person(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    variants = ["Count Guard AI ", " count guard ai", "COUNT  GUARD AI", "ai (on behalf of Ward 3)", "  AI (ON BEHALF OF x)"]
    for by in variants:
        r = _post_json(client, eid, "/count", {"step": "closing", "returned": 10, "by": by})
        assert r.status_code == 422, (by, r.text)
        client.app.state.morning.append(
            eid, "count.closing", {"opened": 10, "returned": 10, "unaccounted": 0, "detail": "", "by": by}, ts_ms=10**9
        )
        assert states.count_gate(_events(client, eid)) == "none", by
    assert _end(client, eid).status_code == 409
