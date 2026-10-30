"""The "AI at work" summary: which model made which call in the roster's records. Pure."""

from __future__ import annotations

import statistics

from app.journey.ask import short_name
from app.journey.live import mode_of
from app.journey.stories import clock, plain

MODELS = [
    {"key": "voice", "name": "Muse Voice", "role": "Writes down what staff say: orders, discharges, answers and task updates."},
    {"key": "spark", "name": "Muse Spark 1.3", "role": "Reads photos and drafts orders and answers from the record."},
    {"key": "sam", "name": "SAM 3.1", "role": "Finds and counts instruments, swabs and photo regions."},
    {"key": "spark-open", "name": "Muse Spark Open", "role": "Explains a count discrepancy on the camera screen; ward questions come later."},
]
MAX_RECENT = 20


def _rows(roster: list[tuple[dict, list[dict]]]) -> list[dict]:
    """One row per (event, call), in record order (event order, then call order)."""
    rows = []
    for episode, events in roster:
        for event in events:
            for call in (event.get("payload") or {}).get("calls") or []:
                rows.append({"episode": episode, "event": event, "call": call, "seq": len(rows)})
    return rows


def _newest(rows: list[dict]) -> dict | None:
    return max(rows, key=lambda r: (r["event"]["ts_ms"], r["seq"]), default=None)


def _last(row: dict | None) -> dict | None:
    if row is None:
        return None
    event = row["event"]
    return {
        "at_ms": event["ts_ms"],
        "episode_id": row["episode"]["id"],
        "event_id": event["id"],
        "evidence_id": event["payload"].get("evidence_id"),
        "text": plain(event),
    }


def _card(model: dict, rows: list[dict], configured: dict) -> dict:
    mine = [r for r in rows if r["call"].get("model") == model["key"]]
    newest = _newest(mine)
    times = [r["call"]["ms"] for r in mine if r["call"].get("ms") is not None]
    mode = mode_of(newest["call"].get("source", "")) if newest else None
    return {
        **model,
        "model_id": newest["call"].get("model_id") if newest else None,
        "mode": mode or ("live" if configured.get(model["key"]) else "prepared"),
        "calls": len(mine),
        "median_ms": round(statistics.median(times)) if times else None,
        "last": _last(newest),
    }


def _recent(rows: list[dict]) -> list[dict]:
    names = {m["key"]: m["name"] for m in MODELS}
    newest_first = sorted(rows, key=lambda r: -r["event"]["ts_ms"])  # stable: ties keep record order
    out = []
    for r in newest_first[:MAX_RECENT]:
        event, call = r["event"], r["call"]
        out.append({
            "at_ms": event["ts_ms"],
            "when": clock(event["ts_ms"]),
            "model": call.get("model"),
            "name": names.get(call.get("model"), call.get("model")),
            "mode": mode_of(call.get("source", "")) or "prepared",
            "patient": short_name(r["episode"].get("label")),
            "what": plain(event),
            "episode_id": r["episode"]["id"],
            "event_id": event["id"],
            "evidence_id": event["payload"].get("evidence_id"),
        })
    return out


def summary(roster: list[tuple[dict, list[dict]]], configured: dict) -> dict:
    rows = _rows(roster)
    return {"models": [_card(m, rows, configured) for m in MODELS], "recent": _recent(rows)}
