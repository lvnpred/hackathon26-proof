"""Final-review fixes for P2: proof re-check on confirm, grounding words, live fallbacks, photo bytes."""

from __future__ import annotations


import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.sam import SamAdapter
from app.adapters import spark as spark_mod
from app.adapters.voice import VoiceAdapter
from app.journey import dictation, live, proof, spoken
from app.main import create_app
from tests.test_flow_states import _new, _to_ward
from tests.test_flow_tasks import NURSE, OBS, DOSE, _ack, _done, _sign, _url
from tests.test_p2_live import _keyed, _no_key

PNG = b"\x89PNG\r\n\x1a\nfake"
JPEG = b"\xff\xd8\xff\xe0fake"
WEBP = b"RIFF\x00\x00\x00\x00WEBPfake"


def bare(result: dict) -> dict:
    """A model result without its `calls` list (covered in test_ai_calls.py)."""
    return {k: v for k, v in result.items() if k not in ("calls", "regions", "raw", "handmade")}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _ward(client, eid, items):
    _to_ward(client, eid)
    order = _sign(client, eid, items).json()["order_list"][0]
    return _ack(client, eid, order["id"]).json()["tasks"]


def _photo(client, eid, task_id, name="monitor-88-54.png", data=PNG, kind="image/png", at_ms=0, **form):
    form = {"purpose": "proof", "by": NURSE, "at_ms": at_ms, "task_id": task_id, **form}
    return client.post(_url(eid, "photos"), data=form, files={"file": (name, data, kind)})


def _done_payload(client, eid):
    return [e for e in client.app.state.morning.events(eid) if e["event_type"] == "task.done"][-1]["payload"]


# 1. the monitor photo is compared with the values the nurse confirms
def test_confirmed_values_are_compared_with_the_monitor_reading(tmp_path):
    client, eid = _new(tmp_path)
    obs = _ward(client, eid, [OBS])[0]
    shot = _photo(client, eid, obs["id"], sbp=88, dbp=54, hr=112).json()["photos"][-1]
    assert shot["check"]["match"] == "ok"
    assert _done(client, eid, obs["id"], values={"sbp": 82, "dbp": 54, "hr": 112}, proof_id=shot["id"]).status_code == 200
    done = _done_payload(client, eid)
    assert done["match"] == "mismatch"
    assert "88/54" in done["why"] and "82/54" in done["why"]


def test_photo_added_before_values_are_compared_on_confirm(tmp_path):
    client, eid = _new(tmp_path)
    obs = _ward(client, eid, [OBS])[0]
    shot = _photo(client, eid, obs["id"]).json()["photos"][-1]
    assert shot["check"]["match"] == "none"
    view = _done(client, eid, obs["id"], values={"sbp": 88, "dbp": 54, "hr": 112}, proof_id=shot["id"]).json()
    assert _done_payload(client, eid)["match"] == "ok"
    assert view["tasks"][0]["done"][0]["match"] == "ok"
    assert "88/54" in view["tasks"][0]["done"][0]["why"]


def test_unreadable_monitor_stays_none_on_confirm(tmp_path):
    client, eid = _new(tmp_path)
    obs = _ward(client, eid, [OBS])[0]
    shot = _photo(client, eid, obs["id"], name="IMG_9.png").json()["photos"][-1]
    _done(client, eid, obs["id"], values={"sbp": 88, "dbp": 54, "hr": 70}, proof_id=shot["id"])
    assert _done_payload(client, eid)["match"] == "none"


def test_photo_from_an_earlier_cycle_is_refused(tmp_path):
    client, eid = _new(tmp_path)
    dose = _ward(client, eid, [DOSE])[0]
    first = _photo(client, eid, dose["id"], name="strip-paracetamol.png").json()["photos"][-1]
    assert _done(client, eid, dose["id"], proof_id=first["id"]).status_code == 200
    again = _done(client, eid, dose["id"], at_ms=1, proof_id=first["id"])
    assert again.status_code == 409
    assert "taken before" in again.json()["detail"]
    fresh = _photo(client, eid, dose["id"], name="strip-paracetamol.png", at_ms=1).json()["photos"][-1]
    assert _done(client, eid, dose["id"], at_ms=1, proof_id=fresh["id"]).status_code == 200


# 3. a live reply with null and 0 placeholders is usable
def test_reply_with_null_and_zero_placeholders_is_used():
    tasks = [{"id": "t1", "title": "BP every 1 h", "kind": "obs", "status": "open"}]
    said = "Blood pressure 88 over 54 pulse 112 done"
    reply = '{"task_ids": ["t1"], "values": {"sbp": 88, "dbp": 54, "hr": 112, "spo2": null, "temp": 0}}'
    assert spoken.completion_from_reply(reply, tasks, said)["values"] == {"sbp": 88, "dbp": 54, "hr": 112}
    zeros = '{"task_ids": ["t1"], "values": {"sbp": 88, "dbp": 54, "hr": 112, "spo2": 0, "temp": 0}}'
    assert spoken.completion_from_reply(zeros, tasks, said)["values"] == {"sbp": 88, "dbp": 54, "hr": 112}
    invented = '{"task_ids": ["t1"], "values": {"sbp": 88, "dbp": 54, "hr": 99}}'
    assert spoken.completion_from_reply(invented, tasks, said) is None


def test_prompt_says_omit_unsaid_values():
    assert "omit" in spoken.TASK_PROMPT.lower()
    assert '"sbp": 0' not in spoken.TASK_PROMPT


# 4. direction and negation words must be said
def test_grounded_checks_negation_and_direction():
    assert not dictation.grounded("Patient not allergic to penicillin", "Patient allergic to penicillin")
    assert dictation.grounded("Patient not allergic to penicillin", "Patient is not allergic to penicillin")
    assert not dictation.grounded("Call if systolic over 90", "Call if systolic under 90")
    assert dictation.grounded("Call if systolic under 90", "Call if systolic under 90")
    assert not dictation.grounded("Review before discharge", "Review after discharge")


# 5. a failed keyed call is unavailable: no prepared result picked by the file name (spec §4)
def test_failed_transcribe_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "to_wav", lambda raw, content_type: raw)

    def boom(self, path, offset_ms=0, content_type="audio/wav"):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(VoiceAdapter, "transcribe", boom)
    for name in ("kumar-orders.wav", "recording.webm"):
        out = live.transcribe(_keyed(tmp_path), b"x", name, "audio/wav")
        assert out["source"] == "unavailable" and out["text"] is None


def test_failed_read_photo_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: [])
    def boom(self, url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(spark_mod.SparkAdapter, "read_monitor", boom)
    for name in ("monitor-88-54.png", "IMG_1.png"):
        out = live.read_photo(_keyed(tmp_path), "monitor", b"x", name, "image/png")
        assert (out["source"], out["text"]) == ("unavailable", None)


# 6a. the bytes must be the declared image type
def test_photo_bytes_must_match_declared_type(tmp_path):
    client, eid = _new(tmp_path)
    ref = {"purpose": "reference", "by": NURSE}

    def send(data, kind):
        return client.post(_url(eid, "photos"), data=ref, files={"file": ("a.img", data, kind)})

    assert send(b"fake bytes", "image/png").status_code == 400
    assert send(PNG, "image/jpeg").status_code == 400
    assert send(JPEG, "image/webp").status_code == 400
    assert send(b"RIFF\x00\x00\x00\x00WAVEfake", "image/webp").status_code == 400
    assert send(JPEG, "image/jpeg").status_code == 200
    view = send(WEBP, "image/webp").json()
    assert len(view["photos"]) == 2
    got = client.get(view["photos"][-1]["url"])
    assert got.headers["x-content-type-options"] == "nosniff"
