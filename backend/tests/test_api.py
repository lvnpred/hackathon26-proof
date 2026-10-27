"""HTTP path: scripted upload, blocked close, human resolution, PDF."""

from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

from app.agent.verifier import ADVICE
from app.config import Settings
from app.main import create_app
from app.morning.camera_file import camera_count_events
from conftest import pdf_text


def client(tmp_path, meta_api_key: str = "") -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        meta_api_key=meta_api_key,
        meta_base="https://api.meta.ai/v1",
        sam_model="sam-3.1",
        voice_model="muse-voice-transcribe-1.0",
        spark_model="muse-spark-1.3",
        baseten_api_key="",
        spark_open_base="https://inference.baseten.co/v1",
        spark_open_model="meta-models/muse-spark-open-1026",
        low_confidence=0.45,
        unannounced_window_ms=30_000,
        lost_after_frames=4,
        sam_fps=2,
    )
    return TestClient(create_app(settings))


def test_health_names_models(tmp_path):
    response = client(tmp_path).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["banner"] == "Research demo. Not for clinical use."
    assert "sam-3.1" in body["adapters"]
    assert body["adapters"]["muse-voice-transcribe"]["note"].startswith("Turn-level")


def test_demo_blocks_then_resolves_and_writes_pdf(tmp_path):
    api = client(tmp_path)
    created = api.post("/cases", json={"label": "Prop tray demo", "item_types": ["lap sponge"]})
    assert created.status_code == 200
    case_id = created.json()["id"]
    uploaded = api.post(f"/cases/{case_id}/upload", params={"scenario": "demo"})
    assert uploaded.status_code == 200
    rules = {(row["rule_id"], row["item_type"]) for row in uploaded.json()["discrepancies"] if row["status"] == "open"}
    assert ("R3", "lap sponge") in rules
    blocked = api.post(f"/cases/{case_id}/close")
    assert blocked.status_code == 409
    for row in uploaded.json()["discrepancies"]:
        if row["status"] != "open" or row["rule_id"] == "R5":
            continue
        resolved = api.post(
            f"/discrepancies/{row['id']}/resolve",
            json={"reason": "Found under drape, placed in bucket", "by": "demo user"},
        )
        assert resolved.status_code == 200
    closed = api.post(f"/cases/{case_id}/close")
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["ok"] is True
    assert "recommend" not in body["narrative"].lower()
    assert "should" not in body["narrative"].lower()
    pdf = api.get(body["report_url"])
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    frame_id = uploaded.json()["frames"][0]["id"]
    frame = api.get(f"/frames/{frame_id}")
    assert frame.status_code == 200
    assert frame.headers["content-type"].startswith("image/png")


def test_demo_shows_unannounced_gauze(tmp_path):
    api = client(tmp_path)
    case_id = api.post("/cases", json={"label": "Prop tray demo", "item_types": ["lap sponge"]}).json()["id"]
    uploaded = api.post(f"/cases/{case_id}/upload", params={"scenario": "demo"})
    assert uploaded.status_code == 200
    rules = {(row["rule_id"], row["item_type"]) for row in uploaded.json()["discrepancies"] if row["status"] == "open"}
    assert ("R4", "gauze swab") in rules
    items = {row["item_type"]: row for row in api.get(f"/cases/{case_id}/ledger").json()["items"]}
    sponge = items["lap sponge"]
    assert (sponge["opened"], sponge["bucket"], sponge["unaccounted"]) == (10, 9, 1)
    closing = camera_count_events(list(items.values()), uploaded.json()["discrepancies"], case_id)[-1]["payload"]
    assert (closing["opened"], closing["returned"], closing["unaccounted"]) == (10, 9, 1)
    assert "gauze swab" in closing["detail"]


def test_resolution_reason_is_on_rows_and_sheet(tmp_path):
    api = client(tmp_path)
    case_id = api.post("/cases", json={"label": "Prop tray demo", "item_types": ["lap sponge"]}).json()["id"]
    uploaded = api.post(f"/cases/{case_id}/upload", params={"scenario": "demo"}).json()
    reason = "Found under drape, placed in bucket"
    for row in uploaded["discrepancies"]:
        if row["status"] != "open" or row["rule_id"] == "R5":
            continue
        api.post(f"/discrepancies/{row['id']}/resolve", json={"reason": reason, "by": "demo user"})
    rows = api.get(f"/cases/{case_id}/discrepancies").json()["discrepancies"]
    resolved = [row for row in rows if row["status"] == "resolved"]
    assert resolved
    for row in resolved:
        assert row["resolution"]["reason"] == reason
        assert row["resolution"]["by"] == "demo user"
        assert row["resolution"]["wall_clock"]
    assert all(row.get("resolution") is None for row in rows if row["status"] == "open")
    closed = api.post(f"/cases/{case_id}/close")
    assert closed.status_code == 200, closed.text
    text = pdf_text(api.get(closed.json()["report_url"]).content)
    assert f"Resolved by demo user: {reason}" in text
    assert ADVICE.search(text) is None


def test_video_upload_without_key_is_refused(tmp_path):
    api = client(tmp_path)
    case_id = api.post("/cases", json={"label": "x", "item_types": ["lap sponge"]}).json()["id"]
    refused = api.post(
        f"/cases/{case_id}/upload",
        files={"file": ("clip.mp4", b"not a video", "video/mp4")},
    )
    assert refused.status_code == 400
    assert "MODEL_API_KEY" in refused.json()["detail"]


def _case(api) -> str:
    return api.post("/cases", json={"label": "x", "item_types": ["lap sponge"]}).json()["id"]


def test_upload_filename_cannot_escape_the_case_folder(tmp_path):
    data = tmp_path / "data"
    api = client(data)
    case_id = _case(api)
    refused = api.post(
        f"/cases/{case_id}/upload",
        files={"file": ("../../evil.mp4", b"not a video", "video/mp4")},
    )
    assert refused.status_code == 400
    assert "MODEL_API_KEY" in refused.json()["detail"]
    case_folder = data / "uploads" / case_id
    escaped = [path for path in tmp_path.rglob("evil.mp4") if case_folder not in path.parents]
    assert escaped == []
    assert not (data / "evil.mp4").exists()
    bare = api.post(f"/cases/{case_id}/upload", files={"file": ("..", b"not a video", "video/mp4")})
    assert bare.status_code == 400


def test_video_is_not_stored_without_a_key(tmp_path):
    api = client(tmp_path)
    case_id = _case(api)
    refused = api.post(
        f"/cases/{case_id}/upload",
        files={"file": ("clip.mp4", b"not a video", "video/mp4")},
    )
    assert refused.status_code == 400
    uploads = tmp_path / "uploads"
    assert not uploads.exists() or [path for path in uploads.rglob("*") if path.is_file()] == []


def test_wrong_shape_scenario_json_is_400(tmp_path):
    api = client(tmp_path)
    case_id = _case(api)
    for body in (b'{"a":1}', b"[1,2]"):
        refused = api.post(
            f"/cases/{case_id}/upload",
            files={"file": ("scenario.json", body, "application/json")},
        )
        assert refused.status_code == 400, refused.text
        detail = refused.json()["detail"]
        assert "zones" in detail and "steps" in detail


_ZONES = {
    "zones": [
        {"name": name, "polygon": [[0, 0], [1, 0], [1, 1]]}
        for name in ("tray", "field", "bucket")
    ]
}


def test_video_errors_are_clear_not_500(tmp_path, monkeypatch):
    from app.adapters.sam import SamAdapter

    def no_network(self, path, concepts):
        raise AssertionError("SAM must not be called in this case")

    monkeypatch.setattr(SamAdapter, "segment_video", no_network)
    api = client(tmp_path, meta_api_key="fake-key-never-sent")
    case_id = _case(api)
    assert api.post(f"/cases/{case_id}/zones", json=_ZONES).status_code == 200

    def upload():
        return api.post(
            f"/cases/{case_id}/upload",
            files={"file": ("clip.mp4", b"not a video", "video/mp4")},
        )

    def missing_binary(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "ffmpeg")

    def bad_clip(cmd, *args, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, output="", stderr="moov atom not found\n")

    for fake_run in (missing_binary, bad_clip):
        monkeypatch.setattr(subprocess, "run", fake_run)
        refused = upload()
        assert 400 <= refused.status_code < 500 or refused.status_code == 502, refused.text
        detail = refused.json()["detail"]
        assert "ffmpeg" in detail and "\n" not in detail

    def ffmpeg_ok_ffprobe_fails(cmd, *args, **kwargs):
        if cmd[0] == "ffprobe":
            raise subprocess.CalledProcessError(1, cmd, output="", stderr="Invalid data\n")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def sam_down(self, path, concepts):
        raise ConnectionError("upstream unreachable")

    monkeypatch.setattr(subprocess, "run", ffmpeg_ok_ffprobe_fails)
    monkeypatch.setattr(SamAdapter, "segment_video", lambda self, path, concepts: [])
    refused = upload()
    assert refused.status_code == 400, refused.text
    assert "ffprobe" in refused.json()["detail"] or "ffmpeg" in refused.json()["detail"]

    monkeypatch.setattr(SamAdapter, "segment_video", sam_down)
    refused = upload()
    assert refused.status_code == 502, refused.text
    detail = refused.json()["detail"]
    assert "SAM 3.1" in detail and "\n" not in detail
    uploads = tmp_path / "uploads"
    assert [path for path in uploads.rglob("*") if path.is_file()] == []


def test_video_without_zones_is_refused_before_the_clip_is_written(tmp_path):
    api = client(tmp_path, meta_api_key="fake-key-never-sent")
    case_id = _case(api)
    refused = api.post(
        f"/cases/{case_id}/upload",
        files={"file": ("clip.mp4", b"not a video", "video/mp4")},
    )
    assert refused.status_code == 400
    assert "zones" in refused.json()["detail"]
    assert not (tmp_path / "uploads").exists()


def test_count_sheet_survives_non_latin1_reason(tmp_path):
    api = client(tmp_path)
    case_id = api.post("/cases", json={"label": "Prop tray demo", "item_types": ["lap sponge"]}).json()["id"]
    uploaded = api.post(f"/cases/{case_id}/upload", params={"scenario": "demo"}).json()
    reason = "Found under drape — “bucket” ✓"
    for row in uploaded["discrepancies"]:
        if row["status"] != "open" or row["rule_id"] == "R5":
            continue
        api.post(f"/discrepancies/{row['id']}/resolve", json={"reason": reason, "by": "demo user"})
    closed = api.post(f"/cases/{case_id}/close")
    assert closed.status_code == 200, closed.text
    text = pdf_text(api.get(closed.json()["report_url"]).content)
    assert 'Found under drape - "bucket"' in text


def test_case_and_zone_input_is_validated(tmp_path):
    from app.config import SAM_CONCEPTS

    api = client(tmp_path)
    banana = api.post("/cases", json={"label": "x", "item_types": ["banana"]})
    assert banana.status_code == 422, banana.text
    every = api.post("/cases", json={"label": "x", "item_types": list(SAM_CONCEPTS)})
    assert every.status_code == 200, every.text
    case_id = every.json()["id"]

    def zones(tray_polygon, names=("tray", "field", "bucket")):
        good = [[0.02, 0.05], [0.40, 0.05], [0.40, 0.95], [0.02, 0.95]]
        rows = [{"name": name, "polygon": good} for name in names]
        rows[0]["polygon"] = tray_polygon
        return {"zones": rows}

    off_frame = zones([[5, 0], [0.4, 0.1], [0.4, 0.9]])
    assert api.post(f"/cases/{case_id}/zones", json=off_frame).status_code == 422
    three_numbers = zones([[0.1, 0.1, 0.1], [0.4, 0.1], [0.4, 0.9]])
    assert api.post(f"/cases/{case_id}/zones", json=three_numbers).status_code == 422
    tray_three_times = zones([[0.1, 0.1], [0.4, 0.1], [0.4, 0.9]], names=("tray", "tray", "tray"))
    assert api.post(f"/cases/{case_id}/zones", json=tray_three_times).status_code == 422
    fine = zones([[0.02, 0.05], [0.40, 0.05], [0.40, 0.95]])
    assert api.post(f"/cases/{case_id}/zones", json=fine).status_code == 200
