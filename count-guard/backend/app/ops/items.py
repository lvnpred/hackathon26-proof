"""Work items are events. This module folds them into rows and into the view the chart shows."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.journey.ask import short_name
from app.journey.stories import clock, plain
from app.morning.discharge import visible_events

ADVICE_WORDS = ("give", "take", "stop", "increase", "reduce", "start", "administer", "consider")
PAUSED_NOTE = "Paused · not done"
EXECUTABLE_LEVELS = ("L2", "L3")  # while paused, only these would have been carried out
HANDLING_MAX = 5
_STATUS_OF = {"work.done": "done", "work.proposed": "proposed", "work.dropped": "dropped",
              "work.undone": "undone"}

# Plain words for the record an item cites (R20). Unknown types read as "Earlier record".
_LABELS = {
    "order.signed": "Signed orders", "order.acknowledged": "Acknowledged orders",
    "task.created": "Nurse task", "task.done": "Finished task", "task.assigned": "Task assignment",
    "proof.checked": "Monitor photo read", "swabs.counted": "Camera count",
    "count.pack_opened": "Opened pack", "count.closing": "Closing count",
    "question.asked": "Patient question", "question.routed": "Routed question",
    "question.answered": "Answer to the patient", "nudge.raised": "Overdue reminder",
    "discharge.card": "Discharge card", "patient.state": "Patient move",
}
_FALLBACK_LABEL = "Earlier record"


@dataclass(frozen=True)
class WorkItem:
    kind: str
    reason: str
    inputs: tuple[str, ...]
    owner_role: str
    rule: str
    key: str


@dataclass(frozen=True)
class Action:
    kind: str
    args: dict
    summary: str
    sentence: str = ""
    draft: str = ""
    cited: tuple[dict, ...] = ()
    model: str = "rules"
    reason: str = ""  # overrides the item's reason on what the gate writes, when the planner knows more


def work_items(events: list[dict]) -> list[dict]:
    """One dict per `work.opened`, in opening order. `status` is the last of the work events for it."""
    rows: dict[str, dict] = {}
    for event in visible_events(events):
        kind, p = event["event_type"], event["payload"]
        if kind == "work.opened":
            rows[event["id"]] = {
                "id": event["id"], "kind": p.get("kind", ""), "status": "open",
                "level": p.get("level", ""), "owner_role": p.get("owner_role", ""),
                "reason": p.get("reason", ""), "inputs": list(p.get("inputs") or []),
                "key": p.get("key", ""), "at_ms": event["ts_ms"], "done": None, "proposed": None,
            }
        elif kind in _STATUS_OF and p.get("work_id") in rows:
            row = rows[p["work_id"]]
            row["status"] = _STATUS_OF[kind]
            if kind == "work.done":
                row["done"] = {**p, "at_ms": event["ts_ms"], "event_id": event["id"]}
            elif kind == "work.proposed":
                row["proposed"] = {**p, "at_ms": event["ts_ms"]}
    return list(rows.values())


def assignees(events: list[dict]) -> dict[str, str]:
    """task_id -> who it was assigned to; the latest visible `task.assigned` wins."""
    out: dict[str, str] = {}
    for event in visible_events(events):
        if event["event_type"] == "task.assigned":
            out[event["payload"]["task_id"]] = event["payload"]["to"]
    return out


def routes(events: list[dict]) -> dict[str, str]:
    """question_id -> the short name of whoever it was routed to."""
    out: dict[str, str] = {}
    for event in visible_events(events):
        if event["event_type"] == "question.routed":
            out[event["payload"]["question_id"]] = short_name(event["payload"]["to"])
    return out


def _plain_words(text: str) -> bool:
    words = set(re.findall(r"[a-z]+", text.lower()))
    return bool(text) and not words & set(ADVICE_WORDS) and not re.search(r"\b[a-z]+_[a-z_]+\b", text)


def _label(event: dict | None) -> str:
    if event is None:
        return _FALLBACK_LABEL
    if event["event_type"] == "task.created":  # name the task (M2); a title that reads as advice falls back
        p = event["payload"]
        title = str(p.get("title") or p.get("name") or p.get("kind") or "").strip()
        return f"Nurse task: {title}" if _plain_words(title) else _LABELS["task.created"]
    return _LABELS.get(event["event_type"], _FALLBACK_LABEL)


def _inputs(ids: list[str], by_id: dict[str, dict]) -> list[dict]:
    rows = []
    for input_id in ids:
        event = by_id.get(input_id)
        rows.append({"id": input_id, "label": _label(event), "when": clock(event["ts_ms"]) if event else ""})
    return rows


def _written(d: dict, by_id: dict[str, dict]) -> list[dict]:
    """The record rows the action wrote, then its own `work.done`: the shape of `ai_moments._written` (M1)."""
    ids = [i for i in d.get("wrote") or [] if i in by_id] + [i for i in [d.get("event_id")] if i in by_id]
    out = []
    for event_id in dict.fromkeys(ids):
        e = by_id[event_id]
        p = e["payload"]
        out.append({"event_id": e["id"], "type": e["event_type"], "when": clock(e["ts_ms"]), "by": p.get("by"),
                    "plain": plain(e), **{k: p[k] for k in ("read", "saved") if k in p}})
    return out


def handling_row(row: dict, by_id: dict[str, dict]) -> dict:
    """The C4 row of one done or undone work item."""
    d = row["done"]
    return {
        "work_id": row["id"], "kind": row["kind"], "level": d.get("level") or row["level"],
        "summary": d.get("summary", ""), "at_ms": d["at_ms"],
        "undo_until_ms": d.get("undo_until_ms") if row["status"] == "done" else None,
        "reason": d.get("reason") or row["reason"],
        "inputs": _inputs(d.get("inputs") or row["inputs"], by_id), "status": row["status"],
        "model": d.get("model") or "rules", "written": _written(d, by_id),
    }


def handled(events: list[dict]) -> list[dict]:
    """Every done or undone item, newest first, with no per-patient cap (the feed)."""
    by_id = {event["id"]: event for event in events}
    rows = [r for r in work_items(events) if r["status"] in ("done", "undone") and r["done"]]
    rows.sort(key=lambda r: r["done"]["at_ms"], reverse=True)
    return [handling_row(r, by_id) for r in rows]


def _open_rows(shown: list[dict], paused: bool) -> list[dict]:
    """Open items. Only while paused do they carry the note, and then only those the AI would have done itself (I4)."""
    rows = [row for row in shown if row["status"] == "open"]
    if not paused:
        return [{"work_id": row["id"], "kind": row["kind"], "reason": row["reason"]} for row in rows]
    return [{"work_id": row["id"], "kind": row["kind"], "reason": row["reason"], "paused_note": PAUSED_NOTE}
            for row in rows if row["level"] in EXECUTABLE_LEVELS]


def ops_view(events: list[dict], paused: bool = False) -> dict:
    """The C4 view: what the AI handled, what waits for a person, what is open, who got what."""
    by_id = {event["id"]: event for event in events}
    shown = work_items(events)
    done = [row for row in shown if row["status"] in ("done", "undone") and row["done"]]
    done.sort(key=lambda row: row["done"]["at_ms"])
    handling = [handling_row(row, by_id) for row in reversed(done)]
    proposals = []
    for row in shown:
        if row["status"] != "proposed":
            continue
        p = row["proposed"]
        proposals.append({
            "work_id": row["id"], "kind": row["kind"], "owner_role": row["owner_role"], "level": "L1",
            "model": p.get("model") or "rules", "sentence": p.get("sentence", ""), "draft": p.get("draft", ""),
            "cited": p.get("cited") or [], "at_ms": p["at_ms"], "editable": bool(p.get("editable")),
            "reason": p.get("reason") or row["reason"],
            "inputs": _inputs(p.get("inputs") or row["inputs"], by_id),
        })
    return {
        "handling": handling[:HANDLING_MAX],
        "proposals": proposals,
        "open": _open_rows(shown, paused),
        "routes": routes(events),
        "assignees": assignees(events),
        "by_event": {event_id: row["id"] for row in done if row["status"] == "done"
                     for event_id in row["done"].get("wrote") or []},
    }
