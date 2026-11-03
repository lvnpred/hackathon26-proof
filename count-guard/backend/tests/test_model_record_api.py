"""The Expand view's record of one model point (care-app clarity §4.2): one event's evidence and source words, read
back by id, only for its own episode, with no key, token or header in it.
"""

from __future__ import annotations

from dataclasses import replace

from tests.test_flow_states import _new
from tests.test_flow_tasks import _url

DOC = "Dr. A. Rao (synthetic)"
SECRET = "sk-test-SECRET-key-0123456789"


def _drafted(client, eid):
    client.post(_url(eid, "dictate/orders"), data={"by": DOC, "text": "paracetamol one gram every six hours"})
    return next(e for e in client.app.state.morning.events(eid) if e["event_type"] == "order.drafted")


def test_record_reads_back_the_event_evidence(tmp_path):
    client, eid = _new(tmp_path)
    draft = _drafted(client, eid)
    got = client.get(_url(eid, f"events/{draft['id']}/model"))
    assert got.status_code == 200
    body = got.json()
    assert (body["id"], body["type"], body["at_ms"]) == (draft["id"], "order.drafted", draft["ts_ms"])
    assert body["evidence"] == draft["payload"]["evidence"]
    assert body["evidence"]["captured"]["transcript"].startswith("paracetamol")
    assert body["items"] == draft["payload"]["items"]


def test_record_is_only_for_its_own_episode(tmp_path):
    client, eid = _new(tmp_path)
    draft = _drafted(client, eid)
    other = client.post("/journey/episodes", json={"label": "Synthetic demo, S. Iyer"}).json()["id"]
    assert client.get(_url(other, f"events/{draft['id']}/model")).status_code == 404
    assert client.get(_url(eid, "events/not-an-event/model")).status_code == 404
    assert client.get(_url("no-such-episode", f"events/{draft['id']}/model")).status_code == 404


def test_record_carries_no_secret(tmp_path):
    client, eid = _new(tmp_path)
    client.app.state.settings = replace(client.app.state.settings, meta_api_key=SECRET)
    draft = _drafted(client, eid)
    store = client.app.state.morning
    # A payload that somehow holds a key-named field or a token in text never goes out.
    store.append(eid, "vitals.card", {"text": f"Bearer {SECRET}", "api_key": SECRET, "by": "AI"}, ts_ms=draft["ts_ms"] + 1)
    card = next(e for e in store.events(eid) if e["event_type"] == "vitals.card")
    body = client.get(_url(eid, f"events/{card['id']}/model")).text
    assert SECRET not in body and "api_key" not in body


def test_a_photo_check_row_names_its_event():
    from app.journey import verdict

    events = [{"id": "e1", "event_type": "check.photo", "episode_id": "ep", "ts_ms": 1,
               "payload": {"item": "wristband", "photo_id": "p1", "verdict": "accepted", "why": "ok", "source": "prepared",
                           "calls": [], "by": "Nurse Meena (synthetic)"}}]
    [row] = [r for r in verdict.checks_view(events) if r["item"] == "wristband"]
    assert row["event_id"] == "e1"


def test_only_model_points_are_read_back(tmp_path):
    client, eid = _new(tmp_path)
    _drafted(client, eid)
    store = client.app.state.morning
    store.append(eid, "ward.orders_set", {"items": [], "by": DOC}, ts_ms=9)  # a record event, not a model point
    plain = next(e for e in store.events(eid) if e["event_type"] == "ward.orders_set")
    assert client.get(_url(eid, f"events/{plain['id']}/model")).status_code == 404
    store.append(eid, "help.requested", {"says": "pain", "by": "patient"}, ts_ms=10)
    help_ = next(e for e in store.events(eid) if e["event_type"] == "help.requested")
    assert client.get(_url(eid, f"events/{help_['id']}/model")).status_code == 404


def test_the_patient_lens_never_gets_the_raw_reply_the_text_sent_or_the_calls(tmp_path):
    client, eid = _new(tmp_path)
    draft = _drafted(client, eid)
    ev = draft["payload"]["evidence"]
    ev_raw = {**ev, "returned": {**ev["returned"], "raw": "RAW-REPLY"}, "captured": {**ev["captured"], "text": "PROMPT-TEXT"}}
    store = client.app.state.morning
    store.append(eid, "handover.drafted", {"text": "t", "evidence": ev_raw, "calls": [{"model": "spark", "raw": "RAW-REPLY"}]}, ts_ms=10)
    hand = next(e for e in store.events(eid) if e["event_type"] == "handover.drafted")
    staff = client.get(_url(eid, f"events/{hand['id']}/model")).json()
    assert staff["evidence"]["returned"]["raw"] == "RAW-REPLY" and staff["evidence"]["captured"]["text"] == "PROMPT-TEXT"
    patient = client.get(_url(eid, f"events/{hand['id']}/model?lens=patient"))
    assert patient.status_code == 200
    body = patient.json()
    assert "RAW-REPLY" not in patient.text and "PROMPT-TEXT" not in patient.text
    assert "calls" not in body and "calls" not in body["evidence"] and body["evidence"]["returned"]["raw"] is None
    assert body["evidence"]["returned"]["model"] is None
    assert body["evidence"]["captured"]["transcript"] == ev["captured"]["transcript"]
