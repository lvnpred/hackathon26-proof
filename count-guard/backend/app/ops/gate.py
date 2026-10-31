"""The gate: writes an AI action as ordinary events, by the level in force (spec 4.4). Never reads a clock."""

from __future__ import annotations

from app.journey import states, tasks
from app.ops.items import Action
from app.ops.policy import AI_BY, NEVER_WORDS, UNDO_MS
from app.ops.site import level_of


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
    if level == "L1" or action.kind not in _DO:
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
