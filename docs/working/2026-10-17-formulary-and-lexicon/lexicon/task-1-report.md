# Task 1 report (denylist + two hooks)

Status: DONE (uncommitted). Task 0 Step 2 not run (controller's).

## Files
- NEW `doctor_dictation/core/commonwords.py` (36 lines): copied from the scratch reference; `_EN`, `_HI`, `WORDS = frozenset(...)`, 603 words, no imports.
- MOD `doctor_dictation/core/determinism.py` 408 -> 410 lines: import line after `from . import formulary, rowcheck`; two-word split condition (anchor: `if len(w1) < 2 or len(w2) < 3`); pass-2 guard (anchor: `if _ambiguous_for(low):  # two generics claim it`) plus one comment line. Text exactly as the plan.
- NEW `tests/test_commonwords.py`.

## TDD
Red: `ModuleNotFoundError: doctor_dictation.core.commonwords` at collection. After adding the module without hooks: 2 failed (the twice/after case and the Afterfood case), 4 passed. After hooks: green.

## Adaptations (all)
1. Anchors found by symbol text; line numbers moved nothing material (split guard in `correct_drugs` pass 1, pass-2 guard in pass 2).
2. Docstring of commonwords.py is the reference's (mentions "the lexicon import refuses a brand that is one or holds one", i.e. Task 2) instead of the plan's one-liner. Harmless; trim if wanted.
3. Tests: the plan's 4 verbatim, plus 2 more (6 total), and one extra assertion:
   - `test_the_module_is_pure_data_and_the_two_blocks_are_unique`: AST check of no imports, only `frozenset` call; each block deduplicated, blocks disjoint, 603 total.
   - `test_a_normal_brand_is_still_written_as_dictated`: "tab dolotab 650 mg twice daily" -> "tab Dolotab 650 mg twice daily".
   - In test 2: "tab take fen 650 mg" -> "tab Takefen 650 mg" (one ordinary word still joins). Added because the mutation "either word instead of both" survived the plan's tests.
4. "Sorted": the list is NOT globally sorted (plan's text is alphabetical within groups, with appended groups and a Hinglish block). I kept the plan's words exactly (603) and test uniqueness, not order. Say if a sorted file is wanted.

## Results
- Focused set (commonwords, test_determinism*, test_brand_as_dictated, test_file_sizes, test_lasa): 134 passed (before the extra assertion), commonwords now 6 passed.
- Full suite: 1542 passed, 1 skipped, 1 deselected. Baseline measured today WITHOUT my file: 1536 passed (the ledger says 1537), so +6 tests = 1542, not the plan's +4 (1541). Delta explained by the 2 extra tests; ledger baseline is off by one.

## Mutations (scratch copy, `.../scratchpad/mut1/mut.py`, tests/test_commonwords.py only)
7 mutants, 0 survivors in the final test file: split hook removed (killed), pass-2 hook removed (killed), denylist emptied (killed), `twice` removed (killed), `after` removed (killed), `clear` removed (killed), split uses either-word `&` instead of both `<=` (initially SURVIVED, killed after the Takefen assertion).

## Concerns
- Plan expected +4; actual +6. Unsorted list (item 4).
- Other lexicon tests still pass; no data file touched, no DB opened except temp DB_PATH.
