"""HTTP path: scripted upload, blocked close, human resolution, PDF."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def client(tmp_path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        meta_api_key="",
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


def test_video_upload_without_key_is_refused(tmp_path):
    api = client(tmp_path)
    case_id = api.post("/cases", json={"label": "x", "item_types": ["lap sponge"]}).json()["id"]
    refused = api.post(
        f"/cases/{case_id}/upload",
        files={"file": ("clip.mp4", b"not a video", "video/mp4")},
    )
    assert refused.status_code == 400
    assert "MODEL_API_KEY" in refused.json()["detail"]
