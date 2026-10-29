"""The P3 story with no model key: tray checked by video in theatre, saline set-up checked by video."""

from __future__ import annotations

import re

import httpx
import pytest

from app.journey import video_api
from app.journey.procedures import tray_plan
from tests.test_flow_states import ADMIT_CHECKS, _move, _new, _view
from tests.test_flow_tasks import DOC, NURSE, _ack, _url
from tests.test_p2_story import _dictate
from tests.test_p3_setup import _begin, _row, _setup
from tests.test_p3_tray import JPEG, MP4, _events, _upload

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
H = 3_600_000
MIN = 60_000


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


@pytest.fixture(autouse=True)
def fake_frames(monkeypatch):
    def cut(clip, times, out_dir):
        files = []
        for i, _ in enumerate(times):
            target = out_dir / f"frame{i}.jpg"
            target.write_bytes(JPEG)
            files.append(target)
        return files

    monkeypatch.setattr(video_api, "cut_frames", cut)


def _texts(view):
    nn = view["now_next"]
    return [nn.get("now", ""), nn.get("next", ""), *(row["plain"] for row in view["timeline"]),
            *(c["why"] for c in view["video_checks"])]


def _post(client, eid, tail, body):
    r = client.post(_url(eid, tail), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_p3_done_when_without_a_key(tmp_path):
    client, kumar = _new(tmp_path)
    seen = []
    assert _move(client, kumar, "admitting", reason="Hernia repair", at_ms=0).status_code == 200
    assert _move(client, kumar, "ward", checklist=ADMIT_CHECKS, at_ms=H).status_code == 200
    plan = tray_plan("hernia-repair")
    r = _move(client, kumar, "theatre", procedure="hernia-repair", at_ms=2 * H)
    assert r.status_code == 200 and r.json()["tray"]["planned"]["template"] == "hernia-repair"
    view = _upload(client, kumar, at_ms=str(2 * H + 5 * MIN)).json()
    assert view["tray"]["latest"]["missing"] == ["needle holder"]
    assert len(view["tray"]["latest"]["frames"]) >= 1
    view = _upload(client, kumar, name="tray-hernia-full.mp4", at_ms=str(2 * H + 10 * MIN)).json()
    assert view["tray"]["latest"]["match"] == "ok"
    seen.extend(_texts(view))
    by = {"by": "Nurse Asha (synthetic)"}
    _post(client, kumar, "surgery", {"step": "began", "at_ms": 2 * H + 15 * MIN, **by})
    swabs = plan["swab_total"]
    _post(client, kumar, "count", {"step": "opened", "quantity": swabs, "at_ms": 2 * H + 16 * MIN, **by})
    short = _post(client, kumar, "count", {"step": "closing", "returned": swabs - 1, "at_ms": 3 * H, **by})
    assert [n["kind"] for n in short["nudges"]] == ["count_open"]
    first = next(e for e in _events(client, kumar) if e["event_type"] == "count.closing")["id"]
    _post(client, kumar, "count", {"step": "closing", "returned": swabs, "supersedes_id": first,
                                   "at_ms": 3 * H + 5 * MIN, **by})
    _post(client, kumar, "surgery", {"step": "ended", "at_ms": 3 * H + 10 * MIN, **by})
    assert _move(client, kumar, "ward", at_ms=3 * H + 15 * MIN, by=NURSE, reason="").json()["state"] == "ward"
    view = _view(client, kumar)
    seen.extend(_texts(view))
    checks = view["video_checks"]
    assert [c["match"] for c in checks] == ["mismatch", "ok"]
    assert all(c["frames"] and c["frames"][0]["url"].startswith("/journey/") for c in checks)

    client2, iyer = _new(tmp_path)
    assert _move(client2, iyer, "admitting", reason="Observation", at_ms=0).status_code == 200
    assert _move(client2, iyer, "ward", checklist=ADMIT_CHECKS, at_ms=0).status_code == 200
    orders = _dictate(client2, iyer, "dictate/orders", "iyer-saline.wav", DOC, 0).json()["drafts"]["order"]
    signed = client2.post(_url(iyer, "orders/sign"),
                          json={"items": orders["items"], "by": DOC, "draft_id": orders["id"], "at_ms": 0})
    tasks = _ack(client2, iyer, signed.json()["order_list"][0]["id"], at_ms=0).json()["tasks"]
    drip = next(t for t in tasks if t["kind"] == "procedure")
    assert drip["proof"] == "video"
    view = _setup(client2, iyer, drip["id"], at_ms=H).json()
    assert _row(view, drip["id"])["video"]["match"] == "ok"
    assert _begin(client2, iyer, drip["id"], H + 5 * MIN).status_code == 200
    done = client2.post(_url(iyer, f"tasks/{drip['id']}/done"),
                        json={"by": NURSE, "via": "tap", "at_ms": 3 * H + 5 * MIN}).json()
    assert _row(done, drip["id"])["status"] == "done"
    seen.extend(_texts(done))
    assert [c["check"] for c in done["video_checks"]] == ["setup"] and done["video_checks"][0]["frames"]
    assert any(t.startswith("Set-up check by video:") for t in _texts(done))
    assert any(t.startswith("Tray check by video:") for t in _texts(_view(client, kumar)))
    for text in seen:
        assert not ADVICE.search(text), text
