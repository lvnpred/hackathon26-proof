"""Evidence for every model point (care-app clarity §4.2): each model result's event carries `evidence` with what
went in (captured), what the model returned, and how the app used it. Recordings are kept for playback, served only
to their own episode. No evidence carries a key, a token or a header.
"""

from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest

from app.adapters.spark import SparkAdapter
from app.journey import live
from app.journey.evidence_payload import RAW_MAX, evidence_of
from app.morning.brownbag import read_strip
from tests.test_camera_extras import _sentences
from tests.test_count_gate_paths import _begin_with_pack, _camera, _new_patient, _post_json
from tests.test_flow_states import _count, _move, _new, _to_theatre, _to_ward
from tests.test_flow_tasks import DOSE, NURSE, _ack, _sign, _url

DOC = "Dr. A. Rao (synthetic)"
PNG = b"\x89PNG\r\n\x1a\nfake"
SECRET = "sk-test-SECRET-key-0123456789"
PARTS = ("captured", "returned", "used")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _of(client, eid, kind):
    return [e for e in client.app.state.morning.events(eid) if e["event_type"] == kind]


def _shape(ev: dict) -> dict:
    assert all(part in ev for part in PARTS), ev
    assert set(ev["returned"]) >= {"model", "mode", "ms", "raw"}
    assert ev["returned"]["mode"] in ("live", "prepared", "failed", "none")
    assert isinstance(ev["calls"], list)
    return ev


def _keyed(client):
    client.app.state.settings = replace(client.app.state.settings, meta_api_key=SECRET)


def _audio(client, eid, tail, name, **form):
    files = {"file": (name, b"RIFF-" + name.encode(), "audio/wav")}
    return client.post(_url(eid, tail), data={"by": DOC, **form}, files=files)


# --- the helper -----------------------------------------------------------------------------------------------

def test_evidence_of_shape_names_and_truncation():
    calls = [{"model": "voice", "model_id": "v", "source": "prepared", "ms": None},
             {"model": "spark", "model_id": "s", "source": "muse-spark-1.3", "ms": 812}]
    ev = evidence_of("x", inputs={"transcript": "hi"}, reply="y" * (RAW_MAX + 50), used={"items": []}, calls=calls)
    assert ev["captured"] == {"transcript": "hi"} and ev["used"] == {"items": []}
    assert ev["returned"] == {"model": "Spark 1.3", "mode": "live", "ms": 812, "raw": "y" * RAW_MAX}
    assert evidence_of("x", inputs={}, reply="ignored", used={}, calls=[])["returned"] == {
        "model": "rules", "mode": "none", "ms": None, "raw": None}  # no model asked: "No model used — drafted by rules"
    names = {m: evidence_of("x", inputs={}, reply=None, used={}, calls=[{"model": m, "source": "prepared", "ms": 1}])
             ["returned"]["model"] for m in ("sam", "spark", "spark-open", "voice")}
    assert names == {"sam": "SAM 3.1", "spark": "Spark 1.3", "spark-open": "Spark Open", "voice": "Muse Voice"}
    failed = evidence_of("x", inputs={}, reply=None, used={}, calls=[{"model": "spark", "source": "unavailable", "ms": 3}])
    assert failed["returned"]["mode"] == "failed"


def test_evidence_of_drops_secrets():
    ev = evidence_of("x", inputs={"api_key": SECRET, "headers": {"Authorization": "Bearer abc"}, "text": f"Bearer {SECRET}"},
                     reply=f"token {SECRET}", used={"key": "paracetamol", "token": SECRET}, calls=[])
    dumped = json.dumps(ev)
    assert SECRET not in dumped and "Bearer abc" not in dumped
    assert ev["used"]["key"] == "paracetamol"  # a medicine key is data, not a secret


# --- theatre: card, heard drug and pack, recording kept --------------------------------------------------------

def _drop(client, eid):
    client.app.state.morning.append(eid, "brownbag.med_found", read_strip("metoprolol", "25 mg"), ts_ms=0)
    assert _count(client, eid, "opened", quantity=20).status_code == 200
    for _ in range(4):
        assert client.post(_url(eid, "theatre/vitals/step"), json={}).status_code == 200


def test_theatre_card_carries_evidence_template(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    client.post(_url(eid, "theatre/tier"), json={"on": True})
    _drop(client, eid)
    [card] = _of(client, eid, "vitals.card")
    ev = _shape(card["payload"]["evidence"])
    assert ev["captured"]["template"] == card["payload"]["template"] and ev["captured"]["facts"]
    assert ev["used"]["text"] == card["payload"]["text"] and ev["used"]["fallback"] == "template"
    assert (ev["returned"]["mode"], ev["returned"]["model"]) == ("none", "rules")  # SPARK_LIVE off: no model asked


def test_theatre_card_keeps_the_raw_spark_reply(tmp_path, monkeypatch):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    _keyed(client)
    monkeypatch.setattr(live, "spark_text", lambda settings, prompt: "Please give fluids now.")  # fails the wording check
    client.post(_url(eid, "theatre/tier"), json={"on": True})
    _drop(client, eid)
    ev = _shape(_of(client, eid, "vitals.card")[0]["payload"]["evidence"])
    assert ev["returned"]["raw"] == "Please give fluids now." and ev["returned"]["model"] == "Spark 1.3"
    assert ev["used"]["fallback"] == "template"
    assert SECRET not in json.dumps(ev)


def test_typed_drug_and_pack_carry_evidence(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    client.post(_url(eid, "theatre/drug"), data={"text": "lignocaine two percent, five ml, local infiltration", "by": DOC})
    client.post(_url(eid, "theatre/drug"), data={"text": "opening twenty swabs", "by": DOC})
    drug = _shape(_of(client, eid, "druglog.parsed")[0]["payload"]["evidence"])
    assert drug["captured"]["transcript"].startswith("lignocaine") and drug["captured"]["audio_id"] is None
    assert drug["used"]["heard_as"] == "drug" and drug["used"]["row"]["generic"] == "lignocaine"
    pack = _shape(_of(client, eid, "count.pack_heard")[0]["payload"]["evidence"])
    assert pack["used"]["heard_as"] == "pack" and pack["used"]["row"]["n"] == 20
    assert (drug["returned"]["mode"], drug["returned"]["model"]) == ("none", "rules")  # typed: no model heard it


def test_spoken_drug_keeps_its_recording_for_its_own_episode_only(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    assert _audio(client, eid, "theatre/drug", "drug-lignocaine.wav").status_code == 200
    ev = _shape(_of(client, eid, "druglog.parsed")[0]["payload"]["evidence"])
    audio_id = ev["captured"]["audio_id"]
    assert audio_id and ev["returned"]["model"] == "Muse Voice" and ev["returned"]["mode"] == "prepared"
    got = client.get(_url(eid, f"audio/{audio_id}"))
    assert got.status_code == 200 and got.content == b"RIFF-drug-lignocaine.wav"
    assert got.headers["content-type"].startswith("audio/wav")
    other = client.post("/journey/episodes", json={"label": "Synthetic demo, S. Iyer"}).json()["id"]
    assert client.get(_url(other, f"audio/{audio_id}")).status_code == 404  # another patient's recording
    assert client.get(_url(eid, "audio/" + "0" * 32)).status_code == 404
    assert client.get(_url(eid, "audio/..%2F..%2Fsecrets")).status_code == 404
    kept = list(tmp_path.rglob(f"{audio_id}.audio.*"))
    assert len(kept) == 1 and tmp_path in kept[0].parents  # the data dir, never the repo


# --- proof verdict ------------------------------------------------------------------------------------------

def _admitting(tmp_path):
    client, eid = _new(tmp_path)
    assert _move(client, eid, "admitting", reason="Hernia repair").status_code == 200
    return client, eid


def _band(client, eid):
    return client.post(_url(eid, "checks/admission:band/photo"), data={"by": NURSE, "at_ms": 0},
                       files={"file": ("any.png", PNG, "image/png")})


def test_proof_verdict_carries_evidence_prepared(tmp_path):
    client, eid = _admitting(tmp_path)
    assert _band(client, eid).status_code == 200
    [photo] = _of(client, eid, "check.photo")
    ev = _shape(photo["payload"]["evidence"])
    assert ev["captured"]["photo_id"] == photo["payload"]["photo_id"] and ev["captured"]["expect"]
    assert ev["used"]["verdict"] == photo["payload"]["verdict"] and ev["returned"]["mode"] == "prepared"


def test_proof_verdict_keeps_the_raw_reply_live(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _keyed(client)
    reply = '{"verdict": "not_accepted", "why": "No wristband visible"}'
    monkeypatch.setattr(SparkAdapter, "_ask", lambda self, prompt, image=None, **k: reply)
    assert _band(client, eid).status_code == 200
    ev = _shape(_of(client, eid, "check.photo")[0]["payload"]["evidence"])
    assert ev["returned"] == {**ev["returned"], "model": "Spark 1.3", "mode": "live", "raw": reply}
    assert ev["used"]["verdict"] == "not_accepted"
    assert SECRET not in json.dumps(ev)


def test_proof_verdict_failed_call_says_failed(tmp_path, monkeypatch):
    client, eid = _admitting(tmp_path)
    _keyed(client)
    monkeypatch.setattr(SparkAdapter, "_ask", lambda self, prompt, image=None, **k: "not json")
    _band(client, eid)
    ev = _shape(_of(client, eid, "check.photo")[0]["payload"]["evidence"])
    assert ev["returned"]["mode"] == "failed" and ev["used"]["verdict"] == "not_checked"


# --- dictation, the nurse's task voice, the Ask answer --------------------------------------------------------

def test_dictated_orders_keep_audio_and_transcript(tmp_path):
    client, eid = _new(tmp_path)
    assert _audio(client, eid, "dictate/orders", "kumar-orders.wav").status_code == 200
    [draft] = _of(client, eid, "order.drafted")
    ev = _shape(draft["payload"]["evidence"])
    assert ev["captured"]["transcript"] == draft["payload"]["transcript"] and ev["captured"]["audio_id"]
    assert ev["used"]["items"] == draft["payload"]["items"] and ev["used"]["fallback"] == "rules"
    assert client.get(_url(eid, f"audio/{ev['captured']['audio_id']}")).status_code == 200


def test_dictated_discharge_carries_evidence(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    assert _audio(client, eid, "dictate/discharge", "kumar-discharge.wav").status_code == 200
    ev = _shape(_of(client, eid, "discharge.drafted")[-1]["payload"]["evidence"])
    assert ev["captured"]["audio_id"] and ev["used"]["sections"]


def test_task_voice_returns_evidence(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    order = _sign(client, eid, [{**DOSE, "every_h": None}]).json()["order_list"][0]
    _ack(client, eid, order["id"])
    heard = _audio(client, eid, "dictate/task", "kumar-paracetamol.wav").json()
    ev = _shape(heard["evidence"])
    assert ev["captured"]["audio_id"] and ev["captured"]["transcript"] == heard["transcript"]
    assert ev["used"]["task_ids"] == [c["id"] for c in heard["candidates"]]


def test_ask_hear_keeps_audio_and_the_answer_cites_it(tmp_path):
    client, eid = _new(tmp_path)
    heard = _audio(client, eid, "ask/hear", "rao-answer.wav").json()
    ev = _shape(heard["evidence"])
    assert heard["audio_id"] == ev["captured"]["audio_id"] and ev["captured"]["transcript"] == heard["text"]
    assert ev["returned"]["model"] == "Muse Voice"
    assert client.get(_url(eid, f"audio/{heard['audio_id']}")).status_code == 200
    asked = client.post(_url(eid, "ask/doctor"), json={"text": "Is the wound healing?"})
    assert asked.status_code == 200, asked.text
    [question] = _of(client, eid, "question.asked")
    answer = {"text": heard["text"], "by": DOC, "via": "voice", "heard_by": heard["heard_by"]}
    other = client.post("/journey/episodes", json={"label": "Synthetic demo, S. Iyer"}).json()["id"]
    foreign = _audio(client, other, "ask/hear", "rao-answer.wav").json()["audio_id"]
    url = _url(eid, f"questions/{question['id']}/answer")
    assert client.post(url, json={**answer, "audio_id": foreign}).status_code == 422  # another patient's recording
    edited = {**answer, "text": heard["text"] + " Call if it gets worse."}
    assert client.post(url, json={**edited, "audio_id": heard["audio_id"]}).status_code == 200
    cited = _shape(_of(client, eid, "question.answered")[0]["payload"]["evidence"])
    assert cited["captured"]["audio_id"] == heard["audio_id"] and cited["returned"]["model"] == "Muse Voice"
    assert cited["captured"]["transcript"] == heard["text"]  # what Muse Voice heard, kept beside the recording
    assert cited["captured"]["answer"] == edited["text"] and cited["used"]["edited"] is True


# --- handover, discharge wording, camera explanation ---------------------------------------------------------

def test_handover_carries_evidence(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    client.app.state.handover_write = lambda prompt: "Patient: nothing new at all, added 99 mg."
    _keyed(client)
    assert client.post(_url(eid, "handover"), json={"from_nurse": "A", "to_nurse": "B"}).status_code == 200
    ev = _shape(_of(client, eid, "handover.drafted")[0]["payload"]["evidence"])
    assert ev["captured"]["facts"] and ev["returned"]["raw"] == "Patient: nothing new at all, added 99 mg."
    assert ev["used"]["fallback"] == "template" and ev["returned"]["mode"] == "failed"
    assert SECRET not in json.dumps(ev)


def test_discharge_wording_carries_evidence(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    assert client.post(_url(eid, "discharge/draft"), json={"by": DOC}).status_code == 200
    ev = _shape(_of(client, eid, "discharge.drafted")[-1]["payload"]["evidence"])
    assert ev["captured"]["facts"] and ev["used"]["fallback"] == "template" and ev["used"]["summary"]


def test_camera_explanation_carries_evidence(tmp_path):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")
    assert _post_json(client, eid, "/camera/close", {"by": NURSE}).status_code == 200
    ev = _shape(_of(client, eid, "camera.closed")[0]["payload"]["evidence"])
    assert ev["captured"]["case_id"] and ev["used"]["text"] and ev["used"]["fallback"] == "template"
    assert (ev["returned"]["mode"], ev["returned"]["model"]) == ("none", "rules")  # no writer configured


def test_no_event_evidence_carries_the_key(tmp_path, monkeypatch):
    client, eid = _new(tmp_path)
    _keyed(client)
    monkeypatch.setattr(live, "spark_text", lambda settings, prompt: f"Bearer {SECRET}")
    client.post(_url(eid, "dictate/orders"), data={"by": DOC, "text": "paracetamol one gram every six hours"})
    rows = [e["payload"]["evidence"] for e in client.app.state.morning.events(eid) if "evidence" in e["payload"]]
    assert rows and SECRET not in json.dumps(rows)


def test_unusable_reply_is_failed_with_rules_fallback(tmp_path, monkeypatch):
    client, eid = _new(tmp_path)
    _keyed(client)
    monkeypatch.setattr(live, "spark_text", lambda settings, prompt: "not a list of orders")
    client.post(_url(eid, "dictate/orders"), data={"by": DOC, "text": "paracetamol one gram every six hours"})
    ev = _shape(_of(client, eid, "order.drafted")[0]["payload"]["evidence"])
    assert ev["returned"]["mode"] == "failed" and ev["returned"]["model"] == "Spark 1.3"
    assert ev["used"]["fallback"] == "rules" and ev["returned"]["raw"] == "not a list of orders"


def test_rules_only_dictation_says_no_model(tmp_path):
    client, eid = _new(tmp_path)
    client.post(_url(eid, "dictate/orders"), data={"by": DOC, "text": "paracetamol one gram every six hours"})
    ev = _shape(_of(client, eid, "order.drafted")[0]["payload"]["evidence"])
    assert (ev["returned"]["mode"], ev["returned"]["model"]) == ("none", "rules") and ev["used"]["fallback"] == "rules"


def _hears(monkeypatch, text):
    heard = {"text": text, "source": "prepared", "calls": [{"model": "voice", "model_id": "v", "source": "prepared", "ms": 5}]}
    monkeypatch.setattr(live, "transcribe", lambda *a, **k: dict(heard))


def test_refused_lines_keep_no_recording(tmp_path, monkeypatch):
    client, eid = _new(tmp_path)
    _hears(monkeypatch, "...")
    assert _audio(client, eid, "dictate/orders", "any.wav").status_code == 422  # nothing to draft
    _to_theatre(client, eid)
    _hears(monkeypatch, "five ml")
    assert _audio(client, eid, "theatre/drug", "any.wav").status_code == 422  # no medicine name
    assert list(tmp_path.rglob("*.audio.*")) == [] and list(tmp_path.rglob("*.heard.json")) == []


def _camera_closed(tmp_path, monkeypatch, write=None, **keys):
    client, eid = _new_patient(tmp_path)
    _begin_with_pack(client, eid)
    _camera(client, eid, "clip2")
    if write is not None:
        monkeypatch.setattr(SparkAdapter, "write", write)
    client.app.state.settings = replace(client.app.state.settings, **keys)
    assert _post_json(client, eid, "/camera/close", {"by": NURSE}).status_code == 200
    return client, _shape(_of(client, eid, "camera.closed")[0]["payload"]["evidence"])


def test_camera_explanation_failed_call_is_failed_not_prepared(tmp_path, monkeypatch):
    def down(self, prompt):
        raise RuntimeError("down")

    _, ev = _camera_closed(tmp_path, monkeypatch, down, meta_api_key=SECRET)
    assert ev["returned"]["mode"] == "failed" and ev["returned"]["model"] == "Spark 1.3"
    assert ev["used"]["fallback"] == "template" and ev["used"]["why"] == "model call failed (RuntimeError)"
    assert isinstance(ev["returned"]["ms"], int) and SECRET not in json.dumps(ev)


def test_camera_explanation_unusable_reply_is_failed(tmp_path, monkeypatch):
    _, ev = _camera_closed(tmp_path, monkeypatch, lambda self, prompt: "Please give fluids.", meta_api_key=SECRET)
    assert ev["returned"]["mode"] == "failed" and ev["used"]["why"] == "model reply not usable"
    assert ev["used"]["fallback"] == "template"


def test_camera_explanation_live_writer_is_live(tmp_path, monkeypatch):
    _, ev = _camera_closed(tmp_path, monkeypatch, lambda self, prompt: _sentences(prompt), meta_api_key=SECRET)
    assert (ev["returned"]["mode"], ev["returned"]["model"]) == ("live", "Spark 1.3") and ev["returned"]["raw"]
    assert ev["used"]["fallback"] is None and ev["calls"][0]["source"] == "muse-spark-1.3"
