"""The gate: writes an AI action as ordinary events, by the level in force (spec 4.4). Never reads a clock."""

from __future__ import annotations

from app.journey import states, tasks
from app.journey.ask import ANSWERED
from app.journey.stories import by_ai
from app.morning.discharge import visible_events
from app.ops.items import Action, work_items
from app.ops.policy import AI_BY, LEVELS, NEVER_WORDS, UNDO_MS
from app.ops.site import level_of

NOT_FOUND = "Work item not found"
CANNOT_UNDO = "This action cannot be undone."
WINDOW_CLOSED = "The undo window has closed."
PERSON_ACTED = "A person has already acted on this, so it cannot be undone here."
NOT_WAITING = "This proposal is no longer waiting."
DOCTOR_ONLY = "Only the doctor approves an answer to the patient."
NOT_APPROVABLE = "This proposal cannot be approved here."
DOCTOR_PREFIX = "Dr. "


class OpsError(Exception):
    """A refused ops request. `status` is the HTTP code a route maps it to."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _provenance(item, action: Action, level: str) -> dict:
    return {"level": level, "by": AI_BY, "reason": item.reason, "model": action.model, "inputs": list(item.inputs)}


def _assign(store, episode_id, action, level, item, at_ms) -> None:
    for task_id, nurse in action.args["pairs"]:
        store.append(episode_id, "task.assigned",
                     {"task_id": task_id, "to": nurse, **_provenance(item, action, level)}, ts_ms=at_ms)


def _route(store, episode_id, action, level, item, at_ms) -> None:
    store.append(episode_id, "question.routed",
                 {"question_id": action.args["question_id"], "to": action.args["to"], **_provenance(item, action, level)},
                 ts_ms=at_ms)


def _file_read(store, episode_id, action, level, item, at_ms) -> None:
    a = action.args
    if a["source"] == "monitor":
        tasks.complete_task(store, episode_id, a["task_id"], AI_BY, at_ms, values=a["values"], proof_id=a["photo_id"])
        return
    payload = states.closing_payload(store.events(episode_id), a["count"], AI_BY, evidence_id=a["evidence_id"])
    store.append(episode_id, "count.closing", payload, ts_ms=at_ms)


def _ack(store, episode_id, action, level, item, at_ms) -> None:
    tasks.acknowledge_order(store, episode_id, action.args["order_id"], AI_BY, at_ms)


def _nudge(store, episode_id, action, level, item, at_ms) -> None:
    """Nudges are already automatic; the item only records that the AI named the nurse (R18)."""


_DO = {"ack_order": _ack, "assign_task": _assign, "route_question": _route, "file_read": _file_read,
       "nudge_obs_overdue": _nudge}


EXECUTABLE = frozenset(_DO)  # kinds the gate can carry out; the rest are only ever proposed


def execute(store, episode_id: str, action: Action, level: str, item, at_ms: int) -> list[str]:
    """Run the action's writer and return the ids it appended (R7). A TaskError passes through to the caller."""
    before = {e["id"] for e in store.events(episode_id)}
    _DO[action.kind](store, episode_id, action, level, item, at_ms)
    return [e["id"] for e in store.events(episode_id) if e["id"] not in before]


def drop(store, episode_id: str, work_id: str, code: str, reason: str, by: str = AI_BY, at_ms: int = 0) -> dict:
    return store.append(episode_id, "work.dropped", {"work_id": work_id, "by": by, "reason": reason, "code": code},
                        ts_ms=at_ms)


def apply(store, episode_id: str, work_id: str, item, action: Action, at_ms: int, level: str | None = None) -> list[dict]:
    """Write what the level allows: L3 and L2 do it, L1 proposes, Never drops. Returns the events written."""
    level = level or level_of(store, action.kind)
    if level == "Never":
        words = NEVER_WORDS.get(action.kind, action.kind)
        return [drop(store, episode_id, work_id, "never",
                     f"The AI never does this: {words}. A person does it from the chart.", at_ms=at_ms)]
    if level == "L0":
        return []  # observe only: the item stays open
    if level == "L1" or action.kind not in EXECUTABLE:
        sentence = action.sentence or action.summary
        proposed = {"work_id": work_id, **_provenance(item, action, "L1"), "sentence": sentence, "draft": action.draft,
                    "cited": list(action.cited), "action": {"kind": action.kind, "args": action.args},
                    "owner_role": item.owner_role, "editable": bool(action.draft)}
        return [store.append(episode_id, "work.proposed", proposed, ts_ms=at_ms)]
    try:
        wrote = execute(store, episode_id, action, level, item, at_ms)
    except tasks.TaskError as exc:
        return [drop(store, episode_id, work_id, "refused", exc.detail, at_ms=at_ms)]
    done = {"work_id": work_id, **_provenance(item, action, level), "summary": action.summary, "wrote": wrote}
    if level == "L2":
        done["undo_until_ms"] = at_ms + UNDO_MS
    return [store.append(episode_id, "work.done", done, ts_ms=at_ms)]


def _row(events: list[dict], work_id: str) -> dict:
    row = next((r for r in work_items(events) if r["id"] == work_id), None)
    if row is None:
        raise OpsError(404, NOT_FOUND)
    return row


def _person_acted(events: list[dict], wrote: list[str]) -> bool:
    """True when a visible non-AI event points at something the action wrote."""
    ids = set(wrote)
    for e in visible_events(events):
        p = e["payload"]
        if by_ai(p) or e["event_type"].startswith(("work.", "nudge.")):
            continue
        if ids & {p.get("task_id"), p.get("order_id"), p.get("question_id")}:
            return True
    return False


def _revert(store, episode_id: str, row: dict, by: str, at_ms: int) -> None:
    wrote = list((row["done"] or {}).get("wrote") or [])[::-1]  # newest first
    for event_id in wrote:
        store.append(episode_id, "work.reverted", {"work_id": row["id"], "event_id": event_id},
                     ts_ms=at_ms, supersedes_id=event_id)
    store.append(episode_id, "work.undone", {"work_id": row["id"], "by": by, "reverted": wrote}, ts_ms=at_ms)


def undo(store, episode_id: str, work_id: str, by: str, at_ms: int) -> None:
    """Take back an L2 action inside its window (R7). Every refusal is raised before anything is written."""
    events = store.events(episode_id)
    row = _row(events, work_id)
    done = row["done"] or {}
    if row["status"] != "done" or done.get("level") != "L2" or "undo_until_ms" not in done:
        raise OpsError(409, CANNOT_UNDO)
    if at_ms > done["undo_until_ms"]:
        raise OpsError(409, WINDOW_CLOSED)
    wrote = list(done.get("wrote") or [])
    if _person_acted(events, wrote):
        raise OpsError(409, PERSON_ACTED)
    # One level of cascade: AI work that took these ids as input (the assignment of an undone ack).
    follow = [r for r in work_items(events) if r["id"] != work_id and r["status"] == "done"
              and set(r["done"].get("inputs") or r["inputs"]) & set(wrote)]
    for other in follow:
        _revert(store, episode_id, other, by, at_ms)
    _revert(store, episode_id, row, by, at_ms)


def _proposed(events: list[dict], work_id: str) -> dict:
    """The row of a proposal, refusing a Never kind (403) before a wrong status (409)."""
    row = _row(events, work_id)
    if LEVELS.get(row["kind"]) == "Never":
        words = NEVER_WORDS.get(row["kind"], row["kind"])
        raise OpsError(403, f"The AI never does this: {words}. A person does it from the chart.")
    if row["status"] != "proposed":
        raise OpsError(409, NOT_WAITING)
    return row


def _approve_move(store, episode_id: str, events: list[dict], by: str, at_ms: int) -> list[str]:
    try:
        payload = states.move_payload(events, "ward", {"by": by})
    except states.MoveRefused as exc:
        raise OpsError(409, str(exc)) from exc
    return [store.append(episode_id, "patient.state", payload, ts_ms=at_ms)["id"]]


def _approve_answer(store, episode_id: str, row: dict, events: list[dict], by: str, text: str | None,
                    at_ms: int) -> list[str]:
    if not by.startswith(DOCTOR_PREFIX):
        raise OpsError(403, DOCTOR_ONLY)
    proposed = row["proposed"]
    question_id = proposed["action"]["args"]["question_id"]
    if any(e["payload"].get("question_id") == question_id
           for e in visible_events(events) if e["event_type"] == "question.answered"):
        raise OpsError(409, ANSWERED)
    answer = {"question_id": question_id, "answer": text or proposed.get("draft", ""), "by": by, "via": "text",
              "heard_by": "", "sources": [c["id"] for c in proposed.get("cited") or []], "found": True,
              "source": "doctor", "calls": []}
    return [store.append(episode_id, "question.answered", answer, ts_ms=at_ms)["id"]]


def approve(store, episode_id: str, work_id: str, by: str, text: str | None, at_ms: int) -> None:
    """A person approves an L1 proposal (R9, R16). The write is the person's, so `by` is the approver."""
    events = store.events(episode_id)
    row = _proposed(events, work_id)
    if row["kind"] == "propose_move":
        wrote = _approve_move(store, episode_id, events, by, at_ms)
    elif row["kind"] == "draft_answer":
        wrote = _approve_answer(store, episode_id, row, events, by, text, at_ms)
    else:
        raise OpsError(409, NOT_APPROVABLE)
    p = row["proposed"]
    store.append(episode_id, "work.done",
                 {"work_id": work_id, "level": "L1", "by": by, "approved_by": by, "reason": p.get("reason") or row["reason"],
                  "model": p.get("model", "rules"), "inputs": p.get("inputs") or row["inputs"],
                  "summary": p.get("sentence", ""), "wrote": wrote}, ts_ms=at_ms)


def reject(store, episode_id: str, work_id: str, by: str, note: str, at_ms: int) -> None:
    row = _row(store.events(episode_id), work_id)
    if row["status"] != "proposed":
        raise OpsError(409, NOT_WAITING)
    drop(store, episode_id, work_id, "rejected", note or "Rejected", by=by, at_ms=at_ms)
