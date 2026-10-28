# I1-h1 report: clinic formulary rules and table

Status: DONE. Nothing committed, no git writes, no server or browser, DB_PATH always a temp file.

## Tests
- Full suite: 1448 passed, 1 skipped, 1 deselected (baseline 1442 + 6, as expected).
- Order followed: tests written first; collection failed with `ModuleNotFoundError: doctor_dictation.core.formulary` (right reason: module missing); then code; then green.
- New/changed test files under netguard: 0 attempts (6 passed for the two new files; 46 passed incl. the three touched files).
- `test_core_purity` and `test_file_sizes` pass.

## Files
Created: `doctor_dictation/core/formulary.py` (87 lines), `doctor_dictation/db/formulary.py` (41), `doctor_dictation/db/migrations/009_clinic_formulary.sql`, `tests/test_formulary.py`, `tests/test_formulary_db.py`.
Modified (setup values only): `tests/test_db.py` (applied list + `n == 9`), `tests/test_template_scope_db.py`, `tests/test_authorship_db.py`.
No change to `core/determinism.py`, `db/__init__.py`, or any frontend/lexicon file.

## Adaptations and deviations
1. Code and tests are the plan's text verbatim (preflight said it applies as written). Baseline numbers (944) ignored; real 1442 used.
2. Tests strengthened, no new test functions (count stays +6), after the first mutation run showed gaps:
   - `test_clean_name...`: junk list gains `"A12"` and `"B-1"` (3 chars, fewer than 3 letters; the letters rule was untested).
   - `test_layer_version...`: appended asserts for `hint_names()` (cap of `MAX_HINTS` names; the 150-char cap: 4 names of 51 chars give 2). `hint_names` had no test in h1.
3. Plan Interfaces list omits `MAX_WORDS`; it exists in the code (cosmetic, as the preflight noted).
4. Isolation: the table lives in each clinic's own SQLite file (migration reached through `db.migrate`); no query has a clinic column, so isolation depends on the scoped connection. h1 has no cross-clinic test (needs the scoped app; belongs to h4).
5. Preflight R12 (generic column is reserved and always NULL from the page) and R11 (admins should review the tab after demos) are plan-text notes, not code; not added to the plan file by me.

## Mutations (scratch copy in the session scratchpad; 21 run, tests: test_formulary, test_formulary_db, test_db)
Killed (19): key without casefold; clean_name no max words; clean_name any chars; clean_name letters>=3 dropped (after the A12/B-1 fix; survived before); learnable without patient guard; learnable ignoring confirmed rows; learnable without dedupe; learnable without lexicon check; version order-dependent; hint_names without char cap (survived before the fix); ledger plain INSERT (no OR IGNORE); count increments on every call; list_active threshold-1; remove keeps confirm_count; relearn keeps removed_at; remove allows inactive entry; name_key not UNIQUE; ledger without PRIMARY KEY; added_by never set.
Survived (2), both equivalent mutants:
- clean_name without the `3 <=` length bound: the "at least 3 letters" rule already implies length 3.
- list_active without `removed_at IS NULL`: removal always zeroes `confirm_count`, and a re-learn to 2 clears `removed_at`, so the clause is redundant in every reachable state (defence in depth, kept).
Caveat: the "added_by never set" mutant leaves two unused SQL parameters, so it dies on a SQL error, not on an assertion about `added_by`. No test asserts `added_by` equals the confirming user id (tests pass `user_id=None`). Low risk; h3 (API) is the place to pin it.

## Concerns
- A patient's name typed in a medicine cell on two different documents is still learned (guard compares only with the same document's `patientName`); admin removal is the remedy (plan Decision 3).
- `added_by` value is unasserted (see above).

## Fix round
Status: DONE. Suite: 1450 passed, 1 skipped, 1 deselected (+2 tests: person-like/patient-words, added_by activator). Purity and file sizes pass.

Changes:
- `core/formulary.py`: new pure `person_like(name)`; `learnable(structured, confirmed_rows, known_patient_words=None)` skips person-like names and any name with a word of 3+ letters in the set (casefolded).
- Person-like rule as pinned: honorific first word (Dr, Mr, Mrs, Ms, Mx, Prof, Shri, Smt, with or without a dot), OR 2-3 words that are each letters-only and strictly Capitalised (first upper, rest lower) with a first word that is not a form prefix. Decision on 'Zorbexin SR': ACCEPTED, because 'SR' is not Capitalised (strict). 'Tab Zorbexin' accepted (form prefix). 'Zorbexin D3' (digit), 'Zorbexin-Forte Plus' (hyphen), single words, 4-word names accepted. 'RAHUL SHARMA' is rejected (clean_name capitalises it first). Note: the plan's example 'Vitamin D3' is already in the lexicon, so the test uses 'Zorbexin D3'.
- `db/formulary.py`: added_by uses `confirm_count + 1 = THRESHOLD` (activator only); removed_at clear stays `>=`.
- Tests: `test_person_like_names_and_known_patient_words_are_never_learned`, `test_added_by_is_the_user_whose_confirmation_activated_the_name` (real users A, B, C; a not-yet-active name has added_by None; B activates; C does not take over; after removal and re-learn the new activator C is recorded).

Mutations (scratch copy), 9 run, all killed: person-like check removed; honorific rule removed; form-prefix exemption removed; allow 4 words (survived first, killed after pinning a 4-word name); ALLCAPS counts as capitalised; known patient words ignored; no 3-letter floor on known words; added_by back to >=; added_by never updated.

Concerns: a genuine two-word Capitalised brand (e.g. 'Zorbexin Forte') is now never learned (same shape as a person's name); the owner accepted this trade. Rule (c) skipped as ruled (owner risk). `known_patient_words` is not wired yet (h3).
