"""Format a video position as minutes and seconds."""

from __future__ import annotations


def format_media(ms: int | None) -> str:
    if ms is None:
        return "unknown time"
    total = max(0, int(ms) // 1000)
    return f"{total // 60} min {total % 60} sec"
