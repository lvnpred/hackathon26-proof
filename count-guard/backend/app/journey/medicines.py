"""The patient's medicine photo: each strip read is matched to the prescription by exact name (pure).

The app names each strip, restates the doctor's schedule and flags a difference. It never says what to take.
"""

from __future__ import annotations

from app.journey.nudges import _norm
from app.journey.proof import NO_STRIP
from app.journey.rx import key_of
from app.journey.schedule import build, schedule_text


def match_medicines(strips: list[dict], rx: dict) -> dict:
    """{"rows", "match", "why"}: one row per strip in read order. A match is key equality, never a substring."""
    rows_by_key = {row["key"]: row for row in rx.get("rows") or []}
    schedule = {row["key"]: row for row in build(rx)}
    out = []
    for strip in strips:
        read = f"{strip['name_as_read']} {strip['strength']}".strip()
        key = key_of(strip["name_as_read"])
        if key not in schedule:
            out.append(
                {
                    "read": read, "prescribed": False, "medicine": None, "schedule": None, "flag": "not_prescribed",
                    "why": f"{read} is not on your prescription from {rx.get('by')}. Ask Dr. Rao about it.",
                }
            )
            continue
        row = schedule[key]
        text = schedule_text(row)
        prescribed = rows_by_key[key]["strength"]
        differs = bool(strip["strength"] and prescribed and _norm(strip["strength"]) != _norm(prescribed))
        why = (
            f"The strip reads {read}. The prescription says {row['medicine']}."
            if differs else f"On your prescription: {row['medicine']}, {text}."
        )
        out.append(
            {
                "read": read, "prescribed": True, "medicine": row["medicine"], "schedule": text,
                "flag": "strength_differs" if differs else None, "why": why,
            }
        )
    flagged = [r["read"] for r in out if r["flag"]]
    if not out:
        return {"rows": out, "match": "none", "why": NO_STRIP}
    on_rx = sum(r["prescribed"] for r in out)
    why = f"{on_rx} of {len(out)} medicines in the photo are on your prescription."
    if flagged:
        why += f" Flagged: {', '.join(flagged)}."
    return {"rows": out, "match": "mismatch" if flagged else "ok", "why": why}
