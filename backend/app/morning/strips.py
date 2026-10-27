"""Turn a vision model's text into grounded strips. No network here."""

from __future__ import annotations

import json
import re

from app.morning.brownbag import read_strip

_LINE = re.compile(r"^(.+?)\s+(\d+\s*(?:mg|ml|g|mcg))\s*$", re.I)


def parse_strip_text(text: str) -> list[dict]:
    raw = text.strip()
    if not raw:
        return []
    if raw.startswith("{") or raw.startswith("["):
        payload = json.loads(raw)
        rows = payload.get("strips", payload) if isinstance(payload, dict) else payload
        return [read_strip(row["name"], row.get("strength") or "") for row in rows]
    found = []
    for line in raw.splitlines():
        match = _LINE.match(line.strip())
        if match:
            found.append(read_strip(match.group(1), match.group(2)))
    return found
