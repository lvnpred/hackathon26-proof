"""Archived with the routes they test (spec §9 "Archiving", Task 16). Not collected: pytest testpaths is backend/tests.

Original file: backend/tests/test_morning.py. These ran against routes that no longer exist and are kept for reference, not run.
The care-app features they map to have the §9 row tests in the plan appendix; the discharge-tier, PDF-encoding and
nudge-wording checks are re-pinned in backend/tests/test_kept_coverage.py. Not every old edge case has a care twin.
"""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.morning.druglog import parse_drug_phrase
from app.morning.vitals import choose_wording, demo_readings, evaluate, wording_ok
from app.morning.discharge import fold
from conftest import pdf_text


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


def test_card_is_hidden_until_the_tier_is_on(tmp_path):
    api = _client(tmp_path)
    assert api.get("/morning/tier").json()["decision_tier"] == 0
    episode = api.post("/morning/episodes", json={"label": "Synthetic demo"}).json()
    played = api.post(f"/morning/episodes/{episode['id']}/play")
    assert played.status_code == 200
    hidden = api.get(f"/morning/episodes/{episode['id']}/card")
    assert hidden.status_code == 404
    sheet = played.json()["sheet"]
    assert sheet["count"]["unaccounted"] == 1
    assert any(item["generic"] == "metoprolol" for item in sheet["opd"])
    assert any(item["generic"] == "lignocaine" for item in sheet["drugs"])
    assert "treatment" not in sheet["narrative"].lower() or "does not state a treatment" in sheet["narrative"]
    types = {event["event_type"] for event in played.json()["events"]}
    assert "vitals.card" not in types

    turned = api.post("/morning/tier", json={"enabled": True})
    assert turned.json()["decision_tier"] == 1
    again = api.post("/morning/episodes", json={"label": "Synthetic demo"}).json()
    shown = api.post(f"/morning/episodes/{again['id']}/play")
    card = api.get(f"/morning/episodes/{again['id']}/card")
    assert card.status_code == 200
    text = card.json()["card"]["payload"]["text"]
    assert "BP 86/50" in text
    assert "should" not in text.lower()
    folded = fold(shown.json()["events"])
    assert all("consider" not in str(item).lower() for item in folded["drugs"])
    assert folded["count"]["opened"] == 20


def test_unknown_drug_needs_a_confirm_tap(tmp_path):
    api = _client(tmp_path)
    episode = api.post("/morning/episodes", json={}).json()
    heard = api.post(
        f"/morning/episodes/{episode['id']}/druglog",
        json={"text": "xyzolone 10 mg oral"},
    ).json()
    assert heard["grounded"] is False
    assert heard["needs_confirm"] is True
    before = api.get(f"/morning/episodes/{episode['id']}").json()["sheet"]["drugs"]
    assert before == []
    confirmed = api.post(
        f"/morning/episodes/{episode['id']}/druglog/{heard['draft']['id']}/confirm",
        json={"by": "demo user"},
    )
    assert confirmed.status_code == 200
    drugs = confirmed.json()["sheet"]["drugs"]
    assert drugs[0]["name_as_heard"] == "xyzolone"
    assert drugs[0]["grounded"] is False


def test_duplicate_flag_stays_off_with_the_tier(tmp_path):
    api = _client(tmp_path)
    episode = api.post("/morning/episodes", json={}).json()
    body = {
        "strips": [
            {"name": "metoprolol", "strength": "25 mg"},
            {"name": "metoprolol", "strength": "50 mg"},
        ]
    }
    quiet = api.post(f"/morning/episodes/{episode['id']}/brownbag", json=body)
    types = [event["event_type"] for event in quiet.json()["events"]]
    assert types.count("brownbag.med_found") == 2
    assert "brownbag.same_drug_twice" not in types
    api.post("/morning/tier", json={"enabled": True})
    flagged = api.post(f"/morning/episodes/{episode['id']}/brownbag", json=body)
    assert any(event["event_type"] == "brownbag.same_drug_twice" for event in flagged.json()["events"])


def test_stream_resumes_after_the_last_id(tmp_path):
    api = _client(tmp_path)
    episode = api.post("/morning/episodes", json={}).json()
    api.post(f"/morning/episodes/{episode['id']}/play")
    first = api.get(f"/morning/episodes/{episode['id']}/stream")
    assert first.status_code == 200
    assert "brownbag.med_found" in first.text
    event_id = first.text.split("id: ", 1)[1].split("\n", 1)[0]
    resumed = api.get(
        f"/morning/episodes/{episode['id']}/stream",
        headers={"Last-Event-ID": event_id},
    )
    assert event_id not in resumed.text.split("data:", 1)[0]
    assert "id: " in resumed.text


def test_stream_follows_a_new_event_within_one_second(tmp_path):
    api = _client(tmp_path)
    episode = api.post("/morning/episodes", json={}).json()
    store = api.app.state.morning
    written: dict = {}

    def write_later():
        time.sleep(0.2)
        written["at"] = time.monotonic()
        written["event"] = store.append(episode["id"], "druglog.parsed", {"text": "late"}, ts_ms=0)

    url = f"/morning/episodes/{episode['id']}/stream?follow=1&timeout_s=2"
    received = None
    with api.stream("GET", url) as response:
        assert response.status_code == 200
        threading.Thread(target=write_later, daemon=True).start()
        for line in response.iter_lines():
            if line.startswith("id: ") and line[4:] == written.get("event", {}).get("id"):
                received = time.monotonic()
                break
    assert received is not None, "the followed stream never sent the new event"
    assert received - written["at"] < 1.0


def test_discharge_pdf_survives_non_latin1_text(tmp_path):
    api = _client(tmp_path)
    label = "Synthetic demo \u2014 \u201cR. Kumar\u201d \u2026 \u2713"
    episode = api.post("/morning/episodes", json={"label": label}).json()
    api.post(f"/morning/episodes/{episode['id']}/play")
    drafted = api.post(f"/morning/episodes/{episode['id']}/discharge")
    assert drafted.status_code == 200, drafted.text
    text = pdf_text(api.get(drafted.json()["pdf_url"]).content)
    assert 'Session: Synthetic demo - "R. Kumar" ... ?' in text


def test_card_is_written_within_500ms_of_the_drop_reading(tmp_path):
    api = _client(tmp_path)
    api.post("/morning/tier", json={"enabled": True})
    episode = api.post("/morning/episodes", json={"label": "Synthetic demo"}).json()
    started = time.perf_counter()
    seeked = api.post(
        f"/morning/episodes/{episode['id']}/vitals/sim",
        json={"action": "seek", "t_ms": 240_000, "step_ms": 60_000},
    )
    elapsed = time.perf_counter() - started
    assert seeked.status_code == 200
    cards = [event for event in seeked.json()["events"] if event["event_type"] == "vitals.card"]
    assert len(cards) == 1
    assert cards[0]["ts_ms"] == 240_000
    assert elapsed < 0.5
    card = api.get(f"/morning/episodes/{episode['id']}/card")
    assert card.json()["banner"] == "Research demo. Not for clinical use."
