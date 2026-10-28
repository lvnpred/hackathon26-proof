"""The doctor's usual row for a medicine, as a pure rule (plan SH-B6): what they themselves prescribed for a diagnosis.

Each field (form, strength, dose, timing, duration) is chosen by the D-SH2 rule (``spoken.usual_strength``) over the
linked documents; a field without a 60% value stays blank, and a medicine without a usual dose gets no row (the sheet
would invent one). S1: nothing here changes a row's name, status or generic. Nothing here does I/O.
"""
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from . import spoken
from .determinism import ALLOWED_DOSES

USUAL_DOCS = 20        # the newest linked documents read per medicine (R7)
MAX_PER_LINE = 5       # rows sent per diagnosis line; the page shows fewer (R1)
MIN_ROWS = 2           # a usual row needs this many documents that carry the medicine
FIELDS = ("form", "strength", "dose", "timing", "duration")


@dataclass(frozen=True)
class UsualRow:
    form: str
    name: str          # as the doctor said it
    strength: str
    dose: str
    timing: str
    duration: str
    generic: str
    count: int

    def as_dict(self) -> dict:
        return asdict(self)


def _rows_of(term_key: str, forms: Sequence) -> list[dict]:
    """The first Rx row naming the medicine in each readable form; a form without one adds nothing."""
    found = []
    for form in forms:
        rows = form.get("rx") if isinstance(form, dict) else None
        if not isinstance(rows, list):
            continue
        row = next((r for r in rows if isinstance(r, dict) and spoken.key(r.get("name")) == term_key), None)
        if row is not None:
            found.append(row)
    return found


def usual_row(term_key: str, spoken_name: str, generic: str, count: int, forms: Sequence) -> UsualRow | None:
    rows = _rows_of(term_key, forms)
    if len(rows) < MIN_ROWS:
        return None
    chosen = {}
    for field in FIELDS:
        tally: dict[str, int] = {}
        for r in rows:
            v = " ".join(str(r.get(field) or "").split())
            tally[v] = tally.get(v, 0) + 1
        chosen[field] = spoken.usual_strength(tally)
    if chosen["dose"] not in ALLOWED_DOSES:
        return None
    return UsualRow(name=spoken_name, generic=generic, count=count, **chosen)


def pick(lines: Sequence[tuple[int, list[UsualRow]]]) -> list[dict]:
    """Groups in line order: a medicine shows under the first line that has it, at most MAX_PER_LINE a line, no empty line."""
    seen: set[str] = set()
    out = []
    for line, rows in lines:
        items = []
        for row in rows:
            k = spoken.key(row.name)
            if k in seen or len(items) >= MAX_PER_LINE:
                continue
            seen.add(k)
            items.append(row.as_dict())
        if items:
            out.append({"line": line, "items": items})
    return out
