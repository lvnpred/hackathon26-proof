"""Deterministic helpers: transcript normalization, lexicon correction, validation, cache.

Stdlib-only (difflib) so the offline fallback path has zero new native deps.
All functions are pure/deterministic: no randomness, no network, fixed thresholds.
"""
import difflib
import hashlib
import json
import re
from pathlib import Path

from .candidates import suggest_candidates

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
RX_VERIFIED = "verified"
RX_UNVERIFIED_NAME = "unverified-name"
RX_UNKNOWN_MEDICINE = "unknown-medicine"
RX_UNVERIFIED_STRENGTH = "unverified-strength"

# Wording of the unknown-medicine issue. build_repair_message recognises those
# issues by this text, so ground_rx and the message builder share one constant.
UNKNOWN_MEDICINE_TEXT = "not in medicine list"

# Max LLM calls per /api/format request (extract + up to 2 repairs).
FORMAT_LLM_CAP = 3

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


def load_lexicon():
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


def lexicon_size() -> int:
    return len(load_lexicon())


def lexicon_version() -> str:
    """Lexicon version read from the loaded drugs.json (source of truth).

    Reads live from the lexicon after it is (lazily) loaded, so consumers such
    as /api/health report the version in the file rather than the ``1.0.0``
    default bound by value at import time.
    """
    load_lexicon()
    return LEXICON_VERSION


def _alias_map():
    """alias_lower -> canonical.

    Deterministic and file-order independent: pass 1 claims canonical names +
    aliases (sorted by canonical), pass 2 claims brands. So brands always
    resolve to their generic (crocin -> Paracetamol), never to a stub entry.
    """
    m: dict = {}
    entries = sorted(load_lexicon(), key=lambda e: e.get("canonical", ""))
    for e in entries:
        canon = e.get("canonical", "")
        if not canon:
            continue
        for a in [canon] + e.get("aliases", []):
            key = a.strip().lower()
            if key and key not in m:
                m[key] = canon
    for e in entries:
        canon = e.get("canonical", "")
        if not canon:
            continue
        for a in e.get("brands", []):
            key = a.strip().lower()
            if key and key not in m:
                m[key] = canon
    return m


def normalize_numbers(text: str) -> str:
    def _rep(m):
        return str(NUMBER_WORDS[m.group(1).lower()])
    return _NUMBER_RE.sub(_rep, text)


def correct_drugs(text: str) -> str:
    """Fix STT splits/misspellings against the local lexicon (deterministic)."""
    amap = _alias_map()
    if not amap:
        return text
    out = text
    # 0) multiword aliases canonicalized (longest first), with canonical
    #    phrases masked BEFORE alias replacement so a shorter alias can never
    #    match inside an already-correct phrase ("magnesium citrate" inside
    #    "Potassium Magnesium Citrate"). Mask tokens are digit-only, invisible
    #    to the [A-Za-z] passes below.
    masked = {}

    def _mask(s: str) -> str:
        for i, canon in enumerate(sorted({c for c in amap.values() if " " in c},
                                         key=len, reverse=True)):
            pat = re.compile(r"\b" + re.escape(canon) + r"\b", re.I)
            if pat.search(s):
                token = f"\x00{i}\x00"
                if token not in masked:
                    masked[token] = canon
                s = pat.sub(token, s)
        return s

    def _restore(s: str) -> str:
        for token, canon in masked.items():
            s = s.replace(token, canon)
        return s

    out = _mask(out)
    for alias in sorted((a for a in amap if " " in a), key=len, reverse=True):
        out = re.sub(r"\b" + re.escape(alias) + r"\b", amap[alias], out, flags=re.I)
    out = _mask(out)  # protect canonicals introduced by alias replacement

    nospace = {}
    for alias, canon in amap.items():
        key = re.sub(r"[^a-z]", "", alias)
        if len(key) >= 5 and key not in nospace:
            nospace[key] = canon
    # 1) two-word splits: "tam sulosin" -> canonical
    tokens = re.findall(r"[A-Za-z]+", out)
    for i in range(len(tokens) - 1):
        w1, w2 = tokens[i], tokens[i + 1]
        if len(w1) < 2 or len(w2) < 3:
            continue
        key = (w1 + w2).lower()
        if key in nospace:
            canon = nospace[key]
            out = re.sub(r"\b" + re.escape(w1) + r"\s+" + re.escape(w2) + r"\b",
                         canon, out, count=1, flags=re.I)
    # 2) single-word exact alias + fuzzy (cutoff fixed, sorted keys)
    keys = sorted(k for k in amap if len(k) >= 5 and " " not in k)
    for tok in set(re.findall(r"[A-Za-z]{5,}", out)):
        low = tok.lower()
        if low in amap and " " not in low:
            if tok != amap[low]:
                out = re.sub(r"\b" + re.escape(tok) + r"\b", amap[low], out, flags=re.I)
            continue
        best = difflib.get_close_matches(low, keys, n=1, cutoff=0.84)
        if best:
            out = re.sub(r"\b" + re.escape(tok) + r"\b", amap[best[0]], out, flags=re.I)
    return _restore(out)


def normalize_transcript(transcript: str) -> str:
    t = (transcript or "").strip()
    t = re.sub(r"\s+", " ", t)
    t = normalize_numbers(t)
    t = correct_drugs(t)
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


def _canonical_lookup(name: str) -> str:
    """Resolve a dictated/LLM drug name to the lexicon canonical form.

    Exact alias match first, then fixed-cutoff fuzzy. Returns "" when the
    medicine is not in the list. Deterministic (sorted keys).
    """
    amap = _alias_map()
    low = (name or "").strip().lower()
    if not low:
        return ""
    if low in amap:
        return amap[low]
    keys = sorted(k for k in amap if len(k) >= 5)
    best = difflib.get_close_matches(low, keys, n=1, cutoff=0.84)
    return amap[best[0]] if best else ""


def _norm_strength(s: str) -> str:
    return re.sub(r"\s+", "", (s or "").lower())


def _ground_row(name: str, strength: str, transcript_lower: str):
    """Ground one medicine row against lexicon + transcript.

    Returns (status, lexicon_match, issue_or_None). Never raises.
    """
    try:
        canon = _canonical_lookup(name)
        if not canon:
            return (RX_UNKNOWN_MEDICINE, "",
                    f"'{name}': {UNKNOWN_MEDICINE_TEXT} ({lexicon_size()} entries)")
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


def ground_rx(rx_rows, transcript: str):
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
            issues.append(f"rx[{i}]: empty medicine name")
            grounded.append(row)
            continue
        status, match, issue = _ground_row(name, strength, tl)
        row["status"] = status
        row["lexicon_match"] = match
        if issue:
            issues.append(f"rx[{i}] {issue}")
        grounded.append(row)
    return grounded, issues


MAX_CANDIDATE_ROWS = 5  # unknown rows that get a candidate lookup per repair message
_UNKNOWN_ISSUE_RE = re.compile(r"^rx\[\d+\] '(.*)': " + re.escape(UNKNOWN_MEDICINE_TEXT))


def build_repair_message(issues, transcript: str) -> str:
    """Deterministic targeted repair prompt naming each offending row.

    For an unknown-medicine issue the row's name is read back out of the issue
    text and up to 3 sound-alike lexicon names are listed under it. The model
    may pick exactly one or keep its spelling; nothing here edits a row.
    """
    lines = [
        "Your previous JSON has grounding problems against the dictated",
        "transcript and the medicine list. Fix EXACTLY these rows:",
    ]
    offered = False
    looked_up = 0
    for iss in issues:
        lines.append(f"- {iss}")
        m = _UNKNOWN_ISSUE_RE.match(iss)
        cands = []
        if m and looked_up < MAX_CANDIDATE_ROWS:
            looked_up += 1
            cands = suggest_candidates(m.group(1))
        if cands:
            offered = True
            lines.append("  Sound-alike names in the medicine list: " + ", ".join(cands))
    lines.append(
        "For each row: either quote the exact transcript words supporting the"
        " medicine (and use a strength stated in the transcript), or remove"
        " the row. Never invent medicines, strengths, or durations."
    )
    if offered:
        lines.append(
            "Where sound-alike names are listed, pick EXACTLY ONE of them only if"
            " it is what the doctor said (judge by the transcript words);"
            " otherwise keep your spelling unchanged. Never pick a name that is"
            " not listed. A name kept as dictated stays flagged for the doctor."
        )
    lines.append("Return ONLY the FULL corrected JSON matching the schema.")
    return "\n".join(lines)


def loop_should_continue(prev_open: int, new_open: int, llm_calls_used: int,
                         cap: int = FORMAT_LLM_CAP) -> bool:
    """Loop guard: continue only with open issues, budget left, strict progress."""
    return new_open > 0 and llm_calls_used < cap and new_open < prev_open


def open_issues(validated: dict):
    """Issue strings for validated rows whose status is not verified."""
    out = []
    rx = (validated or {}).get("rx") or []
    for i, row in enumerate(rx):
        if isinstance(row, dict) and row.get("status", RX_VERIFIED) != RX_VERIFIED:
            out.append(f"rx[{i}] '{row.get('name', '?')}': {row.get('status')}")
    return out


def _name_in_transcript(name: str, transcript_lower: str) -> bool:
    nl = name.strip().lower()
    if not nl:
        return True
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


def validate_structured(data: dict, transcript: str):
    """Coerce to schema, normalize enums, flag rx names absent from transcript.

    Returns (validated_dict, warnings_list). Never raises on bad input.
    """
    warnings = []
    d = data if isinstance(data, dict) else {}

    def _capped(values, field):
        """Stringify + drop blanks, then cap at LIST_ITEM_LIMIT with a warning."""
        items = [str(x) for x in (values or []) if str(x).strip()]
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
        "investigations": _capped(d.get("investigations"), "investigations"),
        "rx": [],
        "advice": _capped(d.get("advice"), "advice"),
        "review": str(d.get("review") or ""),
    }
    rx = d.get("rx") or []
    if isinstance(rx, list) and len(rx) > RX_ROW_LIMIT:
        warnings.append(
            f"rx: truncated {len(rx) - RX_ROW_LIMIT} rows "
            f"beyond the {RX_ROW_LIMIT}-row limit"
        )
    tl = (transcript or "").lower()
    for i, item in enumerate(rx[:RX_ROW_LIMIT]):
        if not isinstance(item, dict):
            warnings.append(f"rx[{i}]: dropped non-object")
            continue
        form = str(item.get("form") or "Tab.")
        if form not in ALLOWED_FORMS:
            form = "Tab."
        name = str(item.get("name") or "").strip().strip(".")
        strength = str(item.get("strength") or "").strip()
        dose = str(item.get("dose") or "").strip()
        if dose not in ALLOWED_DOSES:
            fixed = normalize_dose(dose.lower()) if dose else ""
            if fixed:
                dose = fixed
            else:
                warnings.append(f"rx[{i}] {name or '?'}: unknown dose '{dose}' -> '1-0-0'")
                dose = "1-0-0"
        timing = str(item.get("timing") or "").strip()
        if timing not in ALLOWED_TIMINGS:
            fixed = normalize_timing(timing.lower())
            if fixed:
                timing = fixed
            elif ("food" in timing.lower() or "bedtime" in timing.lower()
                  or "as needed" in timing.lower()):
                pass  # legacy combined strings from seeded example
            else:
                timing = ""
        duration = normalize_duration(str(item.get("duration") or "").lower()) or str(item.get("duration") or "")
        instructions = str(item.get("instructions") or "")
        if not name and not strength:
            warnings.append(f"rx[{i}]: dropped empty row")
            continue
        # Agent-loop grounding: status + lexicon match on every row.
        status, match, issue = _ground_row(name, strength, tl)
        if status == RX_VERIFIED:
            pass
        elif status == RX_UNKNOWN_MEDICINE:
            warnings.append(f"rx[{i}] '{name}': not in medicine list -> flagged {status}")
            instructions = (instructions + " [unverified: confirm with doctor]").strip()
        elif status == RX_UNVERIFIED_STRENGTH:
            warnings.append(f"rx[{i}] '{name}': {issue} -> flagged {status}")
            instructions = (instructions + " [unverified strength: confirm with doctor]").strip()
        else:  # RX_UNVERIFIED_NAME
            warnings.append(f"rx[{i}] '{name}': not clearly dictated -> flagged unverified")
            instructions = (instructions + " [unverified: confirm with doctor]").strip()
        out["rx"].append({
            "form": form, "name": name, "strength": strength,
            "dose": dose, "timing": timing, "duration": duration,
            "instructions": instructions, "status": status,
            "lexicon_match": match,
        })
    return out, warnings


def cache_get(key: str):
    return _FORMAT_CACHE.get(key)


def cache_put(key: str, value: dict):
    if len(_FORMAT_CACHE) >= _FORMAT_CACHE_MAX:
        _FORMAT_CACHE.pop(next(iter(_FORMAT_CACHE)))
    _FORMAT_CACHE[key] = value
