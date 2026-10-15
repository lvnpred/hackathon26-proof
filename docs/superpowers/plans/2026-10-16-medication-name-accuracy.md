# Medication-name accuracy: proposal

**Status:** PROPOSAL, not approved for execution. Written 2026-10-16. Turn the approved items into task-by-task plans before building.

## Summary

The app already handles drugs it does not know: an unknown name is flagged `unknown-medicine`, and saving is blocked until the doctor confirms it. The real risk is different. Speech-to-text can hear a look-alike drug that is **also in the lexicon** (Prednisone for Prednisolone), and the app then shows a green "verified" tick. Recommended order:

1. Close that silent-wrong gap (P1).
2. Widen the lexicon and give the speech engine more hint names (P2).
3. Learn each clinic's own drugs (P2).
4. Measure every step on real dictations (runs alongside all of the above).

## How names flow today

```
audio → speech-to-text (whisper-1 + ~70 hint names) → correct_drugs (fuzzy-fix against lexicon)
      → LLM extracts rows → ground: in lexicon? in transcript? strength known?
      → up to 2 repair rounds with sound-alike suggestions → status pill → save is blocked unless verified or confirmed
```

What works: in a sample of 12 drugs missing from the lexicon (toradol, metolazone, amiloride, heparin, insulin, ranolazine, trimetazidine, losec, zantac, ...), every one came through unchanged and was flagged `unknown-medicine`. None was quietly swapped for another drug at the 0.84 fuzzy cutoff.

## Gaps found (each tested on 2026-10-16)

1. **A mix-up between two lexicon drugs gets a green tick.** Grounding checks the *normalized* transcript (`core/determinism.py:257`, `api/format.py:127`), which the app's own auto-correction has already rewritten. If speech-to-text writes "Prednisone" when the doctor said "Prednisolone", the row passes both checks (in the lexicon, in the transcript). The tick's tooltip "Verified: in transcript and medicine list" (`frontend/app.js:58`) is then wrong. The lexicon contains about **120 look-alike pairs** (spelling ratio 0.75 or more, or the same phonetic key), for example:
   - Prednisone / Prednisolone
   - Citalopram / Escitalopram
   - Norfloxacin / Ofloxacin
   - Carbamazepine / Oxcarbazepine
   - Dapagliflozin / Empagliflozin
   - Clonazepam / Lorazepam
   - Acyclovir / Valacyclovir

   Comparing spellings cannot catch this class of error.
2. **The lexicon is small for Indian practice.** `core/lexicon/drugs.json` v1.1.0 has 444 generics and 508 brands. Missing drugs (for example heparin, insulin, Pan-D, Losec) land as red "!" rows that the doctor must check by hand.
3. **Brand names are swapped for generics before the LLM sees the text.** `Tab Zyloric 100` becomes `Tab Allopurinol 100` (`core/determinism.py:107-114`, `:178-180`). The dictated brand never reaches the printout. This happens as a side effect, not as a stated policy.
4. **The speech engine gets only a few hints.** About 70 names fit in `MAX_HINT_CHARS = 500` (`core/hints.py:13`), out of roughly 950 known names. The engine is `whisper-1` (`providers/stt/openai.py:21`).
5. **Nothing is learned.** When a doctor confirms an unknown drug, it is still unknown next time. `_doctor_canonical` drops any non-lexicon name from the hints (`core/hints.py:26-34`).
6. **Strength checks are partial.** 79 entries list no strengths, so any strength passes for them. There is no dose-range check and no check that the form is plausible (for example, syrup for a tablet-only drug).

## Proposed changes

| # | Change | Fixes | Effort | Where |
|---|---|---|---|---|
| P1 | **Look-alike guard:** build a table of look-alike pairs (computed from the lexicon plus a published list of easily confused drug names). A row whose drug has a twin gets a new status `lookalike-check` (amber) with "Did you mean X?" and needs one tap to confirm. | 1 | S-M | new `core/lasa.py`; `_ground_row` |
| P1 | **Indication check:** one LLM call asks whether each drug fits the dictated diagnosis (Hydralazine for urticaria is flagged; Hydroxyzine fits). It only adds a flag and never changes a row. | 1, and errors where the lexicon has no twin | M | after grounding in `api/format.py` |
| P1 | **Show what was heard:** keep the original transcript words for each row and show "heard: *tam sulosin* → Tamsulosin" on the pill. Split the pill text into "auto-corrected" and "exact match". | 1, 3 | S | `validate_structured`; `frontend/app.js` PILL |
| P2 | **Bigger lexicon:** import a public Indian brand-to-generic dataset (licence permitting; the CDSCO-approved list for generics) through `build.py --merge`. Target about 5,000 brands for the drug classes these clinics use. | 2 | M | `core/lexicon/` |
| P2 | **Better speech engine with more hints:** benchmark `gpt-4o-transcribe` and plan E, ElevenLabs Scribe v2 Medical (`2026-10-13-e-elevenlabs-scribe-provider.md`; up to 1,000 key terms, so a whole clinic formulary fits). | 4 | S once the benchmark exists | `providers/stt/` |
| P2 | **Clinic formulary:** a drug the doctor confirms twice is added to that clinic's own list, which then feeds the alias map, the hints and verification. An admin can remove entries. | 5 | M | new DB table; a per-clinic layer in `_alias_map` |
| P3 | **Brand policy:** print "Allopurinol (Zyloric)" or the brand as dictated, depending on a setting. `correct_drugs` stops rewriting brands, and the generic goes in `lexicon_match`. | 3 | S | `core/determinism.py` |
| P3 | **Dose sanity:** a max-dose range per lexicon entry, and a check that the form is allowed for the drug. | 6 | M | lexicon schema |
| P3 | **Mixed-case printing for look-alike pairs** on the PDF (hydrOXYzine / hydrALAZINE). | Pharmacist misreads | S | `pdf/` |

Ordering rule: a larger lexicon creates more look-alike pairs, so the P1 look-alike guard must ship **before or with** the P2 lexicon import, not after.

## Measurement

The benchmark harness exists (`bench/run.py`, `drug_recall` in `bench/metrics.py:38`). Add two scores:

1. **End-to-end name and strength accuracy.** Audio goes in, rows come out, and each row's name and strength are compared with a hand-checked answer. Today's score only checks whether the drug name appears in the transcript.
2. **Silent-wrong rate:** rows marked verified whose name is actually wrong. This is the safety number; the target is 0. Also track the share of rows that needed a tap, so the guards do not nag the doctor into ignoring them.

Data:
- 50-100 real, consented, de-identified dictations, as the `bench/run.py` docstring requires.
- A hand-read set of look-alike phrases, spoken by the actual doctors.

## Open decisions (user)

1. Approve P1 (look-alike guard, indication check, "heard" text) as the first plan to write in detail.
2. Brand policy: print the generic, the brand, or both?
3. Can 50-100 consented dictations be collected for the benchmark?

## Not done or not verified

- No code was changed.
- Dataset licences were not checked.
- ElevenLabs and OpenAI pricing was not checked.
- The pair count (about 120) uses spelling ratio and phonetic key only. A clinical look-alike list would add more pairs.
