"""Photos on the chart: strip and BP-monitor proof checks. A mismatch is flagged, never blocking."""

from __future__ import annotations

import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.sam import SamAdapter
from app.adapters.spark import SparkAdapter
from app.journey import proof
from app.journey.stories import plain
from app.main import create_app
from app.morning.brownbag import read_strip
from tests.test_flow_states import _new, _to_ward, _view
from tests.test_flow_tasks import DOSE, NURSE, OBS, _ack, _done, _sign, _url
from tests.test_p2_live import _keyed

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
PNG = b"\x89PNG\r\n\x1a\nfake"
JPEG = b"\xff\xd8\xff\xe0fake"
SALINE = {"kind": "procedure", "text": "Saline 1 litre over 2 hours", "name": "", "amount": "", "every_h": None, "mode": "start_end"}


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


def _photo(client, eid, name="strip-paracetamol.png", kind="image/png", data=None, **form):
    data = data if data is not None else (JPEG if kind == "image/jpeg" else PNG)
    form = {"purpose": "proof", "by": NURSE, "at_ms": 0, **form}
    return client.post(_url(eid, "photos"), data=form, files={"file": (name, data, kind)})


def _last(view):
    return view["photos"][-1]


def test_strip_photo_matches_dose_task(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [DOSE])[0]
    r = _photo(client, eid, task_id=task["id"])
    assert r.status_code == 200
    photo = _last(r.json())
    assert photo["check"]["match"] == "ok"
    assert photo["check"]["source"] == "prepared"
    assert photo["task_id"] == task["id"] and photo["purpose"] == "proof"
    assert "Paracetamol 500 mg" in photo["check"]["why"]


def test_strip_of_other_medicine_is_flagged():
    task = {"name": "Paracetamol", "title": "Paracetamol 1 g every 6 h"}
    out = proof.check_strip([read_strip("Amlodipine", "5 mg")], task)
    assert out["match"] == "mismatch"
    assert out["why"] == "The strip reads Amlodipine 5 mg; the task is paracetamol."
    ok = proof.check_strip([read_strip("Paracetamol", "500 mg")], task)
    assert (ok["match"], ok["read"]) == ("ok", "Paracetamol 500 mg")
    assert proof.check_strip([], task)["match"] == "none"


def test_strip_unknown_name_matches_by_lowercase_key():
    task = {"name": "Cefixime", "title": "Cefixime 200 mg"}
    assert proof.check_strip([read_strip("CEFIXIME", "200 mg")], task)["match"] == "ok"


def test_monitor_photo_flags_mismatch(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [OBS])[0]
    r = _photo(client, eid, "monitor-88-54.png", task_id=task["id"], sbp=82, dbp=54, hr=112)
    check = _last(r.json())["check"]
    assert check["match"] == "mismatch"
    assert "88/54" in check["why"] and "82/54" in check["why"]
    assert check["why"] == "The monitor reads 88/54, pulse 112; stated 82/54, pulse 112."


def test_monitor_photo_matches_and_compares_only_shared_keys():
    assert proof.parse_monitor_text('```json\n{"sbp": 88, "dbp": 54, "hr": 112}\n```') == {"sbp": 88, "dbp": 54, "hr": 112}
    assert proof.parse_monitor_text("not json") == {}
    assert proof.parse_monitor_text('{"sbp": "x", "hr": 70}') == {"hr": 70}
    assert proof.check_monitor({"sbp": 88, "dbp": 54, "hr": 112}, {"sbp": 88, "dbp": 54, "hr": 112})["match"] == "ok"
    assert proof.check_monitor({"sbp": 88}, {"sbp": 88, "hr": 70})["match"] == "ok"
    assert proof.check_monitor({}, {"sbp": 88})["match"] == "none"
    none = proof.check_monitor({"sbp": 88}, {})
    assert none["match"] == "none" and "No stated value" in none["why"]


def test_unknown_photo_without_key_is_kept_not_checked(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [DOSE])[0]
    r = _photo(client, eid, "IMG_0001.jpg", kind="image/jpeg", task_id=task["id"])
    assert r.status_code == 200
    photo = _last(r.json())
    assert photo["check"]["match"] == "none"
    assert photo["id"]


def test_reference_photo_and_served_file(tmp_path):
    client, eid = _new(tmp_path)
    r = _photo(client, eid, "ref.png", purpose="reference")
    photo = _last(r.json())
    assert photo["check"] is None and photo["task_id"] is None
    got = client.get(photo["url"])
    assert got.status_code == 200 and got.content == PNG
    other = _new(tmp_path)[1]
    assert client.get(f"/journey/episodes/{other}/photos/{photo['id']}").status_code == 404
    assert client.get(_url(eid, "photos/unknown")).status_code == 404
    events = client.app.state.morning.events(eid)
    added = next(e for e in events if e["event_type"] == "photo.added")
    assert not added["payload"]["path"].startswith("/")
    assert (client.app.state.settings.data_dir / added["payload"]["path"]).read_bytes() == PNG


def test_reference_takes_no_task_and_bad_files_are_refused(tmp_path):
    client, eid = _new(tmp_path)
    assert _photo(client, eid, purpose="reference", task_id="t1").status_code == 422
    assert _photo(client, eid, "x.gif", purpose="reference", kind="image/gif").status_code == 400
    assert _photo(client, eid, "x.heic", purpose="reference", kind="image/heic").status_code == 400
    assert _photo(client, eid, "x.png", purpose="reference", data=b"").status_code == 400
    assert _photo(client, eid, "x.png", purpose="reference", data=b"0" * (8 * 1024 * 1024 + 1)).status_code == 400
    assert _photo(client, eid, purpose="proof").status_code == 422
    assert _view(client, eid)["photos"] == []


def test_proof_needs_open_task(tmp_path):
    client, eid = _new(tmp_path)
    client2, eid2 = _new(tmp_path)
    one = _ward(client2, eid2, [{**DOSE, "every_h": None}])[0]
    assert _done(client2, eid2, one["id"]).status_code == 200
    assert _photo(client2, eid2, task_id=one["id"]).status_code == 409
    assert _photo(client2, eid2, task_id="nope").status_code == 404
    other_task = _ward(*_new(tmp_path), [DOSE])[0]["id"]
    assert _photo(client2, eid2, task_id=other_task).status_code == 404


def test_photo_on_running_task_keeps_it_running(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [SALINE])[0]
    assert client.post(_url(eid, f"tasks/{task['id']}/begin"), json={"by": NURSE, "at_ms": 0}).status_code == 200
    view = _photo(client, eid, "IMG_2.jpg", kind="image/jpeg", task_id=task["id"], at_ms=1000).json()
    assert next(t for t in view["tasks"] if t["id"] == task["id"])["status"] == "running"
    assert _done(client, eid, task["id"], at_ms=2000).status_code == 200


def test_live_reader_faked(tmp_path, monkeypatch):
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: [])
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/morning/episodes", json={"label": "Synthetic demo, R. Kumar"}).json()["id"]
    task = _ward(client, eid, [DOSE])[0]
    monkeypatch.setattr(SparkAdapter, "read_strips", lambda self, url: '{"strips": [{"name": "Paracetamol", "strength": "500 mg"}]}')
    check = _last(_photo(client, eid, "IMG_3.jpg", kind="image/jpeg", task_id=task["id"]).json())["check"]
    assert (check["match"], check["source"]) == ("ok", "muse-spark-1.3")

    def boom(self, url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(SparkAdapter, "read_strips", boom)
    assert _last(_photo(client, eid, "IMG_4.jpg", kind="image/jpeg", task_id=task["id"]).json())["check"]["match"] == "none"
    monkeypatch.setattr(SparkAdapter, "read_strips", lambda self, url: "{broken")
    assert _last(_photo(client, eid, "IMG_5.jpg", kind="image/jpeg", task_id=task["id"]).json())["check"]["match"] == "none"


def test_other_task_kinds_are_kept_without_reading(tmp_path):
    client, eid = _new(tmp_path)
    task = _ward(client, eid, [SALINE])[0]
    check = _last(_photo(client, eid, task_id=task["id"]).json())["check"]
    assert check["match"] == "none"
    assert check["why"] == "Kept as proof; this kind of task has no reading."


def test_why_strings_have_no_advice_words(tmp_path):
    client, eid = _new(tmp_path)
    tasks = _ward(client, eid, [DOSE, OBS, SALINE])
    dose, obs, saline = tasks
    _photo(client, eid, task_id=dose["id"])
    _photo(client, eid, "IMG_1.jpg", kind="image/jpeg", task_id=dose["id"])
    _photo(client, eid, "monitor-88-54.png", task_id=obs["id"], sbp=88, dbp=54, hr=112)
    _photo(client, eid, "monitor-88-54.png", task_id=obs["id"], sbp=82, dbp=54, hr=112)
    _photo(client, eid, "IMG_1.jpg", kind="image/jpeg", task_id=obs["id"])
    _photo(client, eid, task_id=saline["id"])
    view = _photo(client, eid, "ref.png", purpose="reference").json()
    texts = [p["check"]["why"] for p in view["photos"] if p["check"]]
    task = {"name": "Paracetamol", "title": "Paracetamol"}
    texts += [proof.check_strip(s, task)["why"] for s in ([read_strip("Paracetamol", "500 mg")], [read_strip("Amlodipine", "5 mg")], [])]
    texts += [proof.check_monitor(*pair)["why"] for pair in (({"sbp": 1}, {"sbp": 1}), ({"sbp": 1}, {"sbp": 2}), ({}, {"sbp": 1}), ({"sbp": 1}, {}))]
    texts += [e["plain"] for e in view["timeline"] if e["type"] in ("photo.added", "proof.checked")]
    assert len(texts) > 15
    assert {m for t in texts if (m := ADVICE.search(t))} == set()
    assert any(e["type"] == "photo.added" for e in view["timeline"])


def test_plain_wording():
    assert plain({"event_type": "photo.added", "payload": {"by": "Nurse Asha", "purpose": "proof"}}) == "Nurse Asha added a proof photo."
    assert plain({"event_type": "proof.checked", "payload": {"why": "It fits."}}) == "Photo check: It fits."
