"""The doctor's spoken terms as pure rules (plan SH-H1): what a saved form teaches, how a term is keyed, phrased and ranked.

A term keeps the name as the doctor said it ("Dolo"), never the canonical name the sheet shows. A medicine or test
that reads as a person, or carries a word of a patient's name, is never recorded. Nothing here does I/O or reads a clock.
"""
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

from . import investigations, spelled
from .drugnames import _exact_lookup
from .formulary import MAX_NAME, has_letters, person_like

USUAL_SHARE, USUAL_MIN = 60, 2     # the usual strength: at least 60% of a term's uses, and at least 2 uses
# a strength as hints.py accepts one: 1-4 digits with 3 decimals at most, or 5-6 digits only with IU/units
# ("60000 IU"), so a phone number, PIN code or OP number is never a strength
_STRENGTH = re.compile(r"(?:\d{5,6}\s*(?:iu|units?)|\d{1,4}(?:\.\d{1,3})?\s*(?:mg|mcg|g|gm|ml|iu|units?|%)?)(?:\s*/\s*\d{0,6}(?:\.\d{1,3})?\s*(?:ml|g|gm|tab))?", re.I)
_TRAILING_MG = re.compile(r"\s*mg$", re.I)
LINK_MIN = 2                       # a diagnosis-term link is used once this many documents counted it (H3)
CONTEXT_BYTES, CONTEXT_LINES, CONTEXT_CHARS = 4096, 10, 200   # the correction context: bytes in all, lines, chars per line
PATIENT_FIELDS = ("name", "age_sex", "op_no")
MAX_HEARD_CHARS, MAX_HEARD_WORDS = 60, 9   # check-row's name caps (api/rx.py), plus the one word heard_as may add
TYPED_SIMILAR = 0.6                # a typed fix is a pair when the heard words are this alike to the typed name (SH-B5)


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


def typed_fix(heard: str, name: str, listed=None) -> bool:
    """Whether words a doctor typed over (``heard``) were a mishearing of ``name`` (SH-B5): alike, and not a known medicine.

    ``listed(heard)`` says whether the clinic list knows a name (None: the lexicon only)."""
    return spelled.similarity(heard, name) >= TYPED_SIMILAR and not (_exact_lookup(heard) or (listed and listed(heard)))


def mishearings_from_save(structured, known_patient_words, listed=None) -> list[tuple[str, str]]:
    """[(term key, heard)] of a saved form (plan SH-H2): medicine rows whose heard is another word than the name.

    The heard text is the words a spelled name replaced (``spelled_heard``) when the row has them, else ``heard``,
    else ``typed_heard`` (SH-B5, stricter: ``typed_fix``).
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
        typed = False
        heard = row.get("spelled_heard")
        if not isinstance(heard, str) or not heard.strip():
            heard = row.get("heard")
        if not isinstance(heard, str) or not heard.strip():
            heard, typed = row.get("typed_heard"), True
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
        if typed and not typed_fix(heard, _clean(row.get("name")), listed):
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


def diagnosis_key(line) -> str:
    """A diagnosis line as a link key: ``key(line)`` cut to 80 characters; "" when it has under 3 letters or is no text."""
    if not isinstance(line, str):
        return ""
    k = key(line)[:80]
    return k if sum(c.isalpha() for c in k) >= 3 else ""


def diagnosis_keys(lines) -> list[str]:
    """The unique non-empty diagnosis keys of the text items of ``lines``, in order, at most CONTEXT_LINES."""
    if not isinstance(lines, (list, tuple)):
        return []
    out: list[str] = []
    for line in lines:
        k = diagnosis_key(line)
        if k and k not in out:
            out.append(k)
    return out[:CONTEXT_LINES]


def parse_context(raw) -> tuple[dict | None, str]:
    """Read the correction ``context`` field: (clean context, "") or (None, reason). None or "" is (None, "")."""
    if raw is None or raw == "":
        return None, ""
    if not isinstance(raw, str):
        return None, "not text"
    if len(raw.encode("utf-8", errors="replace")) > CONTEXT_BYTES:
        return None, f"over {CONTEXT_BYTES} bytes"
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):
        return None, "not JSON"
    if not isinstance(data, dict):
        return None, "not an object"
    lines = data.get("diagnosis", [])
    if not (isinstance(lines, list) and len(lines) <= CONTEXT_LINES
            and all(isinstance(x, str) and len(x) <= CONTEXT_CHARS for x in lines)):
        return None, "bad diagnosis"
    patient = data.get("patient", {})
    if not isinstance(patient, dict):
        return None, "bad patient"
    fields = {f: patient.get(f, "") for f in PATIENT_FIELDS}
    if not all(isinstance(v, str) and len(v) <= CONTEXT_CHARS for v in fields.values()):
        return None, "bad patient"
    return {"diagnosis": [c for c in map(_clean, lines) if c], "patient": {f: _clean(v) for f, v in fields.items()}}, ""
