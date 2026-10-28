# I2-b Tasks 1-2 report
Status: DONE, uncommitted. Suite 1730 passed, 1 skipped (baseline 1721 + 4 + 4 plan tests + 1 added test).

Files: NEW core/followup.py (63 lines), api/visit.py, api/review.py, tests/test_followup.py, tests/test_followup_routes.py.
Modified: api/format.py (219), api/persistence.py (424), api/app.py, tests/test_isolation_routes.py (CLASSIFIED), tests/test_api_app.py (EXPECTED_ROUTES).

RED in the real repo: both test files failed at collection (no module followup, cannot import visit). GREEN after implementation.

Anchor adaptations
1. format.py: the plan's `@router.post("/api/format")` anchor does not exist; the decorator has `dependencies=[Depends(use_clinic_layer)]`. _answer inserted before it.
2. Plan's `_answer` body omitted `normalized_transcript` (a key the old returns carried). Added it; signature is `_answer(structured, normalized, **rest)` (dropped the unused `raw`).
3. test_followup_routes test 2: no migration (TestClient runs no lifespan) -> "no such table: patients". Added a get_conn/migrate/close after the DB_PATH setenv.
4. tests/test_api_app.py EXPECTED_ROUTES (not in the plan's file list) needed `POST /api/v1/review-date` (2 tests failed otherwise).
5. persistence.py: `datetime` import kept (used at :395); line 254 anchor is now the `_pdf_inputs(...)` line, same code.
6. Dry-run on the scratch copy covered Task 1 fully and the mutation runs; Task 2 anchors were verified directly in the real repo (RED first), not in a prior scratch pass.

Added test (not in plan): visit.today equals server-local day and Save passes the same day to _pdf_inputs (killed two surviving mutants).

Mutation (20 mutants on scratch copy: limits, clamp, week length, range/event/two-duration rules, zero, year=12 months, fortnight, stamp replace-vs-setdefault, visit.today, cache-copy, stamp on correct, stamp on save, PDF day, route clock, route cap, label, route registration): all killed after the added test; 2 survived before it (visit.today body; PDF day).

Concerns
- format.py/correct stamp: `/api/v1/correct` is stamped after _validate; if validate ever strips unknown keys the stamp still wins (stamped last). Save stamps `validated` after preserve_untouched_rx_status.
- Re-print of a saved document (persistence.py ~:395 area) uses its own day logic; unchanged, no date added (Q8).
- Q7: container is UTC; owner should set TZ=Asia/Kolkata.

## Fix round (clinical-safety review)
Principle: a date only for ONE plain, unconditional review interval; everything else gives no date.
- core/followup.py (now ~82 lines, pure): compiled `_REFUSE` list applied before parsing, one comment per class: day after tomorrow; decimals/halves; slash fractions and explicit dates; frequencies; negations; treatment durations (`for N unit`, then, course, continue, complet*); a repeat test's interval (`repeat ... after N unit`; "In 2 weeks with repeat USG" still dates); dropped sign (-, minus, en dash before a digit); conditions/open ends (if, unless, when, only, earlier, SOS, persist*, worse, needed, required, within, maximum, up to); `next N unit` and weekday names. `_RANGE` now takes en/em dash, comma, or a bare space between two numbers; digits no longer split ("10 days" guarded by `(?!\d)`). `review_date` returns "" on OverflowError/ValueError (visit 9999-12-30).
- Plan test changed: "come back in 2 days or if worse" moved from the dated list to the no-date list (coordinator ruling: a condition means no date).
- Tests (tests/test_followup.py, 4 -> 8): table of 56 refused phrases, table of 24 accepted phrases with exact dates, a refuse-word property test (28 words, before and after "review after 1 week"), end-of-calendar test. RED confirmed first in the real repo.
- Mutation (scratch): each of the 10 refuse classes removed, `(?!\d)` removed, range separators reduced, minus/en-dash sign class reduced, overflow guard removed, `_EVENT` removed: all killed. Survivors found and fixed: "parso" (not a duration anyway, removed from the pattern) and unicode-minus/en-dash sign (two phrases added to the table).
- Concerns: refusal is deliberately broad ("for N unit" and any "no"/"per"/"each" word kills the date, e.g. "Review after 1 week for reports" still dates but "Review for 1 week" does not). Hinglish negations beyond nahi/nahin are not covered.
