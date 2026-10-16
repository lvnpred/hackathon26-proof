# I1-b: Brand as Dictated Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A dictated brand ("Tab Zyloric 100") stays as dictated in the normalized transcript, the LLM rows and the printout; the generic stays in `lexicon_match` and in the new screen-only row field `generic`.

**Architecture:** `correct_drugs` writes from a surface-form map (alias -> text to write: the brand's own spelling for a brand, the canonical for a generic or misspelling) while `_alias_map` and `_canonical_lookup` still return the generic for every check. Task 1 first frees room in `core/determinism.py` (482 lines, limit 500) by a pure move into `core/repair.py`. A brand two generics claim is never guessed.

**Tech Stack:** Python 3.12, stdlib only in `core/` (difflib, re), FastAPI, pytest.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` section 2c; contracts in `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` (section 4 wins).

**Adds 23 tests.** Run the suite first and note N (944 passed, 1 skipped on 2026-10-16); expect N + 23 at the end. No commits: every task ends "leave uncommitted".

## Global Constraints

- Test command `.venv/bin/python -m pytest tests/ -q`, with `DB_PATH` set to a temp file (single mode writes the real dev DB otherwise). Tests are offline: the LLM is stubbed (`_stub_llm`, `tests/test_determinism.py`).
- No source file over 500 lines (`tests/test_file_sizes.py`); `core/` imports stdlib and `doctor_dictation.core.*` only (`tests/test_core_purity.py`).
- Existing endpoints keep status codes and JSON shapes; `generic` is additive and always present (contract 4.1). Existing tests change only where "Changed existing tests" says.

## Review Focus

- A brand two generics claim, exact or near-spelled: not guessed (`unverified-name`, no `lexicon_match`). Test `test_a_brand_two_generics_claim_is_not_guessed`.
- The model writes the generic although the brand was dictated: flagged `unverified-name`, not trusted. Test `test_a_model_that_swaps_the_brand_for_the_generic_is_flagged_not_trusted`, plus a prompt rule.
- Hyphenated or spaced brands (`Neo-Mercazole`, `Alpha D3`) are not torn apart by the fuzzy pass. Tests `test_correct_drugs_brand_as_dictated_generic_normalised`, `test_every_lexicon_name_round_trips`.
- A brand dictated with no strength still reaches the offline rules path. Test `test_rules_path_keeps_a_brand_dictated_without_a_strength`.
- A saved or corrected row keeps `generic` with its status. Tests `test_preserve_restores_generic_with_the_status`, `test_replace_op_drops_the_old_generic`.

## Measured first (lexicon v1.1.0: 444 generics, 508 brands)

| Finding | Consequence |
|---|---|
| 491 of 952 canonical+brand names are rewritten today (`determinism.py:176-184`); 16 brands under 5 letters (`Dolo`) never are | The exact, fuzzy, split and multiword passes all need the surface map |
| 29 brands are also aliases of their own generic (`Emset`, `Alprax`, `Augmentin`, `Alpha D3`) and the alias pass claims the key first | The surface map must prefer the brand spelling |
| 9 hyphenated brands: today `Neo-Mercazole` becomes `Neo-Omeprazole` and `Taxim-O` becomes `Cefotaxime-O` (a different drug) | Mask `-` phrases like spaced ones; also fixes 25 of 33 keys that are rewritten wrongly today (`co-amoxiclav` becomes `co-Co-Amoxiclav`); 8 stay (`KNOWN_UNFIXED`) |
| Names two generics claim: 0 exact. Real example of the wrong single generic: `Combiflam` is listed only under Ibuprofen though it also holds paracetamol | The guard is forward-looking (plan I1-g imports more brands); a pharmacist should add Combiflam to Paracetamol's brands, after which the guard fires |
| 102 near-spelling pairs with different generics (ratio >= 0.84) | Look-alikes: plan I1-a |

Rules path (`core/fallback.py`): the generic parser keeps the name as written (`:112-114`), so strengths work. The no-strength branch (`:155-160`) knew nine literals and relied on `correct_drugs` turning `calpol` into `Paracetamol`; without that, `have calpol twice a day` loses its row, so Task 3 adds the brands of the same generics.

## Changed existing tests

| Where | Was | Becomes | Why |
|---|---|---|---|
| `tests/golden.json:1`, case `hinglish-mix` | `Paracetamol` | `Crocin` | the rules path extracts the word dictated; `correct_drugs` no longer rewrites it |
| `tests/golden.json:1`, case `gastritis` | `Ondansetron` | `Emset` | `emset` is a brand of Ondansetron; dose `SOS` unchanged |
| `tests/test_candidates.py:180` | `import ...determinism as D` | `import ...repair as D` | `suggest_candidates` is looked up in `repair.py` now; assertions stay |

Unchanged on purpose, re-read and run: `tests/test_determinism.py:51-58` and `:73` (generics, aliases, `_alias_map()["crocin"]`), golden `cough-cold`, `tests/test_hints.py`, `tests/test_correction*.py`, the bench tests (none uses a brand).

## File Structure

New `core/repair.py` (moved code), `core/surface.py` (pure maps), `tests/test_brand_as_dictated.py` (built per task). Changed: `core/determinism.py` (482 -> 418 after Task 1 -> 452 at the end), `core/correction.py`, `core/ops.py`, `core/fallback.py`, `api/format.py:44`, `tests/golden.json`, `tests/test_candidates.py`.

### Task 1: Free room in determinism.py (pure move to core/repair.py)

**Files:** Create `doctor_dictation/core/repair.py`, `tests/test_brand_as_dictated.py`; modify `core/determinism.py`, `tests/test_candidates.py:180`.

**Interfaces:** Produces `doctor_dictation.core.repair` with every moved name (`build_repair_message`, `loop_should_continue`, `open_issues`, `MAX_CANDIDATE_ROWS`, `_UNKNOWN_ISSUE_RE`, and `RX_VERIFIED`, `UNKNOWN_MEDICINE_TEXT`, `FORMAT_LLM_CAP`, which the moved code needs and which cannot be imported back from `determinism` at top level). `determinism` re-exports all of them, so `api/format.py:18-30` and `tests/test_determinism.py:21-32` are untouched. `repair.py` imports only `candidates` (which imports `determinism` lazily, `candidates.py:65`), so there is no cycle in either import order.
- [ ] **Step 1: Write the failing tests**
```python
"""I1-b: a dictated brand stays as dictated; the generic is kept for checks (offline)."""
import subprocess
import sys

import pytest

import doctor_dictation.core.determinism as D
import doctor_dictation.core.repair as R


# ---- Task 1: pure move ----
def test_old_import_paths_still_work():
    for n in ("build_repair_message", "loop_should_continue", "open_issues", "MAX_CANDIDATE_ROWS",
              "_UNKNOWN_ISSUE_RE", "UNKNOWN_MEDICINE_TEXT", "FORMAT_LLM_CAP", "RX_VERIFIED"):
        assert getattr(D, n) is getattr(R, n), n
    assert D.build_repair_message.__module__ == "doctor_dictation.core.repair"


@pytest.mark.parametrize("first", ["repair", "determinism"])
def test_no_circular_import_either_order(first):
    other = "determinism" if first == "repair" else "repair"
    code = f"import doctor_dictation.core.{first}, doctor_dictation.core.{other}"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
```
- [ ] **Step 2: Run them.** `DB_PATH=$(mktemp -u) .venv/bin/python -m pytest tests/test_brand_as_dictated.py -q` Expected: FAIL, `ModuleNotFoundError: No module named 'doctor_dictation.core.repair'`.
- [ ] **Step 3: Do the move.** Save as `/tmp/move_to_repair.py` and run `python3 /tmp/move_to_repair.py` from the repo root. It cuts `MAX_CANDIDATE_ROWS ... open_issues` (lines 304-362 today) verbatim, asserts every anchor, and edits the one test whose patch target moved.

```python
"""I1-b Task 1: pure move of the repair-loop helpers out of determinism.py. Run from the repo root."""
from pathlib import Path

det = Path("doctor_dictation/core/determinism.py")
src = det.read_text(encoding="utf-8")
start, end = src.index("MAX_CANDIDATE_ROWS = 5"), src.index("def _name_in_transcript")
moved = src[start:end].rstrip("\n") + "\n"          # lines 304-362 today, verbatim
src = src[:start] + src[end:]
consts = ""
for old in (                                         # the three constants the moved code needs move too
    'RX_VERIFIED = "verified"\n',
    '# Wording of the unknown-medicine issue. build_repair_message recognises those\n'
    '# issues by this text, so ground_rx and the message builder share one constant.\n'
    'UNKNOWN_MEDICINE_TEXT = "not in medicine list"\n\n',
    '# Max LLM calls per /api/format request (extract + up to 2 repairs).\nFORMAT_LLM_CAP = 3\n\n',
):
    assert src.count(old) == 1, old
    src, consts = src.replace(old, ""), consts + old + ("\n" if old.startswith("RX_") else "")
for old, new in (
    ("from .candidates import suggest_candidates\n", ""),
    ("from pathlib import Path\n\n", """from pathlib import Path

from .repair import (  # noqa: F401  (api/format.py and tests import these from here)
    FORMAT_LLM_CAP, MAX_CANDIDATE_ROWS, RX_VERIFIED, UNKNOWN_MEDICINE_TEXT, _UNKNOWN_ISSUE_RE,
    build_repair_message, loop_should_continue, open_issues,
)
"""),
):
    assert src.count(old) == 1, old
    src = src.replace(old, new)
det.write_text(src, encoding="utf-8")
Path("doctor_dictation/core/repair.py").write_text(
    '"""Repair-loop helpers moved out of determinism.py (re-exported there; no behaviour change).\n'
    'The three constants live here because determinism imports this module (importing back is a cycle)."""\n'
    "import re\n\nfrom .candidates import suggest_candidates\n\n" + consts + moved, encoding="utf-8")
t = Path("tests/test_candidates.py")                 # the one patch target that moved; assertions stay
s = t.read_text(encoding="utf-8")
old = "    import doctor_dictation.core.determinism as D\n    calls = []"
assert s.count(old) == 1
t.write_text(s.replace(old, "    import doctor_dictation.core.repair as D\n    calls = []"), encoding="utf-8")
```
- [ ] **Step 4: Run the suite.** `DB_PATH=$(mktemp -u) .venv/bin/python -m pytest tests/ -q` Expected: all pass (N + 3). `wc -l doctor_dictation/core/determinism.py` prints `418`, `repair.py` prints `72`. `.venv/bin/python -c "import doctor_dictation.core.repair"` and the same with `determinism` both exit 0. Leave uncommitted.

### Task 2: Surface forms in correct_drugs

**Files:** Create `doctor_dictation/core/surface.py`; modify `core/determinism.py`, `tests/golden.json`; test `tests/test_brand_as_dictated.py`.

**Interfaces:** Produces `surface_map(entries, amap) -> dict`, `ambiguous_names(entries) -> {name: (generic, ...)}` and in `determinism.py` `_maps() -> (surface map, ambiguous names)`, cached per loaded lexicon list (as `candidates.py:68` does; `tests/test_determinism.py:61` swaps `_lexicon_cache`, which rebuilds it).

Measured on the unmodified code: the multiword pass (`:130-156`) rewrote `Alpha D3` and `Milk of Magnesia`; the split pass (`:158-173`, through `nospace`) turned `zy loric` into `Allopurinol`; the exact pass (`:176-181`) rewrote `Zyloric` and `crocin`; the fuzzy pass (`:182-184`) turned `zylorik` into `Allopurinol`. All four write `amap[...]`, so binding `amap` to the surface map changes them together. Two more edits: `-` phrases join the multiword and mask sets, and a second `_mask` after the split pass protects a brand the split just wrote (without it `neo mercazole` came out `Neo-Omeprazole`).
- [ ] **Step 1: Write the failing tests** (append):
```python


# ---- Task 2: surface forms in correct_drugs ----
from doctor_dictation.core.determinism import correct_drugs
from doctor_dictation.core.surface import ambiguous_names, surface_map

COMBI = [  # one brand, two generics (a combination product)
    {"canonical": "Paracetamol", "aliases": ["paracetamol"], "brands": ["Combiflam"], "strengths": ["500 mg"]},
    {"canonical": "Ibuprofen", "aliases": ["ibuprofen"], "brands": ["Combiflam"], "strengths": ["400 mg"]},
]
# Lexicon names correct_drugs never rewrote correctly (measured before this plan, still unfixed).
KNOWN_UNFIXED = {"artemether+lumefantrine", "coenzymeq10", "coq10", "imipenem+cilastatin",
                 "iron sucrose injection", "levodopa+carbidopa", "piperacillin+tazobactam",
                 "sacubitril+valsartan"}


@pytest.mark.parametrize("text,want", [
    ("crocin twice daily", "Crocin twice daily"),              # brand spelling, not Paracetamol
    ("Neo-Mercazole 5 mg", "Neo-Mercazole 5 mg"),              # hyphenated brand
    ("tablet emset 4 mg", "tablet Emset 4 mg"),                # brand that is also an alias
    ("tab zylorik 100", "tab Zyloric 100"),                    # misspelled brand: fixed, still a brand
    ("zy loric 100", "Zyloric 100"),                           # split brand
    ("neo mercazole 5 mg", "Neo-Mercazole 5 mg"),
    ("tablet tam sulosin 0.4 mg", "tablet Tamsulosin 0.4 mg"),  # generics still normalise
    ("have paracetmol twice a day", "have Paracetamol twice a day"),
    ("tablet azithro 500 mg", "tablet Azithromycin 500 mg"),
    ("syrup Potassium Magnesium Citrate 15 ml and tab Zyloric 100 and Co-Amoxiclav 625",
     "syrup Potassium Magnesium Citrate 15 ml and tab Zyloric 100 and Co-Amoxiclav 625"),
])
def test_correct_drugs_brand_as_dictated_generic_normalised(text, want):
    assert correct_drugs(text) == want


def test_every_lexicon_name_round_trips():
    smap, _amb = D._maps()
    bad = {k for k, v in smap.items()
           if correct_drugs(k) != v and not (len(k) < 5 and correct_drugs(k) == k)}
    assert bad <= KNOWN_UNFIXED, sorted(bad - KNOWN_UNFIXED)


def test_lookups_still_return_the_generic():
    assert D._alias_map()["zyloric"] == "Allopurinol"
    assert D._canonical_lookup("Zyloric") == "Allopurinol"
    assert D._canonical_lookup("zylorik") == "Allopurinol"


def test_surface_map_unit():
    entries = [{"canonical": "Atenolol", "aliases": ["atenolol", "tenormin"], "brands": ["Tenormin"]}]
    assert surface_map(entries, {"atenolol": "Atenolol", "tenormin": "Atenolol"}) == \
        {"atenolol": "Atenolol", "tenormin": "Tenormin"}
    assert ambiguous_names(COMBI) == {"combiflam": ("Ibuprofen", "Paracetamol")}
    assert "combiflam" not in surface_map(COMBI, {"combiflam": "Ibuprofen"})
```
- [ ] **Step 2: Run them.** Same command. Expected: FAIL at import, `ModuleNotFoundError: No module named 'doctor_dictation.core.surface'`.
- [ ] **Step 3: Create `doctor_dictation/core/surface.py`**
```python
"""Surface forms: what `correct_drugs` writes for a lexicon name. Pure; determinism imports this.

A generic or a misspelling is written as the canonical generic; a brand in its own spelling.
`_alias_map` still gives the generic for every check. Names two generics claim are left out.
"""


def _clean(text) -> str:
    return " ".join(str(text or "").split())


def ambiguous_names(entries) -> dict:
    """lower-case name -> sorted tuple of the generics that claim it (two or more)."""
    seen: dict = {}
    for e in entries:
        canon = _clean(e.get("canonical"))
        for a in [canon, *e.get("aliases", []), *e.get("brands", [])] if canon else []:
            if _clean(a):
                seen.setdefault(_clean(a).lower(), set()).add(canon)
    return {k: tuple(sorted(v)) for k, v in seen.items() if len(v) > 1}


def surface_map(entries, amap: dict) -> dict:
    """alias_lower -> text to write; a brand maps to its own spelling when `amap` agrees on its generic."""
    out = dict(amap)
    for e in entries:
        canon = _clean(e.get("canonical"))
        for b in e.get("brands", []):
            key = _clean(b).lower()
            if key and amap.get(key) == canon and key != canon.lower():
                out[key] = _clean(b)
    for key in ambiguous_names(entries):
        out.pop(key, None)
    return out
```
- [ ] **Step 4: Edit `core/determinism.py`**, in order:
In `doctor_dictation/core/determinism.py` (imports, after the `from .repair import (...)` block), insert after `)`:
```python
from .surface import ambiguous_names, surface_map
```
In `doctor_dictation/core/determinism.py` (after `_alias_map`), insert before `def normalize_numbers(text: str) -> str:`:
```python
_maps_cache = (None, None, None)  # (lexicon list, surface map, ambiguous names)


def _maps():
    """(surface map, ambiguous names), cached per loaded lexicon list."""
    global _maps_cache
    lex = load_lexicon()
    if _maps_cache[0] is not lex:
        _maps_cache = (lex, surface_map(lex, _alias_map()), ambiguous_names(lex))
    return _maps_cache[1], _maps_cache[2]
```
In `doctor_dictation/core/determinism.py` (`correct_drugs`, first lines) replace `amap = _alias_map()` with `amap, _ = _maps()  # alias -> text to write (generic, or the brand as spelled)`.
In `doctor_dictation/core/determinism.py` (`correct_drugs`, inside `_mask`) replace `sorted({c for c in amap.values() if " " in c},` with `sorted({c for c in amap.values() if " " in c or "-" in c},`.
In `doctor_dictation/core/determinism.py` (`correct_drugs`, the multiword loop) replace `for alias in sorted((a for a in amap if " " in a), key=len, reverse=True):` with `for alias in sorted((a for a in amap if " " in a or "-" in a), key=len, reverse=True):`.
In `doctor_dictation/core/determinism.py` (`correct_drugs`, between the split loop and step 2), insert after `canon, out, count=1, flags=re.I)`:
```python
    out = _mask(out)  # a hyphenated or spaced brand written by the split must survive pass 2
```
- [ ] **Step 5: Run the new tests.** Expected: 13 new tests pass (before: e.g. `assert 'Paracetamol twice daily' == 'Crocin twice daily'`).
- [ ] **Step 6: Update the two golden cases.** The suite now fails `test_golden_expected_fields` (`missing Paracetamol`, then `missing Ondansetron`). `tests/golden.json` is one line, so use exact-string replacement: replace `{"dose": "1-0-1", "name": "Paracetamol"}], "transcript": "bukhar` with `{"dose": "1-0-1", "name": "Crocin"}], "transcript": "bukhar`, and `{"dose": "SOS", "name": "Ondansetron"}], "transcript": "gastritis` with `{"dose": "SOS", "name": "Emset"}], "transcript": "gastritis`.
- [ ] **Step 7: Run the suite.** Expected: all pass (N + 16); `determinism.py` is `432` lines. Leave uncommitted.

### Task 3: The `generic` field, ambiguous brands, preserve, ops, rules path

**Files:** Modify `core/determinism.py`, `core/correction.py`, `core/ops.py`, `core/fallback.py`; test `tests/test_brand_as_dictated.py`.

**Interfaces:** Produces row field `generic` (contract 4.1: set when `lexicon_match` differs from `name` case-insensitively, else `""`; a misspelled generic also fills it, which is harmless), `_generic_of(name, match)`, `_ambiguous_for(low)`, and `correction.DERIVED_ROW_FIELDS = ("generic",)`, which plan I1-a extends.

`preserve_untouched_rx_status` (`correction.py:247`) must restore it: `persistence.py:200-206` re-validates a saved form with an empty transcript, then calls preserve, and a status-less prior row must not be stamped (`tests/test_correction_ops.py:109`). So a derived field follows the status: restored when the prior row had one (`""` when that row lacks the field, never the freshly derived value), removed when not. `ops._regrounded` (`ops.py:77`) drops it too, or a renamed row would keep the old generic.
- [ ] **Step 1: Write the failing tests** (append):
```python


# ---- Task 3: generic field, ambiguous brands, preserve, ops, rules path ----
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import ground_rx, normalize_transcript, validate_structured
from doctor_dictation.core.fallback import fallback_format
from doctor_dictation.core.ops import apply_ops
from test_determinism import _rx, _stub_llm


def _row(name, strength="", transcript=""):
    rows, _w = validate_structured({"rx": [_rx(name, strength=strength)]}, transcript)
    return rows["rx"][0]


def test_brand_row_keeps_brand_and_carries_generic():
    row = _row("Zyloric", "100 mg", "tab zyloric 100 mg once daily")
    assert (row["name"], row["status"]) == ("Zyloric", "verified")
    assert (row["lexicon_match"], row["generic"]) == ("Allopurinol", "Allopurinol")
    assert _row("Allopurinol", "100 mg", "allopurinol 100 mg")["generic"] == ""
    assert _row("paracetamol", "", "paracetamol")["generic"] == ""            # case only
    assert _row("Medalpha")["generic"] == ""
    rows, _issues = ground_rx([{"name": "Zyloric"}, {"name": ""}], "zyloric")
    assert [r["generic"] for r in rows] == ["Allopurinol", ""]
    assert _row("Zyloric", "77 mg", "zyloric 77 mg")["status"] == "unverified-strength"   # checked via the generic


def test_a_brand_two_generics_claim_is_not_guessed(monkeypatch):
    monkeypatch.setattr(D, "_lexicon_cache", COMBI)
    assert correct_drugs("tab combiflam 500") == "tab combiflam 500"
    for typed in ("Combiflam", "Combiflm"):                                   # exact and near spelling
        row = _row(typed, "", f"tab {typed.lower()} twice daily")
        assert (row["status"], row["lexicon_match"], row["generic"]) == ("unverified-name", "", "")
    _rows, issues = ground_rx([{"name": "Combiflam"}], "combiflam")
    assert "Ibuprofen, Paracetamol" in issues[0]
    assert _row("Paracetamol", "500 mg", "paracetamol 500 mg")["status"] == "verified"


def test_preserve_restores_generic_with_the_status():
    prior = {"name": "Zyloric", "status": "verified", "lexicon_match": "Allopurinol",
             "generic": "Allopurinol", "instructions": ""}
    cur = {"rx": [prior, {"name": "Dolo", "instructions": ""}]}          # Dolo: no status at all
    fresh = {"status": "x", "lexicon_match": "x", "instructions": "", "generic": "STALE"}
    rows = preserve_untouched_rx_status(cur, {}, {"rx": [dict(fresh, name="Zyloric"),
                                                         dict(fresh, name="Dolo")]})["rx"]
    assert rows[0]["generic"] == "Allopurinol"
    assert "generic" not in rows[1] and "status" not in rows[1]


def test_replace_op_drops_the_old_generic():
    cur = {"rx": [{"name": "Zyloric", "status": "verified", "lexicon_match": "Allopurinol",
                   "generic": "Allopurinol", "instructions": ""}]}
    new, _rest, _notes, _t = apply_ops(cur, {"replace": {"rx": [{"from": "Zyloric", "to": "Febuxostat"}]}})
    assert "generic" not in new["rx"][0] and "status" not in new["rx"][0]


def test_rules_path_keeps_a_brand_dictated_without_a_strength():
    rows = fallback_format(normalize_transcript("fever have calpol twice a day"))["rx"]
    assert [(r["name"], r["dose"]) for r in rows] == [("Calpol", "1-0-1")]
```
- [ ] **Step 2: Run them.** Expected: FAIL: `KeyError: 'generic'` (rows have no such field yet) and assertion errors in the preserve, ops and rules-path tests.
- [ ] **Step 3: Edit `core/determinism.py`** (ambiguity guard, `generic` in `ground_rx` and `validate_structured`; the last-but-one edit makes the `unverified-name` warning quote the real issue text):
In `doctor_dictation/core/determinism.py` (module level), insert before `def _norm_strength(s: str) -> str:`:
```python
def _ambiguous_for(low: str) -> tuple:
    """Generics a dictated name could mean when two claim it (exact or a near spelling); else ()."""
    amb = _maps()[1]
    if low in amb:
        return amb[low]
    near = difflib.get_close_matches(low, sorted(k for k in amb if len(k) >= 5), n=1, cutoff=0.84)
    return amb[near[0]] if near and low not in _alias_map() else ()


def _generic_of(name: str, match: str) -> str:
    """The generic to show on screen when the name is a brand (never printed); else ""."""
    return match if match and match.lower() != (name or "").strip().lower() else ""
```
In `doctor_dictation/core/determinism.py` (`_ground_row`), insert after `try:`:
```python
        amb = _ambiguous_for(name.strip().lower())
        if amb:  # a name two generics claim (a combination brand): never guess
            return (RX_UNVERIFIED_NAME, "",
                    f"'{name}': matches more than one medicine ({', '.join(amb)})")
```
In `doctor_dictation/core/determinism.py` (`ground_rx`, empty-name branch), insert after `row["lexicon_match"] = ""`:
```python
            row["generic"] = ""
```
In `doctor_dictation/core/determinism.py` (`ground_rx`), insert after `row["lexicon_match"] = match`:
```python
        row["generic"] = _generic_of(name, match)
```
In `doctor_dictation/core/determinism.py` (`validate_structured`) replace `warnings.append(f"rx[{i}] '{name}': not clearly dictated -> flagged unverified")` with `warnings.append(f"rx[{i}] {issue} -> flagged unverified")`.
In `doctor_dictation/core/determinism.py` (`validate_structured`, the row dict) replace `"lexicon_match": match,` with `"lexicon_match": match, "generic": _generic_of(name, match),`.
- [ ] **Step 4: Edit `core/correction.py` and `core/ops.py`:**

In `doctor_dictation/core/correction.py` (module level), insert before `GROUNDING_MARKERS = (`:
```python
# Row fields validate_structured derives from the name and the grounding (screen only).
DERIVED_ROW_FIELDS = ("generic",)
```
In `doctor_dictation/core/correction.py` (`preserve_untouched_rx_status`, loop end), insert after `row.pop(field, None)`:
```python
        for field in DERIVED_ROW_FIELDS:  # follow the restored status; absent when the prior row had none
            if "status" in prev:
                row[field] = prev.get(field, "")
            else:
                row.pop(field, None)
```
In `doctor_dictation/core/ops.py` (the imports) replace `from .correction import GROUNDING_MARKERS, LIST_FIELDS,` with `from .correction import DERIVED_ROW_FIELDS, GROUNDING_MARKERS, LIST_FIELDS,`.
In `doctor_dictation/core/ops.py` (`_regrounded`) replace `k not in ("status", "lexicon_match")` with `k not in ("status", "lexicon_match", *DERIVED_ROW_FIELDS)`.
- [ ] **Step 5: Edit `core/fallback.py`** (it may import `determinism`; `determinism` does not import it):
In `doctor_dictation/core/fallback.py` (module level), insert after `import re`:
```python

from .determinism import load_lexicon

# The no-strength branch also knows the brands of these generics: a dictated brand is no longer
# rewritten to its generic before this runs.
_NO_STRENGTH = ("paracetamol", "ibuprofen", "aspirin", "azithromycin", "amoxicillin", "omeprazole", "cetirizine")


def _no_strength_names() -> str:
    names = set(_NO_STRENGTH) | {"crocin", "dolo"}
    names |= {b.lower() for e in load_lexicon() if str(e.get("canonical", "")).lower() in _NO_STRENGTH
              for b in e.get("brands", [])}
    return "|".join(re.escape(n) for n in sorted(names, key=lambda n: (-len(n), n)))
```
In `doctor_dictation/core/fallback.py` (`fallback_format`, no-strength branch), replace:
```python
        m2 = re.search(r"\b(paracetamol|ibuprofen|crocin|dolo|aspirin|azithromycin|amoxicillin|omeprazole|cetirizine)\b([^.]{0,60})", t)
```
with:
```python
        m2 = re.search(rf"\b({_no_strength_names()})\b([^.]{{0,60}})", t)
```
- [ ] **Step 6: Run the suite.** Expected: all pass (N + 21); `determinism.py` is `452` lines. Leave uncommitted.

### Task 4: Tell the model, prove it end to end

**Files:** Modify `api/format.py:44`; test `tests/test_brand_as_dictated.py`.

**Interfaces:** Consumes `_stub_llm`, `_rx` (`tests/test_determinism.py`). The model sees the normalized transcript, which now carries the brand. If it "helps" by writing the generic, `_ground_row` finds neither name in the transcript and flags `unverified-name` (one tap); the prompt asks it not to.
- [ ] **Step 1: Write the tests** (append):
```python


# ---- Task 4: end to end ----
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core.determinism import _FORMAT_CACHE


def test_format_keeps_the_brand_in_prompt_and_row(monkeypatch):
    _FORMAT_CACHE.clear()
    calls = _stub_llm(monkeypatch, [{"rx": [_rx("Zyloric", strength="100 mg")]}])
    r = TestClient(M.app).post("/api/format", json={"transcript": "tab zylorik 100 mg once daily"})
    assert r.status_code == 200, r.text
    j = r.json()
    prompt = calls["messages"][0][-1]["content"]
    assert "Zyloric" in prompt and "Allopurinol" not in prompt
    row = j["structured"]["rx"][0]
    assert (row["name"], row["status"], row["lexicon_match"], row["generic"]) == \
        ("Zyloric", "verified", "Allopurinol", "Allopurinol")
    assert "exactly as dictated, including brand names" in calls["messages"][0][0]["content"]  # system prompt


def test_a_model_that_swaps_the_brand_for_the_generic_is_flagged_not_trusted():
    row = _row("Allopurinol", "100 mg", "tab Zyloric 100 mg once daily")
    assert (row["status"], row["lexicon_match"]) == ("unverified-name", "Allopurinol")
```
- [ ] **Step 2: Run them.** Expected: 1 FAIL (`test_format_keeps_the_brand_in_prompt_and_row`, on the prompt rule); the swap test already passes.
- [ ] **Step 3: Edit the prompt:**

In `doctor_dictation/api/format.py` (rule 4 of `SYSTEM_PROMPT`), replace:
```python
Never invent strengths, durations, or drugs. If a field
```
with:
```python
Never invent strengths, durations, or drugs. Write each medicine name exactly as dictated, including brand names; never replace a brand with its generic. If a field
```
- [ ] **Step 4: Run the suite.** Expected: N + 23 passed (967 if N is 944), 1 skipped; `determinism.py` is `452` lines.
- [ ] **Step 5: Leave uncommitted.** Changed files: `core/repair.py` (new), `core/surface.py` (new), `core/determinism.py`, `core/correction.py`, `core/ops.py`, `core/fallback.py`, `api/format.py`, `tests/golden.json`, `tests/test_candidates.py`, `tests/test_brand_as_dictated.py` (new).

## Left out, and disagreements

- `transcript_sha256` changes for transcripts holding a brand of 5+ letters; it is a cache key and a document reference, nothing compares old and new.
- Not done: the UI line "generic: X" (plan I1-e; `readRx`, `frontend/app.js:610`, does not send `generic` back, the server recomputes it). The PDF prints `name` (`pdf/sheet.py:92`), now the brand. Brand-like aliases (`alprax`, `panto`, `azithro`) are still aliases, so they normalise to the generic; moving them to `brands` is a data change for a pharmacist.
- Disagreement with the index: none (fact 4 and contract 4.1 are implemented as written). Self-review: spec 2c items all map to Tasks 2-4; no placeholders; names match across tasks.
