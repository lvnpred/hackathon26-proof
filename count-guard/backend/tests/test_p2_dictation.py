"""Dictated orders and discharge become drafts; nothing a model made is a record until signed."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.voice import VoiceAdapter
from app.journey import dictation as d, live
from app.journey.stories import plain
from app.main import create_app
from tests.test_flow_states import _move, _new, _to_ward, _view
from tests.test_p2_live import ORDERS_TEXT, _keyed

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
DOC = "Dr. A. Rao (synthetic)"
DISCHARGE_TEXT = json.load(open(live.PREPARED_DIR / "kumar-discharge.json"))["transcript"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _url(eid, tail):
    return f"/journey/episodes/{eid}/{tail}"


def _upload(client, eid, tail, name, **form):
    files = {"file": (name, b"RIFF", "audio/wav")}
    return client.post(_url(eid, tail), data={"by": DOC, "at_ms": 0, **form}, files=files)


def _typed(client, eid, tail, text, heard_by=None):
    extra = {} if heard_by is None else {"heard_by": heard_by}
    return client.post(_url(eid, tail), data={"by": DOC, "at_ms": 0, "text": text, **extra})


def _keyed_client(tmp_path):
    return TestClient(create_app(_keyed(tmp_path)))


def test_parse_kumar_orders():
    out = d.parse_order_text(ORDERS_TEXT)
    assert out["reason"] == "Open hernia repair"
    dose, obs = out["items"]
    assert (dose["kind"], dose["name"], dose["amount"], dose["every_h"], dose["proof"]) == ("dose", "paracetamol", "1 g", 6, "photo")
    assert (obs["kind"], obs["every_h"], obs["limits"], obs["proof"]) == ("obs", 1, {"sbp_min": 90}, "none")
    assert "limits" not in dose and "name" not in obs


def test_parse_iyer_saline():
    saline, obs = d.parse_order_text("Saline 1 litre over 2 hours. BP and pulse every 15 minutes.")["items"]
    assert (saline["kind"], saline["mode"]) == ("procedure", "start_end")
    assert obs["every_h"] == 0.25


def test_digits():
    assert d.digits("eighty two over fifty four") == "82 over 54"
    assert d.digits("one gram") == "1 gram"
    assert d.digits("twenty") == "20"


def test_discharge_sections_kumar():
    sections = d.discharge_sections(DISCHARGE_TEXT)
    assert [s["heading"] for s in sections] == list(d.HEADINGS)
    assert sections[-1]["text"] == "Review in clinic on day 7."


def test_discharge_section_drops_a_spoken_heading_cue():
    sections = d.discharge_sections("Diagnosis: right inguinal hernia. Review in clinic on day 7.")
    assert sections[0] == {"heading": "Diagnosis", "text": "Right inguinal hernia."}


def test_dictate_orders_prepared_no_key(tmp_path):
    client, eid = _new(tmp_path)
    view = _upload(client, eid, "dictate/orders", "kumar-orders.wav").json()
    draft = view["drafts"]["order"]
    assert len(draft["items"]) == 2 and draft["reason"] == "Open hernia repair"
    assert (draft["source"], draft["heard_by"]) == ("rules", "prepared")
    assert view["order_list"] == [] and view["tasks"] == []


def test_typed_text_and_exactly_one_input(tmp_path):
    client, eid = _new(tmp_path)
    view = _typed(client, eid, "dictate/orders", "Paracetamol one gram every six hours").json()
    assert view["drafts"]["order"]["heard_by"] == "typed"
    assert view["drafts"]["order"]["items"][0]["every_h"] == 6
    both = client.post(
        _url(eid, "dictate/orders"), data={"by": DOC, "text": "x"}, files={"file": ("a.wav", b"RIFF", "audio/wav")}
    )
    assert both.status_code == 422
    assert client.post(_url(eid, "dictate/orders"), data={"by": DOC}).status_code == 422


@pytest.mark.parametrize("hearer", ["prepared", "muse-voice-transcribe", "prepared (live call failed)"])
def test_typed_text_keeps_the_hearer_it_was_heard_by(tmp_path, hearer):
    client, eid = _new(tmp_path)
    view = _typed(client, eid, "dictate/orders", ORDERS_TEXT, heard_by=hearer).json()
    assert view["drafts"]["order"]["heard_by"] == hearer


def test_a_forged_hearer_is_stored_as_typed(tmp_path):
    client, eid = _new(tmp_path)
    view = _typed(client, eid, "dictate/orders", ORDERS_TEXT, heard_by="a doctor signed this").json()
    assert view["drafts"]["order"]["heard_by"] == "typed"


def test_hearer_is_ignored_with_a_recording(tmp_path):
    client, eid = _new(tmp_path)
    view = _upload(client, eid, "dictate/orders", "kumar-orders.wav", heard_by="forged").json()
    assert view["drafts"]["order"]["heard_by"] == "prepared"


def test_upload_checks(tmp_path):
    client, eid = _new(tmp_path)
    bad = client.post(_url(eid, "dictate/orders"), data={"by": DOC}, files={"file": ("a.png", b"x", "image/png")})
    assert bad.status_code == 400
    big = client.post(
        _url(eid, "dictate/orders"), data={"by": DOC}, files={"file": ("a.wav", b"x" * (10 * 1024 * 1024 + 1), "audio/wav")}
    )
    assert big.status_code == 400
    unknown = _upload(client, eid, "dictate/orders", "recording.wav")
    assert unknown.status_code == 409 and "Type what was said" in unknown.json()["detail"]


def test_nothing_heard_is_422_and_wrong_state_409(tmp_path):
    client, eid = _new(tmp_path)
    res = _typed(client, eid, "dictate/orders", "...")
    assert res.status_code == 422 and res.json()["detail"] == "Nothing to draft was heard. Type the orders instead."
    _move(client, eid, "clinic_done")
    assert _typed(client, eid, "dictate/orders", "Paracetamol 1 g every 6 hours").status_code == 409


GOOD_REPLY = {
    "reason": "Open hernia repair",
    "items": [
        {"kind": "dose", "text": "Paracetamol 1 g every 6 hours", "name": "paracetamol", "amount": "1 g", "every_h": 6, "proof": "photo"},
        {"kind": "obs", "text": "BP and pulse every 1 hour, lower systolic limit 90", "every_h": 1, "limits": {"sbp_min": 90}},
    ],
}


def test_model_reply_used_when_grounded(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "spark_text", lambda s, prompt: json.dumps(GOOD_REPLY))
    client = _keyed_client(tmp_path)
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    draft = _typed(client, eid, "dictate/orders", ORDERS_TEXT).json()["drafts"]["order"]
    assert draft["source"] == "muse-spark-1.3"
    assert draft["items"][0] == {"kind": "dose", "text": "Paracetamol 1 g every 6 hours", "mode": "tick", "proof": "photo",
                                 "every_h": 6, "name": "paracetamol", "amount": "1 g"}


@pytest.mark.parametrize("reply", [
    json.dumps({**GOOD_REPLY, "items": GOOD_REPLY["items"] + [
        {"kind": "dose", "text": "Ondansetron 4 mg every 8 h", "name": "Ondansetron", "amount": "4 mg", "every_h": 8}]}),
    json.dumps({**GOOD_REPLY, "items": [{**GOOD_REPLY["items"][0], "every_h": 4}]}),
    json.dumps({**GOOD_REPLY, "items": [{**GOOD_REPLY["items"][0], "amount": "2 g"}]}),
    "not json",
])
def test_model_reply_with_invented_content_falls_back(tmp_path, monkeypatch, reply):
    monkeypatch.setattr(live, "spark_text", lambda s, prompt: reply)
    client = _keyed_client(tmp_path)
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    draft = _typed(client, eid, "dictate/orders", ORDERS_TEXT).json()["drafts"]["order"]
    assert draft["source"] == "rules (model reply not usable)"
    assert len(draft["items"]) == 2 and not any("ondansetron" in i["text"].lower() for i in draft["items"])


def _with_item(item):
    return json.dumps({**GOOD_REPLY, "items": GOOD_REPLY["items"] + [item]})


@pytest.mark.parametrize("item", [
    {"kind": "other", "text": "Insert urinary catheter"},
    {"kind": "other", "text": "Ceftriaxone IV"},
    {"kind": "other", "text": "Paracetamol rest", "proof": "none", "mode": "start_end"},
])
def test_digit_free_invention_falls_back(tmp_path, monkeypatch, item):
    monkeypatch.setattr(live, "spark_text", lambda s, prompt: _with_item(item))
    client = _keyed_client(tmp_path)
    eid = client.post("/morning/episodes", json={"label": "x"}).json()["id"]
    draft = _typed(client, eid, "dictate/orders", ORDERS_TEXT).json()["drafts"]["order"]
    assert draft["source"] == "rules (model reply not usable)" and len(draft["items"]) == 2


def test_invented_proof_and_mode_not_accepted():
    said = "Paracetamol 1 g every 6 hours."
    item = {"kind": "dose", "text": "Paracetamol 1 g every 6 hours", "name": "paracetamol", "amount": "1 g", "every_h": 6}
    reply = lambda extra: json.dumps({"reason": "", "items": [{**item, **extra}]})
    assert d.items_from_reply(reply({}), said) is not None
    assert d.items_from_reply(reply({"proof": "photo"}), said) is None
    assert d.items_from_reply(reply({"proof": "video"}), said) is None
    assert d.items_from_reply(reply({"mode": "start_end"}), said) is None
    assert d.items_from_reply(reply({"proof": "photo"}), said + " Photo as proof.") is not None


def test_reworded_same_words_reply_is_used():
    said = "Paracetamol 1 g every 6 hours. Review in clinic on day 7."
    reply = json.dumps({"reason": "", "items": [{"kind": "dose", "text": "Every 6 hours paracetamol 1 g", "name": "paracetamol", "amount": "1 g"}]})
    assert d.items_from_reply(reply, said) is not None
    sec = json.dumps({"sections": [{"heading": "Follow-up", "text": "Clinic review on day 7."}]})
    assert d.sections_from_reply(sec, said) is not None
    bad = json.dumps({"sections": [{"heading": "Follow-up", "text": "Clinic review and catheter removal."}]})
    assert d.sections_from_reply(bad, said) is None


def test_sign_with_draft_id_closes_draft(tmp_path):
    client, eid = _new(tmp_path)
    draft = _upload(client, eid, "dictate/orders", "kumar-orders.wav").json()["drafts"]["order"]
    body = {"items": draft["items"], "by": DOC, "at_ms": 0, "draft_id": draft["id"]}
    signed = client.post(_url(eid, "orders/sign"), json=body)
    assert signed.status_code == 200
    view = signed.json()
    assert view["drafts"]["order"] is None and len(view["order_list"]) == 1
    events = client.get(_url(eid, "audit")).json()["rows"]
    assert any(r["type"] == "order.signed" for r in events)
    assert client.post(_url(eid, "orders/sign"), json=body).status_code == 409
    assert client.post(_url(eid, "orders/sign"), json={**body, "draft_id": "nope"}).status_code == 404


def test_draft_id_must_be_a_matching_kind(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    discharge = _upload(client, eid, "dictate/discharge", "kumar-discharge.wav").json()["drafts"]["discharge"]
    body = {"items": [{"kind": "other", "text": "Rest"}], "by": DOC, "draft_id": discharge["id"]}
    assert client.post(_url(eid, "orders/sign"), json=body).status_code == 404


def test_dictate_discharge_and_sign(tmp_path):
    client, eid = _new(tmp_path)
    assert _upload(client, eid, "dictate/discharge", "kumar-discharge.wav").status_code == 409
    _to_ward(client, eid)
    draft = _upload(client, eid, "dictate/discharge", "kumar-discharge.wav").json()["drafts"]["discharge"]
    assert [s["heading"] for s in draft["sections"]] == list(d.HEADINGS)
    body = {"summary": "Summary", "by": DOC, "at_ms": 0, "draft_id": draft["id"]}
    assert client.post(_url(eid, "discharge/sign"), json={**body, "draft_id": "nope"}).status_code == 404
    assert _view(client, eid)["state"] == "ward"
    view = client.post(_url(eid, "discharge/sign"), json=body).json()
    assert view["state"] == "discharging" and view["drafts"]["discharge"] is None
    assert client.post(_url(eid, "discharge/sign"), json=body).status_code == 409


def test_models_endpoint_reports_no_key(tmp_path):
    client, _ = _new(tmp_path)
    got = client.get("/journey/models").json()
    assert (got["live"], got["voice"]) == (False, False) and not any(got["switches"].values())


def test_sections_reply_checks(tmp_path):
    ok = json.dumps({"sections": [{"heading": "Medicines", "text": "Paracetamol 1 g every 6 hours for 3 days."}]})
    assert d.sections_from_reply(ok, DISCHARGE_TEXT) is not None
    invented = json.dumps({"sections": [{"heading": "Medicines", "text": "Ibuprofen 400 mg."}]})
    assert d.sections_from_reply(invented, DISCHARGE_TEXT) is None
    assert d.sections_from_reply(json.dumps({"sections": [{"heading": "Other", "text": "x"}]}), "x") is None
    advice = json.dumps({"sections": [{"heading": "Follow-up", "text": "Stop the clinic."}]})
    assert d.sections_from_reply(advice, DISCHARGE_TEXT) is None


def test_transcribe_maps_non_json_and_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "to_wav", lambda raw, content_type: raw)

    def not_json(self, path, offset_ms=0, content_type="audio/wav"):
        raise ValueError("no json")

    monkeypatch.setattr(VoiceAdapter, "transcribe", not_json)
    assert live.transcribe(_keyed(tmp_path), b"x", "a.webm", "audio/webm")["source"] == "unavailable"
    monkeypatch.setattr(VoiceAdapter, "transcribe", lambda self, path, offset_ms=0, content_type="audio/wav": [{"text": "  ", "t0_ms": 0, "t1_ms": 0}])
    with pytest.raises(live.NotHeard) as err:
        live.transcribe(_keyed(tmp_path), b"x", "a.webm", "audio/webm")
    assert err.value.status == 409 and "Type what was said" in err.value.detail


def test_empty_transcript_is_not_parsed_as_orders(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "to_wav", lambda raw, content_type: raw)
    monkeypatch.setattr(VoiceAdapter, "transcribe", lambda self, path, offset_ms=0, content_type="audio/wav": [])
    client = _keyed_client(tmp_path)
    eid = client.post("/morning/episodes", json={"label": "x"}).json()["id"]
    res = _upload(client, eid, "dictate/orders", "a.wav")
    assert res.status_code == 409 and "Type what was said" in res.json()["detail"]


def test_new_plain_lines_have_no_advice_words():
    order = plain({"event_type": "order.drafted", "payload": {"by": DOC, "items": [1, 2]}})
    discharge = plain({"event_type": "discharge.drafted", "payload": {"by": DOC}})
    assert order == f"{DOC} dictated 2 orders (draft, not signed)."
    assert "discharge summary (draft, not signed)" in discharge
    assert not ADVICE.search(order) and not ADVICE.search(discharge)
    for prompt in (d.ORDER_PROMPT, d.DISCHARGE_PROMPT):
        assert "Do not give medical advice." in prompt
