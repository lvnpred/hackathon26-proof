"""Proof checks for photos. Pure: a strip is matched to a dose task by medicine name, a monitor to the stated values.

A mismatch is flagged and never blocks anything (D9). Strength is shown, never compared.
"""

from __future__ import annotations

import json
import re

from app.journey.rx import key_of

NO_STRIP = "No strip could be read; the photo is kept."
NO_MONITOR = "The monitor could not be read; the photo is kept."
NO_STATED = "No stated value to compare; the photo is kept."
NO_READING = "Kept as proof; this kind of task has no reading."
MONITOR_KEYS = ("sbp", "dbp", "hr")
_FENCE = re.compile(r"^```[a-z]*\s*|\s*```$", re.I)


def parse_monitor_text(text: str) -> dict:
    """{sbp, dbp, hr} for the whole numbers present in a model's JSON reply. Anything else gives {}."""
    try:
        payload = json.loads(_FENCE.sub("", (text or "").strip()))
    except ValueError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {k: payload[k] for k in MONITOR_KEYS if isinstance(payload.get(k), int) and not isinstance(payload[k], bool)}


def check_strip(strips: list[dict], task: dict) -> dict:
    if not strips:
        return {"read": "", "match": "none", "why": NO_STRIP}
    read = ", ".join(f"{s['name_as_read']} {s['strength']}".strip() for s in strips)
    wanted = key_of(task.get("name") or task["title"])
    if any(key_of(s["name_as_read"]) == wanted for s in strips):
        return {"read": read, "match": "ok", "why": f"The strip reads {read}; the task is {wanted}."}
    return {"read": read, "match": "mismatch", "why": f"The strip reads {read}; the task is {wanted}."}


def _shown(values: dict, keys: list[str]) -> str:
    parts = []
    if "sbp" in keys and "dbp" in keys:
        parts.append(f"{values['sbp']}/{values['dbp']}")
    else:
        parts += [f"{k} {values[k]}" for k in ("sbp", "dbp") if k in keys]
    if "hr" in keys:
        parts.append(f"pulse {values['hr']}")
    return ", ".join(parts)


def check_monitor(read: dict, stated: dict) -> dict:
    if not read:
        return {"read": "", "match": "none", "why": NO_MONITOR}
    shown = _shown(read, [k for k in MONITOR_KEYS if k in read])
    shared = [k for k in MONITOR_KEYS if k in read and k in stated]
    if not shared:
        return {"read": shown, "match": "none", "why": NO_STATED}
    if all(read[k] == stated[k] for k in shared):
        return {"read": shown, "match": "ok", "why": f"The monitor reads {_shown(read, shared)}; stated the same."}
    why = f"The monitor reads {_shown(read, shared)}; stated {_shown(stated, shared)}."
    return {"read": shown, "match": "mismatch", "why": why}


def photos_view(events: list[dict]) -> list[dict]:
    """Every photo on the chart, oldest first, with its latest proof check."""
    checks = {e["payload"]["photo_id"]: e["payload"] for e in events if e["event_type"] == "proof.checked"}
    out = []
    for e in events:
        if e["event_type"] != "photo.added":
            continue
        p, found = e["payload"], checks.get(e["id"])
        if p["purpose"] == "frame":  # frames belong to a video check, not to the photo list
            continue
        out.append(
            {
                "id": e["id"],
                "purpose": p["purpose"],
                "task_id": p.get("task_id"),
                "by": p["by"],
                "at_ms": e["ts_ms"],
                "url": f"/journey/episodes/{e['episode_id']}/photos/{e['id']}",
                "check": {k: found[k] for k in ("read", "match", "why", "source")} if found else None,
            }
        )
    return out
