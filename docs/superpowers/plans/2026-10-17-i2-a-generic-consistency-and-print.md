# I2-a: Generic Consistency, Inline "Did You Mean" and the Printed Generic Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Summary.** Today a brand row shows `generic: Paracetamol`, but a generic-named row (`Tab Cetirizine 10 mg`) gets `generic: ""` (`core/surface.py:47`) and an unknown name (`citrizene`, `croissin`) gets nothing until the doctor opens Spell it. This plan makes it consistent: every row the lexicon knows carries its generic on first authoring, after `/correct` and after Save; an unknown row carries one inline "Did you mean Cetirizine?" computed at format time (a suggestion, never a rewrite); and the PRINTED prescription shows `generic: X` on a second small line under a brand. Adds 14 tests: 1694 -> **1708 passed, 1 skipped**.

**Decision needed from the owner.** Confirm index Q1 (a generic-named row shows a small screen-only `generic` tag, no second line), Q2 (suggest the closest spelling, so `croissin` -> `Crocin`, generic Paracetamol) and Q3 (print the line whenever the generic differs from the name). The plan builds those defaults. It also REVERSES the I1-b rule "generic on screen only" (owner decision D2, index section 2).

- **Goal:** One generic rule for every row, on screen and on paper; one inline suggestion for an unknown name.
- **Architecture:** `surface._generic_of` returns the lexicon match for every matched row. `candidates.scored_spellings` ranks lexicon SPELLINGS (a brand in its own spelling). `rowcheck.options` builds the one suggestion list (reasons per name) and `rowcheck.did_you_mean` takes its clear winner for an `unknown-medicine` row; both row fields are recomputed by `correction`. The page renders the generic line (printable), the `generic` tag (screen only) and the inline button through a new shared component `frontend/suglist.js`; a tap runs the existing Spell it `useName` flow. `pdf/sheet.py` prints the generic line.
- **Tech Stack:** Python 3 / FastAPI, vanilla JS, pytest, node (fake DOM tests). No new dependency.
- **Spec:** index `2026-10-17-i2-00-index.md` sections 2 (D1, D2), 4.1, 4.4, 4.5, 4.6. I1 contracts: `2026-10-16-i1-00-index-and-contracts.md` 4.1 (row JSON), 4.5 (row state, name-only Spell rule).
- **Produces:** `core.surface._generic_of` (new rule), `core.candidates.scored_spellings`, `core.rowcheck.options`, `rowcheck.did_you_mean`, `rowcheck.MAX_OPTIONS = 40`, `rowcheck.INLINE_MIN = 0.9`, `rowcheck.INLINE_GAP = 0.05`, row fields `did_you_mean` and `did_you_mean_generic`, `frontend/suglist.js` (`SugList.item`), `RxState.rowState(...).didYouMean`, `RxState.sameName`. Files: `tests/test_generic_consistency.py` (3), `tests/test_did_you_mean.py` (5), `tests/test_frontend_generic_dom.py` (4), 2 tests appended to `tests/test_pdf_sheet.py`.

## Global Constraints
- `core/` stays pure (`tests/test_core_purity.py`). No `.py` file over 500 lines (`tests/test_file_sizes.py:12`); budgets below.
- Never rename a row: `did_you_mean` is data the page offers; `name`, `status`, `instructions` and the Save gate (`core/safety.py:9-30`) are unchanged by it.
- Tests offline: blank provider keys (`tests/conftest.py`), temp `DB_PATH`. Test command `.venv/bin/python -m pytest tests/ -q`. No commits; every "commit" step is "leave uncommitted".
- Frontend DOM is built with `createElement` and `textContent` only (no `innerHTML`, pinned by `tests/test_frontend_rxspell.py:75`).

## Review Focus (inputs most likely to bite)
| Input | Expected | Pinned in |
|---|---|---|
| `citrizene` (unknown) | `did_you_mean` Cetirizine / Cetirizine; row stays `Citrizene`, `unknown-medicine`, blocks Save | T2 tests 2, 3 |
| `croissin` | `did_you_mean` **Crocin**, generic Paracetamol (a brand spelling, Q2); `suggest_candidates` still gives `["Paracetamol"]` | T2 tests 1, 2 |
| `Tab Cetirizine 10 mg`, `Cap Omeprazole 20` | `generic` = itself; screen tag `generic`; no printed line | T1 test 1, T3 test 1, T4 test 1 |
| A brand two generics claim (`Combiflam`) | `unverified-name`, `lexicon_match ""`, `generic ""` (unchanged, `tests/test_brand_as_dictated.py:104-112`) | existing |
| A brand with the same stem as its generic (`Pantop`, alias of Pantoprazole) | `generic: Pantoprazole` line (the name differs) | T1 test 1 (`Amlo`) |
| A name hand-edited after authoring (Zyloric -> Febuxostat, `data-lexicon` still Allopurinol) | page: generic line and Did you mean vanish on the name edit; server: `generic ""` (`correction.py:270-274`) | `tests/test_brand_as_dictated.py:355-361`, T3 test 3 |
| A document saved before this change (no `generic` on generic rows, no `did_you_mean`) | Opens and prints as before: no line, no button | T4 test 1 (row without the key) |
| Near-equal sound-alikes, or a top name on the curated look-alike list | No inline suggestion; Spell it lists them | T2 test 3 (faked lists) |
| A hostile generic text | Escaped on paper, `textContent` on screen | T4 test 1, T3 test 1 |

## Decisions (and why)
1. **Generic rule.** `generic = lexicon_match` for every matched row (brand, generic-named, alias), `""` otherwise. The page decides how to show it: a line `generic: X` when X differs from the name (ignoring case), else a small tag. Why: one server rule, and the "no repeated line" choice stays a display choice (Q1).
2. **Spellings, not canonicals, for an unknown name.** `scored_spellings` keeps the best score per spelling as written (`surface_map`, `core/surface.py:50-61`: a brand in its own spelling, an alias as its generic). Measured on v1.2.0: `croissin` -> `[("Crocin", "Paracetamol", 1.0)]`; `citrizene` -> Cetirizine 1.0, Ceftriaxone 0.805. `suggest_candidates` and `rowcheck.suggestions` stay exactly as I1-r1 left them (`tests/test_formulary_usage.py` keeps passing).
3. **A clear winner only.** The inline button shows when the top sound-alike scores >= 0.9, is at least 0.05 ahead of the next DIFFERENT generic, and is not on the curated look-alike list (`lasa.always_flag_names`, `core/lasa.py:92-94`). Otherwise the doctor opens Spell it. Why: one tap must not pick between two drugs (backlog card (c)). 0.05 is a third of one consonant step (about 0.15, I1-r1 decision 4).
4. **One tap = Spell it "Use this".** The button calls the same `useName` (`frontend/rxview.js:156-183`): check-row, confirmed set updated BEFORE the render, `how = "spell"`, Undo record `respell`. It answers the NAME question only (`RxState.afterSpell`, `frontend/rxstate.js:106-108`).
5. **Cost.** `did_you_mean` runs only for `unknown-medicine` rows: one `scored_spellings` pass, measured 12-18 ms per name. Rows are capped at 20 (`determinism.py:32`).
6. **Print.** `pdf/sheet.py` `_rx_rows` (`:72-97`) adds `<div class="gen">generic: X</div>` inside the Medicine cell when X differs from the name. The PDF is server-rendered HTML with its own `<style>`, JavaScript off (`pdf/renderer.py:61`); frontend CSS never reaches it. The browser-print fallback (`frontend/app.js:1148-1154`) prints the on-screen line, so the line drops its `no-print` class and gets a print rule in `rx.css`.

## File Structure and line budgets
| File | Change | Lines now -> after (budget) |
|---|---|---|
| `doctor_dictation/core/surface.py` | `_generic_of` | 61 -> 61 |
| `doctor_dictation/core/candidates.py` | `scored_spellings` | 121 -> about 140 (<= 150) |
| `doctor_dictation/core/rowcheck.py` | `options`, `did_you_mean`, `_sound_options`, the row hook | 92 -> about 160 (<= 180) |
| `doctor_dictation/core/correction.py` | two derived fields | 431 -> about 437 (<= 445) |
| `doctor_dictation/pdf/sheet.py` | generic line, `.gen` style | 317 -> about 322 |
| `frontend/suglist.js` | NEW `SugList.item`, `reasonText` | about 40 |
| `frontend/rxstate.js`, `rxview.js`, `rx.css`, `index.html` | meta keys, `didYouMean`, line/tag/button, panel-free `useName`, print rule, script tag, `?v=` | 163 -> 175; 257 -> 280; 58 -> 62 |

---

### Task 1: Every matched row carries its generic
**Files:** Modify `doctor_dictation/core/surface.py`, `tests/test_brand_as_dictated.py` (3 expectations); Create `tests/test_generic_consistency.py`.

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-a: every row the lexicon knows carries its generic: first authoring, /correct and Save. Offline."""
import json

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import db as dbmod
from doctor_dictation.config import override_settings
from doctor_dictation.core.determinism import _FORMAT_CACHE, ground_rx, validate_structured

T = "tab cetirizine 10 mg once daily, tab crocin 500 mg sos, cap omeprazole 20 mg before food, tab citrizene 10 mg, tab amlo 5 mg"

def test_every_row_the_lexicon_knows_carries_its_generic():
    s, _w = validate_structured({"rx": [{"form": "Tab.", "name": n} for n in ("Cetirizine", "Crocin", "Omeprazole", "Citrizene", "Amlo")]}, T)
    assert [(r["name"], r["lexicon_match"], r["generic"]) for r in s["rx"]] == [
        ("Cetirizine", "Cetirizine", "Cetirizine"),      # a generic-named row: itself (was "")
        ("Crocin", "Paracetamol", "Paracetamol"),        # a brand: its generic (unchanged)
        ("Omeprazole", "Omeprazole", "Omeprazole"),
        ("Citrizene", "", ""),                           # unknown: no generic (Task 2 adds a Did you mean)
        ("Amlo", "Amlodipine", "Amlodipine")]            # a short alias kept as dictated: its generic
    rows, _issues = ground_rx([{"name": "Cetirizine"}, {"name": ""}], "cetirizine")
    assert [r["generic"] for r in rows] == ["Cetirizine", ""]

def test_first_authoring_shows_the_generic_on_every_known_row(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")          # the rules path: no provider
    _FORMAT_CACHE.clear()
    j = TestClient(M.app).post("/api/format", json={"transcript": "tab cetirizine 10 mg once daily. tab crocin 650 mg sos"}).json()
    assert [(r["name"], r["generic"]) for r in j["structured"]["rx"]] == [("Cetirizine", "Cetirizine"), ("Crocin", "Paracetamol")]

def test_the_generic_survives_correct_and_save(tmp_path, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "a.db"))
    client = TestClient(M.app)
    row = {"form": "Tab.", "name": "Cetirizine", "strength": "10 mg", "dose": "1-0-0", "timing": "", "duration": "",
           "instructions": "", "status": "verified", "lexicon_match": "Cetirizine"}          # what readRx sends: no generic
    out = client.post("/api/v1/correct", json={"transcript": "", "current_form": {"rx": [row]}}).json()
    assert out["structured"]["rx"][0]["generic"] == "Cetirizine"
    r = client.post("/api/v1/documents", json={"structured": {"patientName": "Anita", "opNo": "OP-9", "rx": [row]}, "confirmed_rows": []})
    assert r.status_code == 200, r.text
    conn = dbmod.get_conn(tmp_path / "a.db")
    saved = json.loads(dbmod.get_document(conn, r.json()["document_id"])["structured_json"])["rx"][0]
    conn.close()
    assert (saved["name"], saved["generic"]) == ("Cetirizine", "Cetirizine")
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_generic_consistency.py -q`. Expected: 3 FAIL (`('Cetirizine', 'Cetirizine', '')` where `'Cetirizine'` was expected).
- [ ] **Step 3: Change `_generic_of`** (`core/surface.py:41-47`):
```python
def _generic_of(name: str, match: str) -> str:
    """The generic of a row the lexicon knows: its lexicon match, for a brand AND for a generic-named row (plan I2-a);
    "" without a match. ``name`` stays for the call sites. Shown on screen; printed under a brand (pdf/sheet.py)."""
    return (match or "").strip()
```
`correction._recomputed_generic` (`core/correction.py:270-274`) keeps its guard, so a hand-edited name still gets `""`.

- [ ] **Step 4: Update the three I1-b expectations deliberately** (they pinned the old "screen only for brands" rule): `tests/test_brand_as_dictated.py:96` `== ""` -> `== "Allopurinol"`; `:97` `== ""` -> `== "Paracetamol"` (keep the comment `# case only`); `:351-352` `("Allopurinol", "")` -> `("Allopurinol", "Allopurinol")`. Leave `:98`, `:100` (`["Allopurinol", ""]`: the second row is blank), `:109`, `:329` and `:361` as they are.
- [ ] **Step 5: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_generic_consistency.py tests/test_brand_as_dictated.py tests/test_lasa.py tests/test_rowcheck.py tests/test_correction.py -q`. Expected: all pass.

---

### Task 2: Spellings, the options list and the inline Did you mean (server)
**Files:** Modify `core/candidates.py`, `core/rowcheck.py`, `core/correction.py`; Create `tests/test_did_you_mean.py`.

**Interfaces:** `scored_spellings(name, k=3) -> [(spelling, canonical, score)]`; `rowcheck.options(row, cap=MAX_OPTIONS) -> ([{"name", "generic", "reason"}], total)`, reasons `matched | clinic | sounds | lookalike`; `rowcheck.did_you_mean(name, status) -> {"did_you_mean", "did_you_mean_generic"}`.

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-a: lexicon spellings, the one suggestion list, and the inline Did you mean (a suggestion, never a rewrite)."""
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.core import formulary as F, rowcheck
from doctor_dictation.core.candidates import scored_spellings, suggest_candidates
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import _FORMAT_CACHE, validate_structured
from doctor_dictation.core.safety import screen_unverified

NONE = {"did_you_mean": "", "did_you_mean_generic": ""}

def test_scored_spellings_keep_a_brand_in_its_own_spelling(frozen_lexicon):
    assert [(s, c) for s, c, _sc in scored_spellings("croissin", 5)] == [("Crocin", "Paracetamol")]
    assert [(s, c) for s, c, _sc in scored_spellings("citrizene", 5)] == [("Cetirizine", "Cetirizine"), ("Ceftriaxone", "Ceftriaxone")]
    assert scored_spellings("the doctor", 5) == [] and scored_spellings("croissin", 0) == []
    assert suggest_candidates("croissin") == ["Paracetamol"]                  # the canonical list is unchanged (I1-r1)

def test_unknown_rows_carry_a_did_you_mean_from_the_first_authoring_and_stay_as_dictated(frozen_lexicon, monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    _FORMAT_CACHE.clear()
    j = TestClient(M.app).post("/api/format", json={"transcript": "tab citrizene 10 mg at night. tab croissin 500 mg sos. tab cetirizine 10 mg once daily"}).json()
    rows = j["structured"]["rx"]
    assert [(r["name"], r["status"], r["did_you_mean"], r["did_you_mean_generic"]) for r in rows] == [
        ("Citrizene", "unknown-medicine", "Cetirizine", "Cetirizine"),
        ("Croissin", "unknown-medicine", "Crocin", "Paracetamol"),
        ("Cetirizine", "verified", "", "")]
    assert "[unverified: confirm with doctor]" in rows[0]["instructions"]               # never renamed, never verified
    assert [b["index"] for b in screen_unverified(j["structured"], [])] == [0, 1]        # the Save gate still blocks both
    s, _w = validate_structured({"rx": [{"name": "Zzqxwv"}]}, "zzqxwv")
    assert {k: s["rx"][0][k] for k in NONE} == NONE                                      # nothing close: nothing offered

def test_the_inline_suggestion_needs_a_clear_winner_and_never_a_curated_twin(monkeypatch):
    def fake(opts):
        monkeypatch.setattr(rowcheck, "_sound_options", lambda name, k, clinic=True: opts)
    fake([("Alfa", "Alfa", 0.95, "sounds"), ("Alfo", "Alfo", 0.93, "sounds")])
    assert rowcheck.did_you_mean("Alfx", "unknown-medicine") == NONE                     # 0.02 apart: the doctor picks
    fake([("Alfa", "Alfa", 0.95, "sounds"), ("Alfa Forte", "Alfa", 0.94, "sounds")])
    assert rowcheck.did_you_mean("Alfx", "unknown-medicine")["did_you_mean"] == "Alfa"   # the same generic is no rival
    fake([("Alfa", "Alfa", 0.89, "sounds")])
    assert rowcheck.did_you_mean("Alfx", "unknown-medicine") == NONE                     # under INLINE_MIN
    fake([("Prednisolone", "Prednisolone", 1.0, "sounds")])
    assert rowcheck.did_you_mean("Prednisolon", "unknown-medicine") == NONE              # a curated look-alike pair
    fake([("Zorbexin", "", 1.0, "clinic")])
    assert rowcheck.did_you_mean("Zorbexim", "unknown-medicine") == {"did_you_mean": "Zorbexin", "did_you_mean_generic": ""}
    for status in ("verified", "unverified-name", "lookalike-check", "dose-check", "unverified-strength", ""):
        assert rowcheck.did_you_mean("Alfx", status) == NONE
    assert (rowcheck.INLINE_MIN, rowcheck.INLINE_GAP, rowcheck.MAX_OPTIONS) == (0.9, 0.05, 40)

def test_options_carry_a_generic_and_a_reason_for_each_name(frozen_lexicon):
    F.activate(F.ClinicLayer((("Zorbexin", "Paracetamol"),)))
    try:
        opts, total = rowcheck.options({"name": "Prednisone", "lexicon_match": "Prednisone"})
        assert opts[:2] == [{"name": "Prednisone", "generic": "Prednisone", "reason": "matched"},
                            {"name": "Prednisolone", "generic": "Prednisolone", "reason": "lookalike"}] and total == len(opts)
        assert "Zorbexin" not in [o["name"] for o in opts]          # a matched row never offers clinic names (I1-r1 decision 3)
        assert rowcheck.options({"name": "Zorbexim", "lexicon_match": ""})[0][0] == {"name": "Zorbexin", "generic": "Paracetamol", "reason": "clinic"}
        assert rowcheck.options({"name": "Croissin", "lexicon_match": ""})[0][0] == {"name": "Crocin", "generic": "Paracetamol", "reason": "sounds"}
    finally:
        F.activate(F.ClinicLayer())

def test_correct_and_save_recompute_the_did_you_mean_the_page_never_sends(frozen_lexicon):
    cur = {"rx": [{"name": "Citrizene", "status": "unknown-medicine", "lexicon_match": "", "instructions": "[unverified: confirm with doctor]"}]}
    fresh = {"name": "Citrizene", "status": "x", "lexicon_match": "x", "instructions": "", "did_you_mean": "STALE"}
    row = preserve_untouched_rx_status(cur, {}, {"rx": [fresh]})["rx"][0]
    assert (row["status"], row["did_you_mean"], row["did_you_mean_generic"]) == ("unknown-medicine", "Cetirizine", "Cetirizine")
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_did_you_mean.py -q`. Expected: 5 FAIL (`ImportError: cannot import name 'scored_spellings'`).
- [ ] **Step 3: `core/candidates.py`.** Add after `scored_candidates` (`:89-100`):
```python
def scored_spellings(name: str, k: int = 3) -> list:
    """[(spelling, canonical, score)] by the same rules as scored_candidates, one entry per lexicon spelling as written
    (a brand in its own spelling, an alias as its generic), best first; ties by spelling (plan I2-a)."""
    from .determinism import _maps
    low = re.sub(r"[^a-z]", "", (name or "").lower())
    key = phonetic_key(low)
    if k <= 0 or len(low) < 4 or len(low) > MAX_NAME_LETTERS or len(key) < 3:
        return []
    shown, best = _maps()[0], {}
    for text, tkey, canon in _rows():
        sc = _score(low, key, text, tkey)
        spelling = shown.get(text, canon)                       # a name two generics claim is not in the surface map
        if sc >= MIN_SCORE and sc > best.get(spelling, (0.0, ""))[0]:
            best[spelling] = (sc, canon)
    ranked = sorted(best.items(), key=lambda kv: (-round(kv[1][0], 6), kv[0].lower(), kv[0]))
    return [(s, c, sc) for s, (sc, c) in ranked[:k]]
```
- [ ] **Step 4: `core/rowcheck.py`.** Change the import line to `from .candidates import MIN_SCORE, scored_spellings, similarity, suggest_candidates`, add the constants under `SUGGESTION_LIMIT`, add the hook in `ground_with_notes` and the three functions at the end. `suggestions` (`:77-92`) is not touched.
```python
MAX_OPTIONS, POOL_ALL = 40, 100       # the Spell it list: names returned, names looked at (I2-c pages them)
INLINE_MIN, INLINE_GAP = 0.9, 0.05    # the inline Did you mean: a clear winner only (plan I2-a)
```
```diff
-        **formulary.row_extras(name, match, status),
+        **formulary.row_extras(name, match, status), **did_you_mean(name, status),
```
```python
def _sound_options(name, k, clinic=True):
    """[(name, generic, score, reason)]: lexicon spellings ("sounds") and, when ``clinic``, this clinic's single-word
    names ("clinic") by one score, then the I1-r1 near-tie rule (usage moves clinic names only)."""
    layer = formulary.active_layer()
    mine = [(n, g, s, "clinic") for n, g in layer.items if clinic and (s := similarity(name, n)) >= MIN_SCORE]
    lex = [(s, c, sc, "sounds") for s, c, sc in scored_spellings(name, k + len(mine))]
    merged = sorted(lex + mine, key=lambda o: (-round(o[2], 6), o[0].lower(), o[0]))
    by_name = {o[0]: o for o in merged}
    return [by_name[n] for n in formulary.tie_break([(o[0], o[2], o[3] == "clinic") for o in merged], layer.usage_of)][:k]

def options(row: dict, cap: int = MAX_OPTIONS):
    """([{"name", "generic", "reason"}], total): the one list behind Spell it and the inline Did you mean (I2-a, I2-c).

    Order as ``suggestions``: the lexicon match ("matched"), else the row's own clinic name ("clinic"); sound-alikes;
    the match's look-alike twins. A twin keeps the reason "lookalike" wherever it appears. One entry per name
    (case-insensitive); ``total`` counts entries before the cap."""
    from . import lasa
    match, name = row.get("lexicon_match") or "", row.get("name", "")
    twins = {t.casefold() for t in (lasa.twins(match) if match else [])}
    out, seen = [], set()

    def add(n, generic, reason):
        if n and n.casefold() not in seen:
            seen.add(n.casefold())
            out.append({"name": n, "generic": generic or "", "reason": "lookalike" if n.casefold() in twins else reason})
    if match:
        add(match, match, "matched")
    elif (hit := formulary.active_layer().get(name)):
        add(hit[0], hit[1], "clinic")
    for n, generic, _score, reason in _sound_options(name, POOL_ALL, clinic=not match):
        add(n, generic, reason)
    for t in (lasa.twins(match) if match else []):
        add(t, t, "lookalike")
    return out[:cap], len(out)

def did_you_mean(name: str, status: str) -> dict:
    """The inline suggestion for an ``unknown-medicine`` row: the top sound-alike when it scores >= INLINE_MIN, is
    INLINE_GAP ahead of the next different generic and is not on the curated look-alike list. A suggestion only."""
    from . import lasa
    none = {"did_you_mean": "", "did_you_mean_generic": ""}
    alikes = _sound_options(name, 6) if status == D_UNKNOWN else []
    if not alikes or alikes[0][2] < INLINE_MIN:
        return none
    top = alikes[0]
    same = (top[1] or top[0]).casefold()
    rival = next((o for o in alikes[1:] if (o[1] or o[0]).casefold() != same), None)
    if (rival and round(top[2] - rival[2], 6) < INLINE_GAP) or (top[1] and top[1] in lasa.always_flag_names()):
        return none
    return {"did_you_mean": top[0], "did_you_mean_generic": top[1]}
```
Add `D_UNKNOWN = "unknown-medicine"` beside the constants (rowcheck imports determinism lazily, so it cannot use `D.RX_UNKNOWN_MEDICINE` at module level).

- [ ] **Step 5: `core/correction.py`.** Add `from .rowcheck import did_you_mean` to the imports, extend `DERIVED_ROW_FIELDS` (`:267`) to `("generic", "heard", "lookalike", "dose_note", "source", "did_you_mean", "did_you_mean_generic")` and add to `RECOMPUTED_ROW_FIELDS` (`:285-291`):
```python
    "did_you_mean": lambda row: did_you_mean(row.get("name", ""), row.get("status", ""))["did_you_mean"],
    "did_you_mean_generic": lambda row: did_you_mean(row.get("name", ""), row.get("status", ""))["did_you_mean_generic"],
```
- [ ] **Step 6: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_did_you_mean.py tests/test_rowcheck.py tests/test_rx_check_row.py tests/test_formulary_usage.py tests/test_correction.py tests/test_correction_ops.py tests/test_candidates.py tests/test_core_purity.py -q`. Expected: all pass (`test_did_you_mean.py`: 5 passed).

---

### Task 3: The page: generic line, generic tag and the one-tap Did you mean
**Files:** Create `frontend/suglist.js`, `tests/test_frontend_generic_dom.py`; Modify `frontend/rxstate.js`, `frontend/rxview.js`, `frontend/rx.css`, `frontend/index.html`, `tests/test_frontend_rxspell_dom.py` (`_run` loads `suglist.js`), `tests/test_frontend_rxspell.py:87` (pins).

- [ ] **Step 1: Write the failing tests.** In `tests/test_frontend_rxspell_dom.py` `_run`, load the new file too: `require(process.argv[3]);` after `require(process.argv[2]);` and pass `str(FRONT / "suglist.js")` before `rxview.js` in the argument list (order: rxstate, suglist, rxview; adjust the indices). Then create:
```python
"""Plan I2-a, page: the generic line (printable), the generic tag (screen only) and the one-tap Did you mean. Node fake DOM."""
from test_frontend_rxspell import _node
from test_frontend_rxspell_dom import _run

DYM = '{ did_you_mean: "Cetirizine", did_you_mean_generic: "Cetirizine" }'

def test_the_generic_line_prints_under_a_brand_and_a_generic_row_gets_a_screen_tag():
    r = _run("""
      const b = mkRow("g1", "verified", { form: "Tab.", name: "Crocin", strength: "500 mg" }, { generic: "Paracetamol" });
      const g = mkRow("g2", "verified", { name: "cetirizine" }, { generic: "Cetirizine" });
      const u = mkRow("g3", "unknown-medicine", { name: "Zzqxwv" }, {});
      const h = mkRow("g4", "verified", { name: "Evil" }, { generic: "<b>x</b>" });
      const pick = (tr, s) => tr.querySelectorAll(s).map((n) => [n.textContent, n.className]);
      console.log(JSON.stringify({ b: [pick(b, ".rx-gen"), pick(b, ".rx-gen-tag")], g: [pick(g, ".rx-gen"), pick(g, ".rx-gen-tag")],
        u: [pick(u, ".rx-gen"), pick(u, ".rx-gen-tag")], h: pick(h, ".rx-gen")[0][0] }));""")
    assert r["b"] == [[["generic: Paracetamol", "rx-extra rx-sub rx-gen"]], []]       # no no-print: the browser print shows it too
    assert r["g"] == [[], [["generic", "rx-extra rx-gen-tag no-print"]]]               # the same name, any case: a tag, no line
    assert r["u"] == [[], []] and r["h"] == "generic: <b>x</b>"                        # textContent: shown as text, never markup

def test_did_you_mean_is_one_tap_through_the_spell_it_flow_and_answers_the_name_only():
    r = _run("""
      const tr = mkRow("d1", "unknown-medicine", { name: "Citrizene", strength: "10 mg", dose: "0-0-1" }, %s);
      const b = tr.querySelector('[data-action="dym"]');
      const shown = [b.textContent, b.attrs["aria-label"]];
      click(b); const sent = posts[0].body.row;
      await reply({ name: "Cetirizine", status: "unverified-name", lexicon_match: "Cetirizine", generic: "Cetirizine", instructions: "" });
      const after = [cell(tr, "name").textContent, cell(tr, "dose").textContent, confirmed.has("d1"), tr._rx.how, undos.length, !!tr.querySelector('[data-action="dym"]')];
      const t2 = mkRow("d2", "unknown-medicine", { name: "Croissin" }, { did_you_mean: "Crocin", did_you_mean_generic: "Paracetamol" });
      const two = t2.querySelector('[data-action="dym"]').textContent;
      click(t2.querySelector('[data-action="dym"]')); await reply({ name: "Crocin", status: "unknown-medicine", instructions: "" });
      console.log(JSON.stringify({ shown, sent: [sent.name, sent.dose], after, two, open: [confirmed.has("d2"), t2._rx.note] }));""" % DYM)
    assert r["shown"] == ["Did you mean Cetirizine?", "Use Cetirizine for this row"]
    assert r["sent"] == ["Cetirizine", "0-0-1"] and r["two"] == "Did you mean Crocin?generic: Paracetamol"
    assert r["after"] == ["Cetirizine", "0-0-1", True, "spell", 1, False]               # confirmed before the render, Undo pushed
    assert r["open"] == [False, 'Name changed to "Crocin". It still needs your decision.']

def test_did_you_mean_is_off_when_confirmed_view_only_working_or_after_a_name_edit():
    r = _run("""
      const m = %s, has = (tr) => !!tr.querySelector('[data-action="dym"]');
      const a = mkRow("e1", "unknown-medicine", { name: "Citrizene" }, m); confirmed.add("e1"); RxView.renderRow(a);
      const v = mkRow("e2", "unknown-medicine", { name: "Citrizene" }, m);
      globalThis.Authorship = { isViewOnly: () => true }; RxView.renderRow(v);
      const vo = v.querySelector('[data-action="dym"]').disabled; click(v.querySelector('[data-action="dym"]')); const voPosts = posts.length;
      globalThis.Authorship = undefined; flags.working = true; click(v.querySelector('[data-action="dym"]')); const busyPosts = posts.length; flags.working = false;
      const same = mkRow("e3", "unknown-medicine", { name: "cetirizine" }, m);
      const ed = mkRow("e4", "unknown-medicine", { name: "Citrizene" }, m); RxView.onEdit(ed, cell(ed, "name")); RxView.renderRow(ed);
      console.log(JSON.stringify([has(a), vo, voPosts, busyPosts, has(same), has(ed)]));""" % DYM)
    assert r == [False, True, 0, 0, False, False]

def test_row_state_offers_did_you_mean_only_for_an_unknown_name_and_a_name_edit_clears_it():
    got = _node('[["unknown-medicine","Citrizene"],["unverified-name","Citrizene"],["verified","Citrizene"],["unknown-medicine","CETIRIZINE"]]'
                '.map(([s, n]) => RxState.rowState({status: s, name: n, did_you_mean: "Cetirizine", did_you_mean_generic: "Cetirizine"}, {}).didYouMean)'
                '.concat([RxState.afterEdit({did_you_mean: "X", did_you_mean_generic: "Y"}, "name"), RxState.afterEdit({did_you_mean: "X", did_you_mean_generic: "Y"}, "dose"),'
                ' RxState.metaOf({did_you_mean: "X", did_you_mean_generic: 5}), RxState.sameName(" Cetirizine", "cetirizine ")])')
    assert got[:4] == [{"name": "Cetirizine", "generic": "Cetirizine"}, None, None, None]
    assert (got[4]["did_you_mean"], got[4]["did_you_mean_generic"]) == ("", "") and got[5]["did_you_mean"] == "X"
    assert (got[6]["did_you_mean"], got[6]["did_you_mean_generic"]) == ("X", "5") and got[7] is True
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_frontend_generic_dom.py -q`. Expected: 4 FAIL (`Cannot find module .../suglist.js`, then missing classes).
- [ ] **Step 3: `frontend/suglist.js`** (new; Plan I2-c adds paging to it):
```js
"use strict";
// One suggestion, built the same way inline ("Did you mean X?") and in the Spell it list (I2-c). Text only.
window.SugList = (function () {
  const REASON = { matched: "in the medicine list", clinic: "your clinic uses it", sounds: "sounds like", lookalike: "looks alike: a different medicine" };
  const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
  function el(tag, cls, t) { const n = document.createElement(tag); if (cls) n.className = cls; if (t != null) n.textContent = t; return n; }
  const reasonText = (code) => REASON[code] || "";
  // sug: {name, generic, reason}; o: {action, prefix ("Did you mean " inline, "" in the list), reason: bool}
  function item(sug, o) {
    const b = el("button", "rx-act sug " + (o.cls || "")); b.type = "button"; b.dataset.action = o.action; b.dataset.value = sug.name;
    b.append(el("span", "sug-name", (o.prefix || "") + sug.name + (o.prefix ? "?" : "")));
    if (sug.generic && !same(sug.generic, sug.name)) b.append(el("span", "sug-gen", "generic: " + sug.generic));
    if (o.reason && reasonText(sug.reason)) b.append(el("span", "sug-why", reasonText(sug.reason)));
    b.setAttribute("aria-label", "Use " + sug.name + " for this row");
    return b;
  }
  return { item, reasonText, same };
})();
```
- [ ] **Step 4: `frontend/rxstate.js`.** `META_KEYS` (`:15`) gains `"did_you_mean", "did_you_mean_generic"`. `afterEdit` (`:98-103`): in the `col === "name"` branch also set `m.did_you_mean = ""; m.did_you_mean_generic = "";`. `rowState` (`:72-96`) returns one more key, and the export line (`:162`) adds `sameName: same`:
```js
      didYouMean: state === "confirm" && status === "unknown-medicine" && str(row.did_you_mean).trim() && !same(row.did_you_mean, row.name)
        ? { name: str(row.did_you_mean).trim(), generic: str(row.did_you_mean_generic).trim() } : null,
```
- [ ] **Step 5: `frontend/rxview.js`.** (a) Replace the generic line (`:50`):
```js
    const gen = r.meta.generic, nm = val(tr, "name");
    if (!blank && gen && !RxState.sameName(gen, nm)) med.appendChild(el("div", "rx-extra rx-sub rx-gen", "generic: " + gen));   // prints (I2-a)
    else if (!blank && gen) med.appendChild(el("span", "rx-extra rx-gen-tag no-print", "generic"));                              // screen only (Q1)
```
(b) In the `else` branch of the actions (`:79`), before the Confirm button: `if (st.didYouMean) { const b = SugList.item(st.didYouMean, { action: "dym", prefix: "Did you mean " }); b.disabled = vo; acts.appendChild(b); }`. (c) In `onClick` (`:198-203`) add `else if (a === "dym") useName(tr, b.dataset.value);`. (d) Make `useName` (`:156-183`) work without a panel: drop `|| !panel` from the first guard; `if (problem) { if (panel) { say(panel, problem); panel.querySelector("input").focus(); } else { r.note = problem; renderRow(tr); } return; }`; guard `say(panel, "")` and `busy(panel, true)` with `if (panel)`; nothing else changes (the `r.req`, confirmed-before-render and `pushUndo` lines stay as they are).

- [ ] **Step 6: `rx.css`, `index.html`.** Append to `rx.css`: `.rx-gen-tag { margin-left:6px; font-size:11px; color:var(--rx-muted); border:1px solid #c9d2cd; border-radius:999px; padding:0 6px; }`, `.sug-gen, .sug-why { display:block; font-size:11px; font-weight:400; color:var(--rx-muted); }` and `@media print { .rx-gen { font-size:10px; color:#444; } }`. In `index.html` add `<script src="suglist.js?v=1"></script>` before `rxview.js`, and bump `rx.css?v=3`, `rxstate.js?v=3`, `rxview.js?v=3`, `app.js?v=31`. Update the pins in `tests/test_frontend_rxspell.py:87` to `v=3` (`rxstate`, `rxview`, `rx.css`) and `>= 31` (`app.js`).
- [ ] **Step 7: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_frontend_generic_dom.py tests/test_frontend_rxspell.py tests/test_frontend_rxspell_dom.py tests/test_frontend_rxrow.py tests/test_frontend_polish.py -q`. Expected: all pass (`test_frontend_generic_dom.py`: 4 passed).

---

### Task 4: The printed prescription carries the generic
**Files:** Modify `doctor_dictation/pdf/sheet.py`; append to `tests/test_pdf_sheet.py`.

- [ ] **Step 1: Append the failing tests.**
```python
def test_the_medicine_cell_prints_the_generic_on_a_second_line_under_a_brand():
    rows = [{"form": "Tab.", "name": "Crocin", "strength": "500 mg", "generic": "Paracetamol", "status": "verified"},
            {"form": "Tab.", "name": "Cetirizine", "strength": "10 mg", "generic": "Cetirizine", "status": "verified"},
            {"form": "Tab.", "name": "Citrizene", "strength": "10 mg", "generic": "", "status": "unknown-medicine"},
            {"form": "Cap.", "name": "Zyloric", "strength": "100 mg", "status": "verified"},            # saved before I2-a: no key
            {"form": "Tab.", "name": "Evil", "generic": "<b>x</b>"}]
    html = build_sheet_html({"rx": rows}, META)
    table = html[html.index('<table class="rx">'):html.index("</table>")]
    cells = [tr.split("<td>")[2].split("</td>")[0] for tr in table.split("<tr>")[2:]]
    assert cells == ['Tab. Crocin 500 mg<div class="gen">generic: Paracetamol</div>', "Tab. Cetirizine 10 mg",
                     "Tab. Citrizene 10 mg", "Cap. Zyloric 100 mg", 'Tab. Evil<div class="gen">generic: &lt;b&gt;x&lt;/b&gt;</div>']
    assert table.count("<th>") == 6 and ".gen { font-size: 10px; color: #444;" in html

def test_the_pdf_never_loads_frontend_css_and_the_browser_print_shows_the_same_line():
    from pathlib import Path
    html = build_sheet_html({"rx": [{"name": "Crocin", "generic": "Paracetamol"}]}, META)
    assert "<link" not in html and "rx.css" not in html and "<script" not in html        # server HTML, its own <style> only
    css = (Path(__file__).resolve().parents[1] / "frontend" / "rx.css").read_text(encoding="utf-8")
    assert "@media print { .rx-gen { font-size:10px; color:#444; } }" in css
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_pdf_sheet.py -q`. Expected: 2 FAIL (no `class="gen"`).
- [ ] **Step 3: `pdf/sheet.py` `_rx_rows`** (`:81-96`): after `medicine = ...` add
```python
        name, generic = str(row.get("name") or "").strip(), str(row.get("generic") or "").strip()
        gen = f'<div class="gen">generic: {_esc(generic)}</div>' if generic and generic.casefold() != name.casefold() else ""
```
and print `f"<td>{_esc(medicine)}{gen}</td>"`. In the `<style>` block (`:281-282`) add `  .gen {{ font-size: 10px; color: #444; margin-top: 1px; }}`.

- [ ] **Step 4: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_pdf_sheet.py tests/test_pdf.py tests/test_pdf_layout.py tests/test_letterhead_print.py tests/test_document_pdf.py -q`. Expected: all pass. The existing `test_the_printout_has_no_check_column_and_prints_the_same_for_every_status` still holds: its rows have no generic.

---

### Task 5: Mutations, whole suite, sizes, live browser check
- [ ] **Step 1: Mutations.** Apply each alone, run the named test file, see a failure, revert. Report "killed by test N".

| # | Mutation | Must fail |
|---|---|---|
| M1 | `_generic_of` back to `match if match and match.lower() != name.lower() else ""` | `test_generic_consistency.py` 1-3 |
| M2 | drop `**did_you_mean(name, status)` from `ground_with_notes` | `test_did_you_mean.py` 2 |
| M3 | `INLINE_GAP = 0.0` / drop the curated-twin check / run for every status | `test_did_you_mean.py` 3 |
| M4 | `scored_spellings` keys by `canon` instead of `spelling` | `test_did_you_mean.py` 1, 4 |
| M5 | `options` without the `lookalike` override / with `clinic=True` for a matched row | `test_did_you_mean.py` 4 |
| M6 | remove `did_you_mean` from `RECOMPUTED_ROW_FIELDS` | `test_did_you_mean.py` 5 |
| M7 | the generic line keeps `no-print` / the tag condition is inverted | `test_frontend_generic_dom.py` 1 |
| M8 | `didYouMean` ignores `ctx.confirmed` / `afterEdit` keeps it on a name edit | `test_frontend_generic_dom.py` 3, 4 |
| M9 | `useName` requires a panel again | `test_frontend_generic_dom.py` 2 |
| M10 | `sheet.py` prints the line when the generic equals the name / drops `_esc` | `test_pdf_sheet.py` new 1 |
| M11 | delete the `rx.css` print rule | `test_pdf_sheet.py` new 2 |

- [ ] **Step 2: Whole suite.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: **1708 passed, 1 skipped** (1694 + 14). Any other failure: stop and report.
- [ ] **Step 3: Sizes.** Run: `wc -l doctor_dictation/core/{surface,candidates,rowcheck,correction,determinism}.py doctor_dictation/pdf/sheet.py frontend/{rxview,rxstate,suglist}.js frontend/rx.css`. Expected: inside the budgets; `determinism.py` unchanged (410).
- [ ] **Step 4: Live browser check (Playwright, stub providers, never port 8000).**
  1. `export SCR=<session scratchpad>/i2a-live && mkdir -p $SCR`. Start a SEPARATE server: `DB_PATH=$SCR/live.db OPENAI_API_KEY= DEEPSEEK_API_KEY= ALLOW_STUB_PROVIDERS=1 STT_ENGINE=stub STUB_TRANSCRIPT='tab cetirizine 10 mg once daily. tab crocin 500 mg sos. tab citrizene 10 mg at night. tab croissin 500 mg sos' .venv/bin/python -m uvicorn doctor_dictation.main:app --port 8801` (single mode, rules path, stub speech). The test server on port 8000 uses real providers: never call it.
  2. Open `http://127.0.0.1:8801/`. If the browser has no fake microphone, call `formatTranscript(<the same text>)` through `browser_evaluate` (app.js functions are page globals).
  3. Check: Crocin shows `generic: Paracetamol` under it; Cetirizine shows the small `generic` tag; Citrizene shows "Did you mean Cetirizine?"; Croissin shows "Did you mean Crocin?" with `generic: Paracetamol`.
  4. Tap "Did you mean Cetirizine?". Expect the row to read "Confirmed by you" / "You chose this name.", the generic tag, and an Undo bar. Press Undo: the row is `Citrizene` again with the button back.
  5. Confirm the rest, Save, Print. Fetch `/api/v1/documents/<id>/pdf`; check the PDF text has `generic: Paracetamol` under Crocin and no line under Cetirizine. If Chromium is missing (503), use `browser_emulate_media` print on the sheet and check the same.
  6. Resize to 390 x 844: the button wraps inside the row; no horizontal page scroll. Console: no errors.
  7. Stop the server, check `lsof -i :8801` is empty, delete `$SCR`. Never commit `live.db` or screenshots; no secrets in any command.
- [ ] **Step 5: Leave uncommitted.** Changed files: the File Structure table plus the three test files and `tests/test_pdf_sheet.py`, `tests/test_brand_as_dictated.py`, `tests/test_frontend_rxspell.py`, `tests/test_frontend_rxspell_dom.py`.

## Regression list (must stay green)
Save gate (`tests/test_safety.py`, `test_lasa.py:145-158`); Spell it race rules (`tests/test_frontend_rxspell_dom.py`, all 12 unchanged apart from the `_run` file list); I1-r1 order (`tests/test_formulary_usage.py`); brand as dictated (`tests/test_brand_as_dictated.py:58`, `:307`); ordinary sentences (`tests/test_ordinary_sentences.py`); print layout and letterhead (`tests/test_pdf_sheet.py` existing 4, `test_pdf_layout.py`, `test_letterhead_print.py`); check-row shape (`tests/test_rx_check_row.py`).

## Self-Review
- D1: Task 1 (generic rule), Task 2 (unknown names), Task 3 (display). D2: Task 4 and the browser-print rule. Every Review Focus row maps to a test.
- Test count: 3 + 5 + 4 + 2 = 14. Edited, not added: 3 expectations in `test_brand_as_dictated.py`, the pins in `test_frontend_rxspell.py:87`, the `_run` file list.
- Deliberately out of scope: the paged Spell it modal and the `options` field on check-row (I2-c); schedule badges (I2-d); a re-check when a name is hand-edited (backlog (j)); printing the `generic` tag for generic-named rows (Q1 says no).

**Decision needed:** the owner's yes on Q1, Q2 and Q3 (index section 6); then run Task 1.
