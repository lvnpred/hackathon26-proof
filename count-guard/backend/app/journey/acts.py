"""Person acts on AI proposals (clarity spec §4.3): who accepted, changed or overrode what the AI proposed, and when.

The chart view carries these as `acts`; the care app's `provenanceOf(item, acts)` turns them into one mark
("Proposed by AI", "Accepted by …", "Changed by …", "Overridden by …", "Seen by …"). A row's `proposed` is what the AI
proposed and `value` what the person saved; they differ when the person changed it. Read only: nothing here writes.
"""

from __future__ import annotations

from app.journey.stories import by_ai
from app.journey.theatre import DOSE, heard
from app.morning.discharge import visible_events

# Event type -> the payload key naming the AI proposal it answers.
REF_KEYS = {
    "order.signed": "draft_id",
    "discharge.signed": "draft_id",
    "handover.accepted": "handover_id",
    "drug.given": "draft_id",
    "count.pack_opened": "draft_id",
    "check.override": "item",
    "camera.ack": "advice_id",
    "camera.resolved": "advice_id",
    "task.done": "task_id",
}
REASONED = ("check.override", "camera.ack", "camera.resolved")


def _heard(payload: dict) -> bool:
    """A task saved from what was heard (a spoken completion), not a tap or typed text."""
    return payload.get("via") == "voice" and payload.get("heard_by") not in (None, "", "typed")


def _dose(payload: dict) -> dict:
    return {k: payload.get(k) for k in DOSE}


def _drug(p: dict, draft: dict) -> tuple[dict, dict]:
    """(proposed, value): the heard words and dose (re-read from the words heard before an edit) vs the given ones."""
    said = draft.get("text") or p.get("text") or ""
    was = draft.get("heard_text") or p.get("heard_text")
    proposed = {"said": was, **_dose(heard(was)[1])} if was else {"said": said, **_dose(draft or p)}
    return proposed, {"said": said, **_dose(p)}


def _pack(p: dict, draft: dict) -> tuple[dict, dict]:
    said = draft.get("text") or ""
    was = draft.get("heard_text")
    proposed_n = heard(was)[1].get("n", draft.get("n")) if was else draft.get("n")
    return {"said": was or said, "n": proposed_n}, {"said": said, "n": p.get("quantity")}


def _values(kind: str, p: dict, by_id: dict) -> dict:
    """{"value", "proposed"} for the act, where the record holds them."""
    if kind == "order.signed":
        return {"value": p.get("items")}
    if kind == "discharge.signed":
        return {"value": p.get("summary"), **({"proposed": p["proposed_summary"]} if "proposed_summary" in p else {})}
    if kind == "task.done":
        value = {"values": p.get("values"), "said": p.get("transcript", "")}
        if "proposed_values" not in p and not p.get("edited"):
            return {"value": value}
        proposed = {"values": p.get("proposed_values", p.get("values")), "said": p.get("heard_text") or value["said"]}
        return {"value": value, "proposed": proposed}
    if kind in ("drug.given", "count.pack_opened"):
        draft = (by_id.get(p.get("draft_id")) or {}).get("payload") or {}
        proposed, value = (_drug if kind == "drug.given" else _pack)(p, draft)
        return {"value": value, "proposed": proposed}
    return {}


def person_acts(events: list[dict]) -> list[dict]:
    """Oldest first: {id, type, ref, by, at_ms[, value, proposed, reason]} for each act a person wrote on an AI proposal."""
    by_id = {e["id"]: e for e in events}
    out = []
    for e in visible_events(events):
        kind, p = e["event_type"], e.get("payload") or {}
        ref = p.get(REF_KEYS.get(kind, ""))
        if not ref or not p.get("by") or by_ai(p) or (kind == "task.done" and not _heard(p)):
            continue
        row = {"id": e["id"], "type": kind, "ref": ref, "by": p["by"], "at_ms": e["ts_ms"], **_values(kind, p, by_id)}
        if kind in REASONED:
            row["reason"] = (p.get("reason") or "").strip()
        out.append(row)
    return out
