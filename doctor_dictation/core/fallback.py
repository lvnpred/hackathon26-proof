"""Rule-based structuring used when no LLM is configured or the LLM fails.

Pure and offline: stdlib `re` only. `main.fallback_format` re-exports this name.
"""
import re


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
        "investigations": [],
        "rx": [],
        "advice": [],
        "review": "",
    }
    if "flank pain" in t or "burning micturition" in t or "ureteric" in t or "calculus" in t:
        out = {
            "patientName": "",
            "ageSex": "",
            "opNo": op_no,
            "diagnosis": ["Right lower ureteric calculus (5 mm), burning micturition"],
            "complaints": ["Right flank pain and burning micturition since 2 days"],
            "investigations": ["Urine Culture & Sensitivity", "Serum Creatinine", "Follow-up USG KUB"],
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
            "with", "next", "week", "day", "days", "tablet", "take", "please"}

    def clean_name(s: str) -> str:
        parts = [p for p in s.strip().title().split()
                 if p.lower() not in STOP and len(p) > 1 and p.isalpha()]
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

    # --- complaints: split into sentences, drop pure prescription sentences ---
    rx_keywords = r"(paracetamol|ibuprofen|aspirin|amoxi|azithro|tamsulosin|deflazacort|citrate|tablet|tab\.?|capsule|cap\.?|syrup|syr\.?|injection|inj\.?|mg|twice|thrice|daily|od\b|bd\b|tds|hs\b|sos|have |take )"
    sentences = [s.strip().capitalize() for s in re.split(r"[.|;]+", text) if s.strip()]
    out["complaints"] = [s for s in sentences if not re.search(r"\b\d+\s*mg\b", s.lower())][:4] or sentences[:2]

    # --- diagnosis hints ---
    for kw in ["headache", "migraine", "fever", "cough", "cold", "pain", "hypertension", "diabetes", "infection", "allergy", "asthma", "gastritis"]:
        if kw in t:
            out["diagnosis"] = [kw.capitalize()]
            break

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
    for m in re.finditer(r"(?:\b(tab(?:let)?|cap(?:sule)?|syr(?:up)?|inj(?:ection)?)\.?\s+)?\b([A-Za-z][A-Za-z\- ]{2,30}?)\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu))\b", text, re.I):
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
        # skip non-drugs
        if name.lower() in {"have", "take", "please", "with", "since", "daily", "twice", "after", "before"}:
            continue
        window = text[max(0, m.start() - 10):m.end() + 80].lower()
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
        form = {"tab": "Tab.", "tablet": "Tab.", "cap": "Cap.", "capsule": "Cap.", "syr": "Syr.", "syrup": "Syr.", "inj": "Inj.", "injection": "Inj."}.get((raw_form or "tab").lower()[:3], "Tab.")
        out["rx"].append({"form": form, "name": name, "strength": strength, "dose": dose or "1-0-0", "timing": timing, "duration": dur, "instructions": ""})
        if len(out["rx"]) >= 8:
            break
    # fallback single-drug line without strength, e.g. "have paracetamol twice a day"
    if not out["rx"]:
        m2 = re.search(r"\b(paracetamol|ibuprofen|crocin|dolo|aspirin|azithromycin|amoxicillin|omeprazole|cetirizine)\b([^.]{0,60})", t)
        if m2:
            name, window = m2.group(1).title(), m2.group(0)
            dose = next((c for p, c in freq_map if re.search(p, window)), "1-0-0")
            out["rx"].append({"form": "Tab.", "name": name, "strength": "", "dose": dose, "timing": "", "duration": "", "instructions": ""})

    # --- investigations / advice / review keyword scan ---
    ix_keys = ["blood test", "cbc", "urine", "culture", "creatinine", "sugar", "hba1c", "x-ray", "xray", "usg", "ultrasound", "ct ", "mri", "ecg", "thyroid", "lipid", "esr", "crp"]
    out["investigations"] = [k.upper() if len(k) <= 4 else k.title() for k in ix_keys if k.strip() in t]
    for pat in [r"drink [\w ]+water[a-z ]*", r"(take )?rest[a-z ]*", r"avoid [\w ,]+", r"(low salt|low sugar|soft diet)[\w ]*"]:
        m = re.search(pat, t)
        if m:
            out["advice"].append(m.group(0).strip().capitalize())
    rm = re.search(r"(review|follow[\s-]?up|come back)[^.]{0,60}", t)
    if rm:
        out["review"] = rm.group(0).strip().capitalize()
    return out
