"""Sync (spec §7.3): pull what Doctor Dictation holds and make the patients Count Guard missed."""

from __future__ import annotations

import copy

import httpx

from app.config import Settings
from app.journey import sync
from app.ops import run as ops_run
from tests.test_care_demo import _client
from tests.test_intake import FIXTURE, _payload, _post, _ward


def _second() -> dict:
    other = copy.deepcopy(FIXTURE)
    other["document_id"] = 43
    other["document"]["document_id"] = 43
    other["document"]["structured"]["patientName"] = "K. Nair (synthetic)"
    return other


class FakeGet:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.calls = rows or [], error, []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        if self.error:
            raise self.error
        return httpx.Response(200, json={"admissions": self.rows}, request=httpx.Request("GET", url))


def _pull(client, get, since=None):
    settings = client.app.state.settings
    return sync.pull(settings, client.app.state.morning, since=since, now_ms=0, get=get)


def test_sync_pulls_missed_admission(tmp_path):
    client = _client(tmp_path)
    got = _pull(client, FakeGet([_payload(), _second()]))
    assert got["new"] == 2 and got["existing"] == 0 and got["updated"] == 0 and got["error"] is None
    assert len(_ward(client)) == 2


def test_sync_twice_is_idempotent(tmp_path):
    client = _client(tmp_path)
    get = FakeGet([_payload(), _second()])
    _pull(client, get)
    got = _pull(client, get)
    assert got["new"] == 0 and got["existing"] == 2 and got["updated"] == 0
    assert len(_ward(client)) == 2


def test_sync_reports_dd_down(tmp_path):
    client = _client(tmp_path)
    got = _pull(client, FakeGet(error=httpx.ConnectError("refused")))
    assert got["error"] == "Doctor Dictation is not reachable"
    assert got["new"] == got["existing"] == got["updated"] == 0
    assert _ward(client) == []


def test_sync_sends_token_header(tmp_path, monkeypatch):
    monkeypatch.setenv("CG_SYNC_TOKEN", "s3cret")
    client = _client(tmp_path, dd_base="http://dd.test")
    get = FakeGet([])
    _pull(client, get, since="2026-11-03T00:00:00")
    url, kw = get.calls[0]
    assert url == "http://dd.test/api/v1/admissions"
    assert kw["headers"]["X-CG-Sync-Token"] == "s3cret"
    assert kw["params"] == {"since": "2026-11-03T00:00:00"}


def test_sync_sends_no_header_without_token(tmp_path, monkeypatch):
    monkeypatch.delenv("CG_SYNC_TOKEN", raising=False)
    client = _client(tmp_path)
    get = FakeGet([])
    _pull(client, get)
    assert "X-CG-Sync-Token" not in get.calls[0][1]["headers"] and not get.calls[0][1]["params"]


def test_sync_skips_send_home_never_admitted(tmp_path):
    client = _client(tmp_path)
    got = _pull(client, FakeGet([_payload(status="send_home"), _second()]))
    assert got["new"] == 1 and got["existing"] == 0 and got["updated"] == 0 and got["error"] is None


def test_sync_counts_a_resave_as_updated(tmp_path):
    client = _client(tmp_path)
    _post(client)
    later = _payload(finalized_at="2026-11-03T11:02:40")
    later["document"]["structured"]["rx"][0]["dose"] = "1-1-1"
    got = _pull(client, FakeGet([later]))
    assert got["updated"] == 1 and got["new"] == 0


def test_sync_reports_bad_reply(tmp_path):
    client = _client(tmp_path)

    def bad(url, **kw):
        return httpx.Response(404, json={}, request=httpx.Request("GET", url))

    assert _pull(client, bad)["error"] == "Doctor Dictation is not reachable"


def test_sync_settles_each_new_patient(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ops_run, "run", lambda store, eid, ts, **kw: calls.append(eid))
    client = _client(tmp_path)
    monkeypatch.setattr(sync.httpx, "get", FakeGet([_payload(), _second()]))
    res = client.post("/journey/sync", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["new"] == 2 and "changed" not in body
    assert len(calls) == 2
    client.post("/journey/sync", json={})
    assert len(calls) == 2  # nothing new, nothing settled


def test_sync_malformed_row_is_counted_and_the_rest_settle(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ops_run, "run", lambda store, eid, ts, **kw: calls.append(eid))
    client = _client(tmp_path)
    third = _second()
    third["document_id"] = 44
    third["document"]["structured"]["patientName"] = "L. Rao (synthetic)"
    bad = {"source": "doctor-dictation"}  # no document_id
    monkeypatch.setattr(sync.httpx, "get", FakeGet([_payload(), bad, third]))
    res = client.post("/journey/sync", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["new"] == 2 and body["failed"] == 1 and body["error"] is None
    assert len(calls) == 2 and len(set(calls)) == 2
    assert len(_ward(client)) == 2


def test_sync_settles_a_resave_counted_as_updated(tmp_path, monkeypatch):
    client = _client(tmp_path)
    _post(client)
    calls = []
    monkeypatch.setattr(ops_run, "run", lambda store, eid, ts, **kw: calls.append(eid))
    later = _payload(finalized_at="2026-11-03T11:02:40")
    later["document"]["structured"]["rx"][0]["dose"] = "1-1-1"
    monkeypatch.setattr(sync.httpx, "get", FakeGet([later]))
    body = client.post("/journey/sync", json={}).json()
    assert body["updated"] == 1 and len(calls) == 1
