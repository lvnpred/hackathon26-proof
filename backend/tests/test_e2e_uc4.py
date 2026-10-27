"""The fact card stays off the discharge sheet while the decision tier is off."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ADVICE = ("should", "recommend", "x-ray", "re-explore", "reexplore")


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


def _card_sentence(text: str) -> bool:
    lowered = text.lower()
    if any(word in lowered for word in ADVICE):
        return True
    return "bp" in lowered and "down " in lowered and "%" in lowered


def _keys_carrying_a_card_sentence(node, key: str | None = None) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for child_key, child in node.items():
            if child_key == "readings":
                continue
            found.extend(_keys_carrying_a_card_sentence(child, child_key))
    elif isinstance(node, list):
        for child in node:
            found.extend(_keys_carrying_a_card_sentence(child, key))
    elif isinstance(node, str) and key and _card_sentence(node):
        found.append(key)
    return found


def test_fact_card_stays_off_and_the_discharge_pdf_has_no_advice(tmp_path):
    api = _client(tmp_path)
    tier = api.post("/morning/tier", json={"enabled": False})
    assert tier.status_code == 200
    assert tier.json()["decision_tier"] == 0

    created = api.post("/morning/episodes", json={"label": "Synthetic, UC4"})
    assert created.status_code == 200
    episode_id = created.json()["id"]

    seek = api.post(
        f"/morning/episodes/{episode_id}/vitals/sim",
        json={"action": "seek", "t_ms": 240000},
    )
    assert seek.status_code == 200
    events = seek.json()["events"]
    readings = [row for row in events if row["event_type"] == "vitals.reading"]
    assert [row["payload"]["systolic"] for row in readings] == [120, 118, 110, 86]
    assert all(row["event_type"] != "vitals.card" for row in events)

    card = api.get(f"/morning/episodes/{episode_id}/card")
    assert card.status_code == 404

    discharge = api.post(f"/morning/episodes/{episode_id}/discharge")
    assert discharge.status_code == 200
    body = discharge.json()
    sheet = body["sheet"]
    narrative = sheet["narrative"]
    for word in ADVICE:
        assert word not in narrative.lower()

    pdf = api.get(body["pdf_url"])
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    for word in ADVICE:
        assert word.encode("ascii") not in pdf.content

    assert sheet["readings"]
    assert _keys_carrying_a_card_sentence(sheet) == []
