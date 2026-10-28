# Independent re-verification of the lexicon import (2026-10-17)

A fresh reviewer repeated the measurements on a copy, after three fix rounds by the original implementer (who had once reported a wrong claim). The live `drugs.json` was never touched. **Verdict: safe to proceed to the clinician review.** No Critical finding.

## Import (runbook Step 3 flags verbatim)

| Measure | Result |
|---|---|
| Rows read / added / already present / skipped | 738 / 155 / 58 / 525 |
| Skips by first failed check | 299 generic, 130 one-slip, 49 curated, 28 short, 12 two-generic, 5 shape, 2 ordinary |
| Generics | exact 150, synonym 3, not in lexicon 111 |
| Version, entries | 1.1.0 -> 1.2.0, 444 |
| Line counts | `drugs.json` 7,646 -> 8,483; `imported.json` 2,601 |
| `--check` | OK |
| Second run | no change; sha256 of `drugs.json`, `imported.json` and the report identical |
| Full suite | 1693 passed, 1 skipped, 1 deselected on the live worktree and on the copy |

## Safety measurements, written from scratch

| Measure | Result |
|---|---|
| 150 new sentences (anatomy, findings, diet, months, people, places, Hinglish) | 0 differences between live and imported lexicon; 20 change at all (spoken numbers to digits), identical on both |
| 155 added brands in 3 forms (465) | 0 rewritten |
| A3 brands as "tablet X 500 mg" (23,614) | wrong-drug rewrites 328 before, 326 after, 0 new, 2 gone (Anti-Thyrox, Emeset Odt) |
| Dictionary scan (220,263 words of 4-14 letters, alone and in a carrier sentence) | live changes 930, imported 940: 5 new rewrites, all rare words: etnean -> Betnelan, lipan -> Clipan, nitrian -> Niftran, pactolus -> Actoluse, populus -> Potplus |
| "works in the garden, allergic rhinitis" | no Rx row |

The 5 dictionary rewrites are the same one-slip class as the "garden" problem but only for rare words (a river, a tribe, a plant genus). They are ACCEPTED for now. Betnelan is a real betamethasone brand. The owner can add any of them to `skip_brands`.

## Curated skips (11 of 49 read against the CSV)

Right: Arden, Gastrium, Rumorf, Advent, Eurythmic, Salazar, Iwata, Magnesium Sulphate, Gris ODT (Gris is griseofulvin, wrong link). Defensible: Singulair (a real brand, skipped to protect "singular"; costs recognition only), Duodopa (link looks correct, skipped as a combination drug). Suboxone is not in the A1 CSV under that spelling.

## API check (offline, stub providers, blank keys, temp DB)

Six new brands moved from `unknown-medicine` (live) to a grounded status (imported). `check-row` matched `/api/format` for each. One oddity to look at later: "tablet Actoluse 500 mg" is `verified` for Lactulose although Lactulose is a syrup, so a 500 mg tablet should read `unverified-strength`. Cause not checked (probably a lexicon entry without strengths, which is existing behaviour).

## Clinician sheets

`clinician_review_sheet.csv` has 155 rows and its (brand, generic) pairs equal the 155 added brands exactly. `clinician_sample_60.csv` is a subset (23 flagged of 60; 56 flagged of 155). On 25 random rows the `doubtful` column was reasonable. Possibly under-flagged, worth a clinician glance: Pilotbg (Pilocarpine as an oral tablet), Dolotram, Deecee (DEC).

## Runbook findings (fixed in the plan)

The re-run counts differ from the first run (`brands_added=0`, `already_present=213`): documented. Python must run with `PYTHONPATH=<copy>` when working from a copy (the venv is an editable install of another checkout): documented. The git rollback commands were not exercised (no git writes): the plan says to try them once on a test branch. A bare temp DB without the `clinic_formulary` table logs a harmless "clinic formulary unavailable" traceback per call (test-only).
