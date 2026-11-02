"""Archived with the routes they test (spec §9 "Archiving", Task 16). Not collected: pytest testpaths is backend/tests.

Original file: backend/tests/test_rest.py. These ran against routes that no longer exist and are kept for reference, not run.
The care-app features they map to have the §9 row tests in the plan appendix; the discharge-tier, PDF-encoding and
nudge-wording checks are re-pinned in backend/tests/test_kept_coverage.py. Not every old edge case has a care twin.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.morning.count_rules import demo_frames, fresh_state, observe, replay
from app.morning.intents import parse_pack


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


def test_routes_for_pack_replay_correction_and_sim(tmp_path):
    api = _client(tmp_path)
    episode = api.post("/morning/episodes", json={"label": "OT"}).json()
    episode_id = episode["id"]
    heard = api.post(f"/morning/episodes/{episode_id}/hear", json={"text": "opening twenty swabs"})
    assert heard.json()["kind"] == "pack"
    replayed = api.post(f"/morning/episodes/{episode_id}/count/replay")
    outs = [row for row in replayed.json()["events"] if row["event_type"] == "count.item_out"]
    assert len(outs) == 19
    closing = [row for row in replayed.json()["events"] if row["event_type"] == "count.closing"][-1]
    assert closing["payload"]["track_id"] == "swab-20"

    given = api.post(
        f"/morning/episodes/{episode_id}/druglog",
        json={"text": "ondansetron 4 mg iv"},
    ).json()["draft"]
    api.post(
        f"/morning/episodes/{episode_id}/druglog/{given['id']}/confirm",
        json={"by": "demo user"},
    )
    confirmed = [
        row
        for row in api.get(f"/morning/episodes/{episode_id}").json()["events"]
        if row["event_type"] == "druglog.given"
    ][-1]
    corrected = api.post(
        f"/morning/episodes/{episode_id}/events/{confirmed['id']}/correct",
        json={"payload": {**confirmed["payload"], "amount": 8}},
    )
    amounts = [item["amount"] for item in corrected.json()["sheet"]["drugs"]]
    assert amounts == [8]

    paused = api.post(
        f"/morning/episodes/{episode_id}/vitals/sim",
        json={"action": "tick", "step_ms": 120_000},
    )
    assert paused.json()["sim"]["emitted"] == []
    seek = api.post(
        f"/morning/episodes/{episode_id}/vitals/sim",
        json={"action": "seek", "t_ms": 60_000},
    )
    readings = [row for row in seek.json()["events"] if row["event_type"] == "vitals.reading"]
    assert [row["payload"]["systolic"] for row in readings] == [120, 118]
    assert "vitals.card" not in {row["event_type"] for row in seek.json()["events"]}


def test_camera_count_is_filed_on_one_patient(tmp_path):
    api = _client(tmp_path)
    case = api.post("/cases", json={"label": "Prop tray", "item_types": ["lap sponge"]}).json()
    uploaded = api.post(f"/cases/{case['id']}/upload", params={"scenario": "demo"})
    assert uploaded.status_code == 200
    episode = api.post("/morning/episodes", json={"label": "Synthetic, camera"}).json()
    filed = api.post(
        f"/morning/episodes/{episode['id']}/count/from-case",
        json={"case_id": case["id"]},
    )
    assert filed.status_code == 200
    count = filed.json()["sheet"]["count"]
    assert count["source"] == "camera"
    assert count["case_id"] == case["id"]
    assert count["unaccounted"] == 1
    assert count["opened"] == 10
    again = api.post(
        f"/morning/episodes/{episode['id']}/count/from-case",
        json={"case_id": case["id"]},
    )
    assert again.json()["already_filed"] is True
    closings = [row for row in again.json()["events"] if row["event_type"] == "count.closing"]
    assert len(closings) == 1


def test_two_patients_do_not_share_a_morning(tmp_path):
    api = _client(tmp_path)
    first = api.post("/morning/episodes", json={"label": "Synthetic, A"}).json()
    second = api.post("/morning/episodes", json={"label": "Synthetic, B"}).json()
    api.post(f"/morning/episodes/{first['id']}/hear", json={"text": "opening twenty swabs"})
    other = api.get(f"/morning/episodes/{second['id']}").json()
    assert other["guide"]["patient"] == "Synthetic, B"
    assert other["guide"]["done"] == 0
    assert "this patient only" in other["guide"]["rule"]
    listed = api.get("/morning/episodes").json()["episodes"]
    assert {row["label"] for row in listed} >= {"Synthetic, A", "Synthetic, B"}


def test_photo_without_a_key_stays_on_the_machine(tmp_path):
    api = _client(tmp_path)
    episode = api.post("/morning/episodes", json={}).json()
    photo = api.post(
        f"/morning/episodes/{episode['id']}/brownbag/photo",
        files={"file": ("strip.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert photo.status_code == 200
    assert photo.json()["status"] == "no_model"
    grounded = api.post(
        f"/morning/episodes/{episode['id']}/brownbag/text",
        json={"text": '{"strips":[{"name":"metoprolol","strength":"25 mg"}]}'},
    )
    meds = grounded.json()["sheet"]["opd"]
    assert meds[0]["generic"] == "metoprolol"
    assert meds[0]["drug_class"] == "beta-blocker"


def test_strip_photo_filename_is_sanitised(tmp_path):
    data = tmp_path / "data"
    api = _client(data)
    episode = api.post("/morning/episodes", json={}).json()
    photo = api.post(
        f"/morning/episodes/{episode['id']}/brownbag/photo",
        files={"file": ("../../evil.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert photo.status_code == 200
    assert photo.json()["saved"] == "evil.jpg"
    folder = data / "strips" / episode["id"]
    assert (folder / "evil.jpg").exists()
    escaped = [path for path in tmp_path.rglob("evil.jpg") if path.parent != folder]
    assert escaped == []
    bare = api.post(
        f"/morning/episodes/{episode['id']}/brownbag/photo",
        files={"file": ("..", b"\xff\xd8\xff\xd9", "image/jpeg")},
    )
    assert bare.json()["saved"] == "strip.jpg"
