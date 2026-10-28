"""Text rules for a generic the doctor types or dictates: validation, cleaning, unknown ingredients.

Pure text work. The lexicon is read lazily (``determinism`` imports ``rowcheck``, which imports this module).
"""
from __future__ import annotations

import re

MAX_GENERIC_CHARS = 160
MAX_COMPONENTS = 6
DOCTOR = "doctor"
DOCTOR_GENERIC_FIELDS = ("generic_source", "generic_suggestion", "generic_suggestion_unknown", "generic_pending")

MESSAGES = {
    "empty": "Type the generic, or press Cancel.",
    "long": "The generic is too long (160 characters at most).",
    "parts": "Separate the ingredients with +, for example Aceclofenac + Paracetamol.",
    "many": "At most 6 ingredients.",
    "chars": "Use letters, digits, spaces and . , ' ( ) / - only.",
}

_PLUS_RE = re.compile(r"\bplus\b", re.IGNORECASE)
_PART_RE = re.compile(r"([0-9]+-)?[A-Za-z][A-Za-z0-9 .,'()/-]*")


def _parts(raw) -> tuple[list[str], str]:
    """(distinct components in the doctor's spelling, problem key or "")."""
    if not isinstance(raw, str) or not raw.strip():
        return [], "empty"
    text = _PLUS_RE.sub("+", re.sub(r"\s+", " ", raw).strip())
    if len(text) > MAX_GENERIC_CHARS:
        return [], "long"
    parts = [p.strip() for p in text.split("+")]
    if any(not p for p in parts):
        return [], "parts"
    distinct: dict[str, str] = {}
    for p in parts:
        distinct.setdefault(p.casefold(), p)
    if len(distinct) > MAX_COMPONENTS:
        return [], "many"
    for p in distinct.values():
        if not _PART_RE.fullmatch(p) or sum(c.isalpha() for c in p) < 3:
            return [], "chars"
    return list(distinct.values()), ""


def generic_problem(raw) -> str:
    """"" when ``raw`` is a valid generic, else the message to show the doctor."""
    return MESSAGES.get(_parts(raw)[1], "")


def clean_generic(raw) -> str:
    """The text to store (components joined by " + ", the doctor's case kept), or "" when it is not valid."""
    parts, problem = _parts(raw)
    return "" if problem else " + ".join(parts)


def unknown_components(generic: str) -> list[str]:
    """The components of ``generic`` that no canonical of the effective list names (a combination canonical is split).

    ``load_lexicon`` returns the clinic's effective entries, which already leave out hidden (blocked) ones, so a
    blocked canonical counts as unknown without extra code.
    """
    from . import determinism
    known = {p.strip().casefold() for e in determinism.load_lexicon() for p in str(e.get("canonical", "")).split("+")}
    return [p for p in (x.strip() for x in str(generic or "").split("+")) if p and p.casefold() not in known]


def _suggestion(item: dict, name: str) -> str:
    """The cleaned ``generic_suggestion``, kept only for a name with no exact lexicon match, not hidden by the clinic,
    that it does not just repeat."""
    from . import determinism                       # lazy, see the module docstring
    text = clean_generic(item.get("generic_suggestion"))
    if not text or determinism._exact_lookup(name) or text.casefold() == str(name or "").strip().casefold():
        return ""
    if determinism.is_blocked(name):                # a name the clinic hid gets no "AI suggests" either
        return ""
    return text


def doctor_fields(item: dict, name: str) -> dict:
    """The keys to overlay on a lexicon-built row (applied last, after ``surface.generic_fields``).

    Always ``generic_suggestion``. When the item claims ``generic_source: "doctor"`` with a valid generic, also the
    cleaned ``generic``, ``generic_source: "doctor"`` and ``generic_pending``. Any other ``generic_source`` the client
    sends (``"lexicon"`` included) is never trusted. Text only: ``status`` and ``lexicon_match`` are never touched, so a
    doctor generic never maps a name (a clinic's blocked name included) to a lexicon entry.
    """
    out = {"generic_suggestion": _suggestion(item, name)}
    generic = clean_generic(item.get("generic")) if item.get("generic_source") == DOCTOR else ""
    if generic:
        out.update(generic=generic, generic_source=DOCTOR, generic_pending=item.get("generic_pending") is True)
    return out


LLM_FORBIDDEN_FIELDS = ("generic", "generic_source", "generic_pending")


def strip_llm_fields(draft) -> dict:
    """A copy of an LLM ``draft`` without the doctor-generic fields on any rx row (only the doctor sets those)."""
    out = dict(draft) if isinstance(draft, dict) else {}
    rx = out.get("rx")
    if isinstance(rx, list):
        out["rx"] = [{k: v for k, v in r.items() if k not in LLM_FORBIDDEN_FIELDS} if isinstance(r, dict) else r
                     for r in rx]
    return out


MODEL_NEVER_SETS = ("generic_source", "generic_suggestion", "generic_suggestion_unknown", "generic_pending")


def _same(a, b) -> bool:
    a, b = clean_generic(a), clean_generic(b)
    return bool(a) and a.casefold() == b.casefold()


def _echo(cleaned: str, names, cur_row) -> bool:
    """True when ``cleaned`` only repeats what the row already has: its own generic, or the lexicon generic of its name
    (the page never sends a listed row's generic, so the lexicon is asked too)."""
    from . import determinism                       # lazy, see the module docstring
    cur = cur_row.get("generic") if isinstance(cur_row, dict) else ""
    return _same(cleaned, cur) or any(_same(cleaned, determinism._exact_lookup(n)) for n in names if n)


def _said(cleaned: str, transcripts) -> bool:
    """True when every component's words are in the correction's dictation ("plus" and "+" alike: neither is a word)."""
    from . import prose
    return all(not prose.missing_words(part, *transcripts) for part in cleaned.split("+"))


def patch_generics(current: dict, patch: dict, *transcripts) -> tuple[dict, list[str]]:
    """(patch copy, warnings): the whitelist for a ``generic`` the correction model returns. Inputs are not mutated.

    Per patch rx row: the source, suggestion and pending keys are always dropped. A ``generic`` becomes a doctor generic
    (``generic_source: "doctor"``, ``generic_pending: True``) only when the doctor said it: an echo (the current row's
    generic, or the lexicon generic of its name) is dropped, and so is one whose words are not in ``transcripts`` (the
    correction's dictation), both silently. An invalid one is dropped with a warning.
    """
    from .ops import _find_rx, _key                 # lazy: ops imports rowcheck, which imports this module
    out = dict(patch) if isinstance(patch, dict) else {}
    rows, warnings = out.get("rx"), []
    if not isinstance(rows, list):
        return out, warnings
    cur_rows = (current or {}).get("rx") if isinstance(current, dict) else None
    cur_rows = cur_rows if isinstance(cur_rows, list) else []
    new_rows = []
    for row in rows:
        if not isinstance(row, dict):
            new_rows.append(row)
            continue
        row = {k: v for k, v in row.items() if k not in MODEL_NEVER_SETS}
        if "generic" in row:
            raw = row.pop("generic")
            name = str(row.get("name") or "").strip()
            idx, _why = _find_rx(cur_rows, _key(name)) if name else (None, "")
            cur_row = cur_rows[idx] if idx is not None else None
            names = [name, str(cur_row.get("name") or "") if isinstance(cur_row, dict) else ""]
            cleaned = clean_generic(raw)
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                pass                                  # an empty generic: nothing stated, nothing to warn about
            elif cleaned and (_echo(cleaned, names, cur_row) or not _said(cleaned, transcripts)):
                pass                                  # an echo, or the model's own idea: the doctor did not say it
            elif cleaned:
                row.update(generic=cleaned, generic_source=DOCTOR, generic_pending=True)
            else:
                warnings.append(f"The generic for {name} was not changed: {generic_problem(raw)}")
        new_rows.append(row)
    out["rx"] = new_rows
    return out, warnings


def settle(validated: dict) -> dict:
    """Drop ``generic_pending`` from every rx row of a form that passed the Save gate; mutates and returns it."""
    rows = validated.get("rx") if isinstance(validated, dict) else None
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            row.pop("generic_pending", None)
    return validated


def new_doctor_generics(structured, confirmed_rows, remember_generics) -> list[tuple[int, str, str]]:
    """[(index, name, generic)] a saved form offers the clinic's list, once per name key.

    Raw rows (indexes match ``confirmed_rows``) with a PENDING doctor generic, confirmed, with a storable name and a valid
    generic. A name the clinic hid (blocked), or a generic naming a hidden canonical, never counts: the admin's hide wins. A listed name (an exact match of the
    clinic's effective list) counts only when its index is in ``remember_generics`` (Q20)."""
    from . import determinism, formulary        # lazy, see the module docstring
    confirmed, remember = set(confirmed_rows or []), set(remember_generics or [])
    rows = structured.get("rx") if isinstance(structured, dict) else None
    out, seen = [], set()
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, dict) or index not in confirmed:
            continue
        if row.get("generic_source") != DOCTOR or row.get("generic_pending") is not True:
            continue
        name, generic = formulary.clean_name(row.get("name")), clean_generic(row.get("generic"))
        if not name or not generic or formulary.key(name) in seen or determinism.is_blocked(name):
            continue
        if any(determinism.is_blocked(p) for p in [generic, *generic.split(" + ")]):
            continue                                # a hidden canonical never comes back (``overlay.conflicts`` agrees)
        if determinism._exact_lookup(name) and index not in remember:
            continue
        seen.add(formulary.key(name))
        out.append((index, name, generic))
    return out
