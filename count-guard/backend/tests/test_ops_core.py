"""Ops core: the level table, the work-item fold, the durable switch."""

from __future__ import annotations

import re

import pytest

from app.config import get_settings
from app.morning.store import MorningStore
from app.ops import items, site
from app.ops.policy import AI_BY, LEVELS, NEVER_WORDS, UNDO_MS

SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")
DOTTED = re.compile(r"\b[a-z]+\.[a-z_]+\b")


def _ev(type, payload, id, ts=0, supersedes=None):
    return {"id": id, "episode_id": "e1", "ts_ms": ts, "wall_clock": "", "event_type": type,
            "payload": payload, "supersedes_id": supersedes, "tier": "documentation"}


def _opened(id, ts=0, kind="ack_order", inputs=("o1",)):
    return _ev("work.opened", {"kind": kind, "reason": "Dr. A. Rao signed orders at 09:02; not acknowledged yet.",
                               "inputs": list(inputs), "owner_role": "nurse", "level": LEVELS[kind],
                               "key": f"{kind}:{inputs[0]}"}, id, ts)


def _done(work_id, id, ts=0, wrote=("w1",)):
    return _ev("work.done", {"work_id": work_id, "level": "L2", "by": AI_BY, "reason": "r",
                             "summary": "Acknowledged Dr. A. Rao's orders", "inputs": ["o1"],
                             "wrote": list(wrote), "undo_until_ms": ts + UNDO_MS}, id, ts)


def test_levels_match_spec():
    assert LEVELS["ack_order"] == "L2"
    assert LEVELS["draft_answer"] == "L1"
    assert LEVELS["nudge_obs_overdue"] == "L3"
    assert {k for k, v in LEVELS.items() if v == "Never"} == set(NEVER_WORDS)
    assert UNDO_MS == 600_000
    assert AI_BY == "AI (on behalf of Ward 4)"


def test_work_status_folds_in_order():
    evs = [_opened("a")]
    assert items.work_items(evs)[0]["status"] == "open"
    evs.append(_done("a", "a1", 5))
    row = items.work_items(evs)[0]
    assert row["status"] == "done" and row["done"]["work_id"] == "a" and row["proposed"] is None
    evs.append(_ev("work.undone", {"work_id": "a", "by": "Nurse", "reverted": ["w1"]}, "a2", 9))
    assert items.work_items(evs)[0]["status"] == "undone"
    evs += [_opened("b", 10, "draft_answer"),
            _ev("work.proposed", {"work_id": "b", "level": "L1"}, "b1", 11)]
    assert items.work_items(evs)[1]["status"] == "proposed"
    assert items.work_items(evs)[1]["proposed"]["level"] == "L1"
    evs.append(_ev("work.dropped", {"work_id": "b", "by": AI_BY, "reason": "x", "code": "rejected"}, "b2", 12))
    assert [w["status"] for w in items.work_items(evs)] == ["undone", "dropped"]
    first = items.work_items(evs)[0]
    assert first["id"] == "a" and first["kind"] == "ack_order" and first["at_ms"] == 0
    assert first["key"] == "ack_order:o1" and first["owner_role"] == "nurse"


def test_assignees_latest_visible():
    evs = [_ev("task.assigned", {"task_id": "t1", "to": "Nurse Meena (synthetic)"}, "x1", 1),
           _ev("task.assigned", {"task_id": "t1", "to": "Nurse Asha (synthetic)"}, "x2", 2)]
    assert items.assignees(evs) == {"t1": "Nurse Asha (synthetic)"}
    evs.append(_ev("work.reverted", {"work_id": "a", "event_id": "x2"}, "x3", 3, supersedes="x2"))
    assert items.assignees(evs) == {"t1": "Nurse Meena (synthetic)"}


def test_routes_use_short_names():
    evs = [_ev("question.routed", {"question_id": "q1", "to": "Dr. A. Rao (synthetic)"}, "r1")]
    assert items.routes(evs) == {"q1": "Dr. A. Rao"}


def test_ops_view_handling_caps_at_five_newest_first():
    evs = []
    for i in range(7):
        evs += [_opened(f"w{i}", i * 10), _done(f"w{i}", f"d{i}", i * 10 + 1, wrote=(f"e{i}",))]
    view = items.ops_view(evs)
    assert [h["work_id"] for h in view["handling"]] == ["w6", "w5", "w4", "w3", "w2"]
    assert view["handling"][0]["status"] == "done"
    assert view["by_event"]["e6"] == "w6"
    assert view["open"] == [] and view["proposals"] == []


def test_ops_view_open_and_proposals():
    evs = [_opened("a"), _opened("b", 1, "draft_answer"),
           _ev("work.proposed", {"work_id": "b", "sentence": "Draft answer to R. Kumar's question",
                                 "draft": "d", "cited": [], "editable": True, "reason": "r",
                                 "inputs": ["o1"]}, "b1", 2)]
    view = items.ops_view(evs)
    assert view["open"][0]["paused_note"] == "Paused · not done"
    assert view["proposals"][0]["work_id"] == "b" and view["proposals"][0]["owner_role"] == "nurse"


def test_ops_view_no_snake_case():
    evs = [_ev("order.signed", {}, "o1", 540000),
           _opened("a"), _done("a", "a1", 600000)]
    view = items.ops_view(evs)
    texts = []
    for row in view["handling"] + view["open"]:
        texts += [row.get("summary", ""), row["reason"]]
        texts += [i["label"] for i in row.get("inputs", [])]
    assert texts and all(texts)
    for text in texts:
        assert not SNAKE.search(text) and not DOTTED.search(text), text
    assert view["handling"][0]["inputs"][0]["label"] == "Signed orders"
    # An unknown input id and an unmapped type still read as words.
    evs.append(_ev("weird.thing_x", {}, "o2"))
    evs.append(_done("a", "a2", 700000))
    odd = items.ops_view(evs + [_opened("c", 1, inputs=("o2",)), _done("c", "c1", 800000)])
    for row in odd["handling"]:
        for i in row["inputs"]:
            assert not SNAKE.search(i["label"]) and not DOTTED.search(i["label"])


def test_pause_resume_is_durable(tmp_path):
    path = tmp_path / "m.db"
    store = MorningStore(path)
    assert site.paused(store) == (False, None)
    site.set_paused(store, True, "Demo dock (Doctor)", 0)
    again = MorningStore(path)
    assert site.paused(again) == (True, "Demo dock (Doctor)")
    assert site.site_episode(store) == site.site_episode(again)
    site.set_paused(again, False, "Owner", 5)
    assert site.paused(again) == (False, "Owner")


def test_board_events(tmp_path):
    store = MorningStore(tmp_path / "m.db")
    assert site.board_events(store) == []
    board = store.create_episode("Ward staff board (synthetic)")["id"]
    store.append(board, "doctor.status", {"doctor": "x"}, ts_ms=0)
    assert len(site.board_events(store)) == 1


def test_set_level_audits_and_refuses_never(tmp_path):
    store = MorningStore(tmp_path / "m.db")
    assert site.level_of(store, "ack_order") == "L2"
    site.set_level(store, "ack_order", "L1", "Owner", 0)
    assert site.level_of(store, "ack_order") == "L1"
    changed = [e for e in store.events(site.site_episode(store)) if e["event_type"] == "ops.policy_changed"]
    assert len(changed) == 1
    assert changed[0]["payload"] == {"kind": "ack_order", "from": "L2", "to": "L1", "by": "Owner"}
    for kind, level in (("prescribe", "L2"), ("nope", "L1"), ("ack_order", "L9"), ("ack_order", "Never")):
        with pytest.raises(ValueError):
            site.set_level(store, kind, level, "Owner", 1)
    assert len(store.events(site.site_episode(store))) == 1


def test_settings_default_off(monkeypatch):
    monkeypatch.delenv("CG_OPS_AGENT", raising=False)
    assert get_settings().ops_agent is False
    monkeypatch.setenv("CG_OPS_AGENT", "1")
    assert get_settings().ops_agent is True
