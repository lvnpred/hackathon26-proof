"""The patient's dose schedule and calendar reminders, restated from the prescription only."""

from __future__ import annotations

import re
from datetime import date, timedelta

SLOTS = ("morning", "afternoon", "night")
SLOT_TIME = {"morning": "080000", "afternoon": "140000", "night": "210000"}
SLOT_WORDS = {"morning": "in the morning", "afternoon": "in the afternoon", "night": "at night"}
_DOSE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*$")
_DAYS = re.compile(r"(\d+)\s*(day|week|month)", re.I)
_PER = {"day": 1, "week": 7, "month": 30}


def slots(dose: str) -> dict | None:
    """'1-0-1' -> {'morning': '1', 'afternoon': '', 'night': '1'}. None for SOS or an unreadable code."""
    match = _DOSE.match(dose or "")
    if not match:
        return None
    return {slot: ("" if value in ("0", "0.0") else value) for slot, value in zip(SLOTS, match.groups())}


def days(duration: str) -> int | None:
    match = _DAYS.search(duration or "")
    if not match:
        return None
    return int(match.group(1)) * _PER[match.group(2).lower()]


def build(rx: dict) -> list[dict]:
    """One row per prescribed medicine. Wording is the doctor's; nothing is added."""
    out = []
    for row in rx.get("rows") or []:
        when = slots(row["dose"])
        out.append(
            {
                "key": row["key"],
                "medicine": " ".join(part for part in (row["form"], row["name"], row["strength"]) if part),
                "slots": when,
                "as_needed": when is None,
                "timing": row["timing"],
                "days": days(row["duration"]),
                "note": row["instructions"],
            }
        )
    return out


def schedule_text(row: dict) -> str:
    """One `build` row as the doctor wrote it: slots, timing, days, note, joined by '; '."""
    if row["as_needed"]:
        when = "as needed"
    else:
        when = ", ".join(f"{amount} {SLOT_WORDS[slot]}" for slot, amount in row["slots"].items() if amount)
    days_text = f"for {row['days']} days" if row["days"] else ""
    return "; ".join(part for part in (when, row["timing"], days_text, row["note"]) if part)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", " ")


def reminders_ics(rows: list[dict], patient: str, start: date | None = None) -> str:
    """Daily repeating reminders, one per filled slot. As-needed medicines get none."""
    first = start or date.today() + timedelta(days=1)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Count Guard//journey//EN"]
    for index, row in enumerate(rows):
        if row["as_needed"]:
            continue
        for slot, amount in row["slots"].items():
            if not amount:
                continue
            repeat = f"RRULE:FREQ=DAILY;COUNT={row['days']}" if row["days"] else "RRULE:FREQ=DAILY"
            detail = ", ".join(part for part in (f"{amount} {SLOT_WORDS[slot]}", row["timing"], row["note"]) if part)
            lines += [
                "BEGIN:VEVENT",
                f"UID:cg-{index}-{slot}@countguard.demo",
                f"DTSTART:{first.strftime('%Y%m%d')}T{SLOT_TIME[slot]}",
                repeat,
                f"SUMMARY:{_escape('Prescribed: ' + row['medicine'])}",
                f"DESCRIPTION:{_escape(detail + '. From the prescription for ' + patient + '. Synthetic demo.')}",
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
