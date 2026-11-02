"""P3 set-up check: saline set-up by video on a start_end task. Never a live call."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.sam import SamAdapter
from app.journey import live, switches, video_api
from app.journey.dictation import parse_order_text
from app.main import create_app
from tests.test_flow_states import _move, _new, _to_ward, _view
from tests.test_flow_tasks import DOC, NURSE, _ack, _done, _sign, _url
from tests.test_p3_tray import JPEG, MP4, _events
from tests.test_p3_video import _keyed

SALINE_TEXT = json.load(open(live.PREPARED_DIR / "iyer-saline.json"))["transcript"]
SALINE = {"kind": "procedure", "text": "Saline 1 litre over 2 hours, video check of the set-up",
          "mode": "start_end", "proof": "video"}
DOSE = {"kind": "dose", "text": "Paracetamol 1 g every 6 h", "name": "Paracetamol", "amount": "1 g",
        "every_h": 6, "proof": "photo"}
DRESSING = {"kind": "procedure", "text": "Dressing change", "mode": "start_end", "proof": "video"}


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


def _ward(client, eid, items, at_ms=0):
    _to_ward(client, eid)
    order = _sign(client, eid, items, at_ms).json()["order_list"][0]
    return {t["title"]: t["id"] for t in _ack(client, eid, order["id"], at_ms).json()["tasks"]}


def _setup(client, eid, task_id, name="saline-setup.mp4", at_ms=0, **form):
    fields = {"check": "setup", "by": NURSE, "at_ms": str(at_ms), **form}
    if task_id is not None:
        fields["task_id"] = task_id
    return client.post(_url(eid, "video"), files={"file": (name, MP4, "video/mp4")}, data=fields)


def _begin(client, eid, task_id, at_ms=0):
    return client.post(_url(eid, f"tasks/{task_id}/begin"), json={"by": NURSE, "at_ms": at_ms})


def _row(view, task_id):
    return next(t for t in view["tasks"] if t["id"] == task_id)


def test_rules_parse_video_proof():
    saline, obs = parse_order_text(SALINE_TEXT)["items"]
    assert (saline["kind"], saline["mode"], saline["proof"]) == ("procedure", "start_end", "video")
    assert obs["every_h"] == 0.25


def test_saline_setup_check_ok(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [SALINE])[SALINE["text"]]
    view = _setup(client, eid, task, at_ms=100).json()
    row = _row(view, task)
    assert row["video"]["match"] == "ok" and row["status"] == "open"
    assert _begin(client, eid, task, 200).status_code == 200
    assert _row(_view(client, eid), task)["status"] == "running"
    done = _done(client, eid, task, at_ms=300).json()
    assert _row(done, task)["status"] == "done"
    stored = next(e for e in _events(client, eid) if e["event_type"] == "setup.checked")["payload"]
    assert stored["task_id"] == task and stored["setup"] == "saline" and stored["source"] == "prepared"
    frames = [e for e in _events(client, eid) if e["event_type"] == "photo.added"]
    assert frames and all(f["payload"]["task_id"] == task for f in frames)


def test_setup_check_while_running_keeps_running(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [SALINE])[SALINE["text"]]
    assert _begin(client, eid, task).status_code == 200
    view = _setup(client, eid, task, at_ms=10).json()
    assert _row(view, task)["status"] == "running" and _row(view, task)["video"]["match"] == "ok"
    assert [c["check"] for c in view["video_checks"]] == ["setup"]


def test_setup_refusals(tmp_path):
    client, eid = _new(tmp_path)
    ids = _ward(client, eid, [SALINE, DOSE, DRESSING])
    saline, dose, dressing = ids[SALINE["text"]], ids[DOSE["text"]], ids[DRESSING["text"]]
    n = len(_events(client, eid))
    assert _setup(client, eid, dose).status_code == 409
    assert _setup(client, eid, dressing).status_code == 409
    assert _setup(client, eid, "no-such-task").status_code == 404
    assert _setup(client, eid, None).status_code == 422
    assert len(_events(client, eid)) == n
    assert _begin(client, eid, saline).status_code == 200
    assert _done(client, eid, saline).status_code == 200
    assert _setup(client, eid, saline).status_code == 409
    assert _move(client, eid, "theatre", procedure="hernia-repair").status_code == 200
    n = len(_events(client, eid))
    assert _setup(client, eid, saline).status_code == 409
    assert len(_events(client, eid)) == n


def test_setup_mismatch_never_blocks(tmp_path, monkeypatch):
    def fake(self, path, concepts):
        return [{"frame_index": 0, "object_id": i, "label": c, "bbox": [0.1, 0.1, 0.1, 0.1], "score": 0.9}
                for i, c in enumerate(concepts) if c != "iv cannula"]

    monkeypatch.setattr(SamAdapter, "segment_video", fake)
    monkeypatch.setattr(live, "clip_seconds", lambda p: 6)
    monkeypatch.setattr(live, "to_sam_clip", lambda src, out, fps: None)
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Iyer"}).json()["id"]
    task = _ward(client, eid, [SALINE])[SALINE["text"]]
    video = _row(_setup(client, eid, task).json(), task)["video"]
    assert video["match"] == "mismatch" and "iv cannula" in video["why"]
    assert _begin(client, eid, task, 5).status_code == 200
    assert _done(client, eid, task, at_ms=6).status_code == 200


def test_setup_live_cut_switch(tmp_path, monkeypatch):
    def boom(self, path, concepts):
        raise AssertionError("the live model was called")

    monkeypatch.setattr(SamAdapter, "segment_video", boom)
    monkeypatch.setattr(switches, "SETUP_LIVE", False)
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Iyer"}).json()["id"]
    task = _ward(client, eid, [SALINE])[SALINE["text"]]
    assert _setup(client, eid, task).status_code == 200
    stored = next(e for e in _events(client, eid) if e["event_type"] == "setup.checked")["payload"]
    assert stored["source"] == "prepared"


def test_task_row_says_whether_a_setup_list_exists(tmp_path):
    client, eid = _new(tmp_path)
    ids = _ward(client, eid, [SALINE, DRESSING, DOSE])
    view = _view(client, eid)
    assert [_row(view, ids[i["text"]])["has_setup"] for i in (SALINE, DRESSING, DOSE)] == [True, False, False]


def test_frame_is_not_task_proof(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [SALINE])[SALINE["text"]]
    assert _begin(client, eid, task, 5).status_code == 200
    assert _setup(client, eid, task, at_ms=6).status_code == 200
    frame = next(e for e in _events(client, eid) if e["event_type"] == "photo.added")
    n = len(_events(client, eid))
    refused = _done(client, eid, task, at_ms=7, proof_id=frame["id"])
    assert refused.status_code == 409 and "not photo proof" in refused.json()["detail"]
    assert len(_events(client, eid)) == n
