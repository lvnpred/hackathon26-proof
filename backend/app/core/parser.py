"""Parse a spoken count. A miss stays unparsed. It never becomes advice."""

from __future__ import annotations

import re

NUMBER_WORDS = {
    "zero": 0,
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
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
}

# Longer phrases first so "lap sponge" wins over a bare swab word.
ITEM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("lap sponge", r"lap sponges?|laps\b"),
    ("needle holder", r"needle holders?"),
    ("surgical forceps", r"surgical forceps|forceps"),
    ("scissors", r"scissors"),
    ("gauze swab", r"gauze swabs?|gauze|swabs?"),
)

_QTY = r"(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty)"
_ITEM = r"(lap sponges?|laps|needle holders?|surgical forceps|forceps|scissors|gauze swabs?|gauze|swabs?)"
_ADD = re.compile(rf"\b(?:adding|added|add|opening|opened|open)\s+{_QTY}\s+{_ITEM}\b", re.I)
_PHASES = (
    ("closing", re.compile(r"\bclosing count\b", re.I)),
    ("final", re.compile(r"\bfinal count\b", re.I)),
    ("initial", re.compile(r"\b(?:initial count|opening count)\b", re.I)),
)
_ZONE = (
    ("bucket", re.compile(r"\b(?:in|into|on)\s+the\s+bucket\b", re.I)),
    ("tray", re.compile(r"\b(?:on|in)\s+the\s+(?:tray|back table)\b", re.I)),
    ("field", re.compile(r"\b(?:in|on)\s+the\s+field\b", re.I)),
)
_COUNT_HINT = re.compile(r"\b(count|sponge|swab|forceps|scissors|needle|gauze|lap)\b", re.I)


def parse_quantity(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def canonical_item(phrase: str) -> str | None:
    text = phrase.lower()
    for name, pattern in ITEM_PATTERNS:
        if re.search(pattern, text, re.I):
            return name
    return None


def _zone(text: str, phase: str | None) -> str | None:
    for name, pattern in _ZONE:
        if pattern.search(text):
            return name
    if phase in {"closing", "final"}:
        return "bucket"
    if phase == "initial":
        return "tray"
    return None


def _first_quantity(text: str) -> int | None:
    match = re.search(_QTY, text, re.I)
    if not match:
        return None
    return parse_quantity(match.group(1))


def parse_utterance(text: str) -> dict:
    """Return checkpoint, adds, and counts found in one utterance.

    `needs_model` is true when the line looks like a count but no rule matched.
    The caller may ask Muse Spark Open to parse it. The rules still decide.
    """
    cleaned = " ".join(text.strip().split())
    phase = None
    for name, pattern in _PHASES:
        if pattern.search(cleaned):
            phase = name
            break

    adds: list[dict] = []
    for match in _ADD.finditer(cleaned):
        qty = parse_quantity(match.group(1))
        item = canonical_item(match.group(2))
        if qty is None or item is None:
            continue
        adds.append({"item_type": item, "quantity": qty, "action": "add", "zone": "tray"})

    counts: list[dict] = []
    if phase is not None:
        qty = _first_quantity(cleaned)
        if qty is not None:
            counts.append(
                {
                    "item_type": canonical_item(cleaned),
                    "quantity": qty,
                    "action": "count",
                    "zone": _zone(cleaned, phase),
                }
            )
    elif not adds:
        qty = _first_quantity(cleaned)
        item = canonical_item(cleaned)
        zone = _zone(cleaned, None)
        if qty is not None and (item or zone):
            counts.append(
                {
                    "item_type": item,
                    "quantity": qty,
                    "action": "count",
                    "zone": zone,
                }
            )

    parsed = bool(phase or adds or counts)
    looks_like_count = bool(_COUNT_HINT.search(cleaned) or _first_quantity(cleaned) is not None)
    return {
        "text": cleaned,
        "phase": phase,
        "adds": adds,
        "counts": counts,
        "needs_model": looks_like_count and not parsed,
    }
