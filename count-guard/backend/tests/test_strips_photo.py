"""Task 8: the clinic's photo of strips is read like the medicines photo, offline from a prepared fixture (R11, R12, R13)."""

from __future__ import annotations

import json

import httpx
import pytest

from app.journey import live
from tests.test_care_demo import _client, _seed
from tests.test_flow_states import ADVICE
from tests.test_p4_ask import PNG

RAO = "Dr. A. Rao (synthetic)"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _url(eid, tail):
    return f"/journey/episodes/{eid}/{tail}"


def _das_with_rx(tmp_path):
    client = _client(tmp_path)
    eid = _seed(client)[2]["id"]
    assert client.post(_url(eid, "rx/demo"), json={"at_ms": 0}).status_code == 200
    return client, eid


def _rows(client, eid, kind):
    return [e for e in client.app.state.morning.events(eid) if e["event_type"] == kind]


def _post(client, eid, name="strip-amlodipine.png", kind="image/png", raw=PNG, **data):
    return client.post(_url(eid, "strips/photo"), files={"file": (name, raw, kind)}, data=data)


def test_strips_photo_offline_uses_fixture(tmp_path):
    client, eid = _das_with_rx(tmp_path)
    r = _post(client, eid, by=RAO)
    assert r.status_code == 200
    rows = _rows(client, eid, "brownbag.med_found")
    assert len(rows) == 1 and rows[0]["payload"]["evidence_id"] and rows[0]["payload"]["source"] == "prepared"
    assert rows[0]["payload"]["by"] == RAO and rows[0]["payload"]["photo_id"]
    assert [c["model"] for c in rows[0]["payload"]["calls"]] == ["sam", "spark"]
    nudge = r.json()["nudges"][0]
    assert nudge["says_staff"] == "Strip reads amlodipine 10 mg; prescription says 5 mg."
    strips = [m for m in r.json()["ai_moments"] if m["capability"] == "strips"]
    assert strips[0]["finding"] == "Read 1 strip: 1 differs from the prescription." and strips[0]["status"] == "flagged"
    assert not ADVICE.search(strips[0]["finding"] + nudge["says_staff"])


def test_strips_photo_defaults_to_the_patient(tmp_path):
    client, eid = _das_with_rx(tmp_path)
    assert _post(client, eid).status_code == 200
    assert _rows(client, eid, "brownbag.med_found")[0]["payload"]["by"] == "patient"


def test_strips_photo_reads_nothing_is_422(tmp_path):
    client, eid = _das_with_rx(tmp_path)
    before = len(client.app.state.morning.events(eid))
    r = _post(client, eid, name="unknown-strip.png")
    assert r.status_code == 422 and r.json()["detail"] == "No strips were read from the photo. Type them instead."
    assert len(client.app.state.morning.events(eid)) == before


def test_strips_photo_refuses_bad_file(tmp_path):
    client, eid = _das_with_rx(tmp_path)
    before = len(client.app.state.morning.events(eid))
    assert _post(client, eid, name="s.txt", kind="text/plain", raw=b"hello").status_code == 400
    assert _post(client, eid, name="s.png", raw=b"not a png").status_code == 400
    assert _post(client, eid, by="x" * 81).status_code == 422
    assert client.post(_url("missing", "strips/photo"), files={"file": ("s.png", PNG, "image/png")}).status_code == 404
    assert len(client.app.state.morning.events(eid)) == before


def test_strips_photo_calls_counted_once(tmp_path, monkeypatch):
    two = {"text": json.dumps({"strips": [{"name": "Amlodipine", "strength": "10 mg"}, {"name": "Metoprolol", "strength": "25 mg"}]}),
           "regions": [], "handmade": True}
    monkeypatch.setattr(live, "prepared", lambda name: two if name == "strip-two.png" else None)
    client, eid = _das_with_rx(tmp_path)
    assert _post(client, eid, name="strip-two.png").status_code == 200
    rows = _rows(client, eid, "brownbag.med_found")
    assert len(rows) == 2 and "calls" in rows[0]["payload"] and "calls" not in rows[1]["payload"]
    summary = client.get(f"/journey/ai/summary?ids={eid}").json()
    spark = next(m for m in summary["models"] if m["key"] == "spark")
    assert spark["calls"] == 1
