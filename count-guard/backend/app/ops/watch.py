"""Watcher rules: decide *that* work is needed, once per input. Pure; `plan` decides who and what."""

from __future__ import annotations

from app.journey import states, tasks
from app.journey.ask import short_name
from app.journey.stories import clock
from app.morning.discharge import visible_events
from app.ops.items import WorkItem, assignees, routes, work_items
from app.ops.policy import FILE_AFTER_MS

WATCHED_KINDS = ("ack_order", "assign_task", "nudge_obs_overdue", "route_question", "draft_answer",
                "file_read", "propose_move")
RULES = ("orders_unacknowledged", "task_unassigned", "obs_overdue", "question_waiting",
         "read_unfiled", "move_ready")
_MONITOR_KEYS = ("sbp", "dbp", "hr")
_OVERDUE = {"obs_overdue": "Observations are overdue.", "dose_overdue": "A dose is overdue."}


def _of(events: list[dict], kind: str) -> list[dict]:
    return [e for e in events if e["event_type"] == kind]


def _latest(events: list[dict], kind: str) -> dict | None:
    rows = _of(events, kind)
    return rows[-1] if rows else None


def _item(kind: str, rule: str, reason: str, inputs: tuple[str, ...], role: str, key_id: str) -> WorkItem:
    return WorkItem(kind, reason, inputs, role, rule, f"{rule}:{kind}:{key_id}")


def orders_unacknowledged(events: list[dict], at_ms: int, opened: set[str]) -> list[WorkItem]:
    if states.current_state(events) not in tasks.ACK_STATES:
        return []
    signed = {e["id"]: e for e in _of(visible_events(events), "order.signed")}
    out = []
    for order in tasks.orders_list(events):
        if order["acknowledged_by"]:
            continue
        reason = f"{short_name(order['by'])} signed orders at {clock(signed[order['id']]['ts_ms'])[-5:]}; not acknowledged yet."
        out.append(_item("ack_order", "orders_unacknowledged", reason, (order["id"],), "nurse", order["id"]))
    return out


def task_unassigned(events: list[dict], at_ms: int, opened: set[str]) -> list[WorkItem]:
    given = assignees(events)
    by_order: dict[str, list[str]] = {}
    finished = {t["id"] for t in tasks.task_list(events) if t["status"] in ("done", "closed")}
    for created in _of(visible_events(events), "task.created"):
        if created["id"] not in given and created["id"] not in finished:
            by_order.setdefault(created["payload"]["order_id"], []).append(created["id"])
    signed = {o["id"]: o for o in tasks.orders_list(events)}
    out = []
    for order_id, ids in by_order.items():
        who = f"{short_name(signed[order_id]['by'])}'s" if order_id in signed else "the"
        noun = "nurse task has" if len(ids) == 1 else "nurse tasks have"
        out.append(_item("assign_task", "task_unassigned", f"{len(ids)} {noun} no nurse from {who} orders yet.",
                         tuple(ids), "nurse", order_id))
    return out


def obs_overdue(events: list[dict], at_ms: int, opened: set[str]) -> list[WorkItem]:
    return [_item("nudge_obs_overdue", "obs_overdue", _OVERDUE[e["payload"]["kind"]], (e["id"],), "nurse", e["id"])
            for e in _of(visible_events(events), "nudge.raised") if e["payload"].get("kind") in _OVERDUE]


def question_waiting(events: list[dict], at_ms: int, opened: set[str]) -> list[WorkItem]:
    shown = visible_events(events)
    answered = {e["payload"]["question_id"] for e in _of(shown, "question.answered")}
    routed = routes(events)
    card = _latest(shown, "discharge.card")
    out = []
    for q in _of(shown, "question.asked"):
        if q["payload"].get("to") != "doctor" or q["id"] in answered:
            continue
        when = f"The patient asked the doctor a question at {clock(q['ts_ms'])[-5:]}; not answered yet."
        if q["id"] not in routed:
            out.append(_item("route_question", "question_waiting", when, (q["id"],), "doctor", q["id"]))
        if card:
            out.append(_item("draft_answer", "question_waiting", when, (q["id"], card["id"]), "doctor", q["id"]))
    return out


def monitor_reads(events: list[dict]) -> list[dict]:
    shown = visible_events(events)
    saved = {e["payload"].get("proof_id") for e in _of(shown, "task.done")}
    live = {t["id"]: t for t in tasks.task_list(events)}
    out = []
    for e in _of(shown, "proof.checked"):
        p = e["payload"]
        read = p.get("values_read") or {}
        task = live.get(p.get("task_id"))
        if not all(read.get(k) is not None for k in _MONITOR_KEYS) or p["photo_id"] in saved:
            continue
        if task and task["kind"] == "obs" and task["status"] in ("open", "running"):
            out.append(e)
    return out


def read_unfiled(events: list[dict], at_ms: int, opened: set[str]) -> list[WorkItem]:
    """Monitor reads only (ruling F-I3). A camera swab count is never filed by the AI: a person saves the closing."""
    reason = f"The read was not saved within {FILE_AFTER_MS // 60_000} minutes."
    return [_item("file_read", "read_unfiled", reason, (e["id"],), "nurse", e["id"])
            for e in monitor_reads(events) if at_ms - e["ts_ms"] >= FILE_AFTER_MS]


def count_unclosed(events: list[dict]) -> bool:
    """True when this stay has a pack opened and no closing count after it."""
    stay = states.stay_events(events)
    pack, closing = states.stay_latest(events, "count.pack_opened"), states.stay_latest(events, "count.closing")
    return bool(pack) and (closing is None or stay.index(closing) < stay.index(pack))


def _move_to_ward(events: list[dict]) -> dict | None:
    if states.current_state(events) != "theatre":
        return None
    return next((m for m in states.allowed_moves(events) if m["to"] == "ward" and not m["needs"]), None)


def move_ready(events: list[dict], at_ms: int, opened: set[str]) -> list[WorkItem]:
    move = _move_to_ward(events)
    if not move:
        return []
    if count_unclosed(events):
        return []  # a count was started and never closed: never nudge leaving theatre
    closing = states.stay_latest(events, "count.closing")
    last = _latest(visible_events(events), "patient.state")
    reason = ("Surgery has ended and the count is closed; the patient can go back to the ward." if closing
              else "Surgery has ended; no swab count was started.")
    return [_item("propose_move", "move_ready", reason, (last["id"],), move["role"], f"ward:{last['id']}")]


_RULE_FNS = (orders_unacknowledged, task_unassigned, obs_overdue, question_waiting, read_unfiled, move_ready)


def watch(events: list[dict], at_ms: int) -> list[WorkItem]:
    """Items whose key no `work.opened` holds yet. A key appears at most once per call."""
    opened = {row["key"] for row in work_items(events)}
    out: list[WorkItem] = []
    for rule in _RULE_FNS:
        for item in rule(events, at_ms, opened):
            if item.key not in opened:
                opened.add(item.key)
                out.append(item)
    return out


def stale(events: list[dict]) -> list[tuple[str, str, str]]:
    """(work_id, code, reason) for each proposal whose condition no longer holds (R14)."""
    shown = visible_events(events)
    answered = {e["payload"]["question_id"] for e in _of(shown, "question.answered")}
    out = []
    for row in work_items(events):
        if row["status"] != "proposed":
            continue
        if row["kind"] == "draft_answer" and row["inputs"] and row["inputs"][0] in answered:
            out.append((row["id"], "done_by_person", "The question was already answered."))
        elif row["kind"] == "propose_move" and not move_ready(events, 0, set()):
            if states.current_state(events) == "ward":
                out.append((row["id"], "done_by_person", "The patient was already moved to the ward."))
            else:
                out.append((row["id"], "no_longer_allowed", "The move back to the ward is no longer allowed."))
    return out
