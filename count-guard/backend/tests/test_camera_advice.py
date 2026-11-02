"""The theatre swab camera (spec §6.4, §6.5): a case linked to the stay, rules R1–R6 as advice, the missing-swab frame."""

from __future__ import annotations

import dataclasses
import re

import pytest

from app.journey import camera_api, switches
from app.journey.stories import CAMERA_BY
from app.media_pipeline import SamCallFailed
from tests.test_care_demo import _client
from tests.test_count_gate_paths import NURSE, _begin_with_pack, _camera, _events, _new_patient, _post_json

RULE_ID = re.compile(r"\bR[1-6]\b")
CLIP = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def _kinds(client, eid, kind):
    return [e for e in _events(client, eid) if e["event_type"] == kind]


def test_camera_case_created_and_linked(tmp_path):
    client, eid = _new_patient(tmp_path)
    r = _post_json(client, eid, "/camera/case", {"by": NURSE})
    assert r.status_code == 200, r.text
    case_id = r.json()["camera"]["case_id"]
    case = client.app.state.store.get_case(case_id)
    assert case is not None
    assert set(client.app.state.store.zones(case_id)) == {"tray", "field", "bucket"}
    linked = _kinds(client, eid, "camera.linked")
    assert [e["payload"]["case_id"] for e in linked] == [case_id]
    assert linked[0]["payload"]["by"] == CAMERA_BY and linked[0]["payload"]["started_by"] == NURSE
    again = _post_json(client, eid, "/camera/case", {"by": NURSE}).json()
    assert again["camera"]["case_id"] == case_id and len(_kinds(client, eid, "camera.linked")) == 1


def test_camera_case_links_an_existing_case(tmp_path):
    client, eid = _new_patient(tmp_path)
    case_id = client.post("/cases", json={"label": "Theatre 2", "item_types": ["lap sponge"]}).json()["id"]
    r = _post_json(client, eid, "/camera/case", {"by": NURSE, "case_id": case_id})
    assert r.status_code == 200 and r.json()["camera"]["case_id"] == case_id
    assert _post_json(client, eid, "/camera/case", {"by": NURSE, "case_id": "nope"}).status_code == 404


def test_camera_only_in_theatre(tmp_path):
    client = _new_patient(tmp_path)[0]
    r = client.post("/journey/patients", json={"name": "L. Rao (synthetic)", "age_sex": "40 F", "reason": "Lump"})
    eid = r.json()["episode_id"]  # still in clinic
    assert _post_json(client, eid, "/camera/case", {"by": NURSE}).status_code == 409
    r = client.post(f"/journey/episodes/{eid}/camera/clip", data={"scenario": "clip2", "by": NURSE})
    assert r.status_code == 409


def test_clip_needs_a_linked_case(tmp_path):
    client, eid = _new_patient(tmp_path)
    r = client.post(f"/journey/episodes/{eid}/camera/clip", data={"scenario": "clip2", "by": NURSE})
    assert r.status_code == 409
    _post_json(client, eid, "/camera/case", {"by": NURSE})
    assert client.post(f"/journey/episodes/{eid}/camera/clip", data={"scenario": "nope", "by": NURSE}).status_code == 400


def test_rules_produce_advice_rows(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    body = _camera(client, eid, "clip4")  # five gauze swabs on the tray, nobody said they were opened
    rows = body["camera"]["advice"]
    r4 = [row for row in rows if row["rule"] == "R4"]
    assert len(r4) == 1 and r4[0]["item_type"] == "gauze swab"
    assert body["camera"]["source"] == "prepared"
    for row in rows:
        assert row["text"] and not RULE_ID.search(row["text"]) and "_" not in row["text"]
    written = _kinds(client, eid, "camera.advice")
    assert written and all(e["payload"]["by"] == CAMERA_BY for e in written)
    _camera(client, eid, "clip4")  # the same finding is not advised twice
    assert len(_kinds(client, eid, "camera.advice")) == len(written)


def test_missing_swab_frame_is_returned(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    body = _camera(client, eid, "clip2")
    r3 = next(row for row in body["camera"]["advice"] if row["rule"] == "R3")
    assert r3["frame_id"] and r3["frame_url"]
    for item in (r3["item"], r3["item_type"]):
        r = client.get(f"/journey/episodes/{eid}/camera/frame", params={"item": item})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/jpeg" and r.content[:2] == b"\xff\xd8"
    assert client.get(f"/journey/episodes/{eid}/camera/frame", params={"item": "nothing"}).status_code == 404


def test_frame_never_crosses_patients(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")
    other = client.post("/journey/patients", json={"name": "L. Rao (synthetic)", "age_sex": "40 F", "reason": "Lump"})
    oid = other.json()["episode_id"]
    assert client.get(f"/journey/episodes/{oid}/camera/frame", params={"item": "lap sponge"}).status_code == 404


def test_advice_ack_is_recorded_and_never_needed(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    advice = _camera(client, eid, "clip2")["camera"]["advice"][0]
    r = _post_json(client, eid, f"/camera/advice/{advice['id']}/ack", {"by": NURSE, "reason": "Found under the drape"})
    assert r.status_code == 200, r.text
    row = next(a for a in r.json()["camera"]["advice"] if a["id"] == advice["id"])
    assert row["acked"] == {"by": NURSE, "reason": "Found under the drape"}
    acks = _kinds(client, eid, "camera.ack")
    assert len(acks) == 1 and acks[0]["payload"]["advice_id"] == advice["id"]
    assert _post_json(client, eid, f"/camera/advice/{advice['id']}/ack", {"by": NURSE}).status_code == 200
    assert len(_kinds(client, eid, "camera.ack")) == 1
    assert _post_json(client, eid, "/camera/advice/nope/ack", {"by": NURSE}).status_code == 404
    assert _post_json(client, eid, f"/camera/advice/{advice['id']}/ack", {"by": CAMERA_BY}).status_code == 422


def test_manual_count_route_in_care(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    r = _post_json(client, eid, "/camera/manual", {"track_id": "sponge-7", "by": NURSE})
    assert r.status_code == 200, r.text
    out = _kinds(client, eid, "count.item_out")
    assert [e["payload"] for e in out] == [{"track_id": "sponge-7", "frame_id": None, "source": "manual", "by": NURSE}]
    assert _post_json(client, eid, "/surgery", {"step": "ended", "by": NURSE}).status_code == 409  # not a closing


def test_camera_live_socket_streams_detections(tmp_path):
    client, eid = _new_patient(tmp_path)
    _post_json(client, eid, "/camera/case", {"by": NURSE})
    with client.websocket_connect(f"/journey/episodes/{eid}/camera/live") as socket:
        ready = socket.receive_json()
        assert ready["type"] == "ready" and ready["perception"] == "scripted"
        detections = [{"track_id": "g1", "label": "gauze swab", "bbox": [0.06, 0.2, 0.05, 0.05], "score": 0.9}]
        socket.send_json({"type": "detections", "detections": detections, "media_ts_ms": 2000})
        state = socket.receive_json()
        assert state["type"] == "state"
        assert any(row["item_type"] == "gauze swab" for row in state["ledger"])
        socket.send_json({"type": "detections", "detections": detections, "media_ts_ms": 60000, "finalize": True})
        state = socket.receive_json()
        assert any(row["rule"] == "R4" for row in state["advice"])
    assert _kinds(client, eid, "camera.advice")


def test_live_socket_refused_without_a_linked_case(tmp_path):
    from starlette.websockets import WebSocketDisconnect

    client, eid = _new_patient(tmp_path)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/journey/episodes/{eid}/camera/live") as socket:
            socket.receive_json()


def _keyed_client(tmp_path):
    """A client whose settings carry a (fake) model key, so the swab switch is live. No call leaves the machine."""
    client = _client(tmp_path)
    settings = dataclasses.replace(client.app.state.settings, meta_api_key="test-key")
    client.app.state.settings = client.app.state.engine.settings = settings
    return client


def test_failed_sam_falls_back_to_the_fixed_prepared_result(tmp_path, monkeypatch):
    from tests.test_count_gate_paths import _to_theatre

    client = _keyed_client(tmp_path)
    eid = client.post("/journey/patients", json={"name": "K. Nair (synthetic)", "age_sex": "35 M", "reason": "x"}).json()["episode_id"]
    _to_theatre(client, eid, from_clinic=True)
    assert switches.is_live(client.app.state.settings, "swabs")

    def fail(*args, **kwargs):
        raise SamCallFailed("SAM 3.1 call failed: down")

    monkeypatch.setattr(camera_api, "run_recorded_video", fail)
    _post_json(client, eid, "/camera/case", {"by": NURSE})
    files = {"file": ("swabs-opening-twenty.mp4", CLIP, "video/mp4")}  # the file name never picks the fixture
    r = client.post(f"/journey/episodes/{eid}/camera/clip", data={"by": NURSE}, files=files)
    assert r.status_code == 200, r.text
    camera = r.json()["camera"]
    assert camera["source"] == "prepared" and camera["fixture"] == switches.PREPARED_BY_CHECK["swabs"]
    seen = {row["item_type"]: row for row in camera["ledger"]}
    assert seen["gauze swab"]["tray"] + seen["gauze swab"]["bucket"] + seen["gauze swab"].get("field", 0) >= 1


def test_without_a_key_a_clip_uses_the_prepared_result(tmp_path):
    client, eid = _new_patient(tmp_path)
    _post_json(client, eid, "/camera/case", {"by": NURSE})
    files = {"file": ("swabs-opening-twenty.mp4", CLIP, "video/mp4")}
    r = client.post(f"/journey/episodes/{eid}/camera/clip", data={"by": NURSE}, files=files)
    assert r.status_code == 200, r.text
    assert r.json()["camera"]["source"] == "prepared"
    assert r.json()["camera"]["fixture"] == switches.PREPARED_BY_CHECK["swabs"]


def test_morning_routes_still_call_the_moved_bodies(tmp_path):
    client = _client(tmp_path)
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    r = client.post(f"/morning/episodes/{eid}/count/manual", json={"track_id": "swab-3"})
    assert r.status_code == 200, r.text
    assert [e["payload"] for e in _kinds(client, eid, "count.item_out")] == [
        {"track_id": "swab-3", "frame_id": None, "source": "manual"}
    ]
    for t in range(3):
        r = client.post(f"/morning/episodes/{eid}/count/frame",
                        json={"track_id": "swab-1", "zone": "bucket", "frame_id": f"f{t}", "t_ms": t * 100})
        assert r.status_code == 200, r.text
    assert r.json()["out"] == ["swab-1"] and len(r.json()["emitted"]) == 1
