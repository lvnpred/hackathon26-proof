# Iteration 1 Plans: Index and Shared Contracts

**Spec:** the "Iteration 1: UI first" section of `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` (approved 2026-10-16), plus the whole-app design canvas https://claude.ai/artifact/W48RNxGR2mjHT5W1h9GMjD (local copy of the artboards: `/private/tmp/claude-502/-Users-narenlingala-Documents-workspace-work-Zebra-doctor-dic-doctor-dictation-main/8c2f5579-3a7d-4332-8c1b-5748dbc166ef/scratchpad/design/project/*.dc.html`). When a plan and the spec disagree, this file's section 4 wins; report the disagreement, do not silently pick.

This file is the single source of truth for **names, paths and interfaces that cross plan boundaries**. Plans are written in parallel; each relies on this file, not on another plan's text. Conventions in `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` section 2 still apply (header, under 500 lines, no commits, test-first with real code, offline tests, test command `.venv/bin/python -m pytest tests/ -q`, verify before quoting line numbers).

## 1. Order and prerequisites

| # | File (under `docs/superpowers/plans/`) | Delivers | Needs |
|---|---|---|---|
| 1 | `2026-10-16-i1-b-brand-as-dictated.md` | Brand names stay as dictated; the generic is kept for checks | baseline suite |
| 2 | `2026-10-16-i1-a-lookalike-and-heard.md` | `core/lasa.py` look-alike guard, `heard` text, status `lookalike-check` | I1-b |
| 3 | `2026-10-16-i1-c-dosing-reference-and-dosecheck.md` | `core/dosing.py`, reference file, `strength_options`, status `dose-check` | I1-a |
| 4 | `2026-10-16-i1-d-check-row-endpoint.md` | `POST /api/v1/rx/check-row` (re-check one row) | I1-a, I1-c |
| 5a | `2026-10-16-i1-e-row-ui.md` | `rxstate.js` (pure row state), `rxview.js`, `rx.css` | I1-d |
| 5b | `2026-10-16-i1-e2-page-wiring.md` | Loads them into the page, summary bar, Save gate, old block-panel decision | I1-e |
| 5c | `2026-10-16-i1-e3-spell-it.md` | Spell it, check-row call, undo | I1-e2 |
| 6a | `2026-10-16-i1-f-steppers-and-polish.md` | `steps.js`: main, Profile and Letterhead steppers | I1-e3 |
| 6b | `2026-10-16-i1-f2-visual-polish.md` | Tokens, fonts decision, `polish.css`, login and Team look | I1-f |
| 7a | `2026-10-16-i1-g1-lexicon-gate-and-adapter.md` | Licence gate in `build.py`, CSV import adapter | I1-a |
| 7b | `2026-10-16-i1-g2-lexicon-merge-and-checks.md` | Merge wiring, `sources`, `imported.json`, look-alike share check, real import under human review | I1-g1, I1-a |
| 8a | `2026-10-16-i1-h1-formulary-rules-and-table.md` | Pure rules, `ClinicLayer`, migration 009, ledger | I1-a |
| 8b | `2026-10-16-i1-h2-formulary-grounding-and-hints.md` | Grounding hook, hints, row `source` | I1-h1, I1-b |
| 8c | `2026-10-16-i1-h3-formulary-api-and-cache.md` | Layer loading, learning on save, cache key, admin routes | I1-h2, I1-d |
| 8d | `2026-10-16-i1-h4-formulary-isolation-and-team-tab.md` | Isolation test, Team "Clinic medicines" tab, full-suite check | I1-h3, I1-f2 |

## 2. Facts found while reading the code (the plans depend on these)

1. `core/determinism.py` is **482 lines** and `tests/test_file_sizes.py` fails above 500. All new logic goes in **new modules**; edits to `determinism.py` must be net-small (about 15 lines at most across all plans together). Put hooks, not logic, in it.
2. The save gate (`core/safety.py:26`, `api/persistence.py:194`) blocks **every row whose status is not exactly `verified`** unless the doctor confirmed its index. So any new blocking status needs no gate change, and a status that must not block has to be `verified`.
3. The dose vocabulary is only `ALLOWED_DOSES = ("1-0-0","1-0-1","1-1-1","0-0-1","SOS")` (`core/determinism.py:20`) and timings only `After food`, `Before food`, `At bedtime`, `""`. `validate_structured` coerces anything else (`determinism.py:386-394`). So today a row's daily count is 1, 2 or 3 units, and `SOS` is not countable. The design canvas rows "2-2-2-2", "Morning" and "Every 6 hours" cannot be produced today; widening the vocabulary is **out of scope** and an open decision (section 5).
4. Brands are rewritten to generics inside `correct_drugs` (`correct_drugs` at `determinism.py:124`, through `_alias_map` at `:90`), so the LLM and the printout never see the dictated brand. `tests/golden.json` case `hinglish-mix` expects `crocin` to become `Paracetamol`; Plan I1-b must update that expectation deliberately.
5. `core/` must stay pure: no `sqlite3`, `fastapi`, `httpx`, no I/O beyond reading the lexicon files (`tests/test_core_purity.py`). Anything per-clinic is passed **in** as data.
6. Each clinic has its own SQLite file and its own numbered migrations in `doctor_dictation/db/migrations/` (latest on disk when this was written: `008_clinic_profile_prefix.sql`; verify with `ls`). The current clinic comes from `doctor_dictation/scope.py` `current_scope()`; `/api/format` already keys its cache per clinic (`api/format.py:96`).
7. `frontend/app.js` is 1271 lines, the row pill lives in `renderCheck` (`:893`), the row builder in `rxRow` (`:845`), the save gate in the browser at `:951`. New frontend code goes in **new files** (`frontend/rxstate.js`, `frontend/rx.css`, `frontend/steps.js`), loaded from `frontend/index.html`, with the cache-busting `?v=` bumped. Frontend tests are `tests/test_frontend_*.py` (read one to copy its method).
8. The lexicon has 444 generics; `strengths` is a list per entry and 79 entries have none (`core/lexicon/drugs.json`, `version` key at top level).

## 3. Layout after Iteration 1

```
doctor_dictation/core/
  lasa.py                  # NEW  twins(), heard_as(), look-alike pairs     (I1-a)
  dosing.py                # NEW  reference loader, strength_options, check_dose  (I1-c)
  rowcheck.py              # NEW  grounding of ONE row, shared by format and check-row (I1-d)
  formulary.py             # NEW  clinic layer merged into the alias map     (I1-h)
  lexicon/dosing.json      # NEW  versioned adult dosing reference           (I1-c)
  lexicon/build_dosing.py  # NEW  idempotent rebuild script (no scheduler)   (I1-c)
doctor_dictation/api/rx.py # NEW  POST /api/v1/rx/check-row                  (I1-d)
doctor_dictation/api/formulary.py  # NEW  admin list/remove                  (I1-h)
doctor_dictation/db/migrations/00N_clinic_formulary.sql  # NEW               (I1-h)
frontend/rxstate.js rx.css steps.js      # NEW                               (I1-e, I1-f)
```

## 4. Contracts

### 4.1 Rx row JSON (additive; existing fields and shapes never change)

Existing fields stay: `form, name, strength, dose, timing, duration, instructions, status, lexicon_match`. New optional fields, always present (empty string or empty list when not applicable) on every row from `/api/format`, `/api/v1/correct` and `/api/v1/rx/check-row`:

| Field | Type | Meaning | Owner |
|---|---|---|---|
| `status` | str | Existing four plus **`lookalike-check`** (I1-a) and **`dose-check`** (I1-c). All are blocking (fact 2). | I1-a, I1-c |
| `heard` | str | The raw transcript words the name came from when they differ from `name` (case-insensitive); `""` when the same. | I1-a |
| `lookalike` | str | The twin drug the doctor might have meant, only when status is `lookalike-check`. | I1-a |
| `generic` | str | The generic when `name` is a brand (`lexicon_match` differs from `name`, case-insensitive); else `""`. Screen only. | I1-b |
| `strength_options` | list[str] | Strengths the drug comes in, usual adult strength first; `[]` when unknown. | I1-c |
| `usual_strength` | str | The usual adult strength or `""`. | I1-c |
| `dose_note` | str | Plain reason when status is `dose-check`, for example `3000 mg a day; usual adult maximum 2000 mg`. | I1-c |
| `source` | str | `"lexicon"` or `"clinic"` (learned by this clinic). | I1-h |

`preserve_untouched_rx_status` (`core/correction.py:247`) restores `status`, `lexicon_match` and `instructions`, and every field of `correction.DERIVED_ROW_FIELDS` (final: `("generic", "heard", "lookalike", "dose_note", "source")`; the prior row's value, `""` if it lacks the field, absent when the prior row had no status); `ops._regrounded` drops the same fields. `strength_options` and `usual_strength` depend on the name only and are recomputed. Each plan that adds a row field adds it to that tuple.

### 4.2 Grounding order inside one row (I1-a, I1-c and I1-h extend, I1-d reuses)

```
unknown-medicine   (not in lexicon and not in clinic list)
unverified-name    (not clearly in the transcript)
unverified-strength
dose-check         (I1-c: reviewed reference says the daily total is above the usual adult maximum)
lookalike-check    (I1-a)
verified           (source "clinic" when the name came from the clinic list)
```

The first condition that holds wins. This order is the contract; plans add their step at the stated place.

### 4.3 `core` functions (all pure; names and signatures are fixed)

```python
# core/lasa.py (I1-a)
def twins(canonical: str) -> list[str]: ...                  # look-alike generics of a generic, [] if none
def heard_as(name: str, raw_transcript: str) -> str: ...     # "" when the name appears as written in the raw transcript
def lookalike_flag(canonical: str, name: str, raw_transcript: str) -> str: ...  # twin to ask about, or ""

# core/dosing.py (I1-c)
@dataclass(frozen=True)
class DoseVerdict:
    state: str          # "in-range" | "above-max" | "form-mismatch" | "cannot-check"   (form-mismatch: decision 2026-10-16)
    daily_mg: float | None
    max_daily_mg: float | None
    note: str           # "" unless above-max or form-mismatch
def strength_options(canonical: str) -> tuple[list[str], str]: ...   # (options, usual)
def check_dose(canonical: str, strength: str, dose: str, age_sex: str, form: str = "") -> DoseVerdict: ...   # a form a REVIEWED entry does not allow, adult only: form-mismatch
def dosing_version() -> str: ...

# core/rowcheck.py (I1-d)
def ground_one(row: dict, raw_transcript: str, normalized_transcript: str, age_sex: str = "") -> dict: ...
```

`validate_structured` gains optional keyword arguments only (`raw_transcript: str = ""`, `age_sex: str = ""`); existing call sites keep working.

### 4.4 HTTP

`POST /api/v1/rx/check-row` (I1-d), session-protected like the other `/api/v1` routes:

```json
request:  {"row": {"form":"Tab.","name":"Prednisone","strength":"10 mg","dose":"1-0-1","timing":"","duration":"5 days","instructions":""},
           "transcript": "<raw transcript, may be empty>", "age_sex": "46 / F"}
response: {"row": { ...grounded row with all section 4.1 fields... }, "suggestions": ["Prednisolone","Prednisone"]}
```

`suggestions` come from `suggest_candidates` (`core/candidates.py`) plus `twins`. Errors: 400 for a missing or non-object `row`, same JSON error shape as the other routes. A doctor-typed name is never trusted: the row is grounded like any other.

### 4.5 Frontend state contract (I1-e)

`frontend/rxstate.js` exposes `window.RxState.rowState(row, ctx) -> {state, label, reason, canConfirm, canSpell, chips}` where `state` is one of `ok | dose | confirm | you | known`, mapped as: `verified` + source lexicon is `ok`; `verified` + source clinic is `known`; `unverified-strength`, `dose-check` are `dose`; `unknown-medicine`, `unverified-name`, `lookalike-check` are `confirm`; a row the doctor confirmed is `you`. A spelled name confirms the row only for name questions (`verified`, `unverified-name`, `lookalike-check`); `unknown-medicine`, `dose-check` and `unverified-strength` stay open after spelling, with the note `Name changed to "X". It still needs your decision.` (decision 2026-10-16, I1-e3). A pure function, no DOM, so it is testable with node.

## 5. Open decisions carried into execution

1. **Dosage reference source and clinician reviewer** (I1-c). The plan builds the file format, loader, check and rebuild script, plus a small fixture for tests. It ships **no real clinical data** until a source and reviewer exist; until then every drug is `cannot-check` and chips come from the lexicon `strengths` only.
2. **Dose vocabulary** (fact 3). Daily-total checks work only on the five codes. Widening them touches the LLM prompt, the schema and the PDF, so it is a separate decision.
3. **Whether "both" brand and generic should also print** (open since the brand-policy answer).
4. **Dataset licence** for the lexicon import (I1-g starts with a gate task).

## 6. What no plan here does

The monthly rebuild action or scheduler, paediatric ranges, voice spelling, the speech-engine change, drug-interaction checks, any commit or push.

## 7. Decisions (owner, 2026-10-16: "go with your recommendations on all four")

1. **Form mismatch stays.** `DoseVerdict.state` has a fourth value `form-mismatch` and `check_dose` an optional `form=""` (only reviewed entries, adults only). Written into contract 4.3; plan I1-c agrees.
2. **The Check column is dropped from the printed prescription.** No header, no cells, no marks in the PDF (`pdf/sheet.py`), and none in browser print (`rx.css` hides `td.check` and its header; the print-only symbol span and `RxState.printSymbol` of I1-e are gone). Done as I1-e2 Task 3 (test first: `tests/test_pdf_sheet.py`); I1-a no longer edits `pdf/sheet.py`. A real PDF was rendered in the dry run: six columns, page width kept.
3. **Spelled rows** follow I1-e3's narrowed rule (contract 4.5 above).
4. **Fonts:** system fonts with Public Sans and Source Serif 4 listed first (I1-f2); self-hosting the two families is a follow-up outside Iteration 1.

## 8. Integration amendments (dry run of the whole chain on a fresh copy, 2026-10-16; the plans were edited to match)

| # | Where two plans met | Resolution (plans changed) |
|---|---|---|
| 1 | `validate_structured` row block: I1-a and I1-c both assign `extra` and both hook after `_ground_row` | Order is `_ground_row`, `dosing.ground_extra` (`extra`), `lasa_row` (`lextra`), row dict `**extra, **lextra`: dose-check outranks look-alike (4.2). I1-c, I1-d |
| 2 | I1-d moves that block into `rowcheck.ground_with_notes` | The moved code already carries `generic`, `lextra`, `elif status == RX_UNVERIFIED_NAME` and the `{issue}` warning; I1-h2 adds `row_extras` there, not in `determinism.py`. I1-d, I1-h2 |
| 3 | `DERIVED_ROW_FIELDS` | Final tuple in 4.1 above. I1-b's restore line is `prev.get(field, "")` (it used the fresh value); I1-c adds `dose_note` to the tuple instead of a separate line (which stamped status-less rows); I1-h2 adds `source` to the tuple instead of the status tuple. I1-b, I1-c, I1-h2 |
| 4 | Format cache key (I1-a raw wording, I1-h3 clinic layer) | One key: `clinic:layer-version:key:rawhash` (`api/format.py`). I1-h3. The dosing reference version is not in the key (cached rows keep their old reference until restart; I1-c, unchanged) |
| 5 | I1-g2's 10% look-alike limit vs I1-a (35% of canonicals have a computed twin) | The share counts only the always-flag (curated) canonicals, 16 of 444 = 3.6%; counting every twin made the bare `build.py --check` fail. I1-g2 |
| 6 | I1-a Task 2 changes `test_candidates` before the raw transcript is plumbed | The edit moved to I1-a Task 3 Step 3b. I1-a |
| 7 | I1-d and I1-h tests use Prednisone (a curated pair) and expect `verified` | They expect `lookalike-check`. I1-d. I1-h2's preserve test compares only the original keys (derived fields are added). I1-h2 |
| 8 | I1-f2 pins "team.js has no tab" but I1-h4 adds it | The two assertions were dropped; I1-h4's tab buttons carry `class="team-tab"` and reuse I1-f2's tab CSS. I1-f2, I1-h4 |
| 9 | I1-e3 CSS heredoc contained a nested code fence (written into `rx.css`); `.rx-sug` never matched the buttons | Fence removed; selector is `.rx-act.sug`. I1-e3 |
| 10 | I1-a's `PILL`/`statusText` lines are deleted again by I1-e2 | Kept (the old pill needs them until I1-e2); noted in I1-a |
| 11 | `determinism.py` line claims (484, 439, 483) are stale in the chain | Chain values: 452 (I1-b), 455 (I1-a), 457 (I1-c), 411 (I1-d, unchanged after). I1-h adds no net line |
