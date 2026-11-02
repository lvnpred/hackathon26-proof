"""Detections kept as an evidence sidecar: frames_from, the sidecar written by a check, the evidence GET."""

from __future__ import annotations

from app.journey import evidence, live, video
from tests.test_flow_states import _new, _to_theatre
from tests.test_p3_tray import _events, _upload, fake_frames  # noqa: F401  (fixture)


def _r(f, oid, label="needle holder", score=0.9, x=0.1):
    return {"frame_index": f, "object_id": oid, "label": label, "bbox": [x, 0.2, 0.1, 0.1], "score": score}


def test_frames_from_marks_low_scores_not_kept():
    frames = video.frames_from([_r(0, "1"), _r(0, "2", score=0.3)], fps=2, min_score=0.45)
    assert frames == [{"t": 0.0, "index": 0, "objects": [
        {"id": "1", "label": "needle holder", "bbox": [0.1, 0.2, 0.1, 0.1], "score": 0.9, "kept": True},
        {"id": "2", "label": "needle holder", "bbox": [0.1, 0.2, 0.1, 0.1], "score": 0.3, "kept": False}]}]


def test_frames_from_caps_at_120_and_keeps_the_best_frame():
    recs = [_r(f, "1") for f in range(300)] + [_r(251, "2")]
    frames = video.frames_from(recs, fps=2, min_score=0.45)
    assert len(frames) <= 120 and 125.5 in [f["t"] for f in frames]
    assert [f["index"] for f in frames] == sorted(f["index"] for f in frames)


def test_frames_from_empty_and_all_low():
    assert video.frames_from([], fps=2, min_score=0.45) == []
    frames = video.frames_from([_r(0, "1", score=0.2)], fps=2, min_score=0.45)
    assert [o["kept"] for o in frames[0]["objects"]] == [False]
    assert video.summarize(video.records_of(frames), 2, 0.45, ["needle holder"]) == {"needle holder": {"count": 0, "at_s": None}}


def test_frames_from_photos_have_no_time():
    assert video.frames_from([_r(1, "1")], fps=1, min_score=0.45, photos=True)[0]["t"] is None


def test_frames_from_drops_unlabelled_and_keeps_none_scores():
    frames = video.frames_from([_r(0, "1", label=None), _r(0, "2", score=None)], fps=2, min_score=0.45)
    assert [(o["id"], o["kept"]) for o in frames[0]["objects"]] == [("2", True)]


def test_records_of_inverts_frames_from():
    recs = [_r(0, "1"), _r(3, "2", score=0.3)]
    assert video.records_of(video.frames_from(recs, fps=2, min_score=0.45)) == recs


def test_tray_check_writes_a_sidecar_the_get_returns(tmp_path, fake_frames):
    client, eid = _new(tmp_path); _to_theatre(client, eid)
    assert _upload(client, eid).status_code == 200
    payload = [e for e in _events(client, eid) if e["event_type"] == "tray.checked"][-1]["payload"]
    body = client.get(f"/journey/episodes/{eid}/evidence/{payload['evidence_id']}").json()
    assert body["kind"] == "tray" and body["handmade"] is True and body["min_score"] == 0.45
    assert body["media"] == "video" and body["fps"] == 2
    assert [i["url"] for i in body["images"]] == [f"/journey/episodes/{eid}/photos/{p}" for p in payload["frame_ids"]]
    assert [c["type"] for c in body["cited_by"]] == ["tray.checked"]
    assert body["frames"] and {"concept", "planned"} == set(body["expected"][0])
    assert body["calls"] == payload["calls"]
    check = client.get(f"/journey/episodes/{eid}").json()["video_checks"][-1]
    assert check["evidence_id"] == payload["evidence_id"]


def test_evidence_get_404s(tmp_path, fake_frames):
    client, eid = _new(tmp_path); _to_theatre(client, eid)
    _upload(client, eid)
    good = [e for e in _events(client, eid) if e["event_type"] == "tray.checked"][-1]["payload"]["evidence_id"]
    other = client.post("/journey/episodes", json={"label": "Synthetic demo, B"}).json()["id"]
    assert client.get(f"/journey/episodes/{eid}/evidence/{good}").status_code == 200
    for path in (f"{eid}/evidence/..%2Fx", f"{eid}/evidence/{'0' * 32}", f"{other}/evidence/{good}",
                 f"{eid}/evidence/{good.upper()}", f"{eid}/evidence/{good[:31]}", f"{eid}/evidence/{good}0", f"{eid}/evidence/{good}%0A"):
        assert client.get(f"/journey/episodes/{path}").status_code == 404, path


def test_evidence_get_404s_when_the_file_is_missing(tmp_path, fake_frames):
    client, eid = _new(tmp_path); _to_theatre(client, eid)
    _upload(client, eid)
    good = [e for e in _events(client, eid) if e["event_type"] == "tray.checked"][-1]["payload"]["evidence_id"]
    next((tmp_path).rglob(f"{good}.evidence.json")).unlink()
    assert client.get(f"/journey/episodes/{eid}/evidence/{good}").status_code == 404


def test_old_check_without_sidecar_still_renders(tmp_path):
    client, eid = _new(tmp_path); _to_theatre(client, eid)
    client.app.state.morning.append(eid, "tray.checked", {"rows": [], "missing": [], "match": "none", "why": "x", "source": "none", "frame_ids": [], "by": "N"}, ts_ms=1)
    check = client.get(f"/journey/episodes/{eid}").json()["video_checks"][-1]
    assert check["evidence_id"] is None and check["rows"] == []


def test_no_fixture_no_sidecar(tmp_path, fake_frames):
    client, eid = _new(tmp_path); _to_theatre(client, eid)
    assert _upload(client, eid, name="unknown.mp4").status_code == 200
    payload = [e for e in _events(client, eid) if e["event_type"] == "tray.checked"][-1]["payload"]
    assert "evidence_id" not in payload


def test_save_caps_raw_and_load_refuses_a_bad_id(tmp_path):
    client, eid = _new(tmp_path)
    settings = client.app.state.settings
    big = {"kind": "tray", "raw": {"spark": "x" * 200_001}}
    small = {"kind": "tray", "raw": {"spark": "ok"}}
    big_id, small_id = evidence.save(settings, eid, big), evidence.save(settings, eid, small)
    assert evidence.EVIDENCE_ID.fullmatch(big_id) and big_id != small_id
    assert not evidence.EVIDENCE_ID.fullmatch(big_id + "\n")
    assert evidence.load(settings, eid, big_id)["raw"] == {"note": "Raw output over 200 KB; not kept."}
    assert evidence.load(settings, eid, small_id)["raw"] == {"spark": "ok"}
    assert evidence.load(settings, eid, small_id)["id"] == small_id
    for bad in ("../x", "0" * 32, small_id.upper(), ""):
        assert evidence.load(settings, eid, bad) is None


def test_held_by_is_oldest_first():
    events = [{"id": "a", "payload": {"evidence_id": "x"}}, {"id": "b", "payload": {}}, {"id": "c", "payload": {"evidence_id": "x"}}]
    assert [e["id"] for e in evidence.held_by(events, "x")] == ["a", "c"]


def test_live_clip_keeps_boxes_and_raw_without_mask_tokens(tmp_path, monkeypatch):
    from app.adapters.sam import SamAdapter
    from tests.test_p3_video import _fake_media, _keyed

    _fake_media(monkeypatch)
    rec = {**_r(1, "1"), "frame_w": 640, "frame_h": 360, "mask_token": "SECRET-TOKEN"}
    monkeypatch.setattr(SamAdapter, "segment_video", lambda self, path, concepts: [rec])
    got = live.segment_clip(_keyed(tmp_path), tmp_path / "c.mp4", "x.mp4", ["needle holder"])
    assert got["frames"][0]["t"] == 0.5 and got["handmade"] is False
    assert got["raw"] == {"sam": [{k: v for k, v in rec.items() if k != "mask_token"}]}
    assert "SECRET-TOKEN" not in str(got["raw"])
    assert live.segment_clip(_keyed(tmp_path), tmp_path / "c.mp4", "unknown.mp4", ["x"], live_ok=False)["frames"] is None
