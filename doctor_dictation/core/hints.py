"""Vocabulary hints (ACC2, SH-H1). Pure. "Common" = widely marketed: brands, strengths, then alphabetical.

The doctor's own spoken forms come first, as said ("Dolo 650", never the canonical "Paracetamol"), then the clinic's
newest names, then the common lexicon names. Only hint-eligible phrases are returned (contract S2): a medicine or
investigation a list knows, so a name typed into a free-text field or a patient's name never leaves the clinic.
The list is also kept inside MAX_HINT_CHARS, measured on the prompt it renders to: Whisper reads only about
224 tokens of prompt (roughly 3 characters per token for drug names), and the local engine adds its own base prompt.
"""
import re
from collections.abc import Sequence

from . import investigations, spoken
from .combo import combo_suffix
from .determinism import _exact_lookup, load_lexicon
from .formulary import active_layer
from .spoken import HintTerm

MAX_HINT_CHARS = 500
_MAX_DOCTOR_NAME = 60  # longer is never a medicine name (equals formulary.MAX_NAME)
_UNIT = r"\s*(?:mg|mcg|g|ml|iu|%)?"
# a plausible strength ("650", "0.4 mg", "40 12.5"), never a phone number: 2 decimals at most, a second number of 1-3 digits
_TRAILING_STRENGTH = re.compile(rf"\s+\d{{1,4}}(?:\.\d{{1,2}})?{_UNIT}(?:\s+\d{{1,3}}(?:\.\d{{1,2}})?{_UNIT})?$", re.I)


def common_lexicon_names() -> list[str]:
    ranked = sorted(
        (e for e in load_lexicon() if str(e.get("canonical") or "").strip()),
        key=lambda e: (-len(e.get("brands") or []), -len(e.get("strengths") or []),
                       e["canonical"].lower()),
    )
    return [e["canonical"].strip() for e in ranked]


def prompt_text(phrases: Sequence[str]) -> str:
    """The sentence a speech engine reads: "Dolo 650. Pan 40. CBC." (empty for no phrases)."""
    return ". ".join(phrases) + "." if phrases else ""


def _base(text: str) -> str:
    """"Dolo 650" -> "Dolo"; a name with a digit inside a word ("Dolo HIV2") stays whole."""
    return _TRAILING_STRENGTH.sub("", text).strip()


def eligible(text: str) -> bool:
    """True when a medicine list, the clinic layer, a combination rule or the investigation catalogue knows ``text``."""
    base = _base(text)
    for n in (text, base):
        if n and (_exact_lookup(n) or active_layer().get(n)):
            return True
    return bool(base and combo_suffix(base)) or investigations.lookup_in(text, investigations.clinic_entries()) is not None


def build_hints(doctor_terms: Sequence[HintTerm] = (), limit: int = 70) -> list[str]:
    """The doctor's spoken phrases first, then the clinic layer's names, then common lexicon names; unique, eligible, capped."""
    out: list[str] = []
    seen: set[str] = set()
    for name in [*(t.phrase for t in spoken.rank(doctor_terms)), *active_layer().hint_names(), *common_lexicon_names()]:
        if len(out) >= max(limit, 0):
            break
        clean = " ".join(str(name).split())
        k = spoken.key(clean)
        if not k or k in seen or len(clean) > _MAX_DOCTOR_NAME or not eligible(clean):
            continue
        if len(prompt_text([*out, clean])) > MAX_HINT_CHARS:     # the budget is measured on the rendered prompt
            break
        seen.update({k, spoken.key(_base(clean))})               # "Urimax 0.4" also claims "Urimax"
        out.append(clean)
    return out
