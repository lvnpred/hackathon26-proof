"""Rules-only sectioning of a dictation (plan I2-b fix round). Pure, stdlib only. Each sentence is cut into clauses at
marker words and commas; each clause goes to ONE list (history, diagnosis, advice, investigations, review) or is dropped
(patient identity, medicine lines). Only dictated words are kept; no clinical judgement is added."""
import re
from dataclasses import dataclass, field

_I = re.I
DX = re.compile(r"(?:(?:provisional|final|clinical|working)\s+)?(?:diagnosis|dx|impression)\b[\s:,-]*(?:(?:is|of|as)\b[\s:,-]*)?"
                r"|diagnosed\s+(?:as|with)\b[\s:,-]*", _I)
RX = re.compile(r"(?:prescribe[sd]?|tablet|tab|capsule|cap|syrup|syr|syp|injection|inj|please\s+have|please\s+take(?!\s+rest))\b\.?", _I)
REVIEW = re.compile(r"(?:(?:no|nil|without)\s+(?:need\s+(?:for\s+|to\s+)?)?)?(?:review|follow[\s-]?up|come\s+back|revisit)\b", _I)
ADVICE = re.compile(r"(?:advis(?:e|ed)|advice|plan)\b[\s:,-]*(?:to\b\s*)?", _I)
ADVICE_START = re.compile(r"(?:admit|refer(?:red)?|gargles?|rest|avoid|continue|drink|take\s+rest|apply|steam|soft\s+diet|low\s+salt)\b", _I)
TEST = re.compile(r"(?:cbc|ns1|usg|ultrasound|sonography|x-?ray|ecg|ekg|ct|mri|hba1c|lipid|thyroid|tsh|esr|crp|urine|culture|creatinine|sugar"
                  r"|blood|serum|widal|echo|scan|lft|kft|rft)\b", _I)
BARE = re.compile(r"(?:cbc|ns1|usg|ultrasound|x-?ray|ecg|ekg|mri|hba1c|lipid\s+profile|tsh|esr|crp|widal|echo|lft|kft|rft|urine\s+culture|blood\s+tests?|serum\s+creatinine)\b", _I)
MARK = re.compile(r"(?<![A-Za-z/])(?:" + "|".join(p.pattern for p in (DX, RX, REVIEW, ADVICE)) + ")", _I)
DOSE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu)\b", _I)
FRAG = re.compile(r"(?:once|twice|thrice|daily|after\s+(?:food|meals?)|before\s+(?:food|meals?)|at\s+(?:bedtime|night))\b", _I)
STRONG = re.compile(r"\b(?:c/o|complain(?:s|ed|ing|t)?\s+of|h/o|k/c/o|known\s+case|old\s+case|presenting|presents?|patient\s+has|having|associated|history\s+of)\b", _I)
WEAK = re.compile(r"\b(?:since|for\s+\d+\s+\w+)\b", _I)
SEX = r"(?:male|female|man|woman|boy|girl)"
AGE = re.compile(rf"\b(?:aged?\s*\d{{1,3}}(?:\s*(?:years?|yrs?|y/o))?(?:\s*old)?(?:\s*[,/]?\s*(?:{SEX}|[mf]\b))?"
                 rf"|\d{{1,3}}\s*(?:years?|yrs?|y/o)\s*old(?:\s*[,/]?\s*(?:{SEX}|[mf]\b))?"
                 rf"|\d{{1,3}}\s*(?:years?|yrs?|y/o)\s*[,/]?\s*(?:{SEX}|[mf]\b)"
                 rf"|\d{{1,3}}\s*/\s*[mf]\b|\d{{1,3}}[mf]\b)", _I)
OPNO = re.compile(r"\bop\s*(?:no|number|#)?[:\s]*[A-Za-z0-9-]*\d[A-Za-z0-9-]*", _I)
NAMED = re.compile(r"^(?:(?:patient|pt)\s+)?(?:named|called)\s+(?:(?!(?:complaining|complains?|complaint|with|having|presenting|suffering|c/o|has|had|known)\b)[A-Za-z]+\s*){1,3}", _I)
LEAD = re.compile(r"^(?:patient|pt)\b|^name\b|^(?:mr|mrs|ms|miss|sri|smt)\b\.?", _I)
CLEAR = re.compile(r"^(?:(?:patient|pt)'?s?\s+)?name\s+(?:is\s+)?\w+(?:\s+\w+){0,2}$|^(?:mr|mrs|ms|miss|sri|smt)\.?\s+\w+(?:\s+\w+)?$|^" + SEX + r"$", _I)
CONTINUE = re.compile(r"(?:at|after|before|once|twice|thrice|daily|for|in|sos|\d)\b", _I)
FILLER = frozenset("have take taking give please and with the a an".split())
LIMITS = {"history": 6, "diagnosis": 3}


@dataclass
class Split:
    history: list = field(default_factory=list)
    diagnosis: list = field(default_factory=list)
    advice: list = field(default_factory=list)
    investigations: list = field(default_factory=list)
    review: str = ""
    medicine: list = field(default_factory=list)       # clauses that name a medicine or a dose


def _up(s):
    return s[:1].upper() + s[1:]


def _identity(s):
    """The clinical remainder of a clause with the patient's name, age, sex and OP number removed."""
    s = OPNO.sub("", s).strip(" ,;:-")
    if CLEAR.match(s):
        return ""
    s = NAMED.sub("", s).strip(" ,;:-")
    m = AGE.search(s)
    if m:
        before = s[:m.start()].strip(" ,;:-")
        words = before.split()
        rest = s[m.end():].strip(" ,;:-")
        if not before or (len(words) <= 4 and (LEAD.match(before) or all(w[:1].isupper() for w in words))):
            return rest                                       # the name and the age phrase both go
        return f"{before} {rest}".strip()                     # clinical words before the age phrase stay
    return s


def _kind(s, prev):
    """(class, text) of one clause; prev is the class of the clause before it in the same sentence."""
    for name, rx in (("dx", DX), ("rx", RX), ("review", REVIEW)):
        m = rx.match(s)
        if m:
            return name, (s[m.end():] if name == "dx" else s).strip(" ,;:-")
    m = ADVICE.match(s)
    if m:
        s = s[m.end():].strip()
        return ("ix" if TEST.match(s) else "advice"), s
    if ADVICE_START.match(s):
        return "advice", s
    if BARE.match(s):
        return "ix", s
    if DOSE.search(s) or FRAG.match(s):
        return "rx", s
    s = _identity(s)
    if not s:
        return "id", ""
    if STRONG.search(s) or prev in (None, "history") or (prev == "dx" and WEAK.search(s)):
        return "history", s
    return prev, s


def _trim(s, names):
    """Cut a history clause at its first medicine name, dropping filler left before it."""
    cut = next((w.start() for w in re.finditer(r"[A-Za-z]{4,}", s) if w.group(0).lower() in names), len(s))
    words = s[:cut].split()
    while words and words[-1].lower().strip(",") in FILLER:
        words.pop()
    return " ".join(words).strip(" ,;:-")


def _test_items(s):
    return [(t.upper() if len(t) <= 4 and t.isalpha() else _up(t)) for t in re.split(r",|\band\b", s) for t in [t.strip()] if t]


def split(text: str, names=frozenset()) -> Split:
    """names: lowercase medicine names/aliases known to the lexicon (history stops at the first one)."""
    out = Split()
    for sentence in (p.strip() for p in re.split(r"(?<!\d)\.(?!\d)|[|;\n]", text or "") if p.strip()):
        cuts = sorted({0, *(m.start() for m in MARK.finditer(sentence))})
        runs, prev, joined_to = [], None, None                                   # runs: [class, [clause texts]]
        for a, b in zip(cuts, cuts[1:] + [len(sentence)]):
            for clause in sentence[a:b].split(","):
                s = clause.strip(" ,;:-")
                if not s:
                    continue
                kind, s = _kind(s, prev)
                if kind == "history":
                    s = _trim(s, names)
                if kind == "id" or not s:
                    continue
                prev = kind
                m = RX.match(s)
                if kind == "rx" and ((m and s[m.end():].strip(" .")) or DOSE.search(s)):    # a bare "prescribe" names nothing
                    if out.medicine and m and CONTINUE.match(s[m.end():].strip()) and joined_to == sentence:
                        out.medicine[-1] += " " + s                  # "1 tab at bedtime": the unit, not a new medicine
                    else:
                        out.medicine.append(s)
                    joined_to = sentence
                if runs and runs[-1][0] == kind:
                    runs[-1][1].append(s)
                else:
                    runs.append([kind, [s]])
        for kind, parts in runs:
            joined = ", ".join(parts)
            if kind == "history":
                out.history.append(_up(joined))
            elif kind == "dx":
                out.diagnosis.append(_up(joined))
            elif kind == "advice":
                out.advice.append(_up(joined))
            elif kind == "ix":
                out.investigations += _test_items(joined)
            elif kind == "review" and not out.review:
                out.review = _up(joined)
    out.history, out.diagnosis = out.history[:LIMITS["history"]], out.diagnosis[:LIMITS["diagnosis"]]
    return out
