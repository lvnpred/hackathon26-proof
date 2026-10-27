"""One labelled patient morning records all six guide steps."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

BANNED = ("should", "recommend", "x-ray", "re-explore")


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


def test_one_labelled_patient_records_all_six_guide_steps(tmp_path):
    api = _client(tmp_path)
    created = api.post("/morning/episodes", json={"label": "Synthetic, UC1"})
    assert created.status_code == 200
    episode_id = created.json()["id"]

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
    body = discharge.json()
    narrative = body["sheet"]["narrative"]
    pdf = api.get(body["pdf_url"])
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    ics = api.get(body["ics_url"])
    assert ics.status_code == 200
    assert "BEGIN:VCALENDAR" in ics.text

    shown = api.get(f"/morning/episodes/{episode_id}")
    assert shown.status_code == 200
    guide = shown.json()["guide"]
    assert guide["done"] == 6
    assert guide["total"] == 6
    assert guide["patient"] == "Synthetic, UC1"
    assert all(step["current"] is False for step in guide["steps"])

    pdf_text = pdf.content.decode("latin-1").lower()
    for word in BANNED:
        assert word not in pdf_text
        assert word not in narrative.lower()
