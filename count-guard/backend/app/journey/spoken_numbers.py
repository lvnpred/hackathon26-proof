"""Spoken numbers as digits (clarity §4.5): "one hundred twenty over eighty" -> "120 over 80".

Pure. Digits already in the text are left as they are. "One twenty" is read as 120 only before "over" or "/" (a blood
pressure said the way staff say it); elsewhere it stays two numbers, as before.
"""

from __future__ import annotations

import re

UNITS = "one two three four five six seven eight nine".split()
TEENS = "ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()

_U, _T, _D = "|".join(UNITS), "|".join(TEENS), "|".join(TENS)
_BELOW_100 = rf"(?:{_D})(?:[\s-]+(?:{_U}))?|{_T}|{_U}"
_POINT = rf"\s+point((?:\s+(?:zero|{_U}))+)"  # thirty eight point one two -> .12
_SAID_NUMBER = rf"\d|(?:{_D}|{_T}|{_U}|a\s+hundred)\b"
_NUMBER = re.compile(
    rf"\b(?:"
    rf"(?P<h>{_U}|a)\s+hundred(?:\s+(?:and\s+)?(?P<rest>{_BELOW_100}))?(?:{_POINT.replace('(', '(?P<hp>', 1)})?"
    # one twenty over eighty: N over N only
    rf"|(?P<lead>{_U})\s+(?P<tail>{_T}|(?:{_D})(?:[\s-]+(?:{_U}))?)(?=\s*(?:over\s+|/\s*)(?:{_SAID_NUMBER}))"
    rf"|(?P<n>{_BELOW_100})(?:{_POINT.replace('(', '(?P<p>', 1)})?"  # seventy two, thirty seven point five
    rf")\b",
    re.I,
)


def _below_100(words: str) -> int:
    parts = re.split(r"[\s-]+", words.lower())
    if parts[0] in TENS:
        return (TENS.index(parts[0]) + 2) * 10 + (UNITS.index(parts[1]) + 1 if len(parts) > 1 else 0)
    if parts[0] in TEENS:
        return TEENS.index(parts[0]) + 10
    return UNITS.index(parts[0]) + 1


def _decimals(words: str | None) -> str:
    """' one two' -> '.12'; None -> ''."""
    if not words:
        return ""
    return "." + "".join("0" if w.lower() == "zero" else str(_below_100(w)) for w in words.split())


def _swap(match: re.Match) -> str:
    if match.group("h"):
        lead = 1 if match.group("h").lower() == "a" else _below_100(match.group("h"))
        whole = lead * 100 + (_below_100(match.group("rest")) if match.group("rest") else 0)
        return f"{whole}{_decimals(match.group('hp'))}"
    if match.group("lead"):
        return str(_below_100(match.group("lead")) * 100 + _below_100(match.group("tail")))
    return f"{_below_100(match.group('n'))}{_decimals(match.group('p'))}"


def words_to_digits(text: str) -> str:
    """Number words become digits: 'BP one hundred twenty over eighty, pulse seventy two' -> 'BP 120 over 80, pulse 72'."""
    return _NUMBER.sub(_swap, text)
