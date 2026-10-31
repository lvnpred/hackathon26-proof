"""The run loop: drop stale proposals, open new work, then plan and apply each open item (R5, R12, R13)."""

from __future__ import annotations

import threading

from app.journey.ask import short_name
from app.ops import gate, site, watch
from app.morning.discharge import visible_events
from app.ops.items import WorkItem, work_items
from app.ops.plan import plan
from app.ops.policy import AI_BY, MAX_PASSES, MAX_PROPOSALS

DONE_BY_PERSON = "A person already did this."
NO_LONGER_NEEDED = "No longer needed."
# One run at a time, across episodes: two overlapping writes must not plan the same item, and the
# gate's before/after diff of event ids must hold only its own events.
_LOCK = threading.Lock()


def _open(store, episode_id: str, item: WorkItem, at_ms: int) -> dict:
    payload = {"kind": item.kind, "reason": item.reason, "inputs": list(item.inputs), "owner_role": item.owner_role,
               "lease": {"holder": "ops-agent", "until_ms": 0}, "level": site.level_of(store, item.kind),
               "created_by_rule": item.rule, "key": item.key, "by": AI_BY, "model": "rules"}
    return store.append(episode_id, "work.opened", payload, ts_ms=at_ms)


def _as_item(row: dict) -> WorkItem:
    return WorkItem(row["kind"], row["reason"], tuple(row["inputs"]), row["owner_role"],
                    row["key"].split(":")[0], row["key"])


def _person_acted(events: list[dict], item: WorkItem) -> bool:
    """True only when a non-AI event shows a person did what the item asked."""
    first = item.inputs[0] if item.inputs else ""
    for e in visible_events(events):
        p, kind = e["payload"], e["event_type"]
        if p.get("by") == AI_BY:
            continue
        if (kind == "order.acknowledged" and item.kind == "ack_order" and p.get("order_id") == first) \
                or (kind == "question.answered" and item.kind in ("route_question", "draft_answer")
                    and p.get("question_id") == first) \
                or (kind == "task.done" and item.kind == "file_read" and p.get("proof_id") == first) \
                or (kind == "count.closing" and item.kind == "file_read"):
            return True
    return False


def _waiting(events: list[dict], role: str) -> int:
    return sum(1 for r in work_items(events) if r["status"] == "proposed" and r["owner_role"] == role)


def _pass(store, episode_id, at_ms, patient, board, settings, write, written) -> int:
    """One sweep. Returns how many items it opened."""
    for work_id, code, reason in watch.stale(store.events(episode_id)):
        written.append(gate.drop(store, episode_id, work_id, code, reason, at_ms=at_ms))
    fresh = watch.watch(store.events(episode_id), at_ms)
    for item in fresh:
        written.append(_open(store, episode_id, item, at_ms))
    if site.paused(store)[0]:
        return len(fresh)
    for row in [r for r in work_items(store.events(episode_id)) if r["status"] == "open"]:
        events = store.events(episode_id)
        item = _as_item(row)
        level = site.level_of(store, item.kind)
        if (level == "L1" or (level != "Never" and item.kind not in gate.EXECUTABLE)) and _waiting(events, item.owner_role) >= MAX_PROPOSALS:
            continue
        action = plan(item, events, board=board, at_ms=at_ms, settings=settings, write=write, patient=patient)
        if action is None:
            why = DONE_BY_PERSON if _person_acted(events, item) else NO_LONGER_NEEDED
            written.append(gate.drop(store, episode_id, row["id"], "done_by_person", why, at_ms=at_ms))
        else:
            written.extend(gate.apply(store, episode_id, row["id"], item, action, at_ms))
    return len(fresh)


def run(store, episode_id: str, at_ms: int, *, settings, write=None) -> list[dict]:
    """Everything the agent wrote for this episode at this moment. [] while the agent is off."""
    if not settings.ops_agent:
        return []
    written: list[dict] = []
    with _LOCK:
        episode = store.get_episode(episode_id)
        patient = short_name(episode["label"]) if episode else ""
        board = site.board_events(store)
        for _ in range(MAX_PASSES):
            if not _pass(store, episode_id, at_ms, patient, board, settings, write, written):
                break
    return written
