"""The patient's medicine photo: each strip read is matched to the prescription by exact name (pure).

The app names each strip, restates the doctor's schedule and flags a difference. It never says what to take.
"""

from __future__ import annotations

from app.journey.nudges import _norm
from app.journey.proof import NO_STRIP
from app.journey.rx import key_of
from app.journey.schedule import build, schedule_text


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


def _matched(read: str, differs: bool, medicine: str, schedule: str, why: str) -> dict:
    return {
        "read": read, "prescribed": True, "medicine": medicine, "schedule": schedule,
        "flag": "strength_differs" if differs else None, "why": why,
    }


def match_medicines(strips: list[dict], rx: dict | None, doses: list[dict] = ()) -> dict:
    """{"rows", "match", "why"}: one row per strip in read order. A match is key equality, never a substring.

    A prescription row wins over a dose row with the same key.
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
            out.append(_matched(read, differs, row["medicine"], text, why))
        elif key in dose_by_key:
            row = dose_by_key[key]
            differs = bool(strip["strength"] and row["strength"] and _norm(strip["strength"]) != _norm(row["strength"]))
            why = (
                f"The strip reads {read}. Your signed orders say {row['medicine']}."
                if differs else f"On your signed orders from {row['by']}: {row['medicine']}, {row['schedule']}."
            )
            out.append(_matched(read, differs, row["medicine"], row["schedule"], why))
        else:
            out.append(
                {
                    "read": read, "prescribed": False, "medicine": None, "schedule": None, "flag": "not_prescribed",
                    "why": f"{read} is not on {where}. Ask Dr. Rao about it.",
                }
            )
    flagged = [r["read"] for r in out if r["flag"]]
    if not out:
        return {"rows": out, "match": "none", "why": NO_STRIP}
    on = sum(r["prescribed"] for r in out)
    why = f"{on} of {len(out)} medicines in the photo are on {noun}."
    if flagged:
        why += f" Flagged: {', '.join(flagged)}."
    return {"rows": out, "match": "mismatch" if flagged else "ok", "why": why}
