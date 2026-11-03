"""Clarity Task 5 (spec §4.3): the person acts that answer an AI proposal, for the AI proposed / accepted marks."""

from __future__ import annotations

from app.journey.acts import person_acts

RAO, ASHA = "Dr. A. Rao (synthetic)", "Nurse Asha (synthetic)"
ITEMS = [{"kind": "dose", "name": "Paracetamol", "amount": "1 g", "every_h": 6, "text": "Paracetamol 1 g every 6 h"}]


def _ev(eid, etype, ts, supersedes_id=None, **payload):
    return {"id": eid, "event_type": etype, "ts_ms": ts, "payload": payload, "episode_id": "e1", "supersedes_id": supersedes_id}


def test_each_person_act_names_what_it_answers_who_and_when():
    events = [
        _ev("s1", "order.signed", 10, draft_id="d1", by=RAO, items=ITEMS),
        _ev("s2", "discharge.signed", 20, draft_id="d2", by=RAO, summary="Course: fine"),
        _ev("h1", "handover.accepted", 30, handover_id="h0", by=ASHA),
        _ev("g1", "drug.given", 40, draft_id="dr1", by=ASHA),
        _ev("p1", "count.pack_opened", 50, draft_id="pk1", by=ASHA, quantity=10),
        _ev("o1", "check.override", 60, item="task:t1", by=ASHA, reason="Seen by eye"),
        _ev("a1", "camera.ack", 70, advice_id="ad1", by=ASHA, reason=""),
        _ev("r1", "camera.resolved", 80, advice_id="ad2", by=ASHA, reason="Counted by hand"),
        _ev("t1", "task.done", 90, task_id="t9", by=ASHA, via="voice", heard_by="voice", values={"sbp": 120}),
    ]
    rows = person_acts(events)
    assert [(r["type"], r["ref"], r["at_ms"]) for r in rows] == [
        ("order.signed", "d1", 10), ("discharge.signed", "d2", 20), ("handover.accepted", "h0", 30),
        ("drug.given", "dr1", 40), ("count.pack_opened", "pk1", 50), ("check.override", "task:t1", 60),
        ("camera.ack", "ad1", 70), ("camera.resolved", "ad2", 80), ("task.done", "t9", 90),
    ]
    assert all(r["by"] in (RAO, ASHA) for r in rows)
    assert rows[0]["value"] == ITEMS
    assert rows[1]["value"] == "Course: fine"
    assert rows[8]["value"] == {"values": {"sbp": 120}, "said": ""}
    assert "value" not in rows[2] and "proposed" not in rows[8]  # an old save without its proposal: nothing to compare


def test_typed_orders_tapped_tasks_ai_writers_and_superseded_rows_are_left_out():
    events = [
        _ev("s1", "order.signed", 10, by=RAO, items=ITEMS),  # typed: no draft to answer
        _ev("t1", "task.done", 20, task_id="t9", by=ASHA, via="tap"),
        _ev("t2", "task.done", 25, task_id="t9", by=ASHA, via="voice", heard_by="typed"),
        _ev("a1", "camera.ack", 30, advice_id="ad1", by="AI (on behalf of Ward 4)"),
        _ev("g1", "drug.given", 40, draft_id="dr1", by=ASHA),
        _ev("g2", "drug.given", 45, supersedes_id="g1", draft_id="dr1", by=RAO),
    ]
    rows = person_acts(events)
    assert [(r["id"], r["by"]) for r in rows] == [("g2", RAO)]


def test_the_chart_view_carries_the_acts(tmp_path):
    from tests.test_journey import _client, _handover, _ward

    api = _client(tmp_path)
    _, base = _ward(api)
    handover = _handover(api, base)
    assert api.get(base).json()["acts"] == []
    view = api.post(f"{base}/handover/{handover['id']}/accept", json={"by": "Nurse B", "at_ms": 4 * 3_600_000}).json()
    assert view["acts"] == [{"id": view["acts"][0]["id"], "type": "handover.accepted", "ref": handover["id"], "by": "Nurse B",
                             "at_ms": 4 * 3_600_000}]
