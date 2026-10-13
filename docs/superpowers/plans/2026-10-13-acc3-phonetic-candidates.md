# ACC3: Sound-Alike Candidates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the repair step meets a medicine the lexicon does not know, show the model up to 3 sound-alike lexicon names and let it pick exactly one or keep its spelling. The system never renames a row itself.

**Architecture:** New pure module `doctor_dictation/core/candidates.py` (`phonetic_key`, `suggest_candidates`). `build_repair_message(issues, transcript)` keeps its signature: it reads each unknown-medicine row's name back out of the issue text it is already given and asks `suggest_candidates` for that name. `ground_rx`, `open_issues`, `validate_structured` and `loop_should_continue` are not touched, so the loop's issue count, cap and status gate are unchanged.

**Tech Stack:** Python 3.12 (`.venv`), `difflib` and `re` only (no new dependency), pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 5.2. Contracts: `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 2 and 4.7. Plan 10 of 15. Adds **16 tests**. **Run the suite first, note the count N, expect N + 16 at the end.**

## Assumptions about earlier plans

- B1a/B1b applied: `doctor_dictation/core/determinism.py` holds `ground_rx`, `build_repair_message`, `open_issues`, `loop_should_continue`, `load_lexicon`, `_alias_map`, `_FORMAT_CACHE`, `_ground_row`; `tests/test_core_purity.py` forbids I/O and third-party imports in `core/`.
- B0/B1c-B1e applied: `/api/format` still runs extract, ground, repair (today `backend/main.py:641-725`; find it with `grep -n build_repair_message -r doctor_dictation`), capped by `FORMAT_LLM_CAP = 3`; `tests/test_determinism.py` still has `_stub_llm(monkeypatch, drafts)` and `_rx(name, **kw)`. If B1d changed the key/provider setup lines in `_stub_llm`, edit only those lines there (contracts rule 9); this plan imports the helper.

## Global Constraints

- `core/` stays pure (stdlib only); `candidates.py` reads the lexicon only via `determinism.load_lexicon()`. No file over 500 lines.
- `/api/format` status codes and JSON shapes do not change.
- **Never auto-accept:** no code writes a candidate into a row. A name the model keeps stays `unknown-medicine` with its `[unverified: confirm with doctor]` note.
- Tests are offline (LLM stubbed via `httpx.AsyncClient`; a real `.env` key exists). Command: `.venv/bin/python -m pytest tests/ -q`. **No `git commit` or `git push`**; leave changes uncommitted.

## Findings (measured on a scratch copy of the repo)

- The lexicon has **444 entries** (`drugs.json` v1.1.0; 444 distinct canonicals, 1,601 alias/brand spellings, 1,364 single words of 4+ letters ranked here). **Growing beyond 444 is a data task, out of scope**; the spec's open question on Indian brand sources stays open.
- `normalize_transcript` already fixes spellings within difflib 0.84 of a key. Candidates matter only for survivors: `cephixime` is 0.8235 from `cefixime`, so it stays unknown today.
- Prototype with `MIN_SCORE = 0.78`: true name in the top 3 for 44/44 mild and 15/15 harder mishearings (top 1 for the 44), and for 25/25 synthetic spellings that the 0.84 lookup misses; 13 junk strings (`medalpha`, `xyzzy`, `the doctor`...) returned `[]`. At 0.72 `medalpha` suggested Methylphenidate, hence 0.78. The sets are hand-made, not real dictations: a smoke result, ACC1's benchmark is the judge. About 13 ms per call.
- If the model picks a candidate the transcript does not literally contain (`azithro all` heard, `Azithromycin` written), `_ground_row` may grade it `unverified-name`, not `verified`. It is still flagged for the doctor, which fits "never auto-accept". Unchanged.

---

### Task 1: `phonetic_key`

**Files:** Create `doctor_dictation/core/candidates.py`, `tests/test_candidates.py`.

- [ ] **Step 1: Write the failing tests**

```python
"""ACC3: sound-alike candidates (offline; the LLM is always stubbed)."""
from doctor_dictation.core.candidates import phonetic_key


def test_key_basic_rules():
    assert phonetic_key("Knee") == "n"            # leading kn drops the k
    assert phonetic_key("pneumonia") == "nmn"      # leading pn drops the p
    assert phonetic_key("wrist") == "rst"          # leading wr drops the w
    assert phonetic_key("phenytoin") == phonetic_key("fenytoin") == "fntn"  # ph = f
    assert phonetic_key("xanax") == "snks"         # leading x = s, inner x = ks
    assert phonetic_key("chlor") == phonetic_key("clor") == "klr"  # ch = k, hard c = k
    assert phonetic_key("cefixime") == phonetic_key("sefixime") == "sfksm"  # soft c = s
    assert phonetic_key("cough") == "k"            # gh is silent


def test_key_classes_and_cleanup():
    assert phonetic_key("pill") == phonetic_key("bill") == "pl"      # b/p merge, ll collapses
    assert phonetic_key("dose") == phonetic_key("toes") == "ts"      # d/t merge, vowels dropped
    assert phonetic_key("Ibuprofen") == phonetic_key("aibuprofen") == "aprfn"  # first vowel = a
    assert phonetic_key("AZITHRAL") == phonetic_key("azithral")      # case ignored
    assert phonetic_key("") == "" and phonetic_key("12 -") == ""     # nothing to key


def test_key_equal_for_real_drug_mishearings():
    assert phonetic_key("Cetirizine") == phonetic_key("cetrizin") == "strsn"
    assert phonetic_key("Azithral") == phonetic_key("azithro all") == "astrl"
    assert phonetic_key("Metformin") == phonetic_key("metforman") == "mtfrmn"
```

- [ ] **Step 2: Run, expect failure**

Run: `.venv/bin/python -m pytest tests/test_candidates.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'doctor_dictation.core.candidates'`.

- [ ] **Step 3: Implement the key**

Create `doctor_dictation/core/candidates.py`:

```python
"""Sound-alike candidates for medicine names the lexicon does not know.

Pure and deterministic: stdlib only (re, difflib), no I/O, no randomness.
Candidates are only ever *suggestions* shown to the LLM in the repair message;
nothing here changes a prescription row.
"""
import difflib
import re

MIN_SCORE = 0.78
MIN_LEN = 4  # shorter lexicon keys ("pan", "pcm") are too noisy to rank

# Consonant classes that speech recognisers confuse: voiced/unvoiced pairs and
# near-identical sounds share one letter.
_CLASS = {
    "b": "p", "p": "p", "d": "t", "t": "t", "g": "k", "k": "k", "q": "k",
    "v": "f", "f": "f", "z": "s", "s": "s", "j": "j", "m": "m", "n": "n",
    "l": "l", "r": "r", "x": "x",
}
_VOWELS = set("aeiouy")


def phonetic_key(word: str) -> str:
    """Compact English phonetic key for drug names (lowercase letters).

    Case, spaces, digits and punctuation are ignored; then, in order:
    1. leading kn/gn/pn/wr lose the first letter; leading x is s.
    2. ph->f, ck->k, sch->sk, ch->k, th->t, sh->s; gh is silent.
    3. c before e/i/y is s, otherwise k; x is ks.
    4. Keep the first letter (a vowel there becomes a); drop later vowels, h, w.
    5. Merge confusable consonants: b/p, d/t, g/k/q, v/f, z/s.
    6. Collapse runs of the same letter ("all" -> "l").
    """
    s = re.sub(r"[^a-z]", "", (word or "").lower())
    if not s:
        return ""
    if s[:2] in ("kn", "gn", "pn", "wr"):
        s = s[1:]
    if s[0] == "x":
        s = "s" + s[1:]
    s = s.replace("sch", "sk").replace("ph", "f").replace("ck", "k")
    s = re.sub(r"gh", "", s)
    s = s.replace("ch", "k").replace("th", "t").replace("sh", "s")
    s = re.sub(r"c(?=[eiy])", "s", s).replace("c", "k").replace("x", "ks")
    out = []
    for i, ch in enumerate(s):
        if i == 0:
            code = "a" if ch in _VOWELS else _CLASS.get(ch, ch)
        elif ch in _VOWELS or ch in "hw":
            continue
        else:
            code = _CLASS.get(ch, ch)
        if not out or out[-1] != code:
            out.append(code)
    return "".join(out)
```

- [ ] **Step 4: Run, expect pass**

Run: `.venv/bin/python -m pytest tests/test_candidates.py -q`
Expected: `3 passed`.

---

### Task 2: `suggest_candidates`

**Files:** Modify `doctor_dictation/core/candidates.py`, `tests/test_candidates.py`.

**Interfaces:** Produces `suggest_candidates(name, k=3) -> list[str]` (canonical lexicon names, best first, `[]` when nothing scores `>= MIN_SCORE`) and constants `MIN_SCORE`, `MIN_LEN`. Consumes `determinism.load_lexicon` and `determinism._alias_map` through a function-level import, because `determinism.py` imports this module (Task 3) and a top-level import would be circular.

- [ ] **Step 1: Write the failing tests.** Replace the import line at the top of `tests/test_candidates.py` with:

```python
from doctor_dictation.core.candidates import MIN_SCORE, phonetic_key, suggest_candidates
from doctor_dictation.core.determinism import load_lexicon
```

Append:

```python
def test_suggest_real_entries_top1():
    # Expected canonicals were read from the lexicon; none is spelled as listed.
    cases = {
        "azithro all": "Azithromycin", "pantaprazole": "Pantoprazole",
        "amoxycilin": "Amoxicillin", "glimiperide": "Glimepiride",
        "cephixime": "Cefixime", "siprofloxacin": "Ciprofloxacin",
        "montelucast": "Montelukast", "phentanyl": "Fentanyl",
    }
    for heard, canon in cases.items():
        got = suggest_candidates(heard)
        assert got and got[0] == canon, (heard, got)


def test_suggest_matches_brand_spelling_to_generic():
    # Azithral and Zithromax are brands of Azithromycin: the candidate is the generic.
    assert suggest_candidates("azithral")[0] == suggest_candidates("Zithromax")[0] == "Azithromycin"


def test_suggest_k_and_dedupe():
    three = suggest_candidates("tel misartan", k=3)
    assert three[0] == "Telmisartan" and len(three) == len(set(three)) <= 3
    assert suggest_candidates("tel misartan", k=1) == ["Telmisartan"]
    assert suggest_candidates("tel misartan", k=0) == []
    assert len(suggest_candidates("doxicyclin", k=10)) <= 10
    assert suggest_candidates("metformin")[0] == "Metformin"  # exact name ranks first


def test_suggest_garbage_returns_empty():
    assert 0.5 < MIN_SCORE < 1.0
    for junk in ["", "ab", "12345", "xyzzy", "qqqq", "asdfgh", "kkkkk", "wxyz",
                 "fever", "hello", "medalpha", "medbeta", "the doctor"]:
        assert suggest_candidates(junk) == [], junk


def test_suggest_deterministic_5x():
    for heard in ["azithro all", "doxicyclin", "lazartan", "medalpha"]:
        runs = [suggest_candidates(heard) for _ in range(5)]
        assert all(r == runs[0] for r in runs), heard


def test_suggest_only_returns_lexicon_canonicals():
    canon = {e["canonical"] for e in load_lexicon()}
    for heard in ["azeethromycin", "lazartan", "cetrizine", "doxicyclin", "ramipral"]:
        assert set(suggest_candidates(heard)) <= canon
```

- [ ] **Step 2: Run, expect failure**

Run: `.venv/bin/python -m pytest tests/test_candidates.py -q`
Expected: collection error `ImportError: cannot import name 'MIN_SCORE'`.

- [ ] **Step 3: Implement.** Append to `candidates.py` (and put the two constants right after the imports, above `_CLASS`):

```python
MIN_SCORE = 0.78
MIN_LEN = 4  # shorter lexicon keys ("pan", "pcm") are too noisy to rank
```

```python
_index = (None, ())  # (lexicon list the index was built from, rows)


def _rows():
    """[(spelling, phonetic key, canonical)], sorted, cached per lexicon."""
    global _index
    from .determinism import _alias_map, load_lexicon

    lex = load_lexicon()
    if _index[0] is lex:
        return _index[1]
    rows = []
    for text, canon in sorted(_alias_map().items()):
        if len(text) >= MIN_LEN and " " not in text:
            rows.append((text, phonetic_key(text), canon))
    _index = (lex, tuple(rows))
    return _index[1]


def _score(a: str, ka: str, b: str, kb: str) -> float:
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    kratio = difflib.SequenceMatcher(None, ka, kb).ratio() if ka and kb else 0.0
    score = 0.5 * ratio + 0.5 * kratio
    if ka and ka == kb:
        score += 0.15
    elif min(len(ka), len(kb)) >= 3 and (ka.startswith(kb) or kb.startswith(ka)):
        score += 0.10
    return min(score, 1.0)


def suggest_candidates(name: str, k: int = 3) -> list:
    """Up to ``k`` lexicon canonical names that sound like ``name``, best first.

    Score = 0.5 * spelling ratio + 0.5 * phonetic-key ratio (difflib), +0.15
    for equal keys, +0.10 for a key prefix (3+ letters), capped at 1.0. A
    canonical keeps its best spelling (generic, alias or brand). Under
    MIN_SCORE nothing is returned, so garbage gives []. Ties sort by name.
    """
    low = re.sub(r"[^a-z]", "", (name or "").lower())
    key = phonetic_key(low)
    if k <= 0 or len(low) < 4 or len(key) < 3:
        return []
    best = {}
    for text, tkey, canon in _rows():
        sc = _score(low, key, text, tkey)
        if sc >= MIN_SCORE and sc > best.get(canon, 0.0):
            best[canon] = sc
    ranked = sorted(best.items(), key=lambda kv: (-round(kv[1], 6), kv[0].lower(), kv[0]))
    return [c for c, _ in ranked[:k]]
```

How it behaves: `azithral` and `azithro all` share key `astrl`, so both score 1.0 against brand `Azithral` and map to canonical `Azithromycin`, kept once at its best score. Ties break on lowercase canonical, then exact name.

---

### Task 3: Candidates in the repair message

**Files:** Modify `doctor_dictation/core/determinism.py`, `tests/test_candidates.py`.

**Design.** `build_repair_message` already receives `ground_rx`'s issue strings; an unknown row reads `rx[0] 'Cephixime': not in medicine list (444 entries)`. The builder matches that shape, takes the quoted name, and adds one indented line under the row; other issue kinds get nothing. A shared constant keeps producer and reader in step. `ground_rx` still returns the same list and `main.py` still counts `len(issues)`, so `n_open`, `loop_should_continue` and `open_issues(structured)` see identical inputs; only the prompt text grows.

- [ ] **Step 1: Write the failing tests.** Replace the imports at the top of `tests/test_candidates.py` with the final block and append the tests:

```python
import re

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.candidates import MIN_SCORE, phonetic_key, suggest_candidates
from doctor_dictation.core.determinism import (
    _FORMAT_CACHE,
    RX_UNKNOWN_MEDICINE,
    RX_VERIFIED,
    UNKNOWN_MEDICINE_TEXT,
    build_repair_message,
    ground_rx,
    load_lexicon,
    loop_should_continue,
)
from test_determinism import _rx, _stub_llm

TRANSCRIPT = "fever, tablet cephixime 200 mg twice daily after food"
```

```python
def _issues(*names):
    return ground_rx([{"name": n, "strength": ""} for n in names], TRANSCRIPT)[1]


def test_repair_message_candidates_only_for_unknown_rows():
    # Cephixime is unknown; Paracetamol is a real medicine absent from the
    # transcript (unverified-name), so it must get no candidate line.
    issues = _issues("Cephixime", "Paracetamol")
    msg = build_repair_message(issues, TRANSCRIPT)
    lines = msg.splitlines()
    i = next(n for n, ln in enumerate(lines) if "'Cephixime'" in ln)
    assert lines[i + 1].strip() == "Sound-alike names in the medicine list: Cefixime"
    j = next(n for n, ln in enumerate(lines) if "'Paracetamol'" in ln)
    assert not lines[j + 1].lstrip().startswith("Sound-alike")
    assert msg.count("Sound-alike names") == 1
    assert "pick EXACTLY ONE" in msg and "keep your spelling" in msg


def test_repair_message_has_no_candidate_text_without_candidates():
    for names in (["Medalpha"], ["Paracetamol"]):   # garbage name; non-unknown row
        msg = build_repair_message(_issues(*names), TRANSCRIPT)
        assert "Sound-alike" not in msg and "pick EXACTLY ONE" not in msg
        assert "FULL corrected JSON" in msg


def test_unknown_issue_text_is_shared_constant():
    issue = _issues("Cephixime")[0]
    assert re.match(r"^rx\[0\] 'Cephixime': " + re.escape(UNKNOWN_MEDICINE_TEXT), issue)


def test_loop_counting_unaffected_by_candidates():
    issues = _issues("Cephixime", "Medalpha", "Paracetamol")
    before = list(issues)
    build_repair_message(issues, TRANSCRIPT)
    assert issues == before and len(issues) == 3   # n_open = len(issues) is untouched
    assert loop_should_continue(3, 2, 1) is True   # guard unchanged
    assert loop_should_continue(1, 1, 2) is False
```

- [ ] **Step 2: Run, expect failure**

Run: `.venv/bin/python -m pytest tests/test_candidates.py -q`
Expected: collection error `ImportError: cannot import name 'UNKNOWN_MEDICINE_TEXT'`.

- [ ] **Step 3: Implement.** In `doctor_dictation/core/determinism.py`:

(a) Add `from .candidates import suggest_candidates` after the `from pathlib import Path` import.

(b) Below `RX_UNVERIFIED_STRENGTH = "unverified-strength"` add:

```python
# Wording of the unknown-medicine issue. build_repair_message recognises those
# issues by this text, so ground_rx and the message builder share one constant.
UNKNOWN_MEDICINE_TEXT = "not in medicine list"
```

(c) In `_ground_row`, change the unknown branch's issue string to use it (find it with `grep -n "not in medicine list" doctor_dictation/core/determinism.py`; the `validate_structured` warning at "not in medicine list -> flagged" stays as is):

```python
                    f"'{name}': {UNKNOWN_MEDICINE_TEXT} ({lexicon_size()} entries)")
```

(d) Replace the whole `build_repair_message` function with:

```python
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
    for iss in issues:
        lines.append(f"- {iss}")
        m = _UNKNOWN_ISSUE_RE.match(iss)
        cands = suggest_candidates(m.group(1)) if m else []
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
```

- [ ] **Step 4: Run, expect pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all earlier tests still pass (notably `test_repair_message_names_offenders` and the three `test_loop_*`), plus 13 in `tests/test_candidates.py` (the 3 e2e tests come in Task 4).

---

### Task 4: End-to-end through `/api/format`

**Files:** Modify `tests/test_candidates.py`. No source change.

All three tests share `TRANSCRIPT`, so `_format` clears the in-memory format cache first (a cached hit would skip the LLM and `calls["n"]` would be 0). The stub serves the drafts in order and records every message list, so the repair prompt can be read back.

- [ ] **Step 1: Append the tests**

```python
def _format(monkeypatch, drafts):
    _FORMAT_CACHE.clear()   # all three e2e tests share one transcript
    calls = _stub_llm(monkeypatch, drafts)
    r = TestClient(M.app).post("/api/format", json={"transcript": TRANSCRIPT})
    assert r.status_code == 200, r.text
    return calls, r.json()


def test_e2e_llm_picks_candidate_and_row_verifies(monkeypatch):
    bad = {"rx": [_rx("Cephixime", strength="200 mg")]}
    fixed = {"rx": [_rx("Cefixime", strength="200 mg")]}
    calls, j = _format(monkeypatch, [bad, fixed])
    assert calls["n"] == 2
    repair = calls["messages"][1][-1]["content"]
    assert "Sound-alike names in the medicine list: Cefixime" in repair
    row = j["structured"]["rx"][0]
    assert (row["name"], row["status"]) == ("Cefixime", RX_VERIFIED)
    assert j["grounding"]["open_issues"] == [] and j["grounding"]["rounds"] == 1


def test_e2e_ignored_candidate_leaves_row_flagged(monkeypatch):
    same = {"rx": [_rx("Cephixime", strength="200 mg")]}
    calls, j = _format(monkeypatch, [same, same])
    assert calls["n"] == 2          # no strict progress -> loop stops after one repair
    row = j["structured"]["rx"][0]
    assert row["name"] == "Cephixime"          # the system never renames it
    assert row["status"] == RX_UNKNOWN_MEDICINE and row["lexicon_match"] == ""
    assert "[unverified" in row["instructions"]
    assert len(j["grounding"]["open_issues"]) == 1


def test_e2e_garbage_name_gets_plain_repair_message(monkeypatch):
    bad = {"rx": [_rx("Medalpha")]}
    calls, j = _format(monkeypatch, [bad, bad])
    assert "Sound-alike" not in calls["messages"][1][-1]["content"]
    assert j["structured"]["rx"][0]["status"] == RX_UNKNOWN_MEDICINE
```

- [ ] **Step 2: Run, expect pass**

Run: `.venv/bin/python -m pytest tests/test_candidates.py -q`
Expected: `16 passed`. They prove: the pick case (`Cephixime` then `Cefixime`) puts `Cefixime` in the repair prompt and ends `verified`, `open_issues == []`, `rounds == 1`; the ignored case (same draft twice) keeps the name, status `unknown-medicine`, the `[unverified` note, 1 open issue and exactly 2 LLM calls; the garbage case (`Medalpha`) gets no candidate text.

---

### Task 5: Verification

Contracts section 5.

- [ ] **Step 1: Full suite.** Run `.venv/bin/python -m pytest tests/ -q`. Expected `N + 16 passed` (N noted before Task 1), including `tests/test_core_purity.py`. If purity fails on `candidates.py`, its only allowed imports are `difflib`, `re` and the package-relative `.determinism`.
- [ ] **Step 2: Run the app once.** With `OPENAI_API_KEY` and `DEEPSEEK_API_KEY` unset (rules fallback, so no repair message) start `.venv/bin/uvicorn doctor_dictation.main:app --port 8001`, then:

```bash
curl -s localhost:8001/api/format -H 'content-type: application/json' -d '{"transcript":"fever, tablet cephixime 200 mg twice daily after food"}' | python3 -m json.tool | grep -E '"status"|"name"|engine'
```
Expected: `name` is `cephixime` (never renamed), `status` is `unknown-medicine`, engine starts `fallback-rules+lexicon`. The candidate path is covered by the stubbed Task 4 tests; **a live-model repair round was not run** (needs a real key).
- [ ] **Step 3: Size and file list.** `wc -l doctor_dictation/core/candidates.py doctor_dictation/core/determinism.py tests/test_candidates.py` shows each under 500. Leave everything uncommitted; changed files: `doctor_dictation/core/candidates.py` (new), `doctor_dictation/core/determinism.py`, `tests/test_candidates.py` (new).

## Review Focus

1. `build_repair_message` keeps its signature; candidates appear only under unknown-medicine rows, and the pick-one instruction only when a candidate was listed.
2. `ground_rx`, `open_issues`, `loop_should_continue`, `FORMAT_LLM_CAP` are unchanged; no code assigns a candidate to a row (`grep -n suggest_candidates -r doctor_dictation`).
3. `MIN_SCORE = 0.78` was tuned on hand-made data; the junk list in `test_suggest_garbage_returns_empty` guards it.

## Out of scope

Growing the lexicon past 444 entries (data task); Double Metaphone (the spec said "such as"; this key avoids a dependency); grading a picked candidate differently when the transcript spells it another way; using candidates outside the repair message; a live-LLM measurement (ACC1's benchmark).
