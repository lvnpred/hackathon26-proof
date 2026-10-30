"""The "AI at work" summary, the Try sample routes and the samples allow-list (Task 7)."""

from __future__ import annotations

import re

from app.journey.ai_summary import MODELS, summary
from tests.test_flow_states import _new

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
S = lambda src, ms, m="sam": {"model": m, "model_id": "x", "source": src, "ms": ms}
EP = {"id": "e1", "label": "R. Kumar, 58 M (synthetic)"}
OFF = {"voice": False, "spark": False, "sam": False, "spark-open": False}


def ev(kind, calls, ts, evidence_id=None):
    return {"id": f"{kind}-{ts}", "episode_id": "e1", "event_type": kind, "ts_ms": ts,
            "payload": {"calls": calls, "by": "N", "why": "w", **({"evidence_id": evidence_id} if evidence_id else {})}}


def test_summary_folds_calls_per_model():
    events = [ev("tray.checked", [S("sam-3.1", 3000)], 10), ev("tray.checked", [S("prepared", None)], 20, "a" * 32), ev("setup.checked", [S("sam-3.1", 1000)], 30)]
    out = summary([(EP, events)], OFF)
    assert [m["key"] for m in out["models"]] == ["voice", "spark", "sam", "spark-open"]
    sam = out["models"][2]
    assert (sam["calls"], sam["median_ms"], sam["mode"], sam["last"]["event_id"]) == (3, 2000, "live", "setup.checked-30")
    assert out["recent"][0]["patient"] == "R. Kumar" and out["recent"][1]["evidence_id"] == "a" * 32


def test_mode_without_calls_follows_the_key_and_failed_wins_when_newest():
    out = summary([(EP, [ev("tray.checked", [S("prepared (live call failed)", None)], 5)])], {**OFF, "voice": True})
    by = {m["key"]: m for m in out["models"]}
    assert (by["voice"]["mode"], by["spark"]["mode"], by["sam"]["mode"]) == ("live", "prepared", "failed")
    assert by["sam"]["median_ms"] is None and by["voice"]["last"] is None


def test_recent_is_capped_and_newest_first():
    events = [ev("tray.checked", [S("sam-3.1", 1)], t) for t in range(30)]
    rows = summary([(EP, events)], OFF)["recent"]
    assert len(rows) == 20 and rows[0]["at_ms"] == 29


def test_one_event_with_two_calls_gives_two_rows_in_call_order():
    rows = summary([(EP, [ev("tray.checked", [S("sam-3.1", 1), S("muse-spark-1.3", 2, "spark")], 7)])], OFF)["recent"]
    assert [r["model"] for r in rows] == ["sam", "spark"]


def test_model_roles_have_no_advice_words():
    assert not ADVICE.search(" ".join(m["role"] for m in MODELS))


def test_summary_route_validates_ids(tmp_path):
    client, eid = _new(tmp_path)
    assert client.get("/journey/ai/summary").status_code == 422
    assert client.get("/journey/ai/summary?ids=nope").status_code == 404
    assert client.get("/journey/ai/summary?ids=" + ",".join([eid] * 11)).status_code == 422
    ok = client.get(f"/journey/ai/summary?ids={eid}")
    assert ok.status_code == 200 and ok.json()["live"] is False


def test_try_sample_without_a_key_writes_nothing(tmp_path):
    client, eid = _new(tmp_path)
    before = len(client.app.state.morning.events(eid))
    body = client.post("/journey/ai/try/sam").json()
    assert body["mode"] == "prepared" and body["evidence"]["handmade"] is True and body["evidence"]["frames"]
    assert body["evidence"]["images"][0]["url"] == "/journey/ai/samples/tray-hernia.png"
    assert body["evidence"]["rows"] and body["evidence"]["expected"]
    spark = client.post("/journey/ai/try/spark").json()
    assert spark["evidence"]["regions"] and spark["evidence"]["handmade"] is True
    assert "text" in client.post("/journey/ai/try/voice").json()
    assert len(client.app.state.morning.events(eid)) == before
    assert client.post("/journey/ai/try/other").status_code == 422
    assert not ADVICE.search(client.post("/journey/ai/try/spark-open").json()["text"])
    assert client.post("/journey/ai/try/spark-open").json()["mode"] == "Sample"


def test_samples_route_is_an_allow_list(tmp_path):
    client, _ = _new(tmp_path)
    for name in ("..%2Fsecret", "tray-hernia.mp4", "x.png", "kumar-orders.wav"):
        assert client.get(f"/journey/ai/samples/{name}").status_code == 404
