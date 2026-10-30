"""Every model result names the models it asked: {model, model_id, source, ms} (C1, R2-R6)."""

from __future__ import annotations

import re

import pytest

from app.adapters.voice import VoiceAdapter
from app.journey import live
from app.journey.handover import draft
from tests.test_flow_states import _new, _to_ward
from tests.test_flow_tasks import DOC, DOSE, NURSE, _ack, _done, _sign, _url
from tests.test_p3_video import _keyed, _no_key, no_network  # noqa: F401  (no_network is autouse)


def _last(client, eid, kind):
    return [e for e in client.app.state.morning.events(eid) if e["event_type"] == kind][-1]


def test_transcribe_carries_one_voice_call(tmp_path, monkeypatch):
    out = live.transcribe(_no_key(tmp_path), b"x", "kumar-orders.wav", "audio/wav")
    assert out["calls"] == [{"model": "voice", "model_id": "muse-voice-transcribe-1.0", "source": "prepared", "ms": None}]
    monkeypatch.setattr(live, "to_wav", lambda raw, kind: raw)
    monkeypatch.setattr(VoiceAdapter, "transcribe", lambda self, path, offset, kind: [{"text": "hi", "t0_ms": 0, "t1_ms": 1}])
    call = live.transcribe(_keyed(tmp_path), b"x", "a.wav", "audio/wav")["calls"][0]
    assert call["source"] == "muse-voice-transcribe" and isinstance(call["ms"], int) and call["ms"] >= 0


def test_nothing_read_is_no_call(tmp_path):
    assert live.segment_clip(_no_key(tmp_path), tmp_path / "x.mp4", "unknown.mp4", ["scissors"])["calls"] == []
    assert live.read_photo(_no_key(tmp_path), "strip", b"x", "unknown.png", "image/png")["calls"] == []


def test_prepared_photo_read_is_a_sam_and_a_spark_call(tmp_path):
    calls = live.read_photo(_no_key(tmp_path), "monitor", b"x", "monitor-88-54.png", "image/png")["calls"]
    assert [(c["model"], c["source"]) for c in calls] == [("sam", "prepared"), ("spark", "prepared")]


def test_mode_of():
    assert [live.mode_of(s) for s in ("sam-3.1", "prepared", live.FALLBACK, "failed", "rules (model reply not usable)", "rules", "typed")] == [
        "live", "prepared", "failed", "failed", "failed", None, None]


def test_dictated_orders_record_the_voice_call_and_no_rules_call(tmp_path):
    client, eid = _new(tmp_path)
    r = client.post(f"/journey/episodes/{eid}/dictate/orders", data={"by": DOC, "at_ms": "0"},
                    files={"file": ("kumar-orders.wav", b"RIFF0000WAVE", "audio/wav")})
    assert r.status_code == 200
    drafted = _last(client, eid, "order.drafted")
    assert [(c["model"], c["source"]) for c in drafted["payload"]["calls"]] == [("voice", "prepared")]


def test_typed_text_has_no_call_and_a_named_hearer_has_one_untimed(tmp_path):
    client, eid = _new(tmp_path)
    url = f"/journey/episodes/{eid}/dictate/orders"
    client.post(url, data={"by": DOC, "text": "Paracetamol 1 g every 6 hours", "at_ms": "0"})
    assert _last(client, eid, "order.drafted")["payload"]["calls"] == []
    client.post(url, data={"by": DOC, "text": "Paracetamol 1 g every 6 hours", "heard_by": "prepared", "at_ms": "0"})
    assert _last(client, eid, "order.drafted")["payload"]["calls"] == [
        {"model": "voice", "model_id": "muse-voice-transcribe-1.0", "source": "prepared", "ms": None}]


def test_keyed_structure_failure_is_a_failed_spark_call(tmp_path, monkeypatch):
    from app.journey import media_api

    monkeypatch.setattr(live, "spark_text", lambda settings, prompt: "not usable")
    _, source, calls = media_api._structure(_keyed(tmp_path), "p", "t", lambda reply, said: None, lambda said: {"x": 1})
    assert source == "rules (model reply not usable)"
    assert [(c["model"], c["source"]) for c in calls] == [("spark", source)] and calls[0]["ms"] >= 0
    _, source, calls = media_api._structure(_no_key(tmp_path), "p", "t", lambda reply, said: None, lambda said: {"x": 1})
    assert (source, calls) == ("rules", [])


def test_bot_answer_carries_the_structure_calls(tmp_path):
    client, eid = _new(tmp_path)
    client.post(f"/journey/episodes/{eid}/ask/bot", json={"text": "What did the doctor say?"})
    assert _last(client, eid, "question.answered")["payload"]["calls"] == []  # no key: rules, no call


def test_task_done_by_voice_records_heard_by(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    order = _sign(client, eid, [DOSE]).json()["order_list"][0]
    tasks = _ack(client, eid, order["id"]).json()["tasks"]
    voice = {"via": "voice", "transcript": "x", "heard_by": "prepared"}
    assert _done(client, eid, tasks[0]["id"], **voice).status_code == 200
    done = _last(client, eid, "task.done")["payload"]
    assert done["heard_by"] == "prepared"
    assert done["calls"] == [{"model": "voice", "model_id": "muse-voice-transcribe-1.0", "source": "prepared", "ms": None}]


def test_task_done_with_a_made_up_hearer_stores_none(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    order = _sign(client, eid, [DOSE]).json()["order_list"][0]
    tasks = _ack(client, eid, order["id"]).json()["tasks"]
    assert _done(client, eid, tasks[0]["id"], via="voice", transcript="x", heard_by="made-up").status_code == 200
    done = _last(client, eid, "task.done")["payload"]
    assert done["heard_by"] == "" and done["calls"] == []


def test_handover_records_one_spark_call_only_when_asked(tmp_path):
    kwargs = dict(patient="P", since_ms=0, at_ms=1, from_nurse="A", to_nurse="B", settings=_keyed(tmp_path))
    assert draft([], use_model=False, **kwargs)["calls"] == []
    failed = draft([], write=lambda prompt: "Give 5 mg now.", **kwargs)
    assert [(c["model"], c["source"]) for c in failed["calls"]] == [("spark", "failed")]
    assert isinstance(failed["calls"][0]["ms"], int)
    lines_text = draft([], use_model=False, **kwargs)["lines"][0]["text"]
    used = draft([], write=lambda prompt: lines_text, **kwargs)
    assert [(c["model"], c["model_id"], c["source"]) for c in used["calls"]] == [("spark", "muse-spark-1.3", "muse-spark-1.3")]


def _pairs(calls):
    return [(c["model"], c["source"]) for c in calls]


def test_keyless_handover_asked_for_the_model_records_no_call(tmp_path):
    out = draft([], patient="P", since_ms=0, at_ms=1, from_nurse="A", to_nurse="B", settings=_no_key(tmp_path))
    assert out["calls"] == [] and out["wording"] == "template"


def test_segment_photos_calls(tmp_path, monkeypatch):
    from app.adapters.sam import SamAdapter

    photo = tmp_path / "a.png"
    photo.write_bytes(b"\x89PNG")
    prepared = live.segment_photos(_no_key(tmp_path), [photo], ["retractor"], "tray-hernia.png")
    assert _pairs(prepared["calls"]) == [("sam", "prepared")]
    assert live.segment_photos(_no_key(tmp_path), [photo], ["retractor"], "unknown.png")["calls"] == []
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: [])
    keyed = live.segment_photos(_keyed(tmp_path), [photo], ["retractor"], "unknown.png")
    assert _pairs(keyed["calls"]) == [("sam", "sam-3.1")] and keyed["calls"][0]["ms"] >= 0


def test_tray_and_setup_checks_record_the_sam_call(tmp_path):
    from tests.test_p3_setup import SALINE, _ward
    from tests.test_p3_tray import _to_theatre
    from tests.test_p4_photo_checks import _checked, _photos

    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    assert _photos(client, eid).status_code == 200
    assert _pairs(_checked(client, eid, "tray.checked")["calls"]) == [("sam", "prepared")]
    client, eid = _new(tmp_path / "setup")
    task = _ward(client, eid, [SALINE])[SALINE["text"]]
    assert _photos(client, eid, ("saline-setup.png",), check="setup", task_id=task).status_code == 200
    assert _pairs(_checked(client, eid, "setup.checked")["calls"]) == [("sam", "prepared")]


def test_proof_check_records_the_sam_and_spark_calls(tmp_path):
    from tests.test_p2_photos import _photo, _ward as _ward_tasks

    client, eid = _new(tmp_path)
    task = _ward_tasks(client, eid, [DOSE])[0]
    assert _photo(client, eid, task_id=task["id"]).status_code == 200
    assert _pairs(_last(client, eid, "proof.checked")["payload"]["calls"]) == [("sam", "prepared"), ("spark", "prepared")]


def test_medicines_photo_records_the_sam_and_spark_calls(tmp_path):
    from tests.test_care_demo import _client
    from tests.test_p4_ask import _home, _patients
    from tests.test_p4_medicines import _post

    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    _home(client, kumar)
    assert _post(client, kumar).status_code == 200
    assert _pairs(_last(client, kumar, "medicines.read")["payload"]["calls"]) == [("sam", "prepared"), ("spark", "prepared")]


def test_doctor_answer_by_voice_records_one_untimed_voice_call(tmp_path):
    from tests.test_care_demo import _client
    from tests.test_p4_ask import _ask, _patients

    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    assert _ask(client, kumar, "When is my review?", to="doctor").status_code == 200
    qid = _last(client, kumar, "question.asked")["id"]
    body = {"text": "Next week.", "by": DOC, "via": "voice", "heard_by": "prepared", "at_ms": 2000}
    assert client.post(_url(kumar, f"questions/{qid}/answer"), json=body).status_code == 200
    assert _last(client, kumar, "question.answered")["payload"]["calls"] == [
        {"model": "voice", "model_id": "muse-voice-transcribe-1.0", "source": "prepared", "ms": None}]


def test_keyed_bot_answer_records_a_timed_spark_call(tmp_path, monkeypatch):
    from dataclasses import replace

    from tests.test_care_demo import _client
    from tests.test_p4_ask import _ask, _patients

    client = _client(tmp_path)
    kumar = _patients(client)["4"]
    client.app.state.settings = replace(client.app.state.settings, meta_api_key="test-key")
    monkeypatch.setattr(live, "spark_text", lambda settings, prompt: "unusable reply")
    assert _ask(client, kumar, "What did the doctor say?").status_code == 200
    calls = _last(client, kumar, "question.answered")["payload"]["calls"]
    assert _pairs(calls) == [("spark", "rules (model reply not usable)")] and calls[0]["ms"] >= 0
