"""One follow-up event. Standard library only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def follow_up_ics(label: str, start: datetime | None = None) -> str:
    when = (start or datetime.now(timezone.utc)) + timedelta(days=7)
    stamp = when.strftime("%Y%m%dT%H%M%SZ")
    safe = label.replace("\n", " ")
    return (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Count Guard//morning//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"DTSTART:{stamp}\r\n"
        f"SUMMARY:Follow-up ({safe}) synthetic demo\r\n"
        "DESCRIPTION:Research demo. Not for clinical use.\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
