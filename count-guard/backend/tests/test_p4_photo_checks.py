"""P4 Task 8: photos wherever a video check is offered. Never a live call."""

from __future__ import annotations

import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.sam import SamAdapter
from app.main import create_app
from tests.test_flow_states import _new
from tests.test_p3_setup import SALINE, _begin, _row, _ward
from tests.test_flow_tasks import _done
from tests.test_p3_tray import JPEG, MP4, NURSE, _events, _to_theatre
from tests.test_p3_video import _keyed

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
PNG = b"\x89PNG\r\n" + b"png"
BOX = "<0f>1<|box;x1=1;y1=1;x2=5;y2=5;w=10;h=10;c=0.9|><|mask;x=0;y=0;c=0.9;data=1,1,~ab|>"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _photos(client, eid, names=("tray-hernia.png",), data=PNG, kind="image/png", **form):
    fields = {"check": "tray", "by": NURSE, "at_ms": "0", **form}
    files = [("files", (n, data, kind)) for n in names]
    return client.post(f"/journey/episodes/{eid}/video", files=files, data=fields)


def _checked(client, eid, event):
    return next(e for e in _events(client, eid) if e["event_type"] == event)["payload"]


def test_tray_check_by_two_photos_offline(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    r = _photos(client, eid, ("tray-hernia.png", "second.png"))
    assert r.status_code == 200, r.text
    latest = r.json()["tray"]["latest"]
    assert latest["match"] == "mismatch" and latest["source"] == "prepared"
    assert len(latest["frames"]) == 2
    for frame in latest["frames"]:
        got = client.get(frame["url"])
        assert got.status_code == 200 and got.content == PNG
    stored = _checked(client, eid, "tray.checked")
    assert stored["media"] == "photos" and stored["clip"] == "tray-hernia.png"
    assert len(stored["frame_ids"]) == 2
    frames = [e for e in _events(client, eid) if e["event_type"] == "photo.added"]
    assert [f["payload"]["purpose"] for f in frames] == ["frame", "frame"]
    assert all(f["payload"]["video"] == "tray" for f in frames)


def test_video_check_records_media_video(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    r = client.post(f"/journey/episodes/{eid}/video", files={"file": ("tray-hernia.mp4", MP4, "video/mp4")},
                    data={"check": "tray", "by": NURSE, "at_ms": "0"})
    assert r.status_code == 200
    assert _checked(client, eid, "tray.checked")["media"] == "video"


def test_setup_check_by_one_photo(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [SALINE])[SALINE["text"]]
    r = _photos(client, eid, ("saline-setup.png",), check="setup", task_id=task, at_ms="100")
    assert r.status_code == 200, r.text
    assert _row(r.json(), task)["video"]["match"] == "ok"
    stored = _checked(client, eid, "setup.checked")
    assert stored["media"] == "photos" and stored["task_id"] == task and stored["source"] == "prepared"
    frames = [e for e in _events(client, eid) if e["event_type"] == "photo.added"]
    assert frames and all(f["payload"]["task_id"] == task for f in frames)
    assert _begin(client, eid, task, 200).status_code == 200  # R19: a photo check at Begin of a start_end task


def test_video_and_photos_together_is_422(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    n = len(_events(client, eid))
    r = client.post(
        f"/journey/episodes/{eid}/video",
        files=[("file", ("a.mp4", MP4, "video/mp4")), ("files", ("a.png", PNG, "image/png"))],
        data={"check": "tray", "by": NURSE},
    )
    assert r.status_code == 422 and r.json()["detail"] == "Send one video or 1 to 6 photos."
    none = client.post(f"/journey/episodes/{eid}/video", data={"check": "tray", "by": NURSE})
    assert none.status_code == 422 and none.json()["detail"] == "Send one video or 1 to 6 photos."
    assert len(_events(client, eid)) == n


def test_seven_photos_is_422_and_six_pass(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    n = len(_events(client, eid))
    r = _photos(client, eid, tuple(f"p{i}.png" for i in range(7)))
    assert r.status_code == 422 and r.json()["detail"] == "Send one video or 1 to 6 photos."
    assert len(_events(client, eid)) == n
    assert _photos(client, eid, tuple(f"p{i}.png" for i in range(6))).status_code == 200


def test_png_with_jpeg_type_and_big_photo_are_400(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    n = len(_events(client, eid))
    assert _photos(client, eid, kind="image/jpeg").status_code == 400
    assert _photos(client, eid, data=JPEG, kind="image/gif").status_code == 400
    assert _photos(client, eid, data=JPEG + b"\0" * (8 * 1024 * 1024), kind="image/jpeg").status_code == 400
    assert len(_events(client, eid)) == n


def test_photo_refusals_match_video_refusals(tmp_path):
    client, eid = _new(tmp_path)
    from tests.test_flow_states import _to_ward

    _to_ward(client, eid)
    n = len(_events(client, eid))
    assert _photos(client, eid).status_code == 409  # not in theatre
    assert _photos(client, eid, task_id="t1").status_code == 422  # a tray check names no task
    assert len(_events(client, eid)) == n


def _seen_by_photo(calls):
    """A fake SAM stream. Per concept the first call is photo 1, the second photo 2.
    'scalpel handle': two objects in photo 1, one in photo 2. Everything else: only in photo 2."""
    def stream(self, body):
        content = body["input"][0]["content"]
        concept, url = content[0]["text"], content[1]["image_url"]
        calls.append((concept, url))
        first = sum(1 for c, _ in calls if c == concept) == 1
        if concept == "scalpel handle":
            return BOX + "\n" + BOX.replace("<0f>1", "<0f>2", 1) if first else BOX
        return "" if first else BOX

    return stream


def test_keyed_live_takes_the_max_per_concept_over_photos(tmp_path, monkeypatch):
    calls: list = []
    monkeypatch.setattr(SamAdapter, "_stream", _seen_by_photo(calls))
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    _to_theatre(client, eid)
    files = [("files", ("one.png", PNG, "image/png")), ("files", ("two.png", PNG + b"x", "image/png"))]
    r = client.post(f"/journey/episodes/{eid}/video", files=files, data={"check": "tray", "by": NURSE, "at_ms": "0"})
    assert r.status_code == 200, r.text
    assert len({c for c, _ in calls}) * 2 == len(calls) and all(u.startswith("data:image/png;base64,") for _, u in calls)
    latest = r.json()["tray"]["latest"]
    assert latest["source"] == "sam-3.1"
    scalpel = next(row for row in latest["rows"] if row["concept"] == "scalpel handle")
    assert scalpel["seen"] == 2  # the max over photos (2 and 1), not the sum (3)


@pytest.mark.parametrize("exc", [httpx.ConnectError("down"), RuntimeError("bad"), ValueError("bad")])
def test_keyed_failure_falls_back_to_prepared(tmp_path, monkeypatch, exc):
    def boom(self, body):
        raise exc

    monkeypatch.setattr(SamAdapter, "_stream", boom)
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    _to_theatre(client, eid)
    r = _photos(client, eid)
    assert r.json()["tray"]["latest"]["source"] == "prepared (live call failed)"
    r2 = _photos(client, eid, ("unknown-photo.png",))
    assert r2.json()["tray"]["latest"]["source"] == "failed"


def test_cut_switch_off_uses_prepared_even_with_a_key(tmp_path, monkeypatch):
    from app.journey import video_api

    def boom(self, body):
        raise AssertionError("the live model was called")

    monkeypatch.setattr(SamAdapter, "_stream", boom)
    monkeypatch.setattr(video_api, "TRAY_LIVE", False)
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    _to_theatre(client, eid)
    assert _photos(client, eid).json()["tray"]["latest"]["source"] == "prepared"


def test_no_prepared_result_is_source_none(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    latest = _photos(client, eid, ("IMG_0001.png",)).json()["tray"]["latest"]
    assert latest["source"] == "none" and latest["match"] == "none"


def test_plain_lines_say_photos_and_have_no_advice(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [SALINE])[SALINE["text"]]
    _photos(client, eid, ("saline-setup.png",), check="setup", task_id=task)
    from app.journey import stories

    events = _events(client, eid)
    texts = [stories.plain(e) for e in events]
    assert any(t.startswith("Set-up check by photos: ") for t in texts)
    assert not any(ADVICE.search(t) for t in texts if "check" in t.lower() or "photo" in t.lower())
    client2, eid2 = _new(tmp_path / "b")
    _to_theatre(client2, eid2)
    _photos(client2, eid2)
    texts2 = [stories.plain(e) for e in _events(client2, eid2)]
    assert any(t.startswith("Tray check by photos: ") for t in texts2)
    assert any(t.startswith("A photo from the tray check") for t in texts2)
    assert not any(ADVICE.search(t) for t in texts2 if "check" in t.lower() or "photo" in t.lower())


def test_photo_why_says_photos_not_clip(tmp_path):
    from app.journey import stories

    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    stored = _photos(client, eid)
    why = _checked(client, eid, "tray.checked")["why"]
    assert why.startswith("Not seen in the photos: ") and "clip" not in why
    assert stories.plain(next(e for e in _events(client, eid) if e["event_type"] == "tray.checked")).endswith(why)
    client2, eid2 = _new(tmp_path / "b")
    task = _ward(client2, eid2, [SALINE])[SALINE["text"]]
    _photos(client2, eid2, ("saline-setup.png",), check="setup", task_id=task)
    ok = _checked(client2, eid2, "setup.checked")["why"]
    assert ok == "Every planned item was seen in the photos."
    assert stories.plain(next(e for e in _events(client2, eid2) if e["event_type"] == "setup.checked")) == f"Set-up check by photos: {ok}"
    client3, eid3 = _new(tmp_path / "c")
    _to_theatre(client3, eid3)
    _photos(client3, eid3, ("IMG_0001.png",))
    none = _checked(client3, eid3, "tray.checked")["why"]
    assert none.startswith("The photos were not checked:") and "clip" not in none
    assert stored.status_code == 200


def test_keyed_reply_without_frame_marker_still_counts(tmp_path, monkeypatch):
    bare = BOX.replace("<0f>", "")

    def stream(self, body):
        concept = body["input"][0]["content"][0]["text"]
        return bare + "\n" + bare.replace("1<|box", "2<|box", 1) if concept == "scalpel handle" else ""

    monkeypatch.setattr(SamAdapter, "_stream", stream)
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    _to_theatre(client, eid)
    latest = _photos(client, eid).json()["tray"]["latest"]
    assert latest["source"] == "sam-3.1"
    seen = {row["concept"]: row["seen"] for row in latest["rows"]}
    assert seen["scalpel handle"] == 2 and all(v == 0 for k, v in seen.items() if k != "scalpel handle")


def test_photo_check_frame_is_not_task_proof(tmp_path):
    from app.journey.tasks import FRAME_NOT_PROOF

    client, eid = _new(tmp_path)
    task = _ward(client, eid, [SALINE])[SALINE["text"]]
    _photos(client, eid, ("saline-setup.png",), check="setup", task_id=task)
    frame = next(e for e in _events(client, eid) if e["event_type"] == "photo.added")
    assert _begin(client, eid, task, 5).status_code == 200
    refused = _done(client, eid, task, at_ms=7, proof_id=frame["id"])
    assert refused.status_code == 409 and refused.json()["detail"] == FRAME_NOT_PROOF
