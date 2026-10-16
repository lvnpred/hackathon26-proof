"""Adult dosing reference: strength chips and the daily-total check. Pure, no AI. Whatever cannot be
computed is ``cannot-check`` (no claim, no flag); only ``reviewed`` entries can flag a row."""
import json
import logging
import math
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

DOSING_PATH = Path(__file__).resolve().parent / "lexicon" / "dosing.json"
DOSE_CHECK = "dose-check"
DAILY_UNITS = {"1-0-0": 1, "1-0-1": 2, "1-1-1": 3, "0-0-1": 1}      # ALLOWED_DOSES minus "SOS"
_MG = {"mg": Decimal(1), "g": Decimal(1000), "mcg": Decimal("0.001"), "ug": Decimal("0.001"),
       "µg": Decimal("0.001"), "μg": Decimal("0.001")}
_STRENGTH = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mg|g|mcg|ug|µg|μg)\s*$", re.I)
_log = logging.getLogger(__name__)
_YEARS = {"y", "yr", "yrs", "year", "years"}
_YOUNG = {"mo", "mos", "mth", "mths", "month", "months", "w", "wk", "wks", "week", "weeks", "d", "day", "days"}
_AGE = re.compile(r"\s*(\d+)(?:\.\d+)?\s*([A-Za-z]*)\s*(?:/.*)?$")
_cache = (None, {})                                                   # (path read, {"version", "entries"})

@dataclass(frozen=True)
class DoseVerdict:
    state: str          # in-range | above-max | form-mismatch | cannot-check
    daily_mg: float | None
    max_daily_mg: float | None
    note: str           # "" unless above-max or form-mismatch

_CANNOT = DoseVerdict("cannot-check", None, None, "")

def _text_list(v, allow_empty=False) -> bool:
    return isinstance(v, list) and (allow_empty or bool(v)) and all(isinstance(x, str) and x for x in v)

def _valid(e) -> bool:
    """Shape check: anything doubtful makes the entry invalid (it is then dropped, never half-trusted)."""
    if not isinstance(e, dict) or not isinstance(e.get("canonical"), str) or not e["canonical"]:
        return False
    adult = e.get("adult")
    cap = adult.get("max_daily_mg") if isinstance(adult, dict) else None
    try:
        return (_text_list(e.get("strengths"), True) and _text_list(e.get("forms", []), True)
                and isinstance(cap, (int, float)) and not isinstance(cap, bool) and math.isfinite(cap) and cap > 0
                and isinstance(adult.get("usual", ""), str))
    except (OverflowError, ValueError):                                       # a 400-digit integer cap
        return False

def _entries(raw) -> dict:
    good, dropped = {}, []
    for e in raw:
        if _valid(e):
            good.setdefault(e["canonical"].casefold(), []).append(e)
        else:
            dropped.append(e.get("canonical") if isinstance(e, dict) else None)
    out = {}
    for key, group in good.items():
        if len(group) == 1:
            out[key] = group[0]
        else:                                                         # never guess which cap is right
            dropped += [e["canonical"] for e in group]
    if dropped:
        _log.warning("dosing reference: dropped %d invalid entries: %s", len(dropped), ", ".join(map(repr, dropped)))
    return out

def _load() -> dict:
    # Re-read when DOSING_PATH changes; a broken file means no entries and version "unreadable".
    global _cache
    if _cache[0] != DOSING_PATH:
        try:
            raw = json.loads(DOSING_PATH.read_text(encoding="utf-8"))
        except Exception:    # noqa: BLE001  missing file, bad JSON, RecursionError on absurd nesting: all "unreadable"
            raw = None
        try:
            data = {"version": str(raw["version"]), "entries": _entries(raw["entries"])}
        except (KeyError, TypeError, AttributeError):
            _log.warning("dosing reference unreadable (%s): no dose-check and no reference strengths", DOSING_PATH)
            data = {"version": "unreadable", "entries": {}}
        _cache = (DOSING_PATH, data)
    return _cache[1]

def dosing_version() -> str:
    return _load()["version"]            # "none" while the shipped file is empty

def parse_strength_mg(strength: str):
    """Decimal mg for '5 mg', '1 g', '250 mcg'; None for anything else (ml, IU, %, 'mg/5ml')."""
    m = _STRENGTH.match(strength) if isinstance(strength, str) else None
    return Decimal(m.group(1)) * _MG[m.group(2).lower()] if m else None

def age_years(age_sex: str):
    """Years from '45 / M', '45', '45Y/M'; 0 for months, weeks or days; None when blank, unclear or over 120."""
    m = _AGE.match(age_sex) if isinstance(age_sex, str) else None
    if not m or int(m.group(1)) > 120:
        return None
    unit = m.group(2).lower()
    return int(m.group(1)) if not unit or unit in _YEARS else 0 if unit in _YOUNG else None

def strength_options(canonical: str) -> tuple:
    """(options, usual): reference strengths with the usual adult one first; else the lexicon list, ''.

    Chips come from any valid entry in the reference, reviewed or not; only ``reviewed`` entries can flag a row.
    """
    entry = _load()["entries"].get((canonical or "").casefold())
    if entry and entry.get("strengths"):
        usual = str((entry.get("adult") or {}).get("usual") or "")
        return ([usual] if usual else []) + [s for s in entry["strengths"] if s != usual], usual
    from .determinism import load_lexicon
    key = (canonical or "").casefold()
    return next((list(e.get("strengths", [])) for e in load_lexicon()
                 if key and str(e.get("canonical", "")).casefold() == key), []), ""

def _lists_every_lexicon_form(canonical: str, forms) -> bool:
    """True when ``forms`` holds every allowed form the lexicon lists for the drug (and it lists at least one).

    A reference that omits a form the lexicon knows is not a full list of usual forms, so a form-mismatch
    would be a guess: the form part is then cannot-check and only the dose is checked.
    """
    from .determinism import ALLOWED_FORMS, load_lexicon
    key = canonical.casefold()
    lex = next((e.get("forms") or [] for e in load_lexicon() if str(e.get("canonical", "")).casefold() == key), [])
    known = [f for f in lex if f in ALLOWED_FORMS]
    return bool(known) and all(f in forms for f in known)

def check_dose(canonical: str, strength: str, dose: str, age_sex: str, form: str = "") -> DoseVerdict:
    """Daily total against the reviewed adult maximum; a given ``form`` is also checked against the entry."""
    entry = _load()["entries"].get((canonical or "").casefold())
    age = age_years(age_sex)
    if not entry or entry.get("reviewed") is not True or age is None or age < 18:
        return _CANNOT
    verdict = _dose_verdict(entry, strength, dose)
    forms = entry.get("forms") or []
    if (verdict.state != "above-max" and form and forms and form not in forms     # an overdose outranks a form note
            and _lists_every_lexicon_form(entry["canonical"], forms)):
        return DoseVerdict("form-mismatch", None, None,
                           f"{form} is not a usual form of {entry['canonical']} (usual: {', '.join(forms)})")
    return verdict

def _dose_verdict(entry: dict, strength: str, dose: str) -> DoseVerdict:
    units, mg, cap = DAILY_UNITS.get(dose), parse_strength_mg(strength), (entry.get("adult") or {}).get("max_daily_mg")
    if units is None or mg is None or isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap <= 0:
        return _CANNOT
    daily, top = mg * units, Decimal(str(cap))
    fmt = lambda d: format(d.normalize(), "f")                                 # noqa: E731
    note = f"{fmt(daily)} mg a day; usual adult maximum {fmt(top)} mg" if daily > top else ""
    return DoseVerdict("above-max" if note else "in-range", float(daily), float(top), note)

def ground_extra(status: str, match: str, form: str, strength: str, dose: str, age_sex: str) -> tuple:
    """Grounding hook: (status, the three row fields of contract 4.1).

    Only a ``verified`` or ``lookalike-check`` row (both rank below dose-check) can become ``dose-check``.
    """
    options, usual = strength_options(match)
    note = ""
    if match and status in ("verified", "lookalike-check"):
        v = check_dose(match, strength, dose, age_sex, form)
        if v.state in ("above-max", "form-mismatch"):
            status, note = DOSE_CHECK, v.note
    return status, {"strength_options": options, "usual_strength": usual, "dose_note": note}
