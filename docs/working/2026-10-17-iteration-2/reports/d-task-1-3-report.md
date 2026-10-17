# I2-d Tasks 1-3 report

Status: DONE (uncommitted). Suite 1913 passed, 1 skipped (baseline 1886 + 9 plan tests + 18 hardening tests).

## Files
New: doctor_dictation/core/lexicon/generics_sync.py (304 lines; reader, gates, plan_sync, sync, --check, report; review-sheet and promote are Task 5, not built),
doctor_dictation/core/generics.py (41), tests/test_generics_sync.py (6), tests/test_generics_runtime.py (3), tests/test_generics_sync_edges.py (18),
tests/data/generics_nlem_fixture.csv, generics_nlem_newer_fixture.csv, generics_fixture.json (synthetic).
Edited: core/lexicon/import_rules.json (+ "skip_generics": {}), core/rowcheck.py (+schedule field), core/correction.py (schedule in DERIVED/RECOMPUTED fields).
No generics.json exists; live drugs.json, imported.json, seed_extra.json untouched by this work (a test hashes them around a sync).

## Anchors (dry run on scratch copy i2d/)
All plan anchors held (frozen lexicon holds Thyroxine, Co-Amoxiclav, Cetirizine; Checker, build.check_source/bump_minor/RESERVED_IDS, DERIVED/RECOMPUTED fields, rowcheck dict, screen_unverified). No failing anchor. Adaptations, none loosening an assert:
1. plan_sync was prose only: written (gates, conflict, duplicate, merge, removals, renames, twins with quick-ratio prefilter).
2. Plan test BOM literal was invisible: written as ﻿.
3. Plan test 7 safe-gate assertion was a tautology (filtered to verified rows, then expected []): now compares screen_unverified over all rows to the expected list, and statuses are asserted equal with and without the file.
4. read_csv additions: csv.Error (field over 128 KB) -> clean exit, empty file, blank/odd list name (1-40 chars, no digits-first) refused.
5. A generic present in the file but skipped by a gate (e.g. bad schedule) is NOT a removal (else --apply-removals would drop it on a typo).
6. A lexicon link (`lexicon`) is recomputed on every sync for all entries (kept ones too); lists/lineage untouched.
7. `lists` field in the task text does not exist in the plan (only `schedule` is a row field).
8. tests/test_package_install fails when run from a scratch copy only (editable install points at the real repo): environmental, passes in the real repo.

## Behaviour pinned
CSV (BOM, CRLF, UTF-8 error, upper-case columns, extra columns, row cap, field cap, source_line cap 20, one list per file, schedule H/H1/X/blank, "Schedule X"/lower case, unknown rejected); gates (exact, synonym, Title Case, combination join, shape incl. 80 cap, duplicate with first_line, conflict 2-3 way kept without schedule, curated-skip incl. class dict, one slip never linked and reported as near+twin); sync (byte-stable, no change rewrites nothing, version 0.1.0 -> 0.2.0, --check exit codes and counts, lineage src/id/published/licence/url per source, reused id with another sha refused, corrupt file refused, report written first, report inside repo and reserved ids and missing/short licence/bad date refused with exit 2 before any read, no argparse default for source flags); removals (kept with old lineage; --apply-removals drops only that list, then empty entries; possible_renames); reader (missing/broken file = no marks, entries without lexicon ignored, strictest over lists, case-insensitive, junk tolerated); schedule from the brand's generic, hand-edited name gets none; grounding identical with and without a file except `schedule`; correct_drugs unchanged and a government-only generic stays unknown-medicine.

## Mutations (27 on scratch copies)
26 killed on first run; 1 survivor (empty entries kept after removal) killed by a strengthened test. Final: 0 survivors.

## Concerns
- do_sync with a new source id and identical entries writes (records source, bumps minor); --check reports it as drift. Deliberate, owner may prefer no-write.
- A kept (unchanged-schedule) membership keeps its OLD line/src even if the new edition renumbers the line.
- Rules file lookups for `skip_generics` are exact casefold matches only.
- Task 4 (badge, frontend) and Task 5 (review-sheet/promote) not started; generics_sync.py at 304 lines leaves ~75 for them (<=380 budget).
