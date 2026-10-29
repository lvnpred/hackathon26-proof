"""P3 tray: the plan at Send to theatre, and the tray check by video. Never a live call."""

from __future__ import annotations

import re
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import media_pipeline
from app.adapters.sam import SamAdapter
from app.journey import live, video, video_api
from app.journey.procedures import tray_plan
from app.main import create_app
from tests.test_p3_video import _keyed
from tests.test_flow_states import _move, _new, _surgery, _to_theatre, _to_ward, _view

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 40
JPEG = b"\xff\xd8\xff" + b"jpg"
NURSE = "Nurse Asha (synthetic)"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


@pytest.fixture(autouse=True)
def fake_frames(monkeypatch):
    def cut(clip, times, out_dir):
        files = []
        for i, _ in enumerate(times):
            target = out_dir / f"frame{i}.jpg"
            target.write_bytes(JPEG)
            files.append(target)
        return files

    monkeypatch.setattr(video_api, "cut_frames", cut)


def _upload(client, eid, name="tray-hernia.mp4", kind="video/mp4", data=MP4, **form):
    fields = {"check": "tray", "by": NURSE, "at_ms": "0", **form}
    return client.post(f"/journey/episodes/{eid}/video", files={"file": (name, data, kind)}, data=fields)


def _events(client, eid):
    return client.app.state.morning.events(eid)


def test_send_to_theatre_writes_tray_plan(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    planned = _view(client, eid)["tray"]["planned"]
    plan = tray_plan("hernia-repair")
    assert planned["template"] == "hernia-repair"
    assert planned["swab_total"] == plan["swab_total"]
    assert planned["by"] == "Dr. A. Rao (synthetic)"
    assert [e["event_type"] for e in _events(client, eid)].count("tray.planned") == 1
    assert _view(client, eid)["tray_templates"]["hernia-repair"]["swab_total"] == plan["swab_total"]


def test_tray_check_flags_missing_needle_holder(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    r = _upload(client, eid)
    assert r.status_code == 200, r.text
    view = r.json()
    latest = view["tray"]["latest"]
    assert latest["missing"] == ["needle holder"]
    assert latest["match"] == "mismatch" and latest["source"] == "prepared"
    assert len(latest["frames"]) >= 1
    for frame in latest["frames"]:
        assert client.get(frame["url"]).content == JPEG
    assert view["photos"] == []
    assert view["video_checks"][0]["check"] == "tray"
    stored = next(e for e in _events(client, eid) if e["event_type"] == "tray.checked")["payload"]
    assert stored["clip"] == "tray-hernia.mp4" and stored["by"] == NURSE and stored["template"] == "hernia-repair"


def test_flag_never_blocks(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    assert _upload(client, eid).json()["tray"]["latest"]["match"] == "mismatch"
    assert _surgery(client, eid, "began").status_code == 200
    url = f"/journey/episodes/{eid}/count"
    assert client.post(url, json={"step": "opened", "quantity": 20, "by": NURSE, "at_ms": 0}).status_code == 200
    assert client.post(url, json={"step": "closing", "returned": 20, "by": NURSE, "at_ms": 0}).status_code == 200
    assert _surgery(client, eid, "ended").status_code == 200
    assert _move(client, eid, "ward").status_code == 200


def test_recheck_with_full_tray_is_ok(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    _upload(client, eid)
    view = _upload(client, eid, name="tray-hernia-full.mp4").json()
    assert view["tray"]["latest"]["match"] == "ok"
    assert [c["match"] for c in view["video_checks"]] == ["mismatch", "ok"]


def test_tray_check_refusals(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    n = len(_events(client, eid))
    assert _upload(client, eid).status_code == 409
    assert len(_events(client, eid)) == n
    assert _move(client, eid, "theatre", procedure="hernia-repair").status_code == 200
    n = len(_events(client, eid))
    assert _upload(client, eid, task_id="t1").status_code == 422
    assert _upload(client, eid, kind="image/png").status_code == 400
    assert _upload(client, eid, data=b"").status_code == 400
    assert _upload(client, eid, data=b"not a video at all, no signature").status_code == 400
    assert _upload(client, eid, check="setup").status_code == 422
    assert len(_events(client, eid)) == n
    assert _surgery(client, eid, "began").status_code == 200
    n = len(_events(client, eid))
    assert _upload(client, eid).status_code == 409
    assert len(_events(client, eid)) == n


def test_upload_is_a_webm_too_and_left_nowhere(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 20
    assert _upload(client, eid, name="tray-hernia.webm", kind="video/webm", data=webm).status_code == 200
    folder = tmp_path / "journey_media" / eid
    assert [p.name for p in folder.iterdir() if p.name.startswith("tmp-")] == []
    assert not any(p.suffix in (".mp4", ".webm") for p in folder.rglob("*"))


@pytest.mark.parametrize("name", ["../../x.mp4", "Tray Hernia.MP4", "unknown-clip.mp4"])
def test_unknown_or_unsafe_clip_name(tmp_path, name):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    r = _upload(client, eid, name=name)
    assert r.status_code == 200
    latest = r.json()["tray"]["latest"]
    assert latest["match"] == "none" and latest["frames"] == []
    stored = next(e for e in _events(client, eid) if e["event_type"] == "tray.checked")["payload"]
    assert stored["frame_ids"] == []
    assert stored["clip"] == ("unknown-clip.mp4" if name.startswith("unknown") else "")


def test_frames_fail_check_still_written(tmp_path, monkeypatch):
    def broken(clip, times, out_dir):
        raise RuntimeError("ffmpeg is not installed on this server")

    monkeypatch.setattr(video_api, "cut_frames", broken)
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    r = _upload(client, eid)
    assert r.status_code == 200
    stored = next(e for e in _events(client, eid) if e["event_type"] == "tray.checked")["payload"]
    assert stored["frame_ids"] == [] and stored["why"].endswith(video.NO_FRAMES)
    assert stored["match"] == "mismatch"
    assert [p.name for p in (tmp_path / "journey_media" / eid).iterdir()] == []


def test_live_tray_faked(tmp_path, monkeypatch):
    seen = {}

    def fake(self, path, concepts):
        seen["concepts"] = list(concepts)
        return [{"frame_index": 0, "object_id": 1, "label": "needle holder", "score": 0.9}]

    monkeypatch.setattr(SamAdapter, "segment_video", fake)
    monkeypatch.setattr(live, "clip_seconds", lambda p: 6)
    monkeypatch.setattr(live, "to_sam_clip", lambda src, out, fps: None)
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    _to_theatre(client, eid)
    latest = _upload(client, eid).json()["tray"]["latest"]
    assert latest["source"] == "sam-3.1" and latest["match"] == "mismatch"
    assert "needle holder" in latest["missing"]
    expected = [r["concept"] for r in video.expected_for_tray(tray_plan("hernia-repair"))]
    assert seen["concepts"] == expected


def test_now_next_and_plain_have_no_advice(tmp_path):
    from app.journey.stories import plain

    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    before = _view(client, eid)["now_next"]["next"]
    assert "tray by video" in before
    view = _upload(client, eid).json()
    assert "tray by video" not in view["now_next"]["next"]
    texts = [before, view["now_next"]["next"], *(c["why"] for c in view["video_checks"])]
    kinds = {"tray.planned", "tray.checked", "photo.added"}
    lines = [plain(e) for e in _events(client, eid) if e["event_type"] in kinds]
    assert len(lines) == 2 + len(view["tray"]["latest"]["frames"])
    assert any(l.startswith("A frame from the tray clip") for l in lines)
    planned = next(l for l in lines if "confirmed the tray plan" in l)
    plan = tray_plan("hernia-repair")
    assert f"{sum(i['qty'] for i in plan['instruments'])} instruments, {plan['swab_total']} swabs" in planned
    for text in texts + lines:
        assert not ADVICE.search(text), text


def test_tool_timeout_is_a_parameter(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(media_pipeline, "_run_tool", lambda cmd, timeout=media_pipeline.TOOL_TIMEOUT_S: seen.append(timeout))
    media_pipeline.to_sam_clip(tmp_path / "a.mp4", tmp_path / "b.mp4", 2)
    assert seen == [60]
    seen.clear()

    class Boom(Exception):
        pass

    def stop(self, clip, names):
        raise Boom

    settings = _keyed(tmp_path)
    engine = SimpleNamespace(settings=settings, store=SimpleNamespace(zones=lambda c: {"tray": 1, "field": 1, "bucket": 1}))
    monkeypatch.setattr(SamAdapter, "segment_video", stop)
    monkeypatch.setattr(media_pipeline, "_video_size", lambda p: (1, 1))
    with pytest.raises(media_pipeline.SamCallFailed):
        media_pipeline.run_recorded_video(engine, "c1", tmp_path / "src.mp4")
    assert seen == [600, 600]


def test_tray_live_cut_switch(tmp_path, monkeypatch):
    def boom(self, path, concepts):
        raise AssertionError("the live model was called")

    monkeypatch.setattr(SamAdapter, "segment_video", boom)
    monkeypatch.setattr(video_api, "TRAY_LIVE", False)
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Iyer"}).json()["id"]
    _to_theatre(client, eid)
    assert _upload(client, eid).status_code == 200
    stored = next(e for e in _events(client, eid) if e["event_type"] == "tray.checked")["payload"]
    assert stored["source"] == "prepared"
