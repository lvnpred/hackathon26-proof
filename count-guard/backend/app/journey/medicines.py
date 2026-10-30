"""The patient's medicine photo: each strip read is matched to the prescription by exact name (pure).

The app names each strip, restates the doctor's schedule and flags a difference. It never says what to take.
"""

from __future__ import annotations

import re

from app.journey.nudges import _norm
from app.journey.proof import NO_STRIP
from app.journey.rx import key_of
from app.journey.schedule import SLOTS, build, schedule_text


def dose_rows(orders: list[dict]) -> list[dict]:
    """One row per named dose item on a signed order, oldest first."""
    return [
        {
            "key": key_of(item["name"]), "medicine": f"{item['name']} {item.get('amount') or ''}".strip(),
            "strength": item.get("amount") or "",
            "schedule": f"every {item['every_h']:g} h" if item.get("every_h") else "as ordered", "by": order["by"],
        }
        for order in orders for item in order["items"] if item.get("kind") == "dose" and item.get("name")
    ]


def record_holds(orders: list[dict]) -> str:
    """What the record holds, in fixed sentences. An order's free text is never repeated."""
    if not orders:
        return "Your record holds no orders yet."
    return "Your record holds signed orders, but none is a medicine."


def _matched(read: str, differs: bool, medicine: str, schedule: str, why: str, rx_strength: str) -> dict:
    return {
        "read": read, "prescribed": True, "medicine": medicine, "schedule": schedule,
        "flag": "strength_differs" if differs else None, "why": why, "rx_strength": rx_strength,
    }


def match_medicines(strips: list[dict], rx: dict | None, doses: list[dict] = (), ward: bool = False) -> dict:
    """{"rows", "match", "why"}: one row per strip in read order. A match is key equality, never a substring.

    A prescription row wins over a dose row with the same key. With `ward` (the patient is leaving or home),
    a dose order is named for what it is: a medicine given on the ward, not a home instruction.
    """
    rx = rx or {}
    rows_by_key = {row["key"]: row for row in rx.get("rows") or []}
    schedule = {row["key"]: row for row in build(rx)} if rx else {}
    dose_by_key = {row["key"]: row for row in doses}
    sources = (bool(rx), bool(dose_by_key))
    where = {
        (True, True): f"your prescription from {rx.get('by')} or your signed orders",
        (True, False): f"your prescription from {rx.get('by')}",
    }.get(sources, "your signed orders")
    noun = {(True, True): "your prescription or signed orders", (True, False): "your prescription"}.get(sources, "your signed orders")
    if ward and sources[1]:
        where = noun = "your prescription or ward orders"
    out = []
    for strip in strips:
        read = f"{strip['name_as_read']} {strip['strength']}".strip()
        key = key_of(strip["name_as_read"])
        if key in schedule:
            row = schedule[key]
            text = schedule_text(row)
            prescribed = rows_by_key[key]["strength"]
            differs = bool(strip["strength"] and prescribed and _norm(strip["strength"]) != _norm(prescribed))
            why = (
                f"The strip reads {read}. The prescription says {row['medicine']}."
                if differs else f"On your prescription: {row['medicine']}, {text}."
            )
            out.append(_matched(read, differs, row["medicine"], text, why, prescribed))
        elif key in dose_by_key:
            row = dose_by_key[key]
            differs = bool(strip["strength"] and row["strength"] and _norm(strip["strength"]) != _norm(row["strength"]))
            if ward:
                why = (
                    f"The strip reads {read}. The ward order says {row['medicine']}: given on the ward (signed order)."
                    if differs else f"{row['medicine']}, {row['schedule']}: given on the ward (signed order)."
                )
            else:
                why = (
                    f"The strip reads {read}. Your signed orders say {row['medicine']}."
                    if differs else f"On your signed orders from {row['by']}: {row['medicine']}, {row['schedule']}."
                )
            out.append(_matched(read, differs, row["medicine"], row["schedule"], why, row["strength"]))
        else:
            out.append(
                {
                    "read": read, "prescribed": False, "medicine": None, "schedule": None, "flag": "not_prescribed",
                    "rx_strength": "", "why": f"{read} is not on {where}. Ask Dr. Rao about it.",
                }
            )
    for row, strip in zip(out, strips):
        row["name"], row["key"] = strip["name_as_read"], key_of(strip["name_as_read"])
    flagged = [r["read"] for r in out if r["flag"]]
    if not out:
        return {"rows": out, "match": "none", "why": NO_STRIP}
    on = sum(r["prescribed"] for r in out)
    why = f"{on} of {len(out)} medicines in the photo are on {noun}."
    if flagged:
        why += f" Flagged: {', '.join(flagged)}."
    return {"rows": out, "match": "mismatch" if flagged else "ok", "why": why}


_AS_NEEDED = re.compile(r"^(sos|prn|as needed)$", re.I)


def _region_of(read: dict | None, match) -> int | None:
    """The index of the first region whose row is a read row that `match` accepts."""
    rows = (read or {}).get("rows") or []
    for index, region in enumerate((read or {}).get("regions") or []):
        row = region.get("row")
        if isinstance(row, int) and 0 <= row < len(rows) and match(rows[row]):
            return index
    return None


def day_plan(rx: dict | None, read: dict | None) -> dict | None:
    """The patient's day, restated from the prescription only. `read` is the latest medicines.read or None."""
    if not rx:
        return None
    plan = {
        "slots": {slot: [] for slot in SLOTS}, "as_needed": [], "as_written": [], "not_prescribed": [],
        "photo_id": (read or {}).get("photo_id"), "evidence_id": (read or {}).get("evidence_id"),
    }
    for row, source in zip(build(rx), rx.get("rows") or []):
        item = {
            "key": row["key"], "medicine": row["medicine"], "text": schedule_text(row),
            "region": _region_of(read, lambda r, key=row["key"]: r.get("key") == key and r.get("prescribed")),
        }
        if not row["as_needed"]:
            for slot, amount in row["slots"].items():
                if amount:
                    plan["slots"][slot].append(item)
        elif _AS_NEEDED.match((source.get("dose") or "").strip()):
            plan["as_needed"].append(item)
        else:
            days_text = f"for {row['days']} days" if row["days"] else ""
            parts = (source.get("dose") or "", row["timing"], days_text, row["note"])
            plan["as_written"].append({**item, "text": "; ".join(part for part in parts if part)})
    for row in (read or {}).get("rows") or []:
        if row.get("flag") == "not_prescribed":
            region = _region_of(read, lambda r, row=row: r is row)
            plan["not_prescribed"].append({"name": row.get("name") or row["read"], "read": row["read"], "region": region})
    return plan
