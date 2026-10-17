# Task 2 report: licence gate, five-check importer, synonym table, report, lineage

Status: DONE (uncommitted). Suite: 1548 passed, 1 skipped, 1 deselected (baseline 1542 + 6: the plan's 4 plus 2 extra pins). Focused set (test_lexicon_import, test_determinism, test_commonwords, test_file_sizes, test_dosing_build): 91 passed. tests/test_build*.py and tests/test_lexicon*.py other than test_lexicon_import.py do not exist.

## Files
- Created: `doctor_dictation/core/lexicon/lexicon_import.py` (173 lines), `import_rules.json`, `tests/data/brands_fixture.csv`, `tests/data/conflict_fixture.csv`, `tests/data/lexicon_frozen.json` (byte copy of live drugs.json, 444 entries, 508 brands, v1.1.0, no lineage), `tests/test_lexicon_import.py`.
- Modified: `doctor_dictation/core/lexicon/build.py` 241 -> 281 lines (gate only: `check_source`, `require_source`, flags, widened `do_merge`/`do_check` with unused new parameters, `main` wiring, `sys.path` + `import lexicon_import`).
- Live drugs.json, seed_extra.json and every data file: untouched.

## Method
Test first: wrote fixtures and tests, confirmed 5/5 fail (FileNotFoundError for lexicon_import.py), then implemented, then green. lexicon_import.py is the validated scratch reference minus `overlay` (plan puts it in Task 3).

## Adaptations
- `overlay` omitted from lexicon_import.py (Task 3). The `import lexicon_import` line in build.py carries `noqa F401` because nothing in build.py uses it until Task 3.
- Because the CSV dispatch is Task 3, a CSV merge that PASSES the gate still hits `load_seed` and fails on CSV-as-JSON (writes nothing). Expected per plan.
- The plan's test count is +4; I added 2 tests (+6 total):
  - `test_checker_pools_and_row_order_on_small_synthetic_inputs`: pins that check 5's pool includes EXISTING brands (Zentrabez vs Zentrabex), check 2 within one file (Moravil under two generics), the first row per brand decides (line), a brand key never names a generic.
  - `test_merge_brands_never_loses_an_existing_entrys_aliases_or_brands`: aliases/strengths/forms kept, existing brands first, casefold duplicate ignored, key order sorted, no-op returns [].
- Plan line numbers: build.py insertion points matched; no anchors moved. The `--report` help text says "outside the repository" instead of "outside git".
- `tests/test_build*.py` glob in the instruction matches no file.

## Dry run (read-only, real A1 + A3 CSVs from main checkout data-draft/, planned against the frozen lexicon in memory; nothing written, no --merge run)
rows_read 738, brands_added 206, already_present 58, generics exact 150 / synonym 3 / not_in_lexicon 111, skipped 474: 1-generic 299, 5-one-slip 128, 3-five-letters 28, 2-one-generic 12, shape 5, 4-ordinary-word 2. Changed entries 120, 367 brands in them. Identical to the plan's numbers.

## Mutation testing (scratch copy in scratchpad g2mut, 32 mutants)
All 32 killed: check 1 (fuzzy accepted, synonym table off, resolve through brand keys), check 2 (conflict map ignored, lexicon owner ignored, same-run rows ignored), check 3 (MIN_LETTERS 2, short_ok), check 4 (whole-name only, off), check 5 (cutoff 0.95, conflict-map names out of pool, existing brands out of pool, off), shape off, merge (drop old brands, drop aliases, new first, lineage dropped, no casefold dedupe), plan (source id lost, already_present never counted, last row wins), read_csv (Rx prefix kept, no flat-case), gate (name min, licence min, report not required, map not required, reserved ids, id pattern, `--check` not gated).
First pass had 3 survivors (one was an equivalent mutant: `self.names[key]` inside `key in self.generics`; replaced by the real mutant `key in self.names`); the 2 extra tests killed the other two.

## Concerns
- Two tests beyond the plan's +4; Task 3/4 baselines in the plan table shift by +2.
- Check 5 on the real list is aggressive (128 one-slip skips, both sides of a pair); this is the owner's rule, not a defect.

## Fix round (rulings I1, I2, M2, M4, M5; M1 to Task 5 clinician sample list, M3 unchanged)
Suite: 1550 passed, 1 skipped, 1 deselected (+2 tests: gate-before-read, report path + check_source). Focused set 93 passed. build.py 285 lines, lexicon_import.py 179.
- I1: `test_the_gate_refuses_before_any_file_is_read_or_written` patches Path.read_bytes/read_text/open/is_file/exists so any touch of the CSV or conflict map raises; missing and 5-char licence, `--merge` and `--check` all exit 2, "Nothing was read or written", nothing created.
- I2: later rows of an already-decided brand are skipped with id `duplicate` (+ `first_line`), documented in the lexicon_import.py docstring as NOT a sixth check. Fixture: Zentramol line 3 -> skipped; added 5 + already_present 1 + skipped 14 == rows_read 20 (pinned). First-row-decides pinned by line->checks. Task 3's plan assertion `len(report["skipped"]) == 13` must become 14. Real A1 dry run unchanged (no duplicate rows): 206 / 58 / 474, 206+58+474 = 738.
- M2: `build.REPO_ROOT`; `--report` resolving inside it is refused by parser.error (exit 2, nothing read or written), for merge and check; tmp_path report still works (all merge tests).
- M4: test comment and lexicon_import.py docstring now say caps are normalised, never rejected.
- M5: `check_source` raises ValueError (message keeps "Nothing was read or written"); `require_source` converts it to parser.error (exit 2). Task 4's `promotion.apply` must catch ValueError from check_source (plan says SystemExit).
- Mutations: 42 mutants on the scratch copy, all killed, including gate after read (merge, check, conflict-map is_file), report inside repo allowed, repo-root check neutered, check_source raising SystemExit / never raising, duplicate not reported / renamed / wrong first_line.
