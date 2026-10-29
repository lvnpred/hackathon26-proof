"""The P2 story with no model key: dictated orders, voice completion with photo proof, dictated discharge."""

from __future__ import annotations

import re

import httpx
import pytest

from tests.test_flow_states import ADMIT_CHECKS, _move, _new
from tests.test_flow_tasks import DOC, NURSE, _ack, _done, _url

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
H = 3_600_000
MIN = 60_000
PNG = b"\x89PNG\r\n\x1a\nfake"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _dictate(client, eid, tail, name, who, at_ms):
    files = {"file": (name, b"RIFF", "audio/wav")}
    return client.post(_url(eid, tail), data={"by": who, "at_ms": at_ms}, files=files)


def _photo(client, eid, task_id, name, at_ms, **form):
    data = {"purpose": "proof", "by": NURSE, "at_ms": at_ms, "task_id": task_id, **form}
    return client.post(_url(eid, "photos"), data=data, files={"file": (name, PNG, "image/png")})


def _texts(view):
    nn = view["now_next"]
    return [nn.get("now", ""), nn.get("next", "")] + [row["plain"] for row in view["timeline"]]


def test_p2_done_when_without_a_key(tmp_path):
    client, kumar = _new(tmp_path)
    seen = []

    def check(view):
        seen.extend(_texts(view))
        seen.extend(n["says"] for n in view["nudges"])
        return view

    draft = check(_dictate(client, kumar, "dictate/orders", "kumar-orders.wav", DOC, 0).json())["drafts"]["order"]
    assert _move(client, kumar, "admitting", reason=draft["reason"], at_ms=10 * MIN).status_code == 200
    signed = client.post(
        _url(kumar, "orders/sign"),
        json={"items": draft["items"], "by": DOC, "draft_id": draft["id"], "at_ms": 12 * MIN},
    )
    assert signed.status_code == 200
    assert _move(client, kumar, "ward", checklist=ADMIT_CHECKS, at_ms=H).status_code == 200
    order = signed.json()["order_list"][0]
    tasks = check(_ack(client, kumar, order["id"], at_ms=H + 5 * MIN).json())["tasks"]
    assert {t["kind"] for t in tasks} == {"dose", "obs"}

    heard = _dictate(client, kumar, "dictate/task", "kumar-paracetamol.wav", NURSE, 4 * H).json()
    assert [c["kind"] for c in heard["candidates"]] == ["dose"] and heard["source"] == "rules"
    dose_id = heard["candidates"][0]["id"]
    shot = check(_photo(client, kumar, dose_id, "strip-paracetamol.png", 4 * H).json())["photos"][-1]
    assert shot["check"]["match"] == "ok"
    body = {"via": "voice", "transcript": heard["transcript"], "proof_id": shot["id"], "at_ms": 4 * H}
    view = check(_done(client, kumar, dose_id, **body).json())
    done = next(t for t in view["tasks"] if t["id"] == dose_id)["done"][0]
    assert (done["via"], done["match"], done["transcript"]) == ("voice", "ok", heard["transcript"])

    discharge = check(_dictate(client, kumar, "dictate/discharge", "kumar-discharge.wav", DOC, 30 * H).json())["drafts"]["discharge"]
    summary = " ".join(f"{s['heading']}: {s['text']}" for s in discharge["sections"])
    r = client.post(
        _url(kumar, "discharge/sign"), json={"summary": summary, "by": DOC, "draft_id": discharge["id"], "at_ms": 30 * H}
    )
    assert r.status_code == 200 and check(r.json())["state"] == "discharging"

    client2, iyer = _new(tmp_path)
    assert _move(client2, iyer, "admitting", reason="Observation", at_ms=0).status_code == 200
    assert _move(client2, iyer, "ward", checklist=ADMIT_CHECKS, at_ms=0).status_code == 200
    orders = _dictate(client2, iyer, "dictate/orders", "iyer-saline.wav", DOC, 0).json()["drafts"]["order"]
    items = [{**i, "limits": {"sbp_min": 90}} if i["kind"] == "obs" else i for i in orders["items"]]
    signed = client2.post(_url(iyer, "orders/sign"), json={"items": items, "by": DOC, "draft_id": orders["id"], "at_ms": 0})
    ack = _ack(client2, iyer, signed.json()["order_list"][0]["id"], at_ms=0).json()
    assert [t["kind"] for t in ack["tasks"]] == ["procedure", "obs"]

    heard = _dictate(client2, iyer, "dictate/task", "iyer-bp.wav", NURSE, H).json()
    assert [c["kind"] for c in heard["candidates"]] == ["obs"]
    assert heard["values"] == {"sbp": 82, "dbp": 54, "hr": 112}
    obs_id = heard["candidates"][0]["id"]
    stated = heard["values"]
    shot = _photo(client2, iyer, obs_id, "monitor-88-54.png", H, **stated).json()["photos"][-1]
    assert shot["check"]["match"] == "mismatch"
    body = {"via": "voice", "transcript": heard["transcript"], "proof_id": shot["id"], "values": stated, "at_ms": H}
    view = check(_done(client2, iyer, obs_id, **body).json())
    assert next(t for t in view["tasks"] if t["id"] == obs_id)["done"][0]["match"] == "mismatch"
    assert any(n["kind"] == "obs_past_limit" for n in view["nudges"])
    assert seen and not [s for s in seen if s and ADVICE.search(s)], [s for s in seen if ADVICE.search(s or "")]
