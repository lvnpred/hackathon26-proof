# I1-h2 report (grounding, hints, source)

Status: complete, uncommitted. Full suite 1457 passed, 1 skipped, 1 deselected (baseline 1450 + 7 new tests).
Offline guard on tests/test_formulary.py: 11 passed, NETGUARD attempts 0.

## Changes (real symbols, not the stale plan diffs)
- `core/formulary.py` (147 lines): imports `suggest_candidates`, adds `VERIFIED/UNVERIFIED_NAME/LOOKALIKE`, `_twin` (lru_cache keyed by name key + lexicon_version), `_lexicon_twin`, `ground_clinic`, `source_of`, `row_extras`.
- `core/determinism.py` (408, net 0): `from . import formulary, rowcheck`; unknown branch of `_ground_row` returns `formulary.ground_clinic(...) or (RX_UNKNOWN_MEDICINE, ...)`.
- `core/rowcheck.py`: `from . import dosing, formulary`; `**formulary.row_extras(name, match, status)` after `**extra, **lextra,` in the row dict (~:76). Spread last, so a clinic look-alike's `lookalike` overrides lasa_row's empty one.
- `core/hints.py`: `_doctor_canonical` keeps names on the active layer; `build_hints` adds `active_layer().hint_names()` after the doctor's names, before lexicon names.
- `core/correction.py` (419): `"source"` added to `DERIVED_ROW_FIELDS`; `RECOMPUTED_ROW_FIELDS["source"]` = `source_of(name, lexicon_match)` (R1). So `source` is recomputed server-side from the restored row and the active layer; status-less rows get none.
- `tests/test_formulary.py`: +7 tests (plan said +4; split plus R1/R3/R4 additions).

## Adaptations vs plan text
1. No `candidates` import edit in determinism (gone); real import `from . import formulary, rowcheck`.
2. Row dict edit lives in `rowcheck.ground_with_notes`, not determinism.
3. `source` added to `DERIVED_ROW_FIELDS` plus `RECOMPUTED_ROW_FIELDS` (not restored from prev, per R1); `ops._regrounded` already drops all DERIVED fields, so a renamed row loses `source`.
4. R2: `ground_clinic` returns issue None for look-alike; test asserts `ground_rx` issues == [].
5. `row_extras` uses `source_of` (clinic only when lexicon_match empty AND layer has the name): the layer can never override a lexicon match.
6. Page-shaped correction test (no `source` in current) plus a node run of `frontend/rxstate.js` proving state `known` (skipped if node is absent).
7. R3 test: formulary-only drug with 10000 mg 1-1-1 stays `verified`, `source clinic`, no `dose_note`, no strength options.
8. R4 test goes through `normalize_transcript` (metformn -> Metformin, amlodipin besy -> Amlodipine besy; zorbexin untouched) with the limit written as a comment. `normalize_transcript` unchanged.

## What h3 must wire
- `POST /api/v1/documents` (api/persistence.py ~:200): add `dependencies=[Depends(use_clinic_layer)]` so Save recomputes `source` (R1); extend the pin test that counts routes using it. Without it, the layer is empty on Save and a clinic name is stored with `source "lexicon"` (UI says "Matched").
- `use_clinic_layer` also on format, correct, transcribe, rx (`/api/v1/check-row`); /correct needs it for the recompute to work.
- Existing h-level items: `known_patient_words`, per-request activate, cache key with `ClinicLayer.version`.

## Mutations (14 on scratch copies in scratchpad/h2mut, run against tests/test_formulary.py)
Killed: layer lookup, source not recomputed, issue on look-alike, layer overriding lexicon, uncapped hints, no look-alike check, lookalike field missing, source not a derived field, transcript check skipped, row_extras missing, hook missing in `_ground_row`, twin always truthy.
First round two survivors (hints omit layer names; `_doctor_canonical` ignores layer). Fixed by strengthening the hints test (no-doctor-history call must lead with `hint_names()`; an old layer name used by the doctor must still lead). Rerun: 0 survivors.

## Concerns
- R4 limit stays (owner flag): a clinic name within 0.84 of a lexicon spelling is rewritten before grounding; no-key fallback extracts only lexicon names.
- `_twin` costs ~10-15 ms cold per name (cached 512); the h2 look-alike check also runs on every `ground_rx` pass for clinic names.
- A clinic look-alike (R13) is checked against the lexicon only; it stays `lookalike-check` on every save until the doctor confirms.
- `ground_rx` rows do not carry `source` (only `validate_structured` rows do), as in the plan.

## Fix round
Gap: a name removed from the layer (or a request without the layer) restored `verified` from the page row but `source` flipped to `lexicon` with an empty `lexicon_match` (green "Matched" for a name nothing backs).
Fix (`core/correction.py`, 424 lines): in `preserve_untouched_rx_status`, a restored `verified` status with no `lexicon_match` and no layer entry is regraded to `unknown-medicine` (plus the standard `[unverified: confirm with doctor]` marker, added once). The `RECOMPUTED_ROW_FIELDS["source"]` entry now returns `""` unless the row has a lexicon match or the layer knows the name, so `lexicon` is never emitted with an empty match. Backed rows, renamed rows, patch-named rows and status-less rows behave as before; `heard`/`lookalike` are still restored from the prior row.
Tests (+2, `tests/test_formulary.py`): layer has the name -> verified/clinic kept; empty layer -> `unknown-medicine`, source "", marker, lexicon row unaffected, status-less and patch-named rows unchanged (through `preserve_untouched_rx_status`); and through `POST /api/v1/correct` offline (empty layer -> `unknown-medicine`, source ""). R4 test gained one line (unrewritten `Metformn` still fuzzy-matches the lexicon).
Final design: helper `_backed(row)` = lexicon_match, or `_canonical_lookup(name)` (a row from an older save may lack the `lexicon_match` key; test_safety caught this), or an active layer entry. Used by both the regrade and the source recompute.
Mutations: 8 on scratch copies (no regrade, backed ignoring layer, ignoring lexicon lookup, source lexicon without backing, no marker, constant source, backed always true, backed ignoring lexicon_match): 7 killed; the survivor (ignoring `lexicon_match` when the name lookup remains) is equivalent in practice, since a match implies the name resolves.
Suite: 1459 passed, 1 skipped, 1 deselected.
For h3 (NOT done here): the empty-layer fail-loud guard. When the layer is not active on /correct or Save, a clinic row is now regraded to `unknown-medicine` (safe direction, but a clinician sees a spurious flag), so h3 must make sure `use_clinic_layer` is on those routes and consider failing loudly when the layer failed to load.
