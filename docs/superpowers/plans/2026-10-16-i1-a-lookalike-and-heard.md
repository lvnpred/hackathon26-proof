# I1-a: Look-alike Guard and "Heard" Text Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `core/lasa.py` (`twins`, `heard_as`, `lookalike_flag`), the blocking status `lookalike-check`, and the row fields `heard` and `lookalike`, without turning a third of the lexicon amber.

**Architecture:** Two tiers. A small curated list (`core/lexicon/lasa_pairs.json`) always flags; every other pair computed from the lexicon flags only on evidence in the raw transcript (the name was auto-corrected, or a twin is dictated too). The hook is one function, `lasa_row`, called from `ground_rx` and `validate_structured`; it only converts a row that is already `verified`, which puts it after every other check (contract 4.2).

**Tech Stack:** Python 3.12, stdlib only (difflib, re, json), FastAPI, pytest.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` (gap 1, P1 rows) and `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` sections 4.1-4.3 (section 4 wins).

**Assumptions about earlier plans:** I1-b is done: `core/repair.py` exists, `determinism.py` is 452 lines, `_generic_of`, the `generic` row field and `correction.DERIVED_ROW_FIELDS = ("generic",)` exist. Locate each edit below with `grep -n`; line numbers drift.

**Adds 23 tests.** Run the suite first and note N (967 passed, 1 skipped if I1-b is applied on the 2026-10-16 baseline); expect N + 23 at the end. No commits: leave everything uncommitted.

## Global Constraints

- Test command `.venv/bin/python -m pytest tests/ -q` with `DB_PATH` set to a temp file; tests are offline (LLM stubbed with `_stub_llm`).
- `core/` stays pure (stdlib and `doctor_dictation.core.*`); no file over 500 lines; the hook adds at most 4 net lines to `determinism.py` (it adds 3: 452 -> 455).
- A new status blocks save with no gate change (`core/safety.py:26` skips only `verified`); row fields are additive and always present (contract 4.1). New files: `core/lasa.py`, `core/lexicon/lasa_pairs.json` (packaged by `pyproject.toml`'s `core/lexicon/*.json`), `tests/test_lasa.py`.

## Review Focus

- Empty raw transcript (`check-row` may send none): no evidence, so only the curated pairs flag; `heard` is `""`. Tests `test_computed_pairs_flag_only_on_evidence`, `test_verified_curated_row_becomes_lookalike_check`.
- A name in a different case (`PREDNISONE`, `prednisone`): same word, never "heard" text, still flags. Tests `test_heard_as`, `test_curated_pair_always_flags_even_with_no_transcript_and_any_case`.
- A drug with two or more twins (`Cefixime`: Cefotaxime, Cefuroxime): the closest twin, or the one dictated, is named. Tests `test_twins_are_computed_symmetric_and_sorted`, `test_computed_pairs_flag_only_on_evidence`.
- A look-alike row must not start an LLM repair round (the model cannot fix it, and might drop the row). Test `test_lookalike_gives_the_repair_loop_nothing_to_fix`.
- The format cache must not hand one wording's `heard` to another wording that normalizes the same. Test `test_format_cache_is_per_raw_wording`.

## Measured first (lexicon v1.1.0: pairwise `difflib` ratio >= 0.75 or equal `phonetic_key`; Task 1 Step 5 reruns it)

| Measure | Result |
|---|---|
| Computed look-alike pairs | 120 (119 by spelling, 1 by sound only: `Biotin`/`Pethidine`, a spurious pair kept because it needs evidence to flag). Hydroxyzine/Hydralazine is ratio 0.727, so it is in the curated list only: 121 in the index |
| Canonicals with at least one twin | 156 of 444 (35.1%; 157 with the curated list): 93 with one twin, 45 with two, 15 with three, 3 with four. 594 of 1601 dictatable names (37.1%) resolve to such a generic. Not "over half" |
| Flag every twin: common drugs that would go amber on every use | Amlodipine, Atorvastatin (3 twins), Pantoprazole, Azithromycin, Omeprazole, Telmisartan, Cetirizine |
| Curated always-flag tier | 8 pairs, 16 canonicals = 3.6% of the lexicon (guard: at most 10%, Task 1 test) |
| Evidence tier | a misspelled dictation of a drug with twins flags in 225 of 250 alias spellings; a clean dictation never does. `heard_as` returns the alias in 538 of 639 alias spellings (the rest append a salt, `amikacin sulphate`, so the name is present: `""` is right) |
| Cost | index built once per process in 0.1 s; `heard_as` about 2 ms for a 159-word transcript |

**What this cannot detect.** If speech-to-text writes a different valid drug exactly as written ("Prednisolone" where the doctor said "Prednisone") nothing in the transcript shows the error: no auto-correction, no twin dictated. The curated always-flag list is the only guard for that case, so it covers only the pairs on it, and **a clinician must review it** (`reviewed: false` on every entry; the pairs come from the proposal's examples, not from a clinical source). Computed pairs add safety only when the transcript shows ambiguity.

## Changed existing tests

`tests/test_candidates.py:149-150` (`test_e2e_llm_picks_candidate_and_row_verifies`): `status == verified` and `open_issues == []` become `status == lookalike-check`, `heard == "cephixime"`, `lookalike == "Cefotaxime"`, one open issue. "cephixime" was auto-corrected to Cefixime, which has twins: the designed case.

`tests/test_determinism.py:476-484` (`test_grounding_status_schema`) passes untouched: its pipeline passes no raw transcript and no golden drug is on the curated list. `tests/test_core_purity.py` and `tests/test_file_sizes.py` pass (checked).

### Task 1: core/lasa.py and the curated list

**Files:** Create `doctor_dictation/core/lasa.py`, `doctor_dictation/core/lexicon/lasa_pairs.json`, `tests/test_lasa.py`.

**Interfaces:** Produces `twins(canonical) -> list[str]`, `heard_as(name, raw_transcript) -> str`, `lookalike_flag(canonical, name, raw_transcript) -> str` (contract 4.3), `always_flag_names() -> frozenset`, `lasa_row(status, canonical, name, raw_transcript) -> (status, {"heard", "lookalike"})`, `RX_LOOKALIKE = "lookalike-check"`. `heard_as`: "" when the name's words appear in the raw transcript (case, punctuation and hyphens ignored); otherwise the best 1-2 word stretch of the raw transcript, in its original case, that is an alias of the same generic or at least 0.8 similar (the grounding's own cut-off) and within 4 letters in length, else "". It imports `determinism` lazily (as `candidates.py:65` does), so `determinism` can import it.
- [ ] **Step 1: Write the failing tests**
```python
"""I1-a: look-alike guard, "heard" text and the new status (offline; the LLM is stubbed)."""
import json

import pytest

from doctor_dictation.core import lasa
from doctor_dictation.core.determinism import load_lexicon
from doctor_dictation.core.lasa import always_flag_names, heard_as, lookalike_flag, twins

CANONICALS = sorted({e["canonical"] for e in load_lexicon()})


# ---- Task 1: twins, the curated list, heard_as, the tiers ----
def test_twins_are_computed_symmetric_and_sorted():
    assert twins("Cefixime") == ["Cefotaxime", "Cefuroxime"]       # two twins, closest first
    assert twins("prednisone") == ["Prednisolone"]                  # input case does not matter
    assert twins("Paracetamol") == [] and twins("") == [] and twins("Nope") == []
    assert all(c in twins(t) for c in CANONICALS for t in twins(c))
    assert len({frozenset((a, b)) for a in CANONICALS for b in twins(a)}) >= 100   # 121 on v1.1.0


def test_curated_list_names_exist_and_is_marked_unreviewed():
    pairs = json.loads(lasa.PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]
    low = {c.lower() for c in CANONICALS}
    assert len(pairs) == 8 and twins("Hydroxyzine")[0] == "Hydralazine"
    assert all(p["a"].lower() in low and p["b"].lower() in low and p["source"] and p["reviewed"] is False
               for p in pairs)


def test_unconditional_flags_stay_under_ten_percent_of_the_lexicon():
    flagged = [c for c in CANONICALS if lookalike_flag(c, c, "") or lookalike_flag(c, c, f"tablet {c} 10 mg")]
    assert set(flagged) == set(always_flag_names())                 # only the curated list flags
    assert len(flagged) / len(CANONICALS) <= 0.10, (len(flagged), len(CANONICALS))   # 16 of 444 today


@pytest.mark.parametrize("name,raw,want", [
    ("Tamsulosin", "tablet tam sulosin 0.4 mg", "tam sulosin"),
    ("Tamsulosin", "TABLET TAMSULOSIN 0.4", ""),                  # case only: same word
    ("Azithromycin", "tab azithro 500", "azithro"),               # alias of the same generic
    ("Zyloric", "tab Zylorik 100", "Zylorik"),                    # original case of the raw words
    ("Neo-Mercazole", "neo mercazole 5 mg", ""),                  # hyphen only: same words
    ("Tamsulosin", "tam sulosin and then Tamsulosin", ""),        # the exact word wins
    ("Tamsulosin", "", ""),
    ("Atorvastatin", "fever, rest advised", ""),
])
def test_heard_as(name, raw, want):
    assert heard_as(name, raw) == want


def test_clean_dictation_of_any_lexicon_name_has_no_heard_text():
    for e in load_lexicon():
        for n in [e["canonical"], *e.get("brands", [])]:
            assert heard_as(n, f"fever tablet {n} 10 mg once daily after food") == "", n


def test_computed_pairs_flag_only_on_evidence():
    A = "Atorvastatin"
    assert lookalike_flag(A, A, "tablet Atorvastatin 10 mg") == "" and lookalike_flag(A, A, "") == ""
    assert lookalike_flag(A, A, "tablet Atorvastatin 10 mg and tablet rosuvastatin 5 mg") == "Rosuvastatin"
    assert lookalike_flag("Rosuvastatin", "Rosuvastatin",
                          "tablet Atorvastatin 10 mg and tablet rosuvastatin 5 mg") == A     # both rows flag
    assert lookalike_flag(A, A, "tablet atorvastin 10 mg") in twins(A)                      # auto-corrected
    # "ferrous" is an alias of Ferrous Ascorbate and the first word of Ferrous Fumarate: not evidence
    assert lookalike_flag("Ferrous Fumarate", "Ferrous Fumarate", "tablet Ferrous Fumarate 10 mg") == ""
    both = "tablet Ferrous Fumarate 10 mg and tablet Ferrous Sulfate 5 mg"
    assert lookalike_flag("Ferrous Fumarate", "Ferrous Fumarate", both) == "Ferrous Sulfate"


def test_curated_pair_always_flags_even_with_no_transcript_and_any_case():
    assert lookalike_flag("Prednisone", "Prednisone", "") == "Prednisolone"
    assert lookalike_flag("prednisone", "PREDNISONE", "tablet PREDNISONE 5 mg") == "Prednisolone"
    assert lookalike_flag("Hydralazine", "Hydralazine", "") == "Hydroxyzine"
```
- [ ] **Step 2: Run them.** `DB_PATH=$(mktemp -u) .venv/bin/python -m pytest tests/test_lasa.py -q` Expected: FAIL, `ImportError: cannot import name 'lasa' from 'doctor_dictation.core'`.
- [ ] **Step 3: Create the curated list `doctor_dictation/core/lexicon/lasa_pairs.json`** (names verified present in the lexicon; `source` points at where each pair is written down; a missing or broken file only switches this tier off):

```json
{
  "note": "High-risk look-alike pairs that ALWAYS ask the doctor to confirm. Not clinically reviewed: a clinician must review this list before it is relied on.",
  "pairs": [
    {"a": "Prednisone", "b": "Prednisolone", "source": "plan 2026-10-16-medication-name-accuracy, gap 1", "reviewed": false},
    {"a": "Citalopram", "b": "Escitalopram", "source": "plan 2026-10-16-medication-name-accuracy, gap 1", "reviewed": false},
    {"a": "Norfloxacin", "b": "Ofloxacin", "source": "plan 2026-10-16-medication-name-accuracy, gap 1", "reviewed": false},
    {"a": "Carbamazepine", "b": "Oxcarbazepine", "source": "plan 2026-10-16-medication-name-accuracy, gap 1", "reviewed": false},
    {"a": "Dapagliflozin", "b": "Empagliflozin", "source": "plan 2026-10-16-medication-name-accuracy, gap 1", "reviewed": false},
    {"a": "Clonazepam", "b": "Lorazepam", "source": "plan 2026-10-16-medication-name-accuracy, gap 1", "reviewed": false},
    {"a": "Acyclovir", "b": "Valacyclovir", "source": "plan 2026-10-16-medication-name-accuracy, gap 1", "reviewed": false},
    {"a": "Hydroxyzine", "b": "Hydralazine", "source": "plan 2026-10-16-medication-name-accuracy, P3 mixed-case row", "reviewed": false}
  ]
}
```
- [ ] **Step 4: Create `doctor_dictation/core/lasa.py`**
```python
"""Look-alike guard and "heard" text (pure). `lasa_row` is the one hook determinism.py calls per row.

Two tiers: the curated list (lexicon/lasa_pairs.json) ALWAYS flags; any other computed pair flags
only on evidence in the raw transcript (the name was auto-corrected, or a twin is dictated too).
"""
import difflib
import json
import re
from pathlib import Path

from .candidates import phonetic_key

RX_LOOKALIKE = "lookalike-check"
PAIRS_PATH = Path(__file__).resolve().parent / "lexicon" / "lasa_pairs.json"
MIN_RATIO = 0.75   # spelling similarity that makes two generics look-alikes
MIN_HEARD = 0.8    # the cut-off grounding uses to find a name in a transcript

_cache = (None, None)  # (lexicon list the index was built from, index)


def _words(text) -> list:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


def _has(words: list, phrase: tuple) -> bool:
    k = len(phrase)
    return bool(k) and any(tuple(words[i:i + k]) == phrase for i in range(len(words) - k + 1))


def _curated() -> list:
    try:
        pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]
    except (OSError, ValueError, KeyError, TypeError):
        return []   # a missing or broken file only switches the always-flag tier off
    return [(str(p["a"]).strip().lower(), str(p["b"]).strip().lower())
            for p in pairs if isinstance(p, dict) and p.get("a") and p.get("b")]


def _index() -> dict:
    """by_low / twins / always / names / amap, cached per loaded lexicon list."""
    global _cache
    from .determinism import _alias_map, load_lexicon

    lex = load_lexicon()
    if _cache[0] is lex:
        return _cache[1]
    canons = sorted({str(e["canonical"]).strip() for e in lex if str(e.get("canonical") or "").strip()})
    by_low = {c.lower(): c for c in canons}
    keys = {c: phonetic_key(c) for c in canons}
    twins: dict = {c: {} for c in canons}
    for i, a in enumerate(canons):
        sm = difflib.SequenceMatcher(None)
        sm.set_seq2(a.lower())
        for b in canons[i + 1:]:
            sm.set_seq1(b.lower())
            fast = sm.real_quick_ratio() >= MIN_RATIO and sm.quick_ratio() >= MIN_RATIO
            ratio = sm.ratio() if fast else 0.0
            if ratio >= MIN_RATIO or (keys[a] and keys[a] == keys[b]):
                twins[a][b] = twins[b][a] = max(ratio, MIN_RATIO)
    always = set()
    for a, b in _curated():
        if a in by_low and b in by_low:
            ca, cb = by_low[a], by_low[b]
            twins[ca][cb] = twins[cb][ca] = 1.0
            always.add(frozenset((ca, cb)))
    names = {c: [] for c in canons}   # every spelling of a canonical, as word tuples
    for e in lex:
        c = str(e.get("canonical") or "").strip()
        if c:
            names[c] += [tuple(_words(x)) for x in [c, *e.get("aliases", []), *e.get("brands", [])]]
    index = {"by_low": by_low, "twins": twins, "always": always, "names": names, "amap": _alias_map()}
    _cache = (lex, index)
    return index


def twins(canonical: str) -> list:
    """Look-alike generics of ``canonical``, closest first; [] if none."""
    ix = _index()
    found = ix["twins"].get(ix["by_low"].get(str(canonical or "").strip().lower()), {})
    return sorted(found, key=lambda t: (-found[t], t.lower()))


def always_flag_names() -> frozenset:
    """Canonicals that flag on every dictation (the curated list)."""
    return frozenset(c for pair in _index()["always"] for c in pair)


def heard_as(name: str, raw_transcript: str) -> str:
    """The raw-transcript words ``name`` came from; "" when the name is there as written (case,
    punctuation and hyphens ignored). Else the best k-1..k+1 word stretch (k = words in the name),
    in its original case, that is an alias of the same generic or >= MIN_HEARD similar and within
    4 letters in length; the earlier stretch wins a tie."""
    nw = _words(name)
    toks = re.findall(r"[A-Za-z0-9]+", str(raw_transcript or ""))
    low = [t.lower() for t in toks]
    if not nw or not toks or _has(low, tuple(nw)):
        return ""
    amap = _index()["amap"]
    nj = " ".join(nw)
    want = amap.get(nj)
    best, best_r = "", 0.0
    for n in sorted({max(1, len(nw) - 1), len(nw), len(nw) + 1}):
        for i in range(len(low) - n + 1):
            g = " ".join(low[i:i + n])
            r = difflib.SequenceMatcher(None, nj, g).ratio()
            alias = bool(want) and amap.get(g) == want
            if (alias or (abs(len(g) - len(nj)) <= 4 and r >= MIN_HEARD)) and r > best_r:
                best, best_r = " ".join(toks[i:i + n]), r
    return best


def lookalike_flag(canonical: str, name: str, raw_transcript: str) -> str:
    """The twin to ask the doctor about, or "". Curated pair: always. Other pairs: only with evidence in
    ``raw_transcript`` (a twin dictated too, or ``name`` auto-corrected); with none, only curated pairs."""
    ix = _index()
    c = ix["by_low"].get(str(canonical or "").strip().lower())
    ts = twins(c) if c else []
    for t in ts:
        if frozenset((c, t)) in ix["always"]:
            return t
    words = _words(raw_transcript)
    if not ts or not words:
        return ""
    own = (_words(name), _words(c))   # a twin's short spelling ("ferrous") inside our own name is no evidence
    for t in ts:
        if any(_has(words, ph) and not any(_has(w, ph) for w in own) for ph in ix["names"].get(t, [])):
            return t
    return ts[0] if heard_as(name, raw_transcript) else ""


def lasa_row(status: str, canonical: str, name: str, raw_transcript: str):
    """(status, {"heard", "lookalike"}) for one grounded row; only a verified row becomes look-alike."""
    twin = lookalike_flag(canonical, name, raw_transcript) if status == "verified" else ""
    heard = heard_as(name, raw_transcript) if name else ""
    return (RX_LOOKALIKE if twin else status), {"heard": heard, "lookalike": twin}
```
- [ ] **Step 5: Run the tests and re-measure.** Expected: 14 passed. Then run `.venv/bin/python -c "from doctor_dictation.core.lasa import twins, always_flag_names as a; from doctor_dictation.core.determinism import load_lexicon as L; cs = sorted({e['canonical'] for e in L()}); print(len({frozenset((x, y)) for x in cs for y in twins(x)}), sum(1 for c in cs if twins(c)), len(a()), len(cs))"`. Expected: `121 157 16 444` (pairs, canonicals with a twin, curated canonicals, canonicals). Leave uncommitted.

### Task 2: The grounding hook and the new fields

**Files:** Modify `core/determinism.py`, `core/correction.py:206`, `tests/test_candidates.py:149`; test `tests/test_lasa.py`.

**Interfaces:** Consumes `lasa_row` (Task 1). Produces `ground_rx(rx_rows, transcript, raw_transcript="")` and `validate_structured(data, transcript, raw_transcript="")`, rows with `heard` and `lookalike` always present, and `DERIVED_ROW_FIELDS = ("generic", "heard", "lookalike")`.

Why the hook sits in the two callers and not in `_ground_row`: the row needs the twin text as well as the status, and `_ground_row` returns a fixed three-tuple. Only a `verified` row converts, so `unverified-name`, `unverified-strength` and I1-c's `dose-check` (all returned by `_ground_row` before `verified`) always win, which is contract 4.2. The `lookalike-check` row has no issue text, so `ground_rx` adds nothing to its issue list and the repair loop never runs for it; `open_issues` still reports it. The old `else:` branch of the status chain in `validate_structured` would have stamped a look-alike row with the "[unverified: confirm with doctor]" marker and a "not clearly dictated" warning, so it becomes `elif status == RX_UNVERIFIED_NAME:`. `preserve_untouched_rx_status` (`correction.py:247`) must restore `heard` and `lookalike`: the save path (`persistence.py:200-206`) re-validates with an empty transcript and would blank them, so they join `DERIVED_ROW_FIELDS`, which preserve already loops over.
- [ ] **Step 1: Write the failing tests** (append):
```python


# ---- Task 2: the grounding hook ----
from doctor_dictation.core.determinism import ground_rx, validate_structured
from test_determinism import _rx, _stub_llm


def _row(name, strength="", normalized="", raw=""):
    out, _w = validate_structured({"rx": [_rx(name, strength=strength)]}, normalized, raw)
    return out["rx"][0]


def test_verified_curated_row_becomes_lookalike_check():
    row = _row("Prednisone", "10 mg", "tablet Prednisone 10 mg", "tablet Prednisone 10 mg")
    assert (row["status"], row["lookalike"], row["heard"]) == ("lookalike-check", "Prednisolone", "")
    assert row["lexicon_match"] == "Prednisone" and "[unverified" not in row["instructions"]
    assert _row("Prednisone", "10 mg", "tablet Prednisone 10 mg")["status"] == "lookalike-check"  # no raw


def test_grounding_order_strength_and_name_checks_come_first():
    assert _row("Prednisone", "7 mg", "prednisone 7 mg")["status"] == "unverified-strength"
    row = _row("Prednisone", "", "fever, rest advised")
    assert (row["status"], row["lookalike"]) == ("unverified-name", "")


def test_rows_without_twins_carry_empty_fields_and_heard_is_filled():
    row = _row("Tamsulosin", "0.4 mg", "tablet Tamsulosin 0.4 mg", "tablet tam sulosin 0.4 mg")
    assert (row["status"], row["heard"], row["lookalike"]) == ("verified", "tam sulosin", "")
    rows, issues = ground_rx([{"name": ""}, {"name": "Prednisone"}], "prednisone", "prednisone")
    assert [(r["heard"], r["lookalike"]) for r in rows] == [("", ""), ("", "Prednisolone")]
    assert rows[1]["status"] == "lookalike-check" and len(issues) == 1     # only the empty name
```
- [ ] **Step 2: Run them.** Expected: FAIL, `TypeError: validate_structured() takes 2 positional arguments but 3 were given`.
- [ ] **Step 3: Edit `core/determinism.py` and `core/correction.py`**, in order:
In `doctor_dictation/core/determinism.py` (the imports), insert before `from .surface import ambiguous_names, surface_map`:
```python
from .lasa import lasa_row
```
In `doctor_dictation/core/determinism.py` (`ground_rx` signature) replace `def ground_rx(rx_rows, transcript: str):` with `def ground_rx(rx_rows, transcript: str, raw_transcript: str = ""):`.
In `doctor_dictation/core/determinism.py` (`ground_rx`, empty-name branch) replace `row["generic"] = ""` with `row.update(generic="", heard="", lookalike="")`.
In `doctor_dictation/core/determinism.py` (`ground_rx`), replace:
```python
        row["status"] = status
        row["lexicon_match"] = match
        row["generic"] = _generic_of(name, match)
```
with:
```python
        status, extra = lasa_row(status, match, name, raw_transcript)
        row["status"] = status
        row["lexicon_match"] = match
        row.update(generic=_generic_of(name, match), **extra)
```
In `doctor_dictation/core/determinism.py` (`validate_structured` signature) replace `def validate_structured(data: dict, transcript: str):` with `def validate_structured(data: dict, transcript: str, raw_transcript: str = ""):`.
In `doctor_dictation/core/determinism.py` (`validate_structured`), insert after `status, match, issue = _ground_row(name, strength, tl)`:
```python
        status, extra = lasa_row(status, match, name, raw_transcript)
```
In `doctor_dictation/core/determinism.py` (`validate_structured`, status chain) replace `else:  # RX_UNVERIFIED_NAME` with `elif status == RX_UNVERIFIED_NAME:`.
In `doctor_dictation/core/determinism.py` (`validate_structured`, the row dict) replace `"generic": _generic_of(name, match),` with `"generic": _generic_of(name, match), **extra,`.
In `doctor_dictation/core/correction.py` (module level) replace `DERIVED_ROW_FIELDS = ("generic",)` with `DERIVED_ROW_FIELDS = ("generic", "heard", "lookalike")`.
- [ ] **Step 4: Change the one existing e2e expectation.** In `tests/test_candidates.py` (`test_e2e_llm_picks_candidate_and_row_verifies`) replace the two assertions on lines 149-150 with:
```python
    # "cephixime" was auto-corrected to Cefixime, which has look-alikes: one tap, not a silent tick
    assert (row["name"], row["status"]) == ("Cefixime", "lookalike-check")
    assert (row["heard"], row["lookalike"]) == ("cephixime", "Cefotaxime")
    assert j["grounding"]["open_issues"] == ["rx[0] 'Cefixime': lookalike-check"]
    assert j["grounding"]["rounds"] == 1
```
- [ ] **Step 5: Run the suite.** Expected: all pass (N + 17); `wc -l doctor_dictation/core/determinism.py` prints `455`. Leave uncommitted.

### Task 3: Plumb the raw transcript from the endpoints

**Files:** Modify `api/format.py`, `pdf/sheet.py:14`, `frontend/app.js:57,994`; test `tests/test_lasa.py`.

**Interfaces:** Consumes `validate_structured(..., raw_transcript)`. `/api/format` passes `raw` (its stripped request text); `/api/v1/correct` passes `text` (the spoken correction). `_validate(data, transcript, raw="")` keeps its old two-argument calls working. The format cache key gains a short hash of `raw`: the normalized text is the same for "tam sulosin" and "Tamsulosin", but `heard` is not. `_ground` in the repair loop stays raw-less on purpose (no evidence needed there, and look-alikes add no issue). Until the new UI (plan I1-e), the old pill shows `lookalike-check` as the generic amber "Needs check", so two label lines (screen, print) are added.
- [ ] **Step 1: Write the tests** (append):
```python


# ---- Task 3: plumbing from the endpoints ----
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.determinism import _FORMAT_CACHE
from test_correction_ops import _post


def test_lookalike_gives_the_repair_loop_nothing_to_fix(monkeypatch):
    _FORMAT_CACHE.clear()
    calls = _stub_llm(monkeypatch, [{"rx": [_rx("Prednisone", strength="10 mg")]}] * 3)
    j = TestClient(M.app).post("/api/format", json={"transcript": "tablet prednisone 10 mg once daily"}).json()
    assert calls["n"] == 1 and j["grounding"]["rounds"] == 0           # no LLM repair round
    assert j["structured"]["rx"][0]["status"] == "lookalike-check"
    assert j["grounding"]["open_issues"] == ["rx[0] 'Prednisone': lookalike-check"]


def test_format_cache_is_per_raw_wording(monkeypatch):
    _FORMAT_CACHE.clear()
    _stub_llm(monkeypatch, [{"rx": [_rx("Tamsulosin", strength="0.4 mg")]}] * 2)
    c = TestClient(M.app)
    a = c.post("/api/format", json={"transcript": "tablet tam sulosin 0.4 mg"}).json()
    b = c.post("/api/format", json={"transcript": "tablet Tamsulosin 0.4 mg"}).json()
    assert a["normalized_transcript"] == b["normalized_transcript"] and b["cached"] is False
    assert (a["structured"]["rx"][0]["heard"], b["structured"]["rx"][0]["heard"]) == ("tam sulosin", "")


def test_correct_route_passes_the_spoken_words(monkeypatch):
    j = _post(monkeypatch, {"rx": [_rx("Tamsulosin", strength="0.4 mg")]}, {"rx": []},
              transcript="add tam sulosin 0.4 mg")
    assert j["structured"]["rx"][0]["heard"] == "tam sulosin"


def test_the_printout_has_a_label_for_the_new_status():
    from doctor_dictation.pdf.sheet import _CHECK
    assert _CHECK["lookalike-check"][1].startswith("Needs check")
```
- [ ] **Step 2: Run them.** Expected: three FAIL: `test_format_cache_is_per_raw_wording` (the second wording is served from the cache), `test_correct_route_passes_the_spoken_words` (`assert '' == 'tam sulosin'`) and the label test (`KeyError: 'lookalike-check'`); the repair-loop test already passes (it guards a regression).
- [ ] **Step 3: Edit `api/format.py`, `pdf/sheet.py`, `frontend/app.js`:**

In `doctor_dictation/api/format.py` (`_validate`) replace `async def _validate(data, transcript):` with `async def _validate(data, transcript, raw=""):`.
In `doctor_dictation/api/format.py` (`_validate`) replace `return await asyncio.to_thread(validate_structured, data, transcript)` with `return await asyncio.to_thread(validate_structured, data, transcript, raw)`.
In `doctor_dictation/api/format.py` (`format_transcript`, cache key), replace:
```python
    ckey = f"{sc.clinic_slug if sc else ''}:{key}"   # per-clinic cache: one clinic never sees another's hit
```
with:
```python
    ckey = f"{sc.clinic_slug if sc else ''}:{key}:{transcript_sha(raw)[:16]}"   # per clinic and raw wording
```
In `doctor_dictation/api/format.py` (`format_transcript`, the two rules-path calls) replace `await _validate(fallback_format(normalized), normalized)` with `await _validate(fallback_format(normalized), normalized, raw)`.
In `doctor_dictation/api/format.py` (`format_transcript`, the LLM path) replace `await _validate(best[1], normalized)` with `await _validate(best[1], normalized, raw)`.
In `doctor_dictation/api/format.py` (`correct`) replace `strip_grounding_markers(merge_form(current2, patch2)), normalized)` with `strip_grounding_markers(merge_form(current2, patch2)), normalized, text)`.
In `frontend/app.js` (`PILL`), insert after `"unverified-strength": ["warn", "±", "Needs check: strength not in known list"],`:
```javascript
  "lookalike-check": ["warn", "≈", "Needs check: looks like another medicine (see the row)"],
```
In `frontend/app.js` (`statusText`), insert before `: s === "verified" ? "verified"`:
```javascript
    : s === "lookalike-check" ? "looks like another medicine"
```
In `doctor_dictation/pdf/sheet.py` (`_CHECK`), insert after `"unverified-strength": ("±", "Needs check: strength not in known list"),`:
```python
    "lookalike-check": ("≈", "Needs check: looks like another medicine"),
```
- [ ] **Step 4: Run the suite.** Expected: all pass (N + 21). Leave uncommitted.

### Task 4: Save gate and save path

**Files:** Modify `core/safety.py` (docstring only); test `tests/test_lasa.py`.

**Interfaces:** Consumes `core.safety.screen_unverified`. No code change is needed: `screen_unverified` blocks every status except `verified` unless the index is confirmed (`safety.py:26`), and `api/persistence.py:194` calls it before saving. The tests prove it for the new status and prove the fields survive the save path (`validate_structured(structured, "")` then `preserve_untouched_rx_status`, as `persistence.py:200-206` does). The docstring lists the statuses, so it gains the new one.
- [ ] **Step 1: Write the tests** (append):
```python


# ---- Task 4: save gate and save path ----
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.safety import screen_unverified


def test_save_gate_blocks_lookalike_until_the_doctor_confirms_it():
    form = {"rx": [{"name": "Prednisone", "status": "lookalike-check"},
                   {"name": "Tamsulosin", "status": "verified"}]}
    assert screen_unverified(form) == [{"index": 0, "name": "Prednisone", "status": "lookalike-check"}]
    assert screen_unverified(form, confirmed_rows=[0]) == []


def test_save_path_keeps_status_heard_and_lookalike():
    saved = {"rx": [dict(_rx("Prednisone"), status="lookalike-check", lexicon_match="Prednisone",
                         heard="predni sone", lookalike="Prednisolone", generic=""),
                    dict(_rx("Dolo"))]}
    validated, _w = validate_structured(saved, "")           # what persistence.py does on save
    rows = preserve_untouched_rx_status(saved, {}, validated)["rx"]
    assert (rows[0]["status"], rows[0]["heard"], rows[0]["lookalike"]) == \
        ("lookalike-check", "predni sone", "Prednisolone")
    assert all(k not in rows[1] for k in ("status", "heard", "lookalike", "generic"))
```
- [ ] **Step 2: Run them.** Expected: PASS at once (they prove existing behaviour).
- [ ] **Step 3: Edit the docstring:**

In `doctor_dictation/core/safety.py` (docstring of `screen_unverified`), replace:
```python
``unverified-strength``). ``confirmed_rows`` is the list of rx indices the
```
with:
```python
``unverified-strength`` / ``lookalike-check``; any status but ``verified``
    blocks). ``confirmed_rows`` is the list of rx indices the
```
- [ ] **Step 4: Run the suite and leave uncommitted.** `DB_PATH=$(mktemp -u) .venv/bin/python -m pytest tests/ -q` Expected: N + 23 passed (990 if N is 967), 1 skipped. Changed files: `core/lasa.py` and `core/lexicon/lasa_pairs.json` and `tests/test_lasa.py` (new); `core/determinism.py`, `core/correction.py`, `core/safety.py`, `api/format.py`, `pdf/sheet.py`, `frontend/app.js`, `tests/test_candidates.py`.

## Disagreements with the index, and left out

- Contract 4.2 is met by converting only `verified` rows, not by a step inside `_ground_row`; I1-c's `dose-check` keeps its place there. The contract says "at most 4 net lines" in `determinism.py`: it is 3.
- Contract 4.1 says `lookalike` only when the status is `lookalike-check`: so it is. The contract is silent on two things this plan decides: a look-alike row gives the repair loop no issue (Task 2), and the format cache key includes the raw wording (Task 3).
- The premise "over half the lexicon would go amber" does not hold: 35.1% of canonicals have a twin. The two-tier design still stands, because the common drugs in the table above would nag.
- Left out: the row UI (I1-e), the per-clinic learned list's twins (I1-h), `check-row` plumbing (I1-d: pass the request `transcript` as `raw_transcript`). I1-c adds `dose-check` to the same status chain: like `lookalike-check` it needs no marker.
