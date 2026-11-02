"""Camera advice (spec §6.4, §6.5, U10): what the rules R1–R6 found on the swab camera case, in plain words.

Advice only. Each row is written as a `camera.advice` event by CAMERA_BY; a person may acknowledge it
(`camera.ack`). Nothing here writes a swab count, and ending surgery reads neither event: `count_gate` alone
decides, on the closing a person saved.
"""

from __future__ import annotations

from urllib.parse import quote

from app.core.ledger import open_discrepancies
from app.core.rules import closing_gate
from app.journey import states
from app.journey.stories import CAMERA_BY

PLACE = {"field": "the sterile field", "tray": "the tray", "bucket": "the bucket"}


def _many(n: int | None, item: str) -> str:
    n = int(n or 0)
    return f"{n} {item}" if n == 1 else f"{n} {item}s"


def _text(row: dict) -> str:
    item = row.get("item_type") or "item"
    rule = row["rule_id"]
    if rule == "R1":
        return f"The camera saw {row.get('observed')} of {_many(row.get('expected'), item)} back at the closing count."
    if rule == "R2":
        return f"The count said aloud and the camera's count of {item}s differ."
    if rule == "R3":
        where = PLACE.get(row.get("last_zone") or "", "the field")
        return f"One {item} was not seen back. It was last seen on {where}."
    if rule == "R4":
        return f"{_many(row.get('observed'), item)} came onto the tray and nobody said a pack was opened."
    return f"The camera is not sure about one {item}. Please look."


def _frame_id(row: dict) -> str | None:
    if row.get("last_frame_id"):
        return row["last_frame_id"]
    return next((ref.split(":", 1)[1] for ref in row.get("evidence") or [] if str(ref).startswith("frame:")), None)


def from_case(engine, case_id: str) -> list[dict]:
    """The open findings on the camera case as advice rows: {"rule", "item", "text", "frame_id"} (+ key, item_type)."""
    events = engine.store.events(case_id)
    rows = []
    for row in open_discrepancies(events):
        if row["status"] != "open" or row["rule_id"] not in ("R1", "R2", "R3", "R4", "R5"):
            continue
        rows.append({
            "rule": row["rule_id"],
            "item": row.get("track_id") or row.get("item_type") or "",
            "item_type": row.get("item_type") or "",
            "text": _text(row),
            "frame_id": _frame_id(row),
            "key": f"{case_id}:{row['id']}",
        })
    if not closing_gate(events)["ok"]:
        rows.append({"rule": "R6", "item": "", "item_type": "", "frame_id": None, "key": f"{case_id}:R6",
                     "text": "The camera count does not add up. The count you save decides."})
    return rows


def write(store, episode_id: str, case_id: str, rows: list[dict], ts: int, source: str) -> list[dict]:
    """Write each advice row not written before for this patient. Returns the new events."""
    seen = {e["payload"].get("key") for e in store.events(episode_id) if e["event_type"] == "camera.advice"}
    written = []
    for row in rows:
        if row["key"] in seen:
            continue
        seen.add(row["key"])
        payload = {**row, "case_id": case_id, "source": source, "by": CAMERA_BY}
        written.append(store.append(episode_id, "camera.advice", payload, ts_ms=ts))
    return written


def linked_case(events: list[dict]) -> str | None:
    """The camera case linked to this theatre stay, or None."""
    linked = states.stay_latest(events, "camera.linked")
    return linked["payload"]["case_id"] if linked else None


def advice_view(episode_id: str, events: list[dict]) -> list[dict]:
    """This stay's advice, oldest first, each with its acknowledgement and its resolve (or None) and its frame link."""
    stay = states.stay_events(events)
    acks = {e["payload"]["advice_id"]: e["payload"] for e in stay if e["event_type"] == "camera.ack"}
    resolved = {e["payload"]["advice_id"]: e["payload"] for e in stay if e["event_type"] == "camera.resolved"}
    out = []
    for e in stay:
        if e["event_type"] != "camera.advice":
            continue
        p = e["payload"]
        ack = acks.get(e["id"])
        out.append({
            "id": e["id"], "rule": p["rule"], "item": p["item"], "item_type": p.get("item_type", ""), "text": p["text"],
            "frame_id": p.get("frame_id"), "source": p.get("source"),
            "frame_url": f"/journey/episodes/{episode_id}/camera/frame?item={quote(p['item'])}" if p.get("frame_id") else None,
            "acked": {"by": ack["by"], "reason": ack.get("reason", "")} if ack else None,
            "resolved": {"by": resolved[e["id"]]["by"], "reason": resolved[e["id"]]["reason"]} if e["id"] in resolved else None,
        })
    return out
