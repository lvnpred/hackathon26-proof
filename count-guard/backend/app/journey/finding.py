"""The pill on an AI moment: the clinical finding in a role and a few words, never "Recorded" (spec section 5.2).

Roles: fine (a person can stop thinking), wait (someone else owns it), check (a person must look),
danger (act now), done (kept, nothing to judge). Texts come from numbers and record fields only.
"""

from __future__ import annotations

from app.journey import nudges
from app.journey.stories import clock, count_of

OVERDUE = ("dose_overdue", "obs_overdue")


def _hhmm(ms: int) -> str:
    return clock(ms)[-5:]


def _late(minutes: int) -> str:
    hours, rest = divmod(max(0, minutes), 60)
    if hours and rest:
        return f"Late {hours} h {rest} min"
    return f"Late {hours} h" if hours else f"Late {rest} min"


def _late_minutes(payload: dict, ix) -> int:
    """Minutes past the due time of an overdue nudge, from the order it compares and the last fact."""
    intent, fact = ix.by_id.get(payload.get("intent_id")), ix.by_id.get(payload.get("fact_id"))
    if not intent:
        return 0
    if payload["kind"] == "obs_overdue":
        every = (intent["payload"].get("obs_every_h") or 0) * nudges.HOUR_MS
    else:
        key = str(payload.get("key", "")).split(":")[1:2]
        order = next((d for d in intent["payload"].get("doses") or [] if key and d["key"] == key[0]), None)
        every = (order["every_h"] if order else 0) * nudges.HOUR_MS
    since = payload.get("at_ms", 0) - (fact["ts_ms"] if fact else intent["ts_ms"])
    return int((since - every) // 60_000)


def _signed_time(moment: dict) -> str | None:
    signed = next((w for w in moment["written"] if w["type"].endswith(".signed")), None)
    return signed["when"][-5:] if signed else None


def _nudge(status: str, moment: dict, ix) -> tuple[str, str]:
    payload = ix.by_id[moment["id"]]["payload"]
    kind = payload.get("kind")
    if status == "open":
        if kind == "obs_past_limit":
            return "danger", "Below limit" if " below " in payload.get("says", "") else "Above limit"
        if kind in OVERDUE:
            return "check", _late(_late_minutes(payload, ix))
        return _waiting(moment)
    if kind == "count_open":  # a correction closed it: the person's count now matches the pack
        return "fine", "Count complete"
    return "done", f"Saved {_hhmm(moment['at_ms'])}"


def _waiting(moment: dict) -> tuple[str, str]:
    return "wait", f"Waiting for the {moment['owner']}" if moment.get("owner") else "Waiting"


def _unaccounted_text(n: int) -> str:
    return f"{count_of(n, 'swab')} unaccounted"


def _open_count(moment: dict, ix) -> int | None:
    """Unaccounted swabs of the closing count a still-open count_open nudge reports."""
    fact = ix.by_id.get((moment["refs"].get("fact") or {}).get("id"))
    return (fact["payload"].get("unaccounted") or 0) if fact else None


def classify(cap: str, status: str, moment: dict, ix, resolver: dict | None = None) -> tuple[str, str]:
    """C3: (role, text) for one moment. `resolver` is the record event that closed a flagged camera check."""
    if status == "undone":
        return "done", "Undone"
    if cap == "nudge":
        if status == "open" and moment["refs"].get("kind") == "count_open":
            n = _open_count(moment, ix)
            if n:
                return "danger", _unaccounted_text(n)
        return _nudge(status, moment, ix)
    if cap in ("tray", "setup", "swabs"):
        if status == "flagged":
            return "check", "Surgeon to decide" if cap == "tray" else "Check this"
        if resolver is not None:
            if cap == "swabs":
                return "done", "Replaced by count"
            return "fine", f"Checked by {resolver['payload'].get('by') or 'staff'}"
    if status == "open":
        return _waiting(moment)
    if status == "matches":
        return "fine", "Matches"
    if status in ("flagged", "failed"):
        return "check", "Check this"
    return "done", f"Signed {_signed_time(moment)}" if _signed_time(moment) else f"Saved {_hhmm(moment['at_ms'])}"
