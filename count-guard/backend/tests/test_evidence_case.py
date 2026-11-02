"""Task 15: the camera case behind a theatre stay, as frames, tracks and events (spec 9). Never another patient's."""

from __future__ import annotations

from tests.test_count_gate_paths import _begin_with_pack, _camera, _new_patient

RAO = {"name": "L. Rao (synthetic)", "age_sex": "40 F", "reason": "Lump"}


def _url(eid, tail=""):
    return f"/journey/episodes/{eid}/camera/evidence{tail}"


def test_evidence_lists_case_frames_and_tracks(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")
    r = client.get(_url(eid))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["case_id"] and body["frames"] and body["tracks"] and body["events"]
    frame = body["frames"][0]
    assert client.get(frame["url"]).status_code == 200
    track = body["tracks"][0]
    detail = client.get(_url(eid, f"/tracks/{track['track_id']}"))
    assert detail.status_code == 200 and isinstance(detail.json()["path"], list)
    assert client.get(_url(eid, "/tracks/nope")).status_code == 404


def test_evidence_never_crosses_patients(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")
    body = client.get(_url(eid)).json()
    oid = client.post("/journey/patients", json=RAO).json()["episode_id"]
    assert client.get(_url(oid)).json() == {"case_id": None, "frames": [], "tracks": [], "events": []}
    assert client.get(_url(oid, f"/frames/{body['frames'][0]['id']}")).status_code == 404
    assert client.get(_url(oid, f"/tracks/{body['tracks'][0]['track_id']}")).status_code == 404
    assert client.get(_url("missing")).status_code == 404
