"""Vitals: the five-field record, read from text, coerced from any shape, merged by field.

Pure and stdlib-only. Every value is a string with its unit ("140/90", "88/min",
"72 kg", "98%", "101 F"); "" means not stated.
"""
import math
import re

VITAL_KEYS = ("bp", "pulse", "weight", "spo2", "temp")
VITAL_CHARS = 20

_LEAD = r"\s*(?:is|of|was|:|=)?\s*"
_NUM = r"(\d+(?:\.\d+)?)"
_RNG = r"(\s*(?:-|\u2013|\u2014|\bto\b)\s*\d)?"       # a range ("88-92") is doubtful: read as ""
_PATTERNS = {
    "bp": re.compile(r"(?:\bbp\b|blood\s+pressure)" + _LEAD + r"(\d{2,3})\s*(?:/|by|over)\s*(\d{2,3})\b", re.I),
    "pulse": re.compile(r"(?:\bpulse(?:\s+rate)?|\bpr\b|heart\s+rate)" + _LEAD + r"(\d{2,3})\b" + _RNG
                        + r"(?:\s*(?:per\s*minute|/\s*min|bpm)\b)?", re.I),
    "weight": re.compile(r"(?:\bweight|\bwt\b)" + _LEAD + _NUM + _RNG + r"(?:\s*(?:kgs?|kilo(?:gram)?s?)\b)?", re.I),
    "spo2": re.compile(r"(?:\bspo2|\bsaturation|\bo2\s+sat)" + _LEAD + r"(\d{2,3})\b" + _RNG + r"(?:\s*(?:%|percent\b))?", re.I),
    "temp": re.compile(r"(?:\btemperature|\btemp)" + _LEAD + _NUM + _RNG
                       + r"(?:\s*(?:\u00b0|degrees?\b|deg\b\.?))?(?:\s*(f|c|fahrenheit|celsius)\b(?!/))?", re.I),
}
_FILLER = re.compile(r"\b(?:and|is|per|minute|min|bpm|kgs?|percent|f|c)\b", re.I)
# A word after the number that makes the reading doubtful (a dose, another weight unit, a duration).
_NOT_VITAL_UNIT = frozenset(
    "mg mcg g gm gms gram grams ml tab tabs tablet tablets cap caps capsule capsules iu unit units lb lbs pound pounds "
    "oz ounce ounces mm cm day days week weeks month months year years hour hours hr hrs time times".split())


def _in(x, lo, hi):
    return lo <= float(x) <= hi


def _norm(key, n, n2="", unit=""):
    """Validate one reading and return it in the stored format, or "" when out of range."""
    if key == "bp":
        return f"{n}/{n2}" if _in(n, 50, 260) and _in(n2, 30, 160) else ""
    if key == "pulse":
        return f"{n}/min" if _in(n, 20, 250) else ""
    if key == "weight":
        return f"{n} kg" if _in(n, 1, 300) else ""
    if key == "spo2":
        return f"{n}%" if _in(n, 50, 100) else ""
    unit = (unit or "")[:1].upper()
    if unit == "C":
        return f"{n} C" if _in(n, 30, 45) else ""
    if unit == "F":
        return f"{n} F" if _in(n, 90, 110) else ""
    return n if _in(n, 30, 45) or _in(n, 90, 110) else ""


def _format(key, m, text):
    """The stored string for one dictated match, or "" when the unit or value is doubtful."""
    nxt = re.match(r"\s*([A-Za-z]+)", text[m.end():])
    if nxt and nxt.group(1).lower() in _NOT_VITAL_UNIT:
        return ""
    if key == "bp":
        return _norm(key, m.group(1), m.group(2))
    if m.group(2):
        return ""                                            # a range was dictated
    return _norm(key, m.group(1), unit=m.group(3) if key == "temp" else "")


_SAFE = re.compile(r"^[0-9A-Za-z .,/%\u00b0:+-]*$")        # what a doctor-typed vital may contain
_NUMBER = r"(\d+(?:\.\d+)?)"
_VALUE = {                                                    # a stored or model-supplied value, whole string
    "bp": re.compile(r"(\d{2,3})\s*/\s*(\d{2,3})(?:\s*mm\s*hg)?", re.I),
    "pulse": re.compile(_NUMBER + r"(?:\s*(?:/\s*min|per\s*min(?:ute)?|bpm))?", re.I),
    "weight": re.compile(_NUMBER + r"(?:\s*(?:kgs?|kilo(?:gram)?s?))?", re.I),
    "spo2": re.compile(_NUMBER + r"(?:\s*(?:%|percent))?", re.I),
    "temp": re.compile(_NUMBER + r"(?:\s*(?:\u00b0|degrees?|deg\.?))?\s*(f|c|fahrenheit|celsius)?", re.I),
}


def _clean(key, s):
    """Normalise one model-supplied value; "" when unreadable or implausible."""
    m = _VALUE[key].fullmatch(s) if len(s) <= VITAL_CHARS else None
    if not m:
        return ""
    return _norm(key, m.group(1), m.group(2) if key == "bp" else "", m.group(2) if key == "temp" else "")


def extract_vitals(text) -> dict:
    """Read the five vitals from dictated text; "" for each one not found."""
    out = dict.fromkeys(VITAL_KEYS, "")
    text = text if isinstance(text, str) else ""
    for key, pat in _PATTERNS.items():
        last = None
        for last in pat.finditer(text):                      # a restatement is the correction: the last mention wins
            pass
        if last:
            out[key] = _format(key, last, text)
    return out


def coerce_vitals(value, typed=False):
    """Return (five-key dict of strings, warnings) for any input shape.

    typed=True is for text the doctor typed on the page (Save): a value that cannot be
    normalised is kept as typed when it is plain text within the length cap.
    """
    out = dict.fromkeys(VITAL_KEYS, "")
    warnings = []
    if isinstance(value, str):
        return extract_vitals(value), warnings
    if not isinstance(value, dict):
        return out, warnings
    for key in VITAL_KEYS:
        v = value.get(key)
        if isinstance(v, bool) or not isinstance(v, (str, int, float)):
            continue
        if isinstance(v, float) and not math.isfinite(v):
            warnings.append(f"vitals.{key}: ignored (not a number)")
            continue
        text = " ".join(str(v).split())
        if not text:
            continue
        out[key] = _clean(key, text)
        if not out[key] and typed and len(text) <= VITAL_CHARS and _SAFE.match(text):
            out[key] = text
        if not out[key]:
            warnings.append(f"vitals.{key}: ignored (unreadable or out of range)")
    return out, warnings


def merge_vitals(current, patch) -> dict:
    """Field by field: a non-empty patch value wins; "" or a missing key keeps the stored one."""
    out = coerce_vitals(current, True)[0]  # the sheet's own text stays as typed
    for key, v in coerce_vitals(patch)[0].items():
        if v:
            out[key] = v
    return out


def is_vitals_only(text) -> bool:
    """True when the text holds at least one vital and nothing else of substance."""
    text = text if isinstance(text, str) else ""
    rest, found = text, False
    for pat in _PATTERNS.values():
        rest, n = pat.subn(" ", rest)
        found = found or n > 0
    rest = _FILLER.sub(" ", rest)
    return found and not re.search(r"[A-Za-z]{2,}|\d", rest)


def _numbers(s):
    return re.findall(r"\d+(?:\.\d+)?", s if isinstance(s, str) else "")


def same_reading(a, b) -> bool:
    """True when both strings hold the same non-empty list of numbers."""
    na = _numbers(a)
    return bool(na) and na == _numbers(b)


def vitals_all_stored(text) -> bool:
    """True when the text is only vitals and every vital it names was stored (none rejected as out of range)."""
    if not is_vitals_only(text):
        return False
    named = {k for k, p in _PATTERNS.items() if p.search(text)}
    return named == {k for k, v in extract_vitals(text).items() if v}


def ground(v, *texts):
    """(copy of v, warnings): a value is blanked unless every number in it appears in one of `texts`.

    For model-drafted and correction-patch vitals only, never on Save or the sheet's own values. A value
    with no digits cannot have come from the dictation's numbers, so it is blanked too.
    """
    heard = {float(n) for t in texts for n in _numbers(t)}
    out = dict(v) if isinstance(v, dict) else {}
    warnings = []
    for key in VITAL_KEYS:
        val = out.get(key)
        if not isinstance(val, str) or not val.strip():
            continue
        nums = _numbers(val)
        if not nums or any(float(n) not in heard for n in nums):
            out[key] = ""
            warnings.append(f'vitals.{key}: removed "{val}" (not in the dictation)')
    return out, warnings
