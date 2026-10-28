"""Plan FB-B (owner item M2): does a correction's dictation name a DIFFERENT patient than the sheet? Pure and offline.

Names come only from labels ("patient ...", "name is ...", "Mr ...") or a leading "Name Name, 45 years"; a name stops at the
first common word, digit or punctuation, and "Dr" is no label, so a referral never counts. After a bare "patient" or as a leading
name, an all-capitals word ("BP") or a word before a dose ("Dolo 650", not "45 years") is no name; "tablet name is" is no label.
Two names are one person when every token of the shorter one matches a distinct token of the longer: equal, or a lone initial.
No fuzzy match: "Suresh Baboo" asks.
"""
import re

from .commonwords import WORDS
from .patientctx import norm_name

_CLINICAL = {"denies", "denied", "reports", "reported", "feels", "feeling", "needs", "needed", "has", "was", "tolerated", "refused",
             "refuses", "diabetic", "hypertensive", "anxious", "insulin", "stable", "better", "worse", "known", "advised", "looks",
             "states", "says", "admits", "improved", "improving", "allergic", "asthmatic", "pregnant", "afebrile", "febrile",
             "diabetes", "dm", "hypertension", "htn", "smoker", "smoking", "alcoholic", "asthma", "thyroid", "hypothyroid", "ckd", "copd"}
_STOP = WORDS | _CLINICAL | {"add", "complaining", "complains", "presenting", "c", "o", "dr", "doctor", "op", "no", "number"}
_HONORIFICS = {"mr", "mrs", "ms", "miss", "sri", "shri", "smt", "dr"}
_STRONG = re.compile(r"\b(?:next patient(?: is)?|patient['’]?s name is|patient name(?: is)?|name is|named|mr|mrs|ms|sri|shri|smt"
                     r"|(?-i:Miss))\b[,.:;-]?\s+", re.I)
_WEAK = re.compile(r"\bpatient(?: is)?[,.:;-]?\s+", re.I)   # bare "patient": the name must be Capitalised
_DRUG_LABEL = re.compile(r"\b(?:medicine|tablet|drug|brand|generic|capsule|injection)s?\s+(?:name is|named)\b", re.I)
_NUMBER_AFTER = re.compile(r"[,.:;-]?\s*\d")
_AGE_AFTER = re.compile(r"[,.:;-]?\s*\d{1,3}\s*/?\s*(?:years?|yrs?|y|yo|male|female|m|f)\b", re.I)
_LEADING = re.compile(r"^([a-z]+(?: [a-z]+){0,2}),?\s+(?:aged\s+)?\d{1,3}\s*(?:years?|yrs?|y)\b", re.I)
_TOKEN = re.compile(r"[A-Za-z][A-Za-z.]*")
_OP = re.compile(r"(?<!post )(?<!post-)\bop\s*(?:number|no\.?)?\s*[:#-]?\s*(\d[\d\s-]*\d|\d)", re.I)
_INTENT = re.compile(r"\b(?:correct this|correction|update|same patient|change (?:the )?(?:patient['’]?s )?name)\b", re.I)


def _name_at(text: str, pos: int, capital: bool = False) -> list:   # up to 3 name tokens from pos, none a stop word
    out = []
    while len(out) < 3:
        m = _TOKEN.match(text, pos)
        if not m or m.group().rstrip(".").casefold() in _STOP or text[m.end():m.end() + 1].isdigit():
            break
        if capital and not out and not m.group()[0].isupper():
            break
        out.append(m.group())
        pos = m.end()
        if text[pos:pos + 1] != " ":
            break
        pos += 1
    return out


def _plain(text: str, pos: int, tokens) -> bool:   # a bare-label or leading name: no "BP", no "Dolo 650"
    if len(tokens[0]) >= 2 and tokens[0].isupper():
        return False
    end = pos + len(" ".join(tokens))
    return not _NUMBER_AFTER.match(text, end) or bool(_AGE_AFTER.match(text, end))


def _title(tokens) -> str:
    return " ".join(t.rstrip(".").capitalize() + ("." if len(t.rstrip(".")) == 1 else "") for t in tokens)


def said_patient(text: str) -> dict:
    """{"name", "op_no"} the dictation states; '' for each one not said. Name is title-cased, at most 3 tokens."""
    t = " ".join(text.split()) if isinstance(text, str) else ""
    labels = _DRUG_LABEL.sub(lambda m: " " * len(m.group()), t)   # same offsets, minus "tablet name is"
    tokens = []
    for rx, weak in ((_STRONG, False), (_WEAK, True)):
        for m in rx.finditer(labels):
            tokens = _name_at(t, m.end(), weak)
            if tokens and weak and not _plain(t, m.end(), tokens):
                tokens = []
            if tokens:
                break
        if tokens:
            break
    if not tokens:
        m = _LEADING.match(t)
        words = m.group(1).split() if m else []
        if words and not any(w.rstrip(".").casefold() in _STOP for w in words) and _plain(t, 0, words):
            tokens = words
    op = _OP.search(t)
    return {"name": _title(tokens), "op_no": re.sub(r"\D", "", op.group(1)) if op else ""}


def _tokens(name) -> list:
    return [w for w in re.split(r"[\s.]+", norm_name(name)) if w and w not in _HONORIFICS]


def _fit(a: str, b: str) -> bool:
    return a == b or (len(a) == 1 and b.startswith(a)) or (len(b) == 1 and a.startswith(b))


def _covers(short: list, long: list) -> bool:     # each short token takes its own long token
    if not short:
        return True
    return any(_fit(short[0], w) and _covers(short[1:], long[:i] + long[i + 1:]) for i, w in enumerate(long))


def same_person(a: str, b: str) -> bool:
    """True when the names are one person, or either has no tokens."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return True
    short, long = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return _covers(short, long)


def _same_op(a: str, b: str) -> bool:
    da, db = re.sub(r"\D", "", a), re.sub(r"\D", "", b)
    if not da or not db:
        return norm_name(a) == norm_name(b)
    return da.endswith(db) or db.endswith(da)


def other_patient(text: str, sheet: dict, patch: dict):
    """{"name", "op_no"} of the different patient the correction names, else None. ``sheet`` is patientctx.patient_of(form)."""
    if _INTENT.search(text or ""):
        return None
    said = said_patient(text or "")
    patch = patch if isinstance(patch, dict) else {}
    name = (patch.get("patientName") or "").strip() if isinstance(patch.get("patientName"), str) else ""
    op = (patch.get("opNo") or "").strip() if isinstance(patch.get("opNo"), str) else ""
    name, op = name or said["name"], op or said["op_no"]
    sheet_name, sheet_op = (sheet.get("name") or "").strip(), (sheet.get("op_no") or "").strip()
    diff_name = name if name and sheet_name and not same_person(name, sheet_name) else ""
    diff_op = op if op and sheet_op and not _same_op(op, sheet_op) else ""
    return {"name": diff_name, "op_no": diff_op} if diff_name or diff_op else None
