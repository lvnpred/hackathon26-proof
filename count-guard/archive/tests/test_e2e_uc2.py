"""A finished morning does not leak into the next patient."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

A_TYPES = (
    "brownbag.med_found",
    "count.pack_opened",
    "count.closing",
    "druglog.given",
    "vitals.reading",
    "discharge.drafted",
)


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


def _walk_uc1(api: TestClient, episode_id: str) -> None:
    strip_text = json.dumps({"strips": [{"name": "metoprolol", "strength": "25 mg"}]})
    strips = api.post(
        f"/morning/episodes/{episode_id}/brownbag/text",
        json={"text": strip_text},
    )
    assert strips.status_code == 200
    found = [row for row in strips.json()["events"] if row["event_type"] == "brownbag.med_found"]
    assert found[0]["payload"]["generic"] == "metoprolol"
    assert found[0]["payload"]["strength"] == "25 mg"

    heard = api.post(
        f"/morning/episodes/{episode_id}/hear",
        json={"text": "opening twenty swabs"},
    )
    assert heard.status_code == 200
    assert heard.json()["kind"] == "pack"

    replayed = api.post(f"/morning/episodes/{episode_id}/count/replay")
    assert replayed.status_code == 200
    closing = [row for row in replayed.json()["events"] if row["event_type"] == "count.closing"][-1]
    assert closing["payload"]["opened"] == 20
    assert closing["payload"]["returned"] == 19
    assert closing["payload"]["unaccounted"] == 1
    assert closing["payload"]["track_id"] == "swab-20"

    drafted = api.post(
        f"/morning/episodes/{episode_id}/druglog",
        json={"text": "ondansetron 4 mg iv"},
    )
    assert drafted.status_code == 200
    draft_id = drafted.json()["draft"]["id"]
    confirmed = api.post(
        f"/morning/episodes/{episode_id}/druglog/{draft_id}/confirm",
        json={"by": "demo user"},
    )
    assert confirmed.status_code == 200

    seek = api.post(
        f"/morning/episodes/{episode_id}/vitals/sim",
        json={"action": "seek", "t_ms": 0},
    )
    assert seek.status_code == 200
    readings = [row for row in seek.json()["events"] if row["event_type"] == "vitals.reading"]
    assert len(readings) == 1

    discharge = api.post(f"/morning/episodes/{episode_id}/discharge")
    assert discharge.status_code == 200


def test_second_patient_morning_is_empty_after_first_finishes(tmp_path):
    api = _client(tmp_path)
    created_a = api.post("/morning/episodes", json={"label": "Synthetic, A"})
    created_b = api.post("/morning/episodes", json={"label": "Synthetic, B"})
    assert created_a.status_code == 200
    assert created_b.status_code == 200
    episode_a = created_a.json()["id"]
    episode_b = created_b.json()["id"]

    _walk_uc1(api, episode_a)

    shown_b = api.get(f"/morning/episodes/{episode_b}")
    assert shown_b.status_code == 200
    body_b = shown_b.json()
    guide_b = body_b["guide"]
    assert guide_b["done"] == 0
    assert guide_b["patient"] == "Synthetic, B"
    leaked = [row["event_type"] for row in body_b["events"] if row["event_type"] in A_TYPES]
    assert body_b["events"] == []
    assert leaked == []

    listed = api.get("/morning/episodes")
    assert listed.status_code == 200
    labels = {row["label"] for row in listed.json()["episodes"]}
    assert "Synthetic, A" in labels
    assert "Synthetic, B" in labels

    shown_a = api.get(f"/morning/episodes/{episode_a}")
    assert shown_a.status_code == 200
    assert shown_a.json()["guide"]["done"] == 6
