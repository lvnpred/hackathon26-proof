"""Parse a spoken drug-log line. Unknown names stay ungrounded."""

from __future__ import annotations

import re

from app.morning.lexicon import ground

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
_UNITS = (
    ("micrograms", "mcg"),
    ("microgram", "mcg"),
    ("mcg", "mcg"),
    ("milligrams", "mg"),
    ("milligram", "mg"),
    ("grams", "g"),
    ("gram", "g"),
    ("ml", "ml"),
    ("mg", "mg"),
    ("g", "g"),
)
_ROUTES = (
    ("local infiltration", "local infiltration"),
    ("intravenous", "iv"),
    ("intramuscular", "im"),
    ("subcutaneous", "subcutaneous"),
    ("oral", "oral"),
    ("iv", "iv"),
    ("im", "im"),
)


def parse_drug_phrase(text: str) -> dict:
    raw = " ".join(text.strip().split())
    lowered = raw.lower().replace(",", " ")
    route, lowered = _take_route(lowered)
    strength, lowered = _take_strength(lowered)
    amount, unit, lowered = _take_amount(lowered)
    name = " ".join(lowered.split())
    found = ground(name)
    return {
        "text": raw,
        "name_as_heard": name,
        "generic": found["generic"],
        "drug_class": found["drug_class"],
        "grounded": found["grounded"],
        "strength": strength,
        "amount": amount,
        "unit": unit,
        "route": route,
        "confirmed": False,
    }


def _qty(token: str) -> int:
    if token.isdigit():
        return int(token)
    return _WORDS[token]


def _take_route(text: str) -> tuple[str | None, str]:
    for phrase, canon in _ROUTES:
        match = re.search(rf"\b{re.escape(phrase)}\b", text)
        if match:
            return canon, (text[: match.start()] + " " + text[match.end() :]).strip()
    return None, text


def _take_strength(text: str) -> tuple[str | None, str]:
    match = re.search(rf"\b{_NUM}\s+percent\b", text) or re.search(rf"\b{_NUM}\s*%", text)
    if not match:
        return None, text
    strength = f"{_qty(match.group(1))}%"
    return strength, (text[: match.start()] + " " + text[match.end() :]).strip()


def _take_amount(text: str) -> tuple[int | None, str | None, str]:
    for unit, canon in _UNITS:
        match = re.search(rf"\b{_NUM}\s+{unit}\b", text)
        if match:
            rest = (text[: match.start()] + " " + text[match.end() :]).strip()
            return _qty(match.group(1)), canon, rest
    return None, None, text
