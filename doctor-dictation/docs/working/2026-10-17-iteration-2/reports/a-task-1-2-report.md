# I2-a Tasks 1-2 report (server side)

Status: DONE, uncommitted. Full suite: 1702 passed, 1 skipped (1694 + 8: T1 3 tests, T2 5 tests). Stays under file limits (rowcheck 148, candidates 139, correction 434 lines).

Changed: core/surface.py (_generic_of = lexicon match), core/candidates.py (scored_spellings), core/rowcheck.py (options, did_you_mean, _sound_options, constants, row hook), core/correction.py (two derived + recomputed fields), tests/test_brand_as_dictated.py (3 deliberate expectation changes, lines 96, 97, 351). New: tests/test_generic_consistency.py, tests/test_did_you_mean.py.

Anchor dry-run (scratch copy): every code anchor matched; no failures. Adaptations:
1. Plan's test_the_generic_survives_correct_and_save omitted the schema: sqlite "no such table: patients". Added dbmod.migrate(conn) after get_conn (same pattern as test_save_keeps_generic_for_a_row_the_client_sent_without_it); conn opened before the POST, not after.
2. Plan said test_brand_as_dictated lines :351-352; real change is the second tuple at line 351 only (one line). Lines 96/97 as planned.
3. Strengthened (no assert loosened): test_options now also has a clinic name Prednizone that sounds like the matched row Prednisone and asserts it is not offered (mutation "clinic names for matched rows" survived the plan's Zorbexin check, which was vacuous).
4. RED proof: shown on the scratch copy (ImportError scored_spellings; 3 T1 tests failing with ('Cetirizine', ...,'') vs expected). In the real repo my first RED command had a shell quoting error, so edits were applied before a real-repo RED run; the scratch RED is identical code/tests.

Safety: no status, name, instructions or Save-gate code changed; did_you_mean only on unknown-medicine; test asserts screen_unverified still blocks both rows and instructions keep the unverified marker.

Mutations (16 on scratch copies): 16 killed after item 3, 1 survived before it. Covered: generic brand-only, generic empty, INLINE_MIN, INLINE_GAP, look-alike guard, status gate, same-generic rival, hook missing, stale did_you_mean in preserve, generic recompute guard dropped, canonical-not-spelling, twin reason lost, clinic names for matched rows, MAX_OPTIONS, DERIVED tuple, did_you_mean_generic.

Concerns: (a) frozen_lexicon pins the did_you_mean tests to v1.1.0; the live v1.2.0 first-authoring path for citrizene/croissin is only tested via frozen lexicon. (b) correction.py now imports rowcheck at module level (no cycle, test_core_purity and imports green). (c) Task 3+ (frontend/pdf) not done; the ledger test count after T1-2 is 1702.

## Fix round
Suite: 1718 passed, 1 skipped (baseline 1708 + 10: 5 in test_did_you_mean.py, 5 in the new tests/test_lexicon_company_names.py).

1. Performance (8-row probe, 4 unknown, rules path, TestClient, median of 7; bench in scratchpad/bench/bench.py):
   before /api/format 72.6 ms, /api/v1/correct 189.1 ms; after, warm cache 14.0 / 14.1 ms; after, cold cache (cache cleared per call) 32.6 / 32.7 ms. Targets 40 / 60 met cold.
   Changes: rowcheck.did_you_mean cached (bounded 512, key = letters of the name + the ClinicLayer object, entry holds the lexicon list and is ignored when the list is not the loaded one; usage/order changes build a new layer so they invalidate too, which a version-string key would miss); `_best_alike` split out; correction.py computes it once per row for both fields (DID_YOU_MEAN_FIELDS, removed from RECOMPUTED_ROW_FIELDS); candidates.scored_spellings skips rows whose upper bound (shared-letter ratio + 0.15) is under MIN_SCORE (cold cost 13-16 ms -> ~4.5 ms per name; exactness tested on 1100 probes and pinned by a test).
   NOTE: my first "after" numbers were measured against a scratch copy shadowing the package (script dir on sys.path); redone from a separate directory.
2. Lexicon: Combiflam originated in imported.json (A1 import; drugs.json carries it, seed_extra.json never had it): removed from imported.json Ibuprofen and drugs.json (via build). PREMISE CORRECTION: "Cipla" is NOT an alias; it verified as Propranolol through the near-spelling cutoff (0.84) to the real brand `Ciplar` (seed_extra.json + imported.json overlay). Removed brand `Ciplar` from seed_extra.json AND imported.json (the overlay would re-append it). Ciplar is a real Cipla propranolol brand: a clinician may prefer a fuzzy-match guard instead (not done; ruling said unknown is the safe direction).
   Files: core/lexicon/seed_extra.json (-1 line), imported.json (-2), drugs.json (-2 brands, version 1.2.0 -> 1.3.0 by `build.py --merge`, default seed; minor bump rule). `build.py --check` exit 0; second --merge: no change, sha256 identical (05186ca6dd97a1a0da7a64cef62c809684ec0d2acb99255786a8b72f0a802802). drugs.json/imported.json were modified here on explicit coordinator ruling.
3. Live-lexicon test (no frozen fixture): citrizene -> Cetirizine/Cetirizine, croissin -> Crocin/Paracetamol; company-name regression list (19 spellings): 0 hits after the fix.
4. Audit: .superpowers/sdd/2026-10-17-i2/lexicon-audit.md; 11 combination candidates, 6 suffix families spanning two generics, about 12 unplaceable brand names; 0 company names, 0 cross-entry brand collisions.
Mutations (scratch copies, 12): cache key without layer (2 variants), lexicon identity unchecked, cache unbounded, shared dict on hit, status gate bypass, computed twice again, bound without key bonus, bound skipping everything, Combiflam restored, Ciplar restored, company alias added: all killed (the bound mutation survived until test_the_pruned_scan_gives_exactly_the_unpruned_result was added).
Concerns: tests that fake `_sound_options` must call `_clear_dym_cache()` (done in the existing test); the pruned scan test takes ~5 s; Ciplar removal drops a real brand.
