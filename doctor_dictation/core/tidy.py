"""Cross-section cleanup of the drafted prose: the patient's details restated, a vitals line, one item in two sections.

Pure and stdlib-only. Runs after validation on /api/format and /api/v1/correct, never on Save, so the doctor's own
text is never rewritten. It never touches rx rows.
"""
import re

from doctor_dictation.core.prose import PROSE_FIELDS
from doctor_dictation.core.vitals import VITAL_KEYS, extract_vitals, same_reading, vitals_all_stored

_SEX = r"(?:male|female|man|woman|boy|girl|m|f)"
_YR = r"\d{1,3}\s*-?\s*(?:y|yr|yrs|year|years)\.?"
# Unmistakably demographic only: an age marker (old, y/o, yo) or a sex token; a bare "5 years" is a duration and stays.
_AGE = (rf"(?:(?:a\s+)?{_YR}\s*-?\s*old(?:\s*/?\s*{_SEX})?\b|\d{{1,3}}\s*(?:y/o|yo)\b(?:\s*/?\s*{_SEX}\b)?"
        rf"|(?:a\s+)?{_YR}\s*/?\s*{_SEX}\b|\d{{1,3}}\s*(?:male|female|man|woman|boy|girl)\b"
        # A bare "3m"/"6 f" is often months or something else: stripped only when it is the patient's age (_strip_lead).
        rf"|(?P<bare>\d{{1,3}})(?:\s*/\s*[mf]\b|-?[mf]\b|\s+[mf](?=\s*(?:[,:;/.]|$))))")
_SEP = r"(?:\s*[,;:.]\s*|\s+(?:with|having)\s+|\s+(?=c/o|h/o|k/c/o))"
_MSG = "{}[{}]: removed the patient's details from the start (they print in the patient line)"


def _lead_pattern(name):
    pre = rf"(?:{re.escape(name.strip())}\s*[,;:]\s*)?" if isinstance(name, str) and name.strip() else ""
    return re.compile(r"\s*" + pre + "(" + _AGE + ")" + _SEP, re.I)


def _age(age_sex):
    m = re.match(r"\s*(\d{1,3})", age_sex) if isinstance(age_sex, str) else None
    return int(m.group(1)) if m else None


def _strip_lead(text, pat, age=None):
    """(text without a leading age-sex clause, the clause) or (text, "") when it does not start with one."""
    m = pat.match(text)
    if not m or (m.group("bare") is not None and int(m.group("bare")) != age):
        return text, ""
    rest = text[m.end():].strip()
    return (rest[:1].upper() + rest[1:] if rest else ""), text[:m.end()]


def _norm(text):
    return " ".join(str(text).casefold().split()).strip(" .,;:")


def _fill(vitals, found):
    """Fill the empty vitals from `found`; False (nothing changed) when a key conflicts."""
    for k in VITAL_KEYS:
        if found.get(k) and vitals.get(k) and not same_reading(found[k], vitals[k]):
            return False
    for k in VITAL_KEYS:
        if found.get(k) and not vitals.get(k):
            vitals[k] = found[k]
    return True


def tidy_sections(structured, fields=PROSE_FIELDS):
    """Mutate `structured`; return one warning per change. Items are only changed or dropped in `fields`."""
    warnings = []
    vitals = structured.get("vitals")
    pat = _lead_pattern(structured.get("patientName"))
    age = _age(structured.get("ageSex"))
    for field in fields:
        items = structured.get(field)
        if not isinstance(items, list):
            continue
        kept = []
        for i, item in enumerate(items):
            if not isinstance(item, str):
                kept.append(item)
                continue
            text, clause = _strip_lead(item, pat, age)
            if clause:
                warnings.append(_MSG.format(field, i))
                if isinstance(vitals, dict):
                    _fill(vitals, extract_vitals(clause))
                if not text:
                    continue
            if isinstance(vitals, dict) and vitals_all_stored(text) and _fill(vitals, extract_vitals(text)):
                warnings.append(f"{field}[{i}]: moved to vitals")
                continue
            kept.append(text)
        items[:] = kept
    comps, dx = structured.get("complaints"), structured.get("diagnosis")
    if "complaints" in fields and isinstance(comps, list) and isinstance(dx, list):
        seen = {_norm(d) for d in dx if isinstance(d, str)} - {""}
        keep = []
        for c in comps:
            if isinstance(c, str) and _norm(c) in seen:
                warnings.append(f'complaints: dropped "{c}", the same as a diagnosis')
            else:
                keep.append(c)
        comps[:] = keep
    return warnings
