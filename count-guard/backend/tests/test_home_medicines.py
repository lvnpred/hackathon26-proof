"""Task 10: one doctor action, a photo of medicines from home. The theatre card reads what it finds (spec 6.3)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.adapters import spark as spark_mod
from app.adapters.sam import SamAdapter
from app.journey import home_medicines
from app.main import create_app
from tests.test_care_demo import _client, _seed
from tests.test_flow_states import _new, _to_theatre
from tests.test_p2_live import _keyed
from tests.test_p4_ask import PNG

DEMO = Path(__file__).resolve().parents[2] / "eval/media/home-medicines/strips-metoprolol-amlodipine-synthetic.png"
RAO = "Dr. A. Rao (synthetic)"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _url(eid, tail):
    return f"/journey/episodes/{eid}/{tail}"


def _post(client, eid, name="anything.png", raw=None, **data):
    raw = DEMO.read_bytes() if raw is None else raw
    return client.post(_url(eid, "strips/photo"), files={"file": (name, raw, "image/png")}, data=data)


def _found(client, eid):
    return [e for e in client.app.state.morning.events(eid) if e["event_type"] == "brownbag.med_found"]


def test_home_medicine_photo_lists_metoprolol(tmp_path):
    client = _client(tmp_path)
    eid = _seed(client)[2]["id"]
    assert client.post(_url(eid, "rx/demo"), json={"at_ms": 0}).status_code == 200
    r = _post(client, eid, name="IMG_0001.png", by=RAO)  # the file name says nothing
    assert r.status_code == 200
    rows = _found(client, eid)
    assert [p["payload"]["generic"] for p in rows] == ["metoprolol", "amlodipine"]
    assert all(p["payload"]["source"] == "prepared" for p in rows)
    listed = r.json()["strips"]
    assert [s["generic"] for s in listed] == ["metoprolol", "amlodipine"]
    assert all(s["match"]["text"] for s in listed)


def test_a_wrong_photo_is_not_read_by_its_file_name(tmp_path):
    client = _client(tmp_path)
    eid = _seed(client)[2]["id"]
    assert _post(client, eid, name="strips-metoprolol-amlodipine-synthetic.png", raw=PNG).status_code == 422
    assert _found(client, eid) == []


def test_live_failure_is_unavailable_not_fixture(tmp_path, monkeypatch):
    client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(create_app(_keyed(tmp_path / "keyed")))
    eid = _seed(client)[2]["id"]

    def boom(self, url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(spark_mod.SparkAdapter, "read_strips", boom)
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: (_ for _ in ()).throw(httpx.ConnectError("down")))
    r = _post(client, eid, name="strip-amlodipine.png")  # a prepared fixture is named like this upload
    assert r.status_code == 502 and "unavailable" in r.json()["detail"].lower()
    assert _found(client, eid) == []


def test_context_card_reads_home_medicine(tmp_path):
    from tests.test_theatre_api import DOCTOR, _drop_with_context, _of, _say, _count, _theatre  # noqa: F401

    client, eid = _theatre(tmp_path)
    assert client.post(_url(eid, "theatre/tier"), json={"on": True}).status_code == 200
    assert _post(client, eid, name="x.png", by=RAO).status_code == 200
    assert _count(client, eid, "opened", quantity=20).status_code == 200
    _say(client, eid, "lignocaine two percent, five ml, local infiltration")
    [draft] = _of(client, eid, "druglog.parsed")
    client.post(_url(eid, f"theatre/drug/{draft['id']}/confirm"), json={"by": DOCTOR})
    for _ in range(4):
        assert client.post(_url(eid, "theatre/vitals/step"), json={}).status_code == 200
    text = client.get(_url(eid, "theatre/card")).json()["card"]["text"]
    assert "on metoprolol" in text


def test_matches_name_the_prescription_row():
    rx = {"id": "r", "ts_ms": 1, "event_type": "rx.ordered", "payload": {"by": "Dr", "rows": [
        {"key": "metoprolol", "name": "Metoprolol", "strength": "25 mg"}]}}

    def strip(i, generic, strength):
        return {"id": i, "ts_ms": 2, "event_type": "brownbag.med_found",
                "payload": {"generic": generic, "name_as_read": generic, "strength": strength}}

    out = home_medicines.matches([rx, strip("a", "metoprolol", "25 mg"), strip("b", "metoprolol", "50 mg"),
                                  strip("c", "amlodipine", "5 mg")])
    assert [m["kind"] for m in out] == ["on_prescription", "strength_differs", "not_on_prescription"]
    assert out[1]["text"] == "Prescription says 25 mg."
    assert home_medicines.matches([strip("d", "metoprolol", "25 mg")])[0]["kind"] == "no_prescription"


def test_demo_photo_hash_is_pinned():
    import hashlib

    assert hashlib.sha256(DEMO.read_bytes()).hexdigest() == home_medicines.DEMO_SHA256
