"""Rule-based structuring used when no LLM is configured or the LLM fails.

Pure and offline: stdlib `re` only. `main.fallback_format` re-exports this name.
"""
import re

from . import rulesplit
from .determinism import _maps, load_lexicon
from .vitals import VITAL_KEYS, extract_vitals, vitals_all_stored

# The no-strength branch also knows the brands of these generics: a dictated brand is no longer
# rewritten to its generic before this runs.
_NO_STRENGTH = ("paracetamol", "ibuprofen", "aspirin", "azithromycin", "amoxicillin", "omeprazole", "cetirizine")


def _no_strength_names() -> str:
    names = set(_NO_STRENGTH) | {"crocin", "dolo"}
    names |= {b.lower() for e in load_lexicon() if str(e.get("canonical", "")).lower() in _NO_STRENGTH
              for b in e.get("brands", [])}
    return "|".join(re.escape(n) for n in sorted(names, key=lambda n: (-len(n), n)))


def _spelled(name: str) -> str:
    """A lexicon name in its own casing ("Moxikind-CV", not the title-cased "Moxikind-Cv").

    Case only: the surface map sends an alias to its generic ("amlo" -> "Amlodipine"), and the
    dictated word must stay (a guessed generic grounds unverified-name).
    """
    s = _maps()[0].get(name.lower())
    return s if s and s.lower() == name.lower() else name


# Drug name: a letter, then letters, spaces, hyphens, or digits after a letter, digit or hyphen
# ("Alpha D3", "B12", "Doxy-1"), or a letter + digit ("D3"). A digit never follows a space, so a
# bare number is never part of a name and cannot pull in the previous row's words.
_NAME = r"(?:[A-Za-z](?:[A-Za-z\- ]|(?<=[A-Za-z0-9\-])\d){2,30}?|[A-Za-z]\d)"


def _own_words_start(m: re.Match, raw_form: str | None, name: str) -> int:
    """Where a medicine match's own words begin.

    Unpunctuated speech makes the lazy name swallow the previous medicine's instructions
    ("twice daily and Pan 40 mg"), so the medicine starts at its form word, else at its kept name.
    """
    if raw_form:
        return m.start(1)
    offset = m.group(2).lower().rfind(name.split()[0].lower()) if name else -1
    if offset < 0:
        return m.start()
    return m.start(2) + offset


# The seeded demo note (ureteric stone) applies only to the whole demo dictation: every one of these phrases, not one keyword.
_DEMO_PHRASES = ("ureteric", "calculus", "tamsulosin", "deflazacort", "citrate")


# Words that follow a medicine name and are not part of it (a frequency, a timing, a unit).
_NOT_SUFFIX = frozenset("od bd tds tid qid hs sos for the and once daily with at in on of to as if tab cap syp inj pm am mg ml day days week per".split())


def _duration(window: str) -> str:
    """"3 days" from "for 3 days" or "for three days"-style digits in the window; "" when none was dictated."""
    m = re.search(r"for (\d+)\s*(day|week|month)", window)
    return f"{m.group(1)} {m.group(2)}{'s' if int(m.group(1)) > 1 else ''}" if m else ""


def unparsed_notes(text: str, rx_rows) -> list:
    """One warning per dictated medicine line that produced no row (only its own words are quoted)."""
    names = [w.lower() for r in rx_rows for w in re.findall(r"[A-Za-z]{3,}", str(r.get("name", "")))]
    return [f"A medicine line was not understood: {line}" for line in rulesplit.split(text, frozenset(_maps()[0])).medicine
            if not any(n in line.lower() for n in names)]


DEMO_WARNING = "Offline demo example: a fixed sample note. Check every line before saving."


def is_demo(t: str) -> bool:
    """Whether the (lower-cased) dictation is the seeded demo, which gets the fixed sample note."""
    return all(p in t for p in _DEMO_PHRASES)


def fallback_format(transcript: str) -> dict:
    """Rule-based fallback when no DeepSeek key. Seeded example + generic med parser."""
    t = transcript.lower()
    # OP/registration number, dictated with the demographics (verbatim).
    # The brief's pattern is kept, but the captured token must contain a digit
    # so ordinary words beginning with "op" (open, operation, options) are not
    # mistaken for an OP number.
    om = re.search(r"\bop\s*(?:no|number|#)?[:\s]*([A-Za-z0-9-]+)", t)
    op_no = om.group(1) if om and re.search(r"\d", om.group(1)) else ""
    out = {
        "patientName": "",
        "ageSex": "",
        "opNo": op_no,
        "diagnosis": [],
        "complaints": [],
        "findings": [],
        "investigations": [],
        "rx": [],
        "advice": [],
        "review": "",
        "vitals": dict.fromkeys(VITAL_KEYS, ""),
    }
    if is_demo(t):
        out = {
            "patientName": "",
            "ageSex": "",
            "opNo": op_no,
            "diagnosis": ["Right lower ureteric calculus (5 mm), burning micturition"],
            "complaints": ["Right flank pain and burning micturition since 2 days"],
            "investigations": ["Urine culture", "Serum creatinine"],   # exactly the tests the demo dictates
            "rx": [
                {"form": "Tab.", "name": "Tamsulosin", "strength": "0.4 mg", "dose": "0-0-1", "timing": "After food, bedtime", "duration": "14 days", "instructions": "Take at bedtime"},
                {"form": "Tab.", "name": "Deflazacort", "strength": "6 mg", "dose": "1-0-1", "timing": "After food", "duration": "5 days", "instructions": ""},
                {"form": "Syr.", "name": "Potassium Magnesium Citrate", "strength": "15 ml", "dose": "1-1-1", "timing": "In half glass of water, after food", "duration": "14 days", "instructions": ""},
                {"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "SOS", "timing": "As needed for pain", "duration": "", "instructions": "Max 3 times daily"},
            ],
            "advice": ["High fluid intake (~3 liters/day)"],
            "review": "In 2 weeks with repeat USG KUB report",
        }
        return out

    text = transcript.strip()
    if not text:
        return out

    # --- demographics: name / age / sex, only if actually dictated ---
    STOP = {"you", "your", "are", "suffering", "having", "patient", "patients",
            "prescription", "dear", "and", "the", "with", "from", "for", "male",
            "female", "year", "years", "old", "age", "aged", "named", "name",
            "with", "next", "week", "day", "days", "tablet", "take", "please",
            "complaining", "presenting", "complains", "complaint", "c"}

    def clean_name(s: str) -> str:
        parts = []
        for p in s.strip().title().split():          # skip leading filler words, stop at the first one after a name word
            if p.lower() in STOP or len(p) < 2 or not p.isalpha():
                if parts:
                    break
                continue
            parts.append(p)
        return " ".join(parts[:3])

    for pat in [r"patient'?s? name (?:is )?([a-z]+(?: [a-z]+){0,2})",
                r"\bname is ([a-z]+(?: [a-z]+){0,2})",
                r"\bnamed ([a-z]+(?: [a-z]+){0,2})",
                r"\b(?:mr|mrs|ms|miss|sri|smt)\.?\s+([a-z]+(?: [a-z]+){0,2})"]:
        m = re.search(pat, t)
        if m and clean_name(m.group(1)):
            out["patientName"] = clean_name(m.group(1))
            break
    if not out["patientName"]:
        m = re.search(r"\b([a-z]+(?: [a-z]+){0,2}),?\s+(?:aged\s+)?(\d{1,3})\s*(?:year|yr)", t)
        if m and clean_name(m.group(1)):
            out["patientName"] = clean_name(m.group(1))

    age, sex = "", ""
    am = re.search(r"(\d{1,3})\s*(?:years?\s*old|years?|yrs?|y/o)\s*(male|female|man|woman|boy|girl)?", t)
    if am:
        age = am.group(1)
        w = (am.group(2) or "").lower()
        if w in ("male", "man", "boy"):
            sex = "M"
        elif w in ("female", "woman", "girl"):
            sex = "F"
    sm = re.search(r"(\d{1,3})\s*/\s*(m|f|male|female)\b", t)
    if sm:
        age = sm.group(1)
        sex = "M" if sm.group(2).startswith("m") else "F"
    if age:
        out["ageSex"] = f"{age} / {sex}" if sex else age

    # --- history / diagnosis / advice / tests / review: each dictated clause to one list, only a dictated "diagnosis X" ---
    parts = rulesplit.split(text, frozenset(_maps()[0]))
    out["complaints"], out["diagnosis"] = parts.history, parts.diagnosis
    out["advice"], out["investigations"], out["review"] = parts.advice, parts.investigations, parts.review

    # --- generic Rx parser: "<Drug> <strength> ... <frequency> ... [for X days]" ---
    freq_map = [
        (r"twice (a|per) day|twice daily|two times (a|per) day|two times daily|\bbd\b|1-0-1", "1-0-1"),
        (r"thrice|thrice daily|three times|three times daily|\btds\b|1-1-1", "1-1-1"),
        (r"once daily|once a day|one time (a|per) day|one time daily|\bod\b|1-0-0", "1-0-0"),
        (r"at bedtime|\bhs\b|0-0-1", "0-0-1"),
        (r"as needed|sos|when required|for pain", "SOS"),
        (r"every \d+ hours|q\d+h", "SOS"),
    ]
    # find drug mentions: optional form + capitalized word + strength
    rx_matches = list(re.finditer(r"(?:\b(tab(?:let)?|cap(?:sule)?|syr(?:up)?|inj(?:ection)?)\.?\s+)?\b(" + _NAME + r")\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu))\b", text, re.I))
    kept = []   # (match, form word, name, strength, where its own words begin), non-drugs left out
    for m in rx_matches:
        raw_form, name, strength = m.groups()
        name = name.strip().strip(".").title()
        # strip filler words browser STT often adds ("please have/take X") — repeat, they stack
        for _ in range(5):
            new_name = re.sub(r"^(Please|Have|Having|Take|Taking|Gave|Give|Giving|You|Your|Ok|Okay|And|Then|Now|Here|There|With|Patient|Has|Had|Suffering|Prescription|Is|Are)\b[\s,]*", "", name, flags=re.I).strip()
            if new_name == name:
                break
            name = new_name
        if len(name.split()) > 2:
            name = name.split()[-1]
        name = _spelled(name)
        # skip non-drugs
        if name.lower() in {"have", "take", "please", "with", "since", "daily", "twice", "after", "before"}:
            continue
        kept.append((m, raw_form, name, strength, _own_words_start(m, raw_form, name)))
    for i, (m, raw_form, name, strength, own_start) in enumerate(kept):
        # each medicine reads only its own stretch: from its own words (the first may also read just before)
        # to where the next kept medicine's own words begin, so "once daily" never leaks across
        prev_end = kept[i - 1][0].end() if i else 0
        next_start = kept[i + 1][4] if i + 1 < len(kept) else len(text)
        w_start = max(0, (m.start() if i == 0 else own_start) - 10, prev_end)
        w_end = min(m.end() + 80, next_start)
        window = text[w_start:w_end].lower()
        dose = ""
        for pat, code in freq_map:
            if re.search(pat, window):
                dose = code
                break
        timing = ""
        if "after food" in window or "after meal" in window:
            timing = "After food"
        elif "before food" in window or "before meal" in window or "empty stomach" in window:
            timing = "Before food"
        elif "bedtime" in window or "at night" in window:
            timing = "At bedtime"
        dur = ""
        dm = re.search(r"for (\d+)\s*(day|week|month)", window)
        if dm:
            n, u = dm.groups()
            dur = f"{n} {u}{'s' if int(n) > 1 else ''}"
        else:
            wm = re.search(r"for (?:the next |next |about )?((?:one|two|three|four|five|six)) (day|week|month)", window)
            if wm:
                numwords = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
                n, u = numwords[wm.group(1)], wm.group(2)
                dur = f"{n} {u}{'s' if n > 1 else ''}"
        form = {"tab": "Tab.", "tablet": "Tab.", "cap": "Cap.", "capsule": "Cap.", "syr": "Syr.", "syrup": "Syr.", "inj": "Inj.", "injection": "Inj."}.get((raw_form or "").lower()[:3], "")   # "" = no form word spoken
        out["rx"].append({"form": form, "name": name, "strength": strength, "dose": dose or "1-0-0", "timing": timing, "duration": dur, "instructions": ""})
        if len(out["rx"]) >= 8:
            break
    # fallback single-drug line without a unit strength, e.g. "have paracetamol twice a day", "Tab Dolo 650 thrice a day for 3 days"
    if not out["rx"]:
        m2 = re.search(rf"(?:\b(tab(?:let)?|cap(?:sule)?|syr(?:up)?|inj(?:ection)?)\.?\s+)?\b({_no_strength_names()})\b(?:[-\s]([A-Za-z]{{1,4}})\b)?", text, re.I)
        if m2:
            raw_form, base, suffix = m2.groups()
            if suffix and suffix.lower() in _NOT_SUFFIX:
                suffix = None
            name = _spelled(base.title()) + (f" {suffix.upper()}" if suffix else "")
            window = text[m2.start(2) + len(base) + (1 + len(suffix) if suffix else 0):][:60].split(".")[0]
            dose = next((c for p, c in freq_map if re.search(p, window.lower())), "1-0-0")
            sm = re.match(r"\s*(\d+(?:\.\d+)?)\b(?!\s*(?:day|week|month|time|tab|cap|x\b))", window, re.I)
            form = {"tab": "Tab.", "cap": "Cap.", "syr": "Syr.", "inj": "Inj."}.get((raw_form or "")[:3].lower(), "")
            out["rx"].append({"form": form, "name": name, "strength": sm.group(1) if sm else "", "dose": dose, "timing": "",
                              "duration": _duration(window.lower()), "instructions": ""})

    out["vitals"] = extract_vitals(text)
    out["complaints"] = [c for c in out["complaints"] if not vitals_all_stored(c)]   # a mixed or rejected one stays
    return out
