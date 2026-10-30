"""Spoken task completion: the server proposes candidates and writes nothing; one tap completes (D10)."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.journey import live, proof, spoken
from app.journey.stories import plain
from app.main import create_app
from tests.test_flow_states import _new, _to_ward, _view
from tests.test_flow_tasks import DOSE, NURSE, OBS, _ack, _done, _sign, _url
from tests.test_p2_live import _keyed

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
PNG = b"\x89PNG\r\n\x1a\nfake"
PARA = {**DOSE, "every_h": None}


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


def _speak(client, eid, name="kumar-paracetamol.wav", **form):
    files = {"file": (name, b"RIFF", "audio/wav")}
    return client.post(_url(eid, "dictate/task"), data={"by": NURSE, "at_ms": 0, **form}, files=files)


def _typed(client, eid, text):
    return client.post(_url(eid, "dictate/task"), data={"by": NURSE, "at_ms": 0, "text": text})


def _photo(client, eid, task_id, name, **form):
    data = {"purpose": "proof", "by": NURSE, "at_ms": 0, "task_id": task_id, **form}
    return client.post(_url(eid, "photos"), data=data, files={"file": (name, PNG, "image/png")})


def _count(client, eid):
    return len(client.app.state.morning.events(eid))


def _voice(client, eid, task_id, **extra):
    return _done(client, eid, task_id, via="voice", transcript="said it", **extra)


def test_parse_values_iyer():
    assert spoken.parse_values("BP 82 over 54, pulse 112, bed 7.") == {"sbp": 82, "dbp": 54, "hr": 112}
    assert spoken.parse_values("eighty two over fifty four") == {"sbp": 82, "dbp": 54}
    assert spoken.parse_values("sats 97, temperature 37.5") == {"spo2": 97, "temp": 37.5}
    assert spoken.parse_values("nothing here") == {}


def test_kumar_paracetamol_matches_one_task(tmp_path):
    client, eid = _new(tmp_path)
    dose, _obs = _ward(client, eid, [DOSE, OBS])
    before = _count(client, eid)
    r = _speak(client, eid)
    assert r.status_code == 200
    body = r.json()
    assert [c["id"] for c in body["candidates"]] == [dose["id"]]
    assert body["candidates"][0].keys() == {"id", "title", "kind", "mode", "status"}
    assert (body["transcript"], body["heard_by"], body["source"]) == ("Paracetamol 1 g given to bed 4.", "prepared", "rules")
    assert body["values"] == {}
    assert _count(client, eid) == before


def test_match_uses_the_strip_key(tmp_path):
    client, eid = _new(tmp_path)
    cef = {"kind": "dose", "text": "Cefixime 200 mg", "name": "Cefixime", "amount": "200 mg"}
    dose, other = _ward(client, eid, [DOSE, cef])
    assert [c["id"] for c in _typed(client, eid, "PARACETAMOL done for bed 2").json()["candidates"]] == [dose["id"]]
    assert [c["id"] for c in _typed(client, eid, "cefixime done").json()["candidates"]] == [other["id"]]


def test_two_obs_tasks_both_offered(tmp_path):
    client, eid = _new(tmp_path)
    tasks = _ward(client, eid, [OBS, {**OBS, "text": "BP every 15 min", "every_h": 0.25}])
    body = _speak(client, eid, "iyer-bp.wav").json()
    assert [c["id"] for c in body["candidates"]] == [t["id"] for t in tasks]
    assert body["values"] == {"sbp": 82, "dbp": 54, "hr": 112}


def test_no_match_returns_empty_candidates(tmp_path):
    client, eid = _new(tmp_path)
    _ward(client, eid, [DOSE, OBS])
    body = _typed(client, eid, "Patient asked for a blanket").json()
    assert body["candidates"] == [] and body["values"] == {}


def test_done_task_is_not_offered_and_wrong_state_is_409(tmp_path):
    client, eid = _new(tmp_path)
    assert _typed(client, eid, "Paracetamol given").status_code == 409
    dose = _ward(client, eid, [PARA])[0]
    assert _done(client, eid, dose["id"]).status_code == 200
    assert _typed(client, eid, "Paracetamol given").json()["candidates"] == []


def test_model_ids_and_values_are_grounded(tmp_path, monkeypatch):
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    dose, obs = _ward(client, eid, [PARA, OBS])
    assert _done(client, eid, dose["id"]).status_code == 200
    reply = json.dumps({"task_ids": [dose["id"], obs["id"]], "values": {"hr": 130}})
    monkeypatch.setattr(live, "spark_text", lambda s, prompt: reply)
    body = _typed(client, eid, "BP 82 over 54, pulse 112").json()
    assert body["source"] == "rules (model reply not usable)"
    assert [c["id"] for c in body["candidates"]] == [obs["id"]]
    assert body["values"] == {"sbp": 82, "dbp": 54, "hr": 112}


def test_model_reply_used_when_grounded(tmp_path, monkeypatch):
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    obs = _ward(client, eid, [OBS])[0]
    seen = []
    reply = json.dumps({"task_ids": [obs["id"]], "values": {"sbp": 82, "dbp": 54, "hr": 112}})
    monkeypatch.setattr(live, "spark_text", lambda s, prompt: seen.append(prompt) or reply)
    body = _typed(client, eid, "BP 82 over 54, pulse 112").json()
    assert body["source"] == "muse-spark-1.3"
    assert [c["id"] for c in body["candidates"]] == [obs["id"]]
    assert f"{obs['id']}: BP every 1 h" in seen[0]


def test_completion_from_reply_rules():
    tasks = [
        {"id": "a", "status": "open", "title": "BP every 1 h", "kind": "obs"},
        {"id": "b", "status": "done", "title": "Old", "kind": "other"},
    ]
    said = "BP 82 over 54, pulse 112"
    ok = {"task_ids": ["a"], "values": {"sbp": 82, "dbp": 54, "hr": 112}}
    assert spoken.completion_from_reply(json.dumps(ok), tasks, said) == ok
    for bad in (
        {"task_ids": ["b"], "values": {}},
        {"task_ids": ["zzz"], "values": {}},
        {"task_ids": ["a"], "values": {"hr": 130}},
        {"task_ids": ["a"], "values": {"sbp": 9999}},
        {"task_ids": ["a"], "values": {"bogus": 1}},
        {"task_ids": "a", "values": {}},
    ):
        assert spoken.completion_from_reply(json.dumps(bad), tasks, said) is None
    assert spoken.completion_from_reply("not json", tasks, said) is None
    assert spoken.completion_from_reply(None, tasks, said) is None


def test_voice_done_needs_transcript(tmp_path):
    client, eid = _new(tmp_path)
    dose = _ward(client, eid, [PARA])[0]
    assert _done(client, eid, dose["id"], via="voice", transcript="").status_code == 422
    assert _done(client, eid, dose["id"], via="voice").status_code == 422
    assert _done(client, eid, dose["id"], via="voice", transcript="x" * 2001).status_code == 422
    assert _done(client, eid, dose["id"], via="voice", transcript="x" * 2000).status_code == 200


def test_typed_done_is_stored_as_typed_and_the_story_says_so(tmp_path):
    client, eid = _new(tmp_path)
    dose = _ward(client, eid, [PARA])[0]
    view = _done(client, eid, dose["id"], via="text", transcript="gave it at nine").json()
    entry = next(t for t in view["tasks"] if t["id"] == dose["id"])["done"][0]
    assert (entry["via"], entry["transcript"]) == ("text", "gave it at nine")
    event = next(e for e in client.app.state.morning.events(eid) if e["event_type"] == "task.done")
    assert plain(event) == f"{NURSE} finished a task (typed)."
    assert not ADVICE.search(plain(event))


def test_done_with_proof_records_match(tmp_path):
    client, eid = _new(tmp_path)
    dose, obs = _ward(client, eid, [PARA, OBS])
    shot = _photo(client, eid, dose["id"], "strip-paracetamol.png").json()["photos"][-1]
    assert shot["check"]["match"] == "ok"
    view = _voice(client, eid, dose["id"], proof_id=shot["id"]).json()
    entry = next(t for t in view["tasks"] if t["id"] == dose["id"])["done"][0]
    assert (entry["via"], entry["transcript"], entry["proof_id"], entry["match"]) == ("voice", "said it", shot["id"], "ok")
    events = client.app.state.morning.events(eid)
    assert any(e["event_type"] == "dose.given" for e in events)
    mon = _photo(client, eid, obs["id"], "monitor-88-54.png", sbp=82, dbp=54, hr=112).json()["photos"][-1]
    assert mon["check"]["match"] == "mismatch"
    values = {"sbp": 82, "dbp": 54, "hr": 112}
    view = _voice(client, eid, obs["id"], proof_id=mon["id"], values=values).json()
    entry = next(t for t in view["tasks"] if t["id"] == obs["id"])["done"][0]
    assert entry["match"] == "mismatch"
    recorded = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "obs.recorded"]
    assert recorded[-1]["payload"]["sbp"] == 82
    done = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "task.done"][-1]["payload"]
    assert done["values"] == values and done["match"] == "mismatch"


def test_match_is_null_without_a_photo(tmp_path):
    client, eid = _new(tmp_path)
    dose = _ward(client, eid, [PARA])[0]
    view = _done(client, eid, dose["id"]).json()
    entry = view["tasks"][0]["done"][0]
    assert (entry["transcript"], entry["proof_id"], entry["match"]) == ("", None, None)
    done = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "task.done"][0]["payload"]
    assert "proof_id" not in done and "match" not in done


def test_photo_kept_but_not_checked_is_none(tmp_path):
    client, eid = _new(tmp_path)
    dose = _ward(client, eid, [PARA])[0]
    added = {"purpose": "proof", "path": "x.png", "by": NURSE, "task_id": dose["id"]}
    shot = client.app.state.morning.append(eid, "photo.added", added, ts_ms=0)
    view = _voice(client, eid, dose["id"], proof_id=shot["id"]).json()
    assert view["tasks"][0]["done"][0]["match"] == "none"


def test_proof_id_rules(tmp_path):
    client, eid = _new(tmp_path)
    dose, obs = _ward(client, eid, [PARA, OBS])
    other_client, other_eid = _new(tmp_path)
    other_dose = _ward(other_client, other_eid, [PARA])[0]
    foreign = _photo(other_client, other_eid, other_dose["id"], "strip-paracetamol.png").json()["photos"][-1]
    assert _voice(client, eid, dose["id"], proof_id=foreign["id"]).status_code == 404
    assert _voice(client, eid, dose["id"], proof_id="nope").status_code == 404
    elsewhere = _photo(client, eid, obs["id"], "monitor-88-54.png", sbp=88, dbp=54, hr=112).json()["photos"][-1]
    before = _count(client, eid)
    refused = _voice(client, eid, dose["id"], proof_id=elsewhere["id"])
    assert refused.status_code == 409
    assert refused.json()["detail"] == "This photo was checked against another task."
    assert _count(client, eid) == before
    assert _done(client, eid, dose["id"], proof_id="x" * 65).status_code == 422


def test_task_view_has_name_amount_and_done_fields(tmp_path):
    client, eid = _new(tmp_path)
    dose, obs = _ward(client, eid, [DOSE, OBS])
    assert (dose["name"], dose["amount"]) == ("Paracetamol", "1 g")
    assert (obs["name"], obs["amount"]) == ("", "")
    done = _done(client, eid, dose["id"]).json()["tasks"][0]["done"][0]
    assert set(done) == {"at_ms", "by", "via", "note", "transcript", "proof_id", "match", "why", "source", "evidence_id", "read", "saved"}


def test_plain_for_voice_done():
    base = {"event_type": "task.done", "payload": {"by": "Nurse Asha", "via": "voice"}}
    assert plain(base) == "Nurse Asha finished a task by voice."
    flagged = {**base, "payload": {**base["payload"], "match": "mismatch"}}
    assert plain(flagged) == "Nurse Asha finished a task by voice. Photo flagged."
    assert plain({**base, "payload": {"by": "Nurse Asha", "via": "tap"}}) == "Nurse Asha finished a task."


def test_task_prompt_forbids_advice():
    assert "Do not give medical advice." in spoken.TASK_PROMPT
    assert "Do not give medical advice." in spoken.task_prompt([{"id": "t1", "title": "BP every 1 h", "status": "open"}])


def test_strings_the_code_produces_have_no_advice_words(tmp_path):
    client, eid = _new(tmp_path)
    dose, obs = _ward(client, eid, [PARA, OBS])
    strings = [
        plain({"event_type": "task.done", "payload": {"by": NURSE, "via": "voice", "match": m}}) for m in ("ok", "mismatch", None)
    ]
    shot = _photo(client, eid, obs["id"], "monitor-88-54.png", sbp=88, dbp=54, hr=112).json()["photos"][-1]
    strings += [
        _typed(client, eid, " ").json()["detail"],
        _voice(client, eid, dose["id"], proof_id=shot["id"]).json()["detail"],
        _voice(client, eid, dose["id"], proof_id="nope").json()["detail"],
        _done(client, eid, dose["id"], via="voice", transcript="").text,
    ]
    view = _typed(client, eid, "Paracetamol given").json()
    strings += [view["source"], view["heard_by"]]
    assert all(s and not ADVICE.search(s) for s in strings), strings
    assert proof.NO_READING and live.NO_KEY
