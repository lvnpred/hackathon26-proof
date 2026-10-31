"""What the models read becomes part of the action or note: swab camera count, monitor photo, correction (§2.5). Never a live call."""

from __future__ import annotations

from app.journey import evidence
from tests.test_flow_states import _new, _surgery, _to_theatre
from tests.test_flow_tasks import NURSE as TASK_NURSE
from tests.test_p3_tray import ADVICE, NURSE, _events, _upload, fake_frames, no_network  # noqa: F401  (fixtures)
from tests.test_regions import _checked, _obs_client, _proof


def _counted(client, eid):
    _to_theatre(client, eid)
    _surgery(client, eid, "began")
    client.post(f"/journey/episodes/{eid}/count", json={"step": "opened", "quantity": 15, "by": NURSE, "at_ms": 0})
    assert _upload(client, eid, name="swabs-closing.mp4", check="swabs").status_code == 200
    return client.get(f"/journey/episodes/{eid}").json()["count"]["camera"]


def _closing(client, eid, **extra):
    return client.post(f"/journey/episodes/{eid}/count", json={"step": "closing", "by": NURSE, **extra})


def test_swab_camera_count_prefills_the_count(tmp_path):
    client, eid = _new(tmp_path)
    camera = _counted(client, eid)
    assert camera["count"] == 14 and evidence.EVIDENCE_ID.match(camera["evidence_id"])


def test_swab_count_needs_the_pack(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    r = _upload(client, eid, name="swabs-closing.mp4", check="swabs")
    assert r.status_code == 409 and r.json()["detail"] == "Record the pack opened first."


def test_swab_count_is_theatre_only(tmp_path):
    client, eid = _new(tmp_path)
    assert _upload(client, eid, name="swabs-closing.mp4", check="swabs").status_code == 409


def test_swab_event_carries_count_and_opened(tmp_path):
    client, eid = _new(tmp_path)
    _counted(client, eid)
    p = [e for e in _events(client, eid) if e["event_type"] == "swabs.counted"][-1]["payload"]
    assert (p["count"], p["opened"], p["by"], p["clip"]) == (14, 15, NURSE, "swabs-closing.mp4")
    assert p["calls"][0]["model"] == "sam" and p["frame_ids"]


def test_camera_count_goes_once_a_closing_stands(tmp_path):
    client, eid = _new(tmp_path)
    ev = _counted(client, eid)["evidence_id"]
    assert _closing(client, eid, returned=14, evidence_id=ev, detail="One swab not found.").status_code == 200
    assert client.get(f"/journey/episodes/{eid}").json()["count"]["camera"] is None


def test_closing_by_camera_keeps_read_and_saved(tmp_path):
    client, eid = _new(tmp_path)
    ev = _counted(client, eid)["evidence_id"]
    _closing(client, eid, returned=15, evidence_id=ev, detail="Found under the drape.")
    p = [e for e in _events(client, eid) if e["event_type"] == "count.closing"][-1]["payload"]
    assert (p["via"], p["evidence_id"], p["read"], p["saved"]) == ("camera", ev, {"returned": 14}, {"returned": 15})
    cited = client.get(f"/journey/episodes/{eid}/evidence/{ev}").json()["cited_by"]
    assert [c["type"] for c in cited] == ["swabs.counted", "count.closing"] and cited[1]["read"] == {"returned": 14}
    assert cited[1]["saved"] == {"returned": 15}


def test_closing_by_camera_unchanged_has_no_correction(tmp_path):
    client, eid = _new(tmp_path)
    ev = _counted(client, eid)["evidence_id"]
    _closing(client, eid, returned=14, evidence_id=ev, detail="One swab not found.")
    p = [e for e in _events(client, eid) if e["event_type"] == "count.closing"][-1]["payload"]
    assert p["via"] == "camera" and "read" not in p and "saved" not in p


def test_closing_cites_an_unreadable_camera_count_without_read_or_saved(tmp_path, monkeypatch):
    from app.journey import count_api

    client, eid = _new(tmp_path)
    ev = _counted(client, eid)["evidence_id"]
    monkeypatch.setattr(count_api, "_camera_count", lambda events, evidence_id: {"payload": {"count": None, "evidence_id": evidence_id}})
    assert _closing(client, eid, returned=15, evidence_id=ev).status_code == 200
    p = [e for e in _events(client, eid) if e["event_type"] == "count.closing"][-1]["payload"]
    assert p["via"] == "camera" and p["evidence_id"] == ev and "read" not in p and "saved" not in p


def test_typed_closing_has_no_evidence(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    _surgery(client, eid, "began")
    client.post(f"/journey/episodes/{eid}/count", json={"step": "opened", "quantity": 15, "by": NURSE, "at_ms": 0})
    _closing(client, eid, returned=14, detail="One swab not found.")
    p = [e for e in _events(client, eid) if e["event_type"] == "count.closing"][-1]["payload"]
    assert "evidence_id" not in p and p.get("via", "typed") == "typed"


def test_closing_refuses_foreign_evidence(tmp_path):
    client, eid = _new(tmp_path)
    other = client.post("/morning/episodes", json={"label": "Synthetic demo, B"}).json()["id"]
    ev_other = _counted(client, other)["evidence_id"]
    _to_theatre(client, eid)
    assert _upload(client, eid).status_code == 200  # a tray check, before surgery begins
    ev_tray = [e for e in _events(client, eid) if e["event_type"] == "tray.checked"][-1]["payload"]["evidence_id"]
    _surgery(client, eid, "began")
    client.post(f"/journey/episodes/{eid}/count", json={"step": "opened", "quantity": 15, "by": NURSE, "at_ms": 0})
    for bad in (ev_other, ev_tray, "f" * 32, "../x"):
        r = _closing(client, eid, returned=14, evidence_id=bad)
        assert r.status_code == 422, bad
    assert [e for e in _events(client, eid) if e["event_type"] == "count.closing"] == []


def test_closing_refuses_the_evidence_of_an_earlier_stay(tmp_path):
    client, eid = _new(tmp_path)
    ev = _counted(client, eid)["evidence_id"]
    _surgery(client, eid, "ended")
    assert client.post(f"/journey/episodes/{eid}/state", json={"to": "ward", "by": NURSE, "at_ms": 0}).status_code in (200, 409)
    r = _closing(client, eid, returned=14, evidence_id=ev)
    assert r.status_code in (409, 422)


def _obs_done(client, eid, task, values):
    return client.post(f"/journey/episodes/{eid}/tasks/{task}/done",
                       json={"by": TASK_NURSE, "via": "tap", "at_ms": 0, "values": values, "proof_id": _photo_id(client, eid)})


def _photo_id(client, eid):
    return [e for e in _events(client, eid) if e["event_type"] == "proof.checked"][-1]["payload"]["photo_id"]


def test_obs_done_with_a_monitor_photo_keeps_evidence_and_correction(tmp_path):
    client, eid, ids = _obs_client(tmp_path)
    assert _proof(client, eid, ids["obs"], "monitor-88-54.png").status_code == 200
    ev = _checked(client, eid)["evidence_id"]
    assert _obs_done(client, eid, ids["obs"], {"sbp": 90, "dbp": 54, "hr": 112}).status_code == 200
    done = [e for e in _events(client, eid) if e["event_type"] == "task.done"][-1]["payload"]
    assert done["evidence_id"] == ev
    assert done["read"] == {"sbp": 88, "dbp": 54, "hr": 112} and done["saved"] == {"sbp": 90, "dbp": 54, "hr": 112}
    rec = [e for e in _events(client, eid) if e["event_type"] == "obs.recorded"][-1]["payload"]
    assert rec["evidence_id"] == ev and rec["source"] == "prepared" and rec["by"] == TASK_NURSE
    shown = [t for t in client.get(f"/journey/episodes/{eid}").json()["tasks"] if t["id"] == ids["obs"]][0]["done"][-1]
    assert shown["evidence_id"] == ev and shown["read"]["sbp"] == 88 and shown["saved"]["sbp"] == 90


def test_obs_done_with_the_values_read_has_no_correction(tmp_path):
    client, eid, ids = _obs_client(tmp_path)
    _proof(client, eid, ids["obs"], "monitor-88-54.png")
    assert _obs_done(client, eid, ids["obs"], {"sbp": 88, "dbp": 54, "hr": 112}).status_code == 200
    done = [e for e in _events(client, eid) if e["event_type"] == "task.done"][-1]["payload"]
    assert done["evidence_id"] and "read" not in done and "saved" not in done


def test_obs_done_without_a_photo_has_no_evidence(tmp_path):
    client, eid, ids = _obs_client(tmp_path)
    r = client.post(f"/journey/episodes/{eid}/tasks/{ids['obs']}/done",
                    json={"by": TASK_NURSE, "via": "tap", "at_ms": 0, "values": {"sbp": 120, "dbp": 80, "hr": 70}})
    assert r.status_code == 200
    rec = [e for e in _events(client, eid) if e["event_type"] == "obs.recorded"][-1]["payload"]
    assert "evidence_id" not in rec and "source" not in rec


def test_timeline_items_carry_evidence(tmp_path):
    client, eid = _new(tmp_path)
    _counted(client, eid)
    line = [t for t in client.get(f"/journey/episodes/{eid}").json()["timeline"] if t["type"] == "swabs.counted"][-1]
    assert line["evidence_id"] and line["calls"][0]["model"] == "sam" and not ADVICE.search(line["plain"])
    assert line["plain"] == "Swab camera count: 14 seen, 15 opened."


def test_a_corrected_closing_keeps_what_the_camera_read(tmp_path):
    client, eid = _new(tmp_path)
    ev = _counted(client, eid)["evidence_id"]
    first = _closing(client, eid, returned=14, evidence_id=ev, detail="One swab not found.")
    first_id = [e for e in _events(client, eid) if e["event_type"] == "count.closing"][-1]["id"]
    assert first.status_code == 200
    assert _closing(client, eid, returned=15, supersedes_id=first_id, detail="Found under the drape.").status_code == 200
    count = client.get(f"/journey/episodes/{eid}").json()["count"]
    assert (count["returned"], count["read"], count["saved"], count["closed_by"]) == (15, {"returned": 14}, {"returned": 15}, NURSE)
