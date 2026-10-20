# PQ-a: Generic only on an exact match + combination-suffix detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A row shows and prints a generic only when its name is an exact brand/alias/generic of the drug list; a known brand plus a combination suffix ("Zerodol-P") gets a blank generic, a visible "Add generic" mark, and can be learned by the clinic.

**Architecture:** Two pure lookups: `determinism._exact_lookup` (exact, separator-insensitive) and `combo.combo_suffix` (brand + suffix). One helper, `surface.generic_fields`, gives every grounding path (`rowcheck`, `ground_rx`, correction recompute, save) the same `generic`, `generic_source` and `combo_base`. A combination row skips the fuzzy lexicon match in `_ground_row`, so it grounds through the clinic list or as `unknown-medicine` with no repair-loop issue. The page shows a screen-only "Add generic" tag from `combo_base`; plan g builds the editing.

**Tech Stack:** Python 3.12 stdlib (`re`, `difflib`), FastAPI routes unchanged, vanilla JS (`frontend/rxstate.js`, `frontend/rxview.js`), pytest + node fake-DOM tests.

**Spec:** `docs/superpowers/plans/2026-10-19-prescription-quality-brainstorm.md` (section 1, options A and B; "Decisions made", decision 1). Shared names: `docs/superpowers/plans/2026-10-19-pq-00-index.md`.

**Owner answers 2026-10-19:** Q1 a confirmed misspelling such as "Crocinn" being learned by the clinic is OK; the clinic-list learning threshold still applies (a name goes on the clinic list only after `formulary.THRESHOLD` = 2 confirmed saves, `core/formulary.py:18`), so one save never learns it. Q2 a learned combination name grounds `verified` (source `clinic`): yes, as Task 4 builds. Q3 the suffix list in Global Constraints is approved as proposed. No task changes beyond the Task 4 threshold test.

## Global Constraints

- Generic: "Show a generic only on an exact match ('100 % confident'); otherwise leave it blank" (decision 1).
- "A fuzzy match may still suggest the name, but the generic stays blank" (option A): `lexicon_match` keeps the fuzzy canonical for name suggestions and dose checks; `generic` is `""`.
- "Name = known brand + suffix (-P, -D, -GP, -AV, -CV, -XT, -LC, -AM, -H, Plus, Forte, MR, SR…) → unknown combination: blank generic, 'Add generic' prompt" (option B).
- "`formulary.learnable` must use exact matching too; today a near match ('Zerodol-P' ≈ 'zerodol') blocks learning" (decision 1).
- Contract names, verbatim: `doctor_dictation/core/determinism.py: _exact_lookup(name: str) -> str`; `doctor_dictation/core/combo.py: combo_suffix(name: str) -> tuple[str, str] | None`; row field `generic_source` values `""` and `"lexicon"` (plan g adds `"doctor"`).
- `_canonical_lookup` (fuzzy, 0.84) stays, for name suggestions and grounding of non-combination names only.
- `generic_hidden` (`core/surface.py:67-80`) keeps working unchanged (no generic, no dose check for the 7 listed brands).
- Suffix list (owner-approved 2026-10-19, casefolded): `a, p, d, sp, th, dsr, gp, pg, av, cv, xt, lc, am, h, m, t, mt, dm, ls, plus, forte, mr, sr, er, xr, cr, od, trio`. ("A" is needed for the spec's own probe row "Amlong-A".)
- Files stay under 500 lines (`tests/test_file_sizes.py`); `correction.py` is at 443, `determinism.py` at 410.
- Tests: `.venv/bin/python -m pytest` (the autouse temp `DB_PATH` in `tests/conftest.py` protects the dev DB). Bump `?v=` on every changed static file.
- No commit without the owner's word: each "Commit" step means "ask, then commit".

## Review Focus

1. **A known combination written with a different separator** ("Moxikind CV" when the list has "Moxikind-CV" → Co-Amoxiclav) must keep its generic and must not be flagged as a combination. Test: Task 1 `test_exact_lookup_ignores_space_versus_hyphen`.
2. **A strength glued to the suffix** ("Glycomet-GP 1", "Glycomet GP2") is still a combination of Glycomet. Test: Task 1 `test_combo_suffix_detects_the_spec_probe_and_a_trailing_strength`.
3. **A generic name plus a release suffix** ("Metformin SR") is not called a combination of a brand (its base is a canonical name), and its generic is still blank (not exact). Test: Task 1 `test_combo_suffix_ignores_generic_bases_short_tails_and_unknown_suffixes` + Task 2 `test_fuzzy_match_keeps_the_match_but_no_generic`.
4. **Shipped brands that look like brand + suffix** (Feronia-XT, Adzolex-Plus, Retino-A, Taxim-O, Moxikind-CV) are exact names and never flagged. Test: Task 1 `test_no_shipped_brand_or_alias_is_flagged_as_a_combination`.
5. **The repair loop and the inline "Did you mean" must not turn "Zerodol-P" back into "Zerodol"**: a combination row raises no repair issue and gets no inline suggestion, also after a spoken correction restores it. Tests: Task 2 `test_combination_row_raises_no_repair_issue_and_no_did_you_mean`, Task 3 `test_untouched_combination_row_keeps_its_blank_generic_after_a_correction`.

## Existing tests affected

A probe run (generic made exact-only, combination rows grounded as unknown, `learnable` exact) passed the whole suite: 2066 passed, 1 skipped. Only one test changes, because it compares a full dict:

| Test | Change |
|---|---|
| `tests/test_frontend_rxrow.py:74` (`test_a_hand_edit_drops_stale_reasons_and_a_name_edit_drops_the_old_drugs_data`) | Expected `afterEdit(..., "name")` dict gains `"generic_source": ""` and `"combo_base": ""` (Task 5). |

Still passing but worth a glance during review: `tests/test_rowcheck.py:11-17` (field subset), `tests/test_lasa.py:162` (status-less rows carry no derived fields; the two new fields are derived too), `tests/test_generic_consistency.py` (exact names: Cetirizine, Crocin, Omeprazole, Amlo).

## Status effects (decided here)

| Row | `status` | `lexicon_match` | `generic` | `generic_source` | `combo_base` |
|---|---|---|---|---|---|
| "Crocin" (exact brand) | as today | Paracetamol | Paracetamol | `lexicon` | `""` |
| "Moxikind CV" (exact, other separator) | as today | Co-Amoxiclav | Co-Amoxiclav | `lexicon` | `""` |
| "Crocinn" (fuzzy only) | as today (`verified` when dictated) | Paracetamol | `""` | `""` | `""` |
| "Zerodol-P", not on clinic list | `unknown-medicine`, no repair issue, no Did you mean | `""` | `""` | `""` | `Zerodol` |
| "Zerodol-P", on clinic list | clinic rules; the look-alike twin equal to the base's generic does not count (Task 4) | `""` | `""` | `""` | `Zerodol` |
| "Feronia-XT" (`generic_hidden`) | as today | Ferrous Ascorbate | `""` | `""` | `""` |

---

### Task 0: Preflight

- [ ] **Step 1: Re-read the files this plan edits** (`core/determinism.py`, `core/surface.py`, `core/rowcheck.py`, `core/correction.py`, `core/formulary.py`, `frontend/rxstate.js`, `frontend/rxview.js`, `frontend/index.html`). Line numbers below are from `main` at 9bf466e.
- [ ] **Step 2: Baseline.** Run: `.venv/bin/python -m pytest -q`. Expected: `2066 passed, 1 skipped`.

### Task 1: The two lookups (`_exact_lookup`, `combo_suffix`)

**Files:**
- Modify: `doctor_dictation/core/determinism.py` (add after `_canonical_lookup`, `:241-255`)
- Create: `doctor_dictation/core/combo.py`
- Test: `tests/test_generic_exact.py` (new)

**Interfaces:**
- Consumes: `determinism._alias_map()` (`:89-114`), `determinism.load_lexicon()` (`:60-71`).
- Produces:
  - `determinism._exact_lookup(name: str) -> str` — the canonical when the name, whitespace collapsed, trailing "." stripped, lower-cased, is a key of `_alias_map()`; else when it equals a key after both sides map `[\s-]+` to one space; else `""`. The separator map is cached per loaded lexicon list (the `is` check `_maps()` uses at `:120-126`), so a plan-f overlay lexicon rebuilds it.
  - `combo.COMBO_SUFFIXES: frozenset[str]` — the list in Global Constraints.
  - `combo.combo_suffix(name: str) -> tuple[str, str] | None` — `(base as written, suffix as written)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_generic_exact.py`

```python
from doctor_dictation.core import determinism as D
from doctor_dictation.core.combo import COMBO_SUFFIXES, combo_suffix

def test_exact_lookup_matches_brand_alias_and_generic_only():
    assert D._exact_lookup("Crocin") == "Paracetamol" and D._exact_lookup("  crocin. ") == "Paracetamol"
    assert D._exact_lookup("Amlo") == "Amlodipine" and D._exact_lookup("Cetirizine") == "Cetirizine"
    assert D._exact_lookup("Crocinn") == "" and D._exact_lookup("Zerodol-P") == "" and D._exact_lookup("") == ""
    assert D._canonical_lookup("Zerodol-P") == "Aceclofenac"          # fuzzy stays, for suggestions

def test_exact_lookup_ignores_space_versus_hyphen():
    assert D._exact_lookup("Moxikind CV") == D._exact_lookup("Moxikind-CV") == "Co-Amoxiclav"
    assert D._exact_lookup("Taxim O") == "Cefixime"

def test_combo_suffix_detects_the_spec_probe_and_a_trailing_strength():
    assert combo_suffix("Zerodol-P") == ("Zerodol", "P") and combo_suffix("zerodol p") == ("zerodol", "p")
    assert combo_suffix("Pantop-D") == ("Pantop", "D") and combo_suffix("Glycomet-GP") == ("Glycomet", "GP")
    assert combo_suffix("Amlong-A") == ("Amlong", "A") and combo_suffix("Ecosprin-AV") == ("Ecosprin", "AV")
    assert combo_suffix("Glycomet-GP 1") == ("Glycomet", "GP") and combo_suffix("Glycomet GP2") == ("Glycomet", "GP")
    assert combo_suffix("Zerodol Forte") == ("Zerodol", "Forte")

def test_combo_suffix_ignores_generic_bases_short_tails_and_unknown_suffixes():
    for name in ("Metformin SR", "Paracetamol-P", "Zerodol", "Zerodol-Q", "Dolo-650", "Zzqxwv-P", "", "P", "Kidrich-D3"):
        assert combo_suffix(name) is None, name

def test_no_shipped_brand_or_alias_is_flagged_as_a_combination():
    names = [n for e in D.load_lexicon() for n in [*e.get("brands", []), *e.get("aliases", [])]]
    assert [n for n in names if combo_suffix(n)] == []
    assert {"p", "d", "gp", "av", "cv", "xt", "lc", "am", "h", "plus", "forte", "mr", "sr", "a"} <= COMBO_SUFFIXES
```

- [ ] **Step 2: Run to verify they fail.** Run: `.venv/bin/python -m pytest tests/test_generic_exact.py -q`. Expected: FAIL, `ModuleNotFoundError: doctor_dictation.core.combo` / `AttributeError: _exact_lookup`.

- [ ] **Step 3: Implement `_exact_lookup(name: str) -> str` in `core/determinism.py`.** Place it right after `_canonical_lookup`; normalise exactly as the docstring above says.

- [ ] **Step 4: Implement `combo_suffix(name: str) -> tuple[str, str] | None` in new `core/combo.py`.** Pure, stdlib only (`tests/test_core_purity.py`); import `determinism` lazily inside the function (determinism will import `surface`, which imports `combo`). Rule, in order:
  1. Normalise as `_exact_lookup` does; `None` when empty or `_exact_lookup(name)` is non-empty (an exact name always wins).
  2. Match `^(?P<base>.+?)[\s-]+(?P<suffix>[A-Za-z]+)(?:[\s-]*\d+(?:\.\d+)?)?$`; `None` without a match or when `suffix.casefold()` is not in `COMBO_SUFFIXES`.
  3. `None` unless `base.lower()` is a key of `_alias_map()` AND not the canonical name of any entry (a generic plus a suffix is not a brand combination).
  4. Return `(base, suffix)` as written. Cache the canonical-name set per loaded lexicon list (same `is` check).

- [ ] **Step 5: Run to verify they pass.** Run: `.venv/bin/python -m pytest tests/test_generic_exact.py tests/test_core_purity.py -q`. Expected: PASS.

- [ ] **Step 6: Commit** (ask first): `git add doctor_dictation/core/combo.py doctor_dictation/core/determinism.py tests/test_generic_exact.py && git commit -m "PQ-a: exact lookup and combination-suffix detection"`

### Task 2: Generic only on an exact match; combination rows ground as unknown

**Files:**
- Modify: `doctor_dictation/core/surface.py:47-54` (`_generic_of`; add `generic_fields`)
- Modify: `doctor_dictation/core/determinism.py:271-299` (`_ground_row`), `:328` (`ground_rx`)
- Modify: `doctor_dictation/core/rowcheck.py:72` (row dict), `:175-190` (`did_you_mean`)
- Test: `tests/test_generic_exact.py`

**Interfaces:**
- Consumes: Task 1 `_exact_lookup`, `combo_suffix`.
- Produces:
  - `surface._generic_of(name: str, match: str) -> str` — `match` only when `match` is non-empty, `_exact_lookup(name) == match` and not `generic_hidden(name, match)`; else `""`.
  - `surface.generic_fields(name: str, match: str) -> dict` — `{"generic": _generic_of(name, match), "generic_source": "lexicon" if that generic else "", "combo_base": (combo_suffix(name) or ("", ""))[0]}`. Plan g wraps this for `"doctor"`.
  - Row fields on every grounded row (`/api/format`, `/api/v1/correct`, `/api/v1/rx/check-row`, save): `generic`, `generic_source`, `combo_base` (the page's "Add generic" signal: non-empty means "known brand + combination suffix, generic unknown").
  - `_ground_row` for a combination name returns `formulary.ground_clinic(...)` or `(RX_UNKNOWN_MEDICINE, "", None)`; issue `None` keeps it out of the repair loop (`api/format.py:138-153`), like a clinic look-alike (`formulary.py:208-220`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_generic_exact.py`)

```python
from doctor_dictation.core import rowcheck
from doctor_dictation.core.determinism import ground_rx, validate_structured

def _row(name, text=None):
    out, _w = validate_structured({"rx": [{"form": "Tab.", "name": name, "dose": "1-0-1"}]}, text or f"tab {name.lower()}")
    return out["rx"][0]

def test_exact_match_shows_the_generic_with_source_lexicon():
    r = _row("Crocin")
    assert (r["generic"], r["generic_source"], r["combo_base"]) == ("Paracetamol", "lexicon", "")

def test_fuzzy_match_keeps_the_match_but_no_generic():
    r = _row("Crocinn", "tab crocinn")
    assert (r["status"], r["lexicon_match"], r["generic"], r["generic_source"]) == ("verified", "Paracetamol", "", "")
    assert _row("Metformin SR")["generic"] == ""

def test_spec_probe_rows_get_no_generic_and_a_combo_base():
    for name, base in (("Zerodol-P", "Zerodol"), ("Pantop-D", "Pantop"), ("Glycomet-GP", "Glycomet"),
                       ("Amlong-A", "Amlong"), ("Ecosprin-AV", "Ecosprin")):
        r = _row(name)
        assert (r["status"], r["lexicon_match"], r["generic"], r["generic_source"], r["combo_base"]) == \
            ("unknown-medicine", "", "", "", base), name

def test_combination_row_raises_no_repair_issue_and_no_did_you_mean():
    rows, issues = ground_rx([{"name": "Zerodol-P"}], "tab zerodol p")
    assert issues == [] and rows[0]["generic"] == "" and rows[0]["combo_base"] == "Zerodol"
    assert _row("Zerodol-P")["did_you_mean"] == ""
    assert rowcheck.did_you_mean("Zerodol-P", "unknown-medicine") == {"did_you_mean": "", "did_you_mean_generic": ""}

def test_generic_hidden_still_hides_and_a_known_combination_entry_still_prints_in_full():
    assert (_row("Feronia-XT")["generic"], _row("Feronia-XT")["lexicon_match"]) == ("", "Ferrous Ascorbate")
    assert _row("Ultracet")["generic"] == "Tramadol + Paracetamol" and _row("Moxikind CV")["generic"] == "Co-Amoxiclav"
```

- [ ] **Step 2: Run to verify they fail.** Run: `.venv/bin/python -m pytest tests/test_generic_exact.py -q`. Expected: FAIL (`KeyError: 'generic_source'`, Zerodol-P `verified`).

- [ ] **Step 3: Implement `_generic_of` and `generic_fields(name: str, match: str) -> dict` in `core/surface.py`.** Lazy-import `determinism` and `combo` inside the functions (as `generic_hidden` does at `:71`). Update the module and `_generic_of` docstrings: generic only on an exact match.

- [ ] **Step 4: Add the combination branch to `_ground_row` (`determinism.py:276-284`).** After the ambiguity check and before `_canonical_lookup`: when `combo_suffix(name)` is not `None`, return `formulary.ground_clinic(name, transcript_lower, _name_in_transcript) or (RX_UNKNOWN_MEDICINE, "", None)`.

- [ ] **Step 5: Use `generic_fields` at `ground_rx` (`determinism.py:328`, and the empty-name branch `:320` gets `generic_source=""`, `combo_base=""`) and in `rowcheck.ground_with_notes` (`rowcheck.py:72`, replacing `"generic": D._generic_of(name, match)`).**

- [ ] **Step 6: Gate `did_you_mean` (`rowcheck.py:181`).** Return `dict(_NO_DYM)` when `status != D_UNKNOWN` or `combo_suffix(name)` is not `None`. One place covers first authoring and the correction restore (`correction.py:403-405`).

- [ ] **Step 7: Run.** Run: `.venv/bin/python -m pytest tests/test_generic_exact.py tests/test_combination_brands.py tests/test_generic_consistency.py tests/test_did_you_mean.py tests/test_rowcheck.py tests/test_determinism.py -q`. Expected: PASS.

- [ ] **Step 8: Commit** (ask first): `git commit -m "PQ-a: generic only on an exact match; brand + suffix grounds as unknown"`

### Task 3: Correction, save and print keep the same generic

**Files:**
- Modify: `doctor_dictation/core/correction.py:270` (`DERIVED_ROW_FIELDS`), `:276-280` (`_recomputed_generic`), `:283-286` (`_backed`), `:291-297` (`RECOMPUTED_ROW_FIELDS`)
- Test: `tests/test_generic_consistency.py`, `tests/test_combination_brands.py`

**Interfaces:**
- Consumes: Task 2 `generic_fields`, `_generic_of`; Task 1 `combo_suffix`.
- Produces: `DERIVED_ROW_FIELDS` gains `"generic_source"`, `"combo_base"`; `RECOMPUTED_ROW_FIELDS` gains `"generic_source": lambda row: "lexicon" if _recomputed_generic(row) else ""` and `"combo_base": lambda row: (combo_suffix(row.get("name", "")) or ("", ""))[0]`. Plan g changes the `generic_source` entry for `"doctor"` rows.

- [ ] **Step 1: Write the failing tests**

In `tests/test_generic_consistency.py` (reuse the `test_the_generic_survives_correct_and_save` setup: rules path, temp DB, `TestClient(M.app)`):

```python
def test_untouched_combination_row_keeps_its_blank_generic_after_a_correction(tmp_path, monkeypatch):
    # current_form row as readRx sends it: no generic, no combo_base
    row = {"form": "Tab.", "name": "Zerodol-P", "strength": "", "dose": "1-0-1", "timing": "", "duration": "",
           "instructions": "", "status": "unknown-medicine", "lexicon_match": ""}
    out = client.post("/api/v1/correct", json={"transcript": "", "current_form": {"rx": [row]}}).json()["structured"]["rx"][0]
    assert (out["generic"], out["generic_source"], out["combo_base"], out["did_you_mean"]) == ("", "", "Zerodol", "")

def test_a_stale_match_on_a_fuzzy_name_saves_no_generic(tmp_path, monkeypatch):
    # a hand-edited name keeps an old lexicon_match: "Crocinn" with lexicon_match "Paracetamol"
    # POST /api/v1/documents with confirmed_rows [0]; the saved row has generic "" and generic_source ""
    # an exact "Crocin" row in the same save has ("Paracetamol", "lexicon")
```

In `tests/test_combination_brands.py`, next to the hidden-brand PDF test (`:74-80`):

```python
def test_a_brand_plus_suffix_prints_no_generic_line():
    html = build_sheet_html({"patientName": "A", "rx": [_row("Zerodol-P"), _row("Crocinn", text="tab crocinn")]}, {})
    assert "generic:" not in html and "Zerodol-P" in html
```

- [ ] **Step 2: Run to verify they fail.** Run: `.venv/bin/python -m pytest tests/test_generic_consistency.py tests/test_combination_brands.py -q`. Expected: the correction test FAILs (`KeyError: 'combo_base'`); the PDF test already passes once Task 2 is in (it pins Task 2 at the print boundary, `pdf/sheet.py:96-97`, which needs no change).

- [ ] **Step 3: Implement in `core/correction.py`.** Add the two fields to `DERIVED_ROW_FIELDS` and `RECOMPUTED_ROW_FIELDS`. `_recomputed_generic` becomes `_generic_of(name, match)` (the exact check now lives there; keep the docstring's Febuxostat example). `_backed` ignores a fuzzy hit on a combination name: `row.lexicon_match or (combo_suffix(name) is None and _canonical_lookup(name)) or active_layer().get(name)`, so a restored `verified` combination row whose clinic name was removed is regraded (`:396-399`).

- [ ] **Step 4: Run.** Run: `.venv/bin/python -m pytest tests/test_generic_consistency.py tests/test_combination_brands.py tests/test_correction.py tests/test_correction_ops.py tests/test_lasa.py tests/test_same_name_rows.py -q`. Expected: PASS. Check `wc -l doctor_dictation/core/correction.py` stays under 500.

- [ ] **Step 5: Commit** (ask first): `git commit -m "PQ-a: correction and save recompute the exact-only generic"`

### Task 4: The clinic can learn a combination name

**Files:**
- Modify: `doctor_dictation/core/formulary.py:61,69` (`learnable`)
- Modify: `doctor_dictation/core/determinism.py` (the Task 2 combination branch in `_ground_row`)
- Test: `tests/test_formulary.py`, `tests/test_formulary_db.py` (threshold pin, imports `THRESHOLD` from `core.formulary`)

**Interfaces:**
- Consumes: Task 1 `_exact_lookup`, `combo_suffix`; `formulary.ground_clinic`, `formulary._lexicon_twin`, `formulary.LOOKALIKE` (`formulary.py:17, 202-220`).
- Produces: `learnable(...)` skips only names `_exact_lookup` knows. A learned combination name grounds `verified` (source `clinic`) when the only look-alike reason is that it sounds like its own base's generic.
- Unchanged: `learnable` only lists candidates; a candidate reaches the clinic list after `THRESHOLD` (2) confirmed saves (owner Q1). A misspelling such as "Crocinn" is a valid candidate (owner OK).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_formulary.py`)

```python
def test_learnable_uses_exact_matching_so_a_combination_brand_is_learned():
    form = {"rx": [{"name": "Zerodol-P"}, {"name": "Zerodol"}, {"name": "Moxikind CV"}, {"name": "Crocinn"}]}
    assert F.learnable(form, [0, 1, 2, 3]) == [("Zerodol-P", ""), ("Crocinn", "")]

# tests/test_formulary_db.py (owner Q1: the threshold applies to combination names and misspellings alike)
def test_a_combination_or_misspelt_name_goes_live_only_after_the_threshold(conn, docs):
    for name in ("Zerodol-P", "Crocinn"):
        assert count(conn, docs[0], name) == 1 and name not in [r["name"] for r in fdb.list_active(conn)]
        assert count(conn, docs[1], name) == THRESHOLD and name in [r["name"] for r in fdb.list_active(conn)]

def test_a_learned_combination_grounds_as_the_clinics_name_not_as_a_lookalike_of_its_base():
    F.activate(F.ClinicLayer(items=(("Zerodol-P", ""),)))
    try:
        row, _n = rowcheck.ground_with_notes({"name": "Zerodol-P", "dose": "1-0-1"}, "tab zerodol p", "tab zerodol p")
        assert (row["status"], row["source"], row["generic"], row["combo_base"]) == ("verified", "clinic", "", "Zerodol")
        assert "lookalike" not in row
        other, _n = rowcheck.ground_with_notes({"name": "Zerodol-P"}, "", "")
        assert other["status"] == "unverified-name"                 # not dictated: the clinic rule still applies
    finally:
        F.activate(F.ClinicLayer())
```

- [ ] **Step 2: Run to verify they fail.** Run: `.venv/bin/python -m pytest tests/test_formulary.py tests/test_formulary_db.py -q`. Expected: the `test_formulary.py` tests FAIL (`learnable` returns `[]` for Zerodol-P; status `lookalike-check`, since `_lexicon_twin("Zerodol-P")` is "Aceclofenac"). The `test_formulary_db.py` threshold pin already passes (the ledger ignores the name's shape); it guards the owner rule.

- [ ] **Step 3: Implement.** In `learnable`, import and call `_exact_lookup` in place of `_canonical_lookup`; update the docstring ("whose name the lexicon does not know exactly"). In the `_ground_row` combination branch: when `ground_clinic` returns `LOOKALIKE` and `formulary._lexicon_twin(name) == _exact_lookup(base)`, return `(RX_VERIFIED, "", None)` instead.

- [ ] **Step 4: Run.** Run: `.venv/bin/python -m pytest tests/test_formulary.py tests/test_formulary_db.py tests/test_formulary_usage.py tests/test_generic_exact.py -q`. Expected: PASS.

- [ ] **Step 5: Commit** (ask first): `git commit -m "PQ-a: learnable uses exact matching; a learned combination is the clinic's name"`

### Task 5: The page shows "Add generic"

**Files:**
- Modify: `frontend/rxstate.js:15` (`META_KEYS`), `:66` (`reasonFor`, unknown-medicine line), `:102-107` (`afterEdit`)
- Modify: `frontend/rxview.js:50-55` (generic line / tag)
- Modify: `frontend/index.html:258,260` (`rxstate.js?v=7` → `?v=8`, `rxview.js?v=8` → `?v=9`)
- Test: `tests/test_frontend_generic_dom.py`, `tests/test_frontend_rxrow.py:74`

**Interfaces:**
- Consumes: row fields `generic`, `generic_source`, `combo_base` (Task 2).
- Produces: `RxState.metaOf` carries `generic_source` and `combo_base`; a screen-only tag `span.rx-extra.rx-gen-tag.rx-add-gen.no-print` with text `Add generic` directly after the name when `combo_base` is set and `generic` is blank. Plan g turns this tag into the editor's entry point. No CSS change (reuses `.rx-gen-tag`, `rx.css:69`).

- [ ] **Step 1: Write the failing tests**

In `tests/test_frontend_generic_dom.py`:

```python
def test_a_combination_row_shows_a_screen_only_add_generic_tag_and_never_a_generic_line():
    r = _run("""
      const c = mkRow("c1", "unknown-medicine", { name: "Zerodol-P" }, { combo_base: "Zerodol" });
      const k = mkRow("c2", "verified", { name: "Crocin" }, { generic: "Paracetamol", generic_source: "lexicon" });
      const pick = (tr, s) => tr.querySelectorAll(s).map((n) => [n.textContent, n.className]);
      console.log(JSON.stringify({ c: [pick(c, ".rx-gen"), pick(c, ".rx-add-gen")], k: pick(k, ".rx-add-gen"),
        reason: RxView.reasonFor(c) }));""")
    assert r["c"] == [[], [["Add generic", "rx-extra rx-gen-tag rx-add-gen no-print"]]] and r["k"] == []
    assert r["reason"] == '"Zerodol-P" is a combination of Zerodol. Its generic is not in the medicine list.'
```

Also assert `index.html` has `rxstate.js?v=8` and `rxview.js?v=9`.

In `tests/test_frontend_rxrow.py:74`: add `"generic_source": ""` and `"combo_base": ""` to the expected `afterEdit(..., "name")` dict.

- [ ] **Step 2: Run to verify they fail.** Run: `.venv/bin/python -m pytest tests/test_frontend_generic_dom.py tests/test_frontend_rxrow.py -q`. Expected: FAIL (no `.rx-add-gen`; dict mismatch).

- [ ] **Step 3: Implement.** `META_KEYS` gains `"generic_source", "combo_base"`; `afterEdit(meta, "name")` blanks both; `reasonFor` for `unknown-medicine` with a non-empty `combo_base` returns the exact sentence in the test; `renderRow` appends the tag (after the name span, like the generic tag at `rxview.js:53-54`) with `title` "A combination of <base>: add its generic" (textContent only, never markup). Bump both `?v=` pins.

- [ ] **Step 4: Run the frontend and full suites.** Run: `.venv/bin/python -m pytest tests/test_frontend_generic_dom.py tests/test_frontend_rxrow.py tests/test_frontend_spell_modal_dom.py -q`, then `.venv/bin/python -m pytest -q`. Expected: all PASS (baseline + the new tests).

- [ ] **Step 5: Commit** (ask first): `git commit -m "PQ-a: page shows Add generic for a brand + suffix row"`

---

## Self-review

- **Spec coverage:** option A → Task 2 (`_generic_of`), Task 3 (correction/save/print); option B → Task 1 (`combo_suffix`), Task 2 (grounding, `combo_base`), Task 5 ("Add generic"); `learnable` exact → Task 4; `generic_source` `""`/`"lexicon"` → Tasks 2-3; `generic_hidden` → Task 2 test. Every compute site named in the brief: `surface.py:47-80` (T2), `determinism.py:241` (kept fuzzy), `:328` (T2), `correction.py:270-298` (T3), `rowcheck.py:72` (T2), `pdf/sheet.py:96` (T3 test, no code change; it prints the stored row's `generic`, which the save path recomputes at `api/persistence.py:215-220`).
- **Type consistency:** `_exact_lookup(name) -> str`, `combo_suffix(name) -> tuple[str, str] | None`, `generic_fields(name, match) -> dict` with keys `generic`, `generic_source`, `combo_base`, used identically in Tasks 2-5.
- **Not done here (out of scope):** editing a generic, `"doctor"` source, AI suggestion (plan g); overlay storage (plan f); `schedule` still follows `lexicon_match` on first authoring (`rowcheck.py:72`) but the generic on correction (`correction.py:293`), unchanged; `hints.py:33` keeps fuzzy lookup (speech hints, not generics).
