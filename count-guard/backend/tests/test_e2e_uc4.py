"""The fact card stays off the discharge sheet while the decision tier is off."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from conftest import pdf_text
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
    text = pdf_text(pdf.content).lower()
    assert "discharge sheet" in text
    for word in ADVICE:
        assert word not in text

    assert sheet["readings"]
    assert _keys_carrying_a_card_sentence(sheet) == []


@pytest.mark.parametrize("enabled", [False, True])
def test_discharge_pdf_text_lists_facts_and_drops_card_in_both_tiers(tmp_path, enabled):
    api = _client(tmp_path)
    tier = api.post("/morning/tier", json={"enabled": enabled})
    assert tier.status_code == 200
    assert tier.json()["decision_tier"] == int(enabled)

    created = api.post("/morning/episodes", json={"label": "Synthetic, UC4 PDF"})
    assert created.status_code == 200
    episode_id = created.json()["id"]

    played = api.post(f"/morning/episodes/{episode_id}/play")
    assert played.status_code == 200
    cards = [row for row in played.json()["events"] if row["event_type"] == "vitals.card"]
    assert len(cards) == (1 if enabled else 0)

    discharge = api.post(f"/morning/episodes/{episode_id}/discharge")
    assert discharge.status_code == 200
    pdf = api.get(discharge.json()["pdf_url"])
    assert pdf.status_code == 200

    text = pdf_text(pdf.content)
    lowered = text.lower()
    assert "metoprolol" in lowered
    assert "lignocaine" in lowered
    assert "Opened 20." in text
    assert "Unaccounted 1." in text
    assert "BP 86/50, down" not in text
    for card in cards:
        assert card["payload"]["text"] not in text
    for word in ADVICE:
        assert word not in lowered
