"""Morning modules from the hackathon pack. No clinic-app code."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.morning.druglog import parse_drug_phrase
from app.morning.vitals import choose_wording, demo_readings, evaluate, wording_ok
from app.morning.discharge import fold


PHRASES = [
    ("lignocaine two percent, five ml, local infiltration", "lignocaine", 5, "ml", "2%", "local infiltration", True),
    ("fentanyl 50 micrograms iv", "fentanyl", 50, "mcg", None, "iv", True),
    ("ceftriaxone one gram intravenous", "ceftriaxone", 1, "g", None, "iv", True),
    ("ondansetron 4 mg iv", "ondansetron", 4, "mg", None, "iv", True),
    ("xyzolone 10 mg oral", None, 10, "mg", None, "oral", False),
]


def test_five_drug_phrases():
    for text, generic, amount, unit, strength, route, grounded in PHRASES:
        parsed = parse_drug_phrase(text)
        assert parsed["generic"] == generic
        assert parsed["amount"] == amount
        assert parsed["unit"] == unit
        assert parsed["strength"] == strength
        assert parsed["route"] == route
        assert parsed["grounded"] is grounded
        assert parsed["confirmed"] is False


def test_bp_drop_fires_once_per_cooldown():
    readings = demo_readings()
    first = evaluate(readings)
    drop = [row for row in first if row["rule_id"] == "bp_drop_pct"]
    assert len(drop) == 1
    assert drop[0]["drop_pct"] == 28
    assert drop[0]["span_min"] == 4
    assert drop[0]["hr_flat"] is True
    second = evaluate(readings, last_fired={"bp_drop_pct": readings[-1].ts_ms})
    assert [row for row in second if row["rule_id"] == "bp_drop_pct"] == []


def test_wording_check_keeps_the_template():
    template = "BP 86/50, down 28% in 4 min. lignocaine 5 ml 3 min ago (voice log)."
    assert wording_ok("BP 86/50, down 28% in 4 min. lignocaine 5 ml.", template)
    bad_number = "BP 86/50, down 40% in 4 min."
    advice = "Consider giving a fluid bolus."
    assert wording_ok(bad_number, template) is False
    assert wording_ok(advice, template) is False
    text, source = choose_wording(template, advice)
    assert source == "template"
    assert text == template


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
