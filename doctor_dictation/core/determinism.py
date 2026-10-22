"""Deterministic helpers: transcript normalization, lexicon correction, validation, cache.

Stdlib-only (difflib) so the offline fallback path has zero new native deps.
All functions are pure/deterministic: no randomness, no network, fixed thresholds.
"""
import difflib
import hashlib
import json
import re
from pathlib import Path

from .repair import (  # noqa: F401  (api/format.py and tests import these from here)
    FORMAT_LLM_CAP, MAX_CANDIDATE_ROWS, RX_VERIFIED, UNKNOWN_MEDICINE_TEXT, _UNKNOWN_ISSUE_RE,
    build_repair_message, loop_should_continue, open_issues,
)
from . import formulary, investigations, overlay, rowcheck, spelled, vitals
from .commonwords import WORDS as COMMON_WORDS  # noqa: F401
from .lasa import lasa_row
from .combo import combo_suffix
from .surface import generic_fields, surface_map  # noqa: F401  (drugnames reads surface_map from here; tests patch it)
from .drugnames import (  # noqa: F401  (name matching lives in drugnames; callers import it from here)
    _SEP_RE, _alias_map, _alias_slot, _ambiguous_for, _block_slot, _build_alias_map, _canonical_lookup, _exact_lookup,
    _maps, _maps_slot, _sep_map, _sep_slot, blocked_names, correct_drugs, is_blocked, without_blocked,
)

LEXICON_PATH = Path(__file__).resolve().parent / "lexicon" / "drugs.json"
LEXICON_VERSION = "1.0.0"

_lexicon_cache = None

ALLOWED_DOSES = ("1-0-0", "1-0-1", "1-1-1", "0-0-1", "SOS")
ALLOWED_TIMINGS = ("After food", "Before food", "At bedtime")
ALLOWED_FORMS = ("Tab.", "Cap.", "Syr.", "Inj.")

# Schema caps: keep LLM output bounded, but a cap that actually truncates must
# say so in ``warnings`` — a dictated medicine is never silently dropped.
RX_ROW_LIMIT = 20
LIST_ITEM_LIMIT = 12

# Agent-loop grounding statuses (Part A). Deterministic, no LLM involved.
RX_UNVERIFIED_NAME = "unverified-name"
RX_UNKNOWN_MEDICINE = "unknown-medicine"
RX_UNVERIFIED_STRENGTH = "unverified-strength"

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
}
_NUMBER_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.I)

FREQ_PATTERNS = [
    (r"three times (a|per) day|three times daily|thrice( daily)?|\btds\b|1-1-1", "1-1-1"),
    (r"two times (a|per) day|two times daily|twice (a|per) day|twice daily|\bbd\b|1-0-1", "1-0-1"),
    (r"once daily|once a day|once per day|one time (a|per) day|one time daily|\bod\b|1-0-0", "1-0-0"),
    (r"at bedtime|\bhs\b|0-0-1", "0-0-1"),
    (r"as needed|\bsos\b|when required|for pain|if pain|whenever pain", "SOS"),
    (r"every \d+ hours|q\d+h|every \d+ hrs", "SOS"),
]

_FORMAT_CACHE: dict = {}
_FORMAT_CACHE_MAX = 512


def shipped_lexicon():
    """The shipped drugs.json entries, read once (``_lexicon_cache``). Callers must not mutate them."""
    global _lexicon_cache, LEXICON_VERSION
    if _lexicon_cache is not None:
        return _lexicon_cache
    try:
        data = json.loads(LEXICON_PATH.read_text(encoding="utf-8"))
        LEXICON_VERSION = data.get("version", LEXICON_VERSION)
        entries = data.get("entries", [])
    except (OSError, ValueError):
        entries = []
    _lexicon_cache = entries
    return entries


def load_lexicon():
    """The medicine list this request matches against: the shipped list with the active clinic overlay applied (the
    shipped list itself when the clinic changed nothing). One object per overlay version; callers must not mutate it."""
    return overlay.effective_view("medicine", shipped_lexicon())


overlay.register_shipped("medicine", shipped_lexicon)


def lexicon_size() -> int:
    """The SHIPPED list's size (health reports the shipped list; it runs outside any clinic)."""
    return len(shipped_lexicon())


def lexicon_version() -> str:
    """Lexicon version read from the loaded drugs.json (source of truth): the SHIPPED version, also outside a clinic.

    Reads live from the lexicon after it is (lazily) loaded, so consumers such
    as /api/health report the version in the file rather than the ``1.0.0``
    default bound by value at import time.
    """
    shipped_lexicon()
    return LEXICON_VERSION


def lexicon_identity() -> str:
    """The list a match was made against: shipped version + this request's overlay version. Key any cache of a
    lexicon-dependent answer on this, never on ``lexicon_version`` alone (that would serve one clinic another's)."""
    return f"{lexicon_version()}+{overlay.active().version}"


def normalize_numbers(text: str) -> str:
    def _rep(m):
        return str(NUMBER_WORDS[m.group(1).lower()])
    return _NUMBER_RE.sub(_rep, text)


def normalize_transcript(transcript: str) -> str:
    t = (transcript or "").strip()
    t = re.sub(r"\s+", " ", t)
    t, found = spelled.apply(t)          # letters the doctor spelled win over the words heard before them
    t = normalize_numbers(t)
    t, tokens = spelled.mask(t, found)   # ... and are never rewritten to a listed name
    t = spelled.unmask(correct_drugs(t), tokens)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def transcript_sha(transcript: str) -> str:
    return hashlib.sha256(transcript.encode("utf-8")).hexdigest()


def normalize_dose(window_lower: str) -> str:
    for pat, code in FREQ_PATTERNS:
        if re.search(pat, window_lower):
            return code
    return ""


def normalize_timing(window_lower: str) -> str:
    if "after food" in window_lower or "after meal" in window_lower:
        return "After food"
    if "before food" in window_lower or "before meal" in window_lower or "empty stomach" in window_lower:
        return "Before food"
    if "bedtime" in window_lower or "at night" in window_lower:
        return "At bedtime"
    return ""


def normalize_duration(window_lower: str) -> str:
    m = re.search(r"for (\d+)\s*(day|week|month)", window_lower)
    if m:
        n, u = int(m.group(1)), m.group(2)
        return f"{n} {u}{'s' if n > 1 else ''}"
    return ""


def _norm_strength(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def _ground_row(name: str, strength: str, transcript_lower: str):
    """Ground one medicine row against lexicon + transcript.

    Returns (status, lexicon_match, issue_or_None). Never raises.
    """
    try:
        amb = _ambiguous_for(name.strip().lower())
        if amb:  # a name two generics claim (a combination brand): never guess
            return (RX_UNVERIFIED_NAME, "",
                    f"'{name}': matches more than one medicine ({', '.join(amb)})")
        if combo_suffix(name):  # known brand + combination suffix (Zerodol-P): the generic is unknown, never guessed
            hit = formulary.ground_clinic(name, transcript_lower, _name_in_transcript)
            if hit and hit[0] == formulary.LOOKALIKE and formulary._lexicon_twin(name) == _exact_lookup(combo_suffix(name)[0]):
                return (RX_VERIFIED, "", None)  # a learned combination only sounds like its own base's generic: the clinic's name
            return hit or (RX_UNKNOWN_MEDICINE, "", None)
        canon = _canonical_lookup(name)
        if not canon:
            return formulary.ground_clinic(name, transcript_lower, _name_in_transcript) or (
                RX_UNKNOWN_MEDICINE, "", f"'{name}': {UNKNOWN_MEDICINE_TEXT} ({lexicon_size()} entries)")
        if not _name_in_transcript(name, transcript_lower) and not _name_in_transcript(
            canon, transcript_lower
        ):
            return (RX_UNVERIFIED_NAME, canon,
                    f"'{name}': not clearly dictated in transcript")
        if strength and str(strength).strip():
            known = [_norm_strength(s)
                     for e in load_lexicon() if e.get("canonical") == canon
                     for s in e.get("strengths", [])]
            if known and _norm_strength(strength) not in known:
                return (RX_UNVERIFIED_STRENGTH, canon,
                        f"'{name} {strength}': strength not in known {known}")
        return (RX_VERIFIED, canon, None)
    except Exception:
        return (RX_UNVERIFIED_NAME, "", f"'{name}': grounding failed")


def ground_rx(rx_rows, transcript: str, raw_transcript: str = ""):
    """Agent-loop grounding step (deterministic, no LLM).

    Returns (grounded_rows, issues). Each grounded row is a copy of the input
    plus `status` and `lexicon_match`. `issues` are human-readable strings
    used to build the targeted repair prompt. Never raises.
    """
    tl = (transcript or "").lower()
    grounded, issues = [], []
    for i, item in enumerate(rx_rows or []):
        if not isinstance(item, dict):
            continue
        row = dict(item)
        name = str(row.get("name") or "").strip().strip(".")
        strength = str(row.get("strength") or "").strip()
        if not name:
            row["status"] = RX_UNVERIFIED_NAME
            row["lexicon_match"] = ""
            row.update(generic="", generic_source="", combo_base="", heard="", lookalike="")
            issues.append(f"rx[{i}]: empty medicine name")
            grounded.append(row)
            continue
        status, match, issue = _ground_row(name, strength, tl)
        status, extra = lasa_row(status, match, name, raw_transcript)
        row["status"] = status
        row["lexicon_match"] = match
        row.update(**generic_fields(name, match), **extra)
        if issue:
            issues.append(f"rx[{i}] {issue}")
        grounded.append(row)
    return grounded, issues


def _name_in_transcript(name: str, transcript_lower: str) -> bool:
    nl = name.strip().lower()
    if not nl:
        return True
    transcript_lower = without_blocked(transcript_lower, name)   # never heard inside a name the clinic removed
    if nl in transcript_lower:
        return True
    toks = re.findall(r"[a-z]+", transcript_lower)
    bigrams = [" ".join(toks[i:i + 2]) for i in range(len(toks) - 1)]
    cands = toks + bigrams
    best = 0.0
    for c in cands:
        if abs(len(c) - len(nl)) > 4:
            continue
        r = difflib.SequenceMatcher(None, nl, c).ratio()
        if r > best:
            best = r
            if best >= 0.8:
                return True
    return best >= 0.8


def validate_structured(data: dict, transcript: str, raw_transcript: str = "", age_sex: str = "", vitals_typed: bool = False):
    """Coerce to schema, normalize enums, flag rx names absent from transcript.

    Returns (validated_dict, warnings_list). Never raises on bad input.
    """
    warnings = []
    d = data if isinstance(data, dict) else {}

    def _capped(values, field, items=None):
        """Stringify + drop blanks (or the given items), then cap at LIST_ITEM_LIMIT with a warning."""
        items = [str(x) for x in (values or []) if str(x).strip()] if items is None else items
        if len(items) > LIST_ITEM_LIMIT:
            warnings.append(
                f"{field}: truncated {len(items) - LIST_ITEM_LIMIT} rows "
                f"beyond the {LIST_ITEM_LIMIT}-row limit"
            )
            items = items[:LIST_ITEM_LIMIT]
        return items

    out = {
        "patientName": str(d.get("patientName") or ""),
        "ageSex": str(d.get("ageSex") or ""),
        "opNo": str(d.get("opNo") or ""),
        "diagnosis": _capped(d.get("diagnosis"), "diagnosis"),
        "complaints": _capped(d.get("complaints"), "complaints"),
        "findings": _capped(d.get("findings"), "findings"),
        "investigations": _capped(None, "investigations", investigations.coerce_items(d.get("investigations"))),   # items, unchecked
        "rx": [],
        "advice": _capped(d.get("advice"), "advice"),
        "review": str(d.get("review") or ""),
    }
    out["vitals"], notes = vitals.coerce_vitals(d.get("vitals"), vitals_typed)
    warnings += notes
    rx = d.get("rx") or []
    if isinstance(rx, list) and len(rx) > RX_ROW_LIMIT:
        warnings.append(
            f"rx: truncated {len(rx) - RX_ROW_LIMIT} rows "
            f"beyond the {RX_ROW_LIMIT}-row limit"
        )
    for i, item in enumerate(rx[:RX_ROW_LIMIT]):
        if not isinstance(item, dict):
            warnings.append(f"rx[{i}]: dropped non-object")
            continue
        row, notes = rowcheck.ground_with_notes(item, raw_transcript, transcript, age_sex or out["ageSex"], i)
        warnings += notes
        if row is not None:
            out["rx"].append(row)
    return out, warnings


def cache_get(key: str):
    return _FORMAT_CACHE.get(key)


def cache_put(key: str, value: dict):
    if len(_FORMAT_CACHE) >= _FORMAT_CACHE_MAX:
        _FORMAT_CACHE.pop(next(iter(_FORMAT_CACHE)))
    _FORMAT_CACHE[key] = value
