"""A camera count filed onto the current patient is the discharge closing line."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _client(tmp_path) -> TestClient:
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


def _closings(events: list[dict]) -> list[dict]:
    return [row for row in events if row["event_type"] == "count.closing"]


def test_camera_count_is_the_discharge_closing(tmp_path):
    api = _client(tmp_path)
    created = api.post("/cases", json={"label": "Prop tray", "item_types": ["lap sponge"]})
    assert created.status_code == 200
    case_id = created.json()["id"]

    uploaded = api.post(f"/cases/{case_id}/upload?scenario=demo")
    assert uploaded.status_code == 200

    episode = api.post("/morning/episodes", json={"label": "Synthetic, camera"})
    assert episode.status_code == 200
    episode_id = episode.json()["id"]

    replayed = api.post(f"/morning/episodes/{episode_id}/count/replay")
    assert replayed.status_code == 200
    theatre = _closings(replayed.json()["events"])[-1]
    assert theatre["payload"]["opened"] == 20

    filed = api.post(
        f"/morning/episodes/{episode_id}/count/from-case",
        json={"case_id": case_id},
    )
    assert filed.status_code == 200

    shown = api.get(f"/morning/episodes/{episode_id}")
    assert shown.status_code == 200
    body = shown.json()
    count = body["sheet"]["count"]
    assert count["source"] == "camera"
    assert count["case_id"] == case_id
    assert count["opened"] == 10
    assert count["returned"] == 9
    assert count["unaccounted"] == 1
    last_closing = _closings(body["events"])[-1]
    assert last_closing["plain"].startswith("Camera count filed")

    again = api.post(
        f"/morning/episodes/{episode_id}/count/from-case",
        json={"case_id": case_id},
    )
    assert again.status_code == 200
    assert again.json()["already_filed"] is True
    camera_closings = [
        row
        for row in _closings(again.json()["events"])
        if row["payload"].get("source") == "camera"
    ]
    assert len(camera_closings) == 1

    discharge = api.post(f"/morning/episodes/{episode_id}/discharge")
    assert discharge.status_code == 200
    sheet_count = discharge.json()["sheet"]["count"]
    assert sheet_count["source"] == "camera"
    assert sheet_count["opened"] == 10
    assert sheet_count["unaccounted"] == 1
