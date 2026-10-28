"""Plan SH-H4: find the patient a dictation names (contract 5.6, owner decision 7). Pure and offline.

The match is deliberately strict: an OP number the doctor's patients share, or one exact name (case and spacing
ignored) that fits the dictated age and sex. Anything unclear matches nobody, so no patient's terms leak to another.
Amended 2026-10-26 (owner, option A): rows of one name and sex with known ages at most AGE_SLACK apart are one person.
"""
import re

from .dosing import age_years

AGE_SLACK = 1                                     # years the dictated age may differ from the stored one

_AFTER_SLASH = re.compile(r"/\s*(male|female|m|f)\b", re.I)
_ANYWHERE = re.compile(r"\b(male|female|m|f)\b", re.I)


def _text(v) -> str:
    return v if isinstance(v, str) else ""


def _norm(v) -> str:
    return " ".join(_text(v).casefold().split())


norm_name = _norm                                # public: one name spelling for every comparison


def sex_letter(age_sex) -> str:
    """'M' or 'F' from '45 / M', '45Y/M', 'Female', '45 M'; '' when the text gives none."""
    s = _text(age_sex)
    m = _AFTER_SLASH.search(s) or _ANYWHERE.search(s)
    return m.group(1)[0].upper() if m else ""


def patient_of(structured) -> dict:
    """The sheet's patient fields; '' for anything that is not text."""
    s = structured if isinstance(structured, dict) else {}
    return {"name": _text(s.get("patientName")), "age_sex": _text(s.get("ageSex")), "op_no": _text(s.get("opNo"))}


def _ident(c) -> tuple:                          # one (name, sex, age); rows are never merged
    return (_norm(c["name"]), sex_letter(c["age_sex"]), age_years(_text(c["age_sex"])))


def _one_person(idents) -> bool:                 # 2026-10-26: one identity, or one name and sex a birthday apart
    if len(idents) == 1:
        return True
    ages = [i[2] for i in idents]
    return len({i[0] for i in idents}) == 1 and len({i[1] for i in idents}) == 1 and None not in ages \
        and max(ages) - min(ages) <= AGE_SLACK


def _fits(want, age, sex, ident) -> bool:
    name, other_sex, other_age = ident
    if name != want or (sex and other_sex and sex != other_sex):
        return False
    return age is None or other_age is None or abs(age - other_age) <= AGE_SLACK


def match_patient(op_no, name, age_sex, candidates) -> tuple:
    """The matched person's row ids in candidate order; () for nobody. ``candidates``: mappings with id, name, age_sex, op_no."""
    pool = list(candidates or ())
    rows = pool[:]

    def ids(idents):                                 # every row of the person, in candidate order
        return tuple(c["id"] for c in rows if _ident(c) in idents)

    op = _text(op_no).strip()
    if op:
        same = [c for c in pool if _text(c["op_no"]).strip() == op]
        idents = {_ident(c) for c in same}
        if _one_person(idents):
            return ids(idents)                       # the OP's person, with their rows that have no OP
        pool = same or pool                          # shared OP: the name rule among them; unknown OP: over all
    want = _norm(name)
    if sum(ch.isalpha() for ch in want) < 3:
        return ()
    age, sex = age_years(_text(age_sex)), sex_letter(age_sex)
    hits = {_ident(c) for c in pool if _fits(want, age, sex, _ident(c))}
    return ids(hits) if hits and _one_person(hits) else ()
