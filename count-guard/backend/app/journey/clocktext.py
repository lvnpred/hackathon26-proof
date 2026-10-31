"""Clock times for the product. ts_ms 0 is Day 0 at 09:00; Day 0 is Monday 2 Nov 2026.

The product shows "09:14", "Yesterday 09:14" or "Wed 4 Nov, 09:14". "Day N" belongs
only to the demo dock (clock.js label) and check-in day numbers.
"""
from __future__ import annotations

from datetime import date, timedelta

DAY0 = date(2026, 11, 2)
_DAY_MS = 24 * 3_600_000
_START_MINUTES = 9 * 60


def _parts(ts_ms: int) -> tuple[int, int]:
    day, rest = divmod(int(ts_ms), _DAY_MS)
    minutes = _START_MINUTES + rest // 60_000
    return day + minutes // (24 * 60), minutes % (24 * 60)


def when_text(ts_ms: int, now_ms: int | None) -> str:
    day, minutes = _parts(ts_ms)
    hhmm = f"{minutes // 60:02d}:{minutes % 60:02d}"
    if now_ms is not None:
        today = _parts(now_ms)[0]
        if day == today:
            return hhmm
        if day == today - 1:
            return f"Yesterday {hhmm}"
    d = DAY0 + timedelta(days=day)
    return f"{d:%a} {d.day} {d:%b}, {hhmm}"


def latest_ms(events: list[dict]) -> int:
    """The newest recorded time: the record's own 'now' when a builder has no request clock."""
    return max((e["ts_ms"] for e in events), default=0)
