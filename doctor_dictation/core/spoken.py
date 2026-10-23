"""The doctor's spoken terms as pure rules (plan SH-H1): what a saved form teaches, how a term is keyed, phrased and ranked.

A term keeps the name as the doctor said it ("Dolo"), never the canonical name the sheet shows. A medicine or test
that reads as a person, or carries a word of a patient's name, is never recorded. Nothing here does I/O or reads a clock.
"""
import re
from collections.abc import Sequence
from dataclasses import dataclass

from . import investigations
from .drugnames import _exact_lookup
from .formulary import MAX_NAME, has_letters, person_like

USUAL_SHARE, USUAL_MIN = 60, 2     # the usual strength: at least 60% of a term's uses, and at least 2 uses
# a strength as hints.py accepts one: 1-4 digits, 2 decimals at most, so a phone number is never a strength
_STRENGTH = re.compile(r"\d{1,4}(?:\.\d{1,2})?\s*(?:mg|mcg|g|gm|ml|iu|units?|%)?(?:\s*/\s*\d{0,4}(?:\.\d{1,2})?\s*(?:ml|g|gm|tab))?", re.I)
_TRAILING_MG = re.compile(r"\s*mg$", re.I)
MAX_HEARD_CHARS, MAX_HEARD_WORDS = 60, 9   # check-row's name caps (api/rx.py), plus the one word heard_as may add


@dataclass(frozen=True)
class Term:
    """One saved row's contribution."""
    kind: str          # "medicine" | "investigation"
    key: str
    spoken: str        # "Dolo"
    form: str          # "Tab" or ""
    strength: str      # "650 mg" or ""
    generic: str


@dataclass(frozen=True)
class HintTerm:
    """One candidate for the hint list."""
    phrase: str        # "Dolo 650"
    weight: float      # usage score, decayed by HALF_LIFE_DAYS
    tier: int = 0      # 0 plain, 1 misheard before (H2), 2 diagnosis-linked (H3), 3 this patient (H4)
    term_id: int = 0   # spoken_terms.id: H2/H3 lift tiers by id; 0 = not from the table
    key: str = ""      # key(spoken): H4 matches patient terms by key


def key(text) -> str:
    """Casefolded, "&" read as " and ", every run of other characters one space."""
    return re.sub(r"[\W_]+", " ", str(text or "").casefold().replace("&", " and ")).strip()


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def _private(name: str, grounded: bool, patient_words: set) -> bool:
    """A patient's word is never kept; a person-like name is kept only when a list matched it at save."""
    if any(len(w) >= 3 and w in patient_words for w in key(name).split()):
        return True
    return not grounded and person_like(name)


def terms_from_save(structured, known_patient_words) -> list[Term]:
    """The terms one saved form teaches: medicines from ``rx`` rows, tests from ``investigations``; once per (kind, key)."""
    if not isinstance(structured, dict):
        return []
    # both sides split like ``key`` splits a name, so "O'Brien" and "Mary-Ann" match whole
    patient_words = {p for w in known_patient_words or () for p in key(w).split()} | set(key(structured.get("patientName")).split())
    rows = structured.get("rx")
    found = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            grounded = bool(row.get("lexicon_match")) or row.get("source") == "clinic"
            strength = _clean(row.get("strength"))
            found.append(("medicine", _clean(row.get("name")), _clean(row.get("form")).rstrip("."),
                          strength if _STRENGTH.fullmatch(strength) else "", _clean(row.get("generic")), grounded))
    for item in investigations.coerce_items(structured.get("investigations")):
        found.append(("investigation", item["text"], "", "", item["canonical"], bool(item["canonical"])))
    out, seen = [], set()
    for kind, name, form, strength, generic, grounded in found:
        k = key(name)
        if not k or len(name) > MAX_NAME or (kind, k) in seen or _private(name, grounded, patient_words):
            continue
        if not has_letters(name) and not (kind == "investigation" and grounded):   # a test the catalogue knows: "Hb"
            continue
        seen.add((kind, k))
        out.append(Term(kind, k, name, form, strength, generic))
    return out


def mishearings_from_save(structured, known_patient_words) -> list[tuple[str, str]]:
    """[(term key, heard)] of a saved form (plan SH-H2): medicine rows whose heard is another word than the name.

    The heard text is the words a spelled name replaced (``spelled_heard``) when the row has them, else ``heard``.
    """
    rows = structured.get("rx") if isinstance(structured, dict) else None
    if not isinstance(rows, list):
        return []
    patient = structured.get("patientName", "")
    patient_words = {p for w in known_patient_words or () for p in key(w).split()} | set(key(patient).split())
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        heard = row.get("spelled_heard")
        if not isinstance(heard, str) or not heard.strip():
            heard = row.get("heard")
        if not isinstance(heard, str):
            continue
        heard = _clean(heard)
        name_key, heard_key = key(row.get("name")), key(heard)
        if not heard or len(heard) > MAX_HEARD_CHARS or len(heard.split()) > MAX_HEARD_WORDS or not heard_key or heard_key == name_key:
            continue
        known = _exact_lookup(heard)
        if known and known == _exact_lookup(_clean(row.get("name"))):
            continue
        if person_like(heard) or any(len(w) >= 3 and w in patient_words for w in heard_key.split()):
            continue
        terms = terms_from_save({"rx": [row], "patientName": patient}, known_patient_words)
        term = next((t for t in terms if t.kind == "medicine"), None)
        if term is None or (term.key, heard_key) in seen or (term.key + " ").startswith(heard_key + " "):
            continue                                  # a name said without its strength ("dolo" for "Dolo 650") is no mishearing
        seen.add((term.key, heard_key))
        out.append((term.key, heard))
    return out


def usual_strength(strength_uses: dict[str, int]) -> str:
    """The strength in at least USUAL_SHARE% of a term's uses (a use with no strength counts) and USUAL_MIN uses, else ""."""
    total = sum(strength_uses.values())
    named = [(-n, s) for s, n in strength_uses.items() if s]
    if not named:
        return ""
    neg, best = min(named)           # highest count first, ties by text
    n = -neg
    return best if n >= USUAL_MIN and n * 100 >= USUAL_SHARE * total else ""


def phrase(spoken: str, usual: str) -> str:
    """"Dolo" + "650 mg" -> "Dolo 650". Free text never joins; a name that already ends with the strength stays alone."""
    usual = _clean(usual)
    if not _STRENGTH.fullmatch(usual):
        return spoken
    short = key(_TRAILING_MG.sub("", usual))
    named = key(spoken)
    if not short or named == short or named.endswith(" " + short):
        return spoken
    return f"{spoken} {_TRAILING_MG.sub('', usual)}"


def rank(terms: Sequence[HintTerm]) -> list[HintTerm]:
    """Tier first, then weight, then phrase: the same order every time."""
    return sorted(terms, key=lambda t: (-t.tier, -t.weight, t.phrase.casefold(), t.phrase))
