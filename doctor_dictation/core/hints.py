"""Vocabulary hints (ACC2). Pure. "Common" = widely marketed: brands, strengths, then alphabetical.

Only lexicon names are ever returned: the doctor's most-used medicines are mapped to their
canonical form and anything the lexicon does not know (free text typed into a name field, a
patient's name) is dropped, so nothing but medicine names leaves the clinic as a prompt.
The list is also kept inside MAX_HINT_CHARS: Whisper reads only about 224 tokens of prompt
(roughly 3 characters per token for drug names), and the local engine adds its own base prompt.
"""
from collections.abc import Sequence

from .determinism import _canonical_lookup, load_lexicon

MAX_HINT_CHARS = 500
_MAX_DOCTOR_NAME = 60  # longer is never a medicine name; also keeps the fuzzy lookup cheap


def common_lexicon_names() -> list[str]:
    ranked = sorted(
        (e for e in load_lexicon() if str(e.get("canonical") or "").strip()),
        key=lambda e: (-len(e.get("brands") or []), -len(e.get("strengths") or []),
                       e["canonical"].lower()),
    )
    return [e["canonical"].strip() for e in ranked]


def _doctor_canonical(names: Sequence[str]) -> list[str]:
    out = []
    for n in names:
        clean = " ".join(str(n).split())
        if clean and len(clean) <= _MAX_DOCTOR_NAME:
            canon = _canonical_lookup(clean)
            if canon:
                out.append(canon)
    return out


def build_hints(doctor_top: Sequence[str] = (), limit: int = 70) -> list[str]:
    """Doctor's most-used medicines first, then common lexicon names; unique, capped."""
    out: list[str] = []
    seen: set[str] = set()
    used = 0
    for name in [*_doctor_canonical(doctor_top), *common_lexicon_names()]:
        if len(out) >= max(limit, 0):
            break
        clean = " ".join(str(name).split())
        if not clean or clean.casefold() in seen:
            continue
        cost = len(clean) + (2 if out else 0)       # ", " between names
        if used + cost > MAX_HINT_CHARS:
            break
        seen.add(clean.casefold())
        out.append(clean)
        used += cost
    return out
