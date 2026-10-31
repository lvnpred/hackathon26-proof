"""Word spans: where each order field was said in the transcript (R9)."""

from __future__ import annotations

import httpx
import pytest

from app.journey.dictation import order_spans, parse_order_text
from tests.test_flow_states import _new
from tests.test_p2_dictation import _typed

KUMAR = "Admit for open hernia repair. Paracetamol 1 g every 6 hours, strip photo as proof. BP and pulse every 1 hour, lower systolic limit 90."


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _got(spans):
    return {(m["item"], m["field"]): spans["text"][m["start"]:m["end"]] for m in spans["marks"]}


def test_spans_for_demo_transcript():
    spans = order_spans(KUMAR, parse_order_text(KUMAR)["items"])
    got = _got(spans)
    assert got[(0, "name")].lower() == "paracetamol" and got[(0, "amount")] == "1 g"
    assert got[(0, "every_h")] == "every 6 hours" and got[(0, "proof")] == "photo"
    assert got[(1, "every_h")] == "every 1 hour" and got[(1, "limits.sbp_min")] == "90"


def test_spans_from_number_words():
    text = "Paracetamol one gram every six hours"
    spans = order_spans(text, parse_order_text(text)["items"])
    assert spans["text"] == "Paracetamol 1 gram every 6 hours"
    got = _got(spans)
    assert got[(0, "name")] == "Paracetamol" and got[(0, "amount")] == "1 gram" and got[(0, "every_h")] == "every 6 hours"


def test_spans_skip_missing_and_never_overlap():
    items = [{"kind": "dose", "text": "Ibuprofen 1 g", "name": "ibuprofen", "amount": "1 g", "every_h": 6, "proof": "photo"}]
    spans = order_spans(KUMAR, items)
    assert (0, "name") not in _got(spans)
    marks = spans["marks"]
    assert marks == sorted(marks, key=lambda m: m["start"])
    assert all(a["end"] <= b["start"] for a, b in zip(marks, marks[1:]))


def test_dictate_orders_writes_spans(tmp_path):
    client, eid = _new(tmp_path)
    view = _typed(client, eid, "dictate/orders", KUMAR).json()
    spans = view["drafts"]["order"]["spans"]
    assert spans["text"] == KUMAR
    assert {m["field"] for m in spans["marks"]} >= {"name", "amount", "every_h", "proof", "limits.sbp_min"}
