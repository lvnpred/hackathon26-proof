"""Spoken pack line. "Opening twenty swabs" records a pack, not a drug."""

from __future__ import annotations

import re

_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twenty": 20,
    "fifty": 50,
}
_NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|twenty|fifty)"
_KIND = {
    "swab": "swab",
    "swabs": "swab",
    "sponge": "lap sponge",
    "sponges": "lap sponge",
    "gauze": "gauze swab",
}


def parse_pack(text: str) -> dict | None:
    match = re.search(
        rf"\b(?:opening|adding|added)\s+{_NUM}\s+(swabs?|sponges?|gauze|lap sponges?)\b",
        text.strip().lower(),
    )
    if not match:
        return None
    token = match.group(1)
    quantity = int(token) if token.isdigit() else _WORDS[token]
    kind = match.group(2)
    if kind.startswith("lap"):
        item_type = "lap sponge"
    else:
        item_type = _KIND[kind]
    return {"item_type": item_type, "quantity": quantity, "text": text.strip()}
