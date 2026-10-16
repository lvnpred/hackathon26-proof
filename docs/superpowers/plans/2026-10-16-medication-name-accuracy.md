# Medication-name accuracy: proposal

**Status:** Iteration 1 plan and the Claude Design canvas approved by the owner on 2026-10-16 ("keep everything"); no code written yet. The accuracy track below (P1 to P3) remains a proposal. Written 2026-10-16, enriched the same day with a UI-first iteration (section "Iteration 1"). Turn the approved items into task-by-task plans before building.

## Iteration 1: UI first (added 2026-10-16)

**Direction from the doctor/owner:** make the experience better first. The doctor should see at a glance whether a medicine and its dose are right or need a decision, fix one row without disturbing the others, and understand what the app is doing at each step. Backend accuracy work (P1 to P3 below) follows the UI and feeds it.

### 1. Row states: "matches" or "you decide"

Today a row shows one pill (`PILL`, `frontend/app.js:57-63`) and a separate Confirm button (`frontend/app.js:915-921`). Replace it with one **match state per row**, built from two independent checks, medicine name and dose:

| State | Meaning | Colour/icon | What the doctor does |
|---|---|---|---|
| Matched | Name is in the medicine list and the dictated strength is one the drug comes in | green check | nothing |
| Check dose | Name matches, but the strength is missing, not in the known list, or far from the usual adult dose | amber "±" | tap a suggested strength chip, or type |
| Confirm medicine | Name unknown, unclear, or has a look-alike (needs P1 for the look-alike case) | red/amber "!" | tap **Confirm**, or **Spell it** |
| Confirmed by doctor | The doctor explicitly accepted it (already exists, `state.confirmed`) | green check with "you" mark | nothing |

Sketch of one row (not final; Claude Design polishes it, see section 5):

```
 1  Tab  Amlodipine  [5 mg] [10 mg]   1-0-0   30 days   after food      ± Check dose
                      ^ ghost chips: tap to set          
 2  Tab  Prednisone  10 mg           1-0-1   5 days                   ! Confirm  [ Spell it ]
                      heard: "prednisone"
 3  Cap  Omeprazole  20 mg           1-0-0   14 days   empty stomach   ✓ Matched
```

Rules that keep this safe:
- A suggested strength is a **ghost chip**. It is never written into the row, never verified, and never printed until the doctor taps it. Tapping sets the strength and marks only that row's dose as doctor-chosen.
- A dictated strength that is in the drug's list is **Matched**, with no tap needed. A dictated strength not in the list becomes **Check dose** and keeps what was dictated.
- The state is always explained in words on hover/focus ("Strength 15 mg is not a usual tablet size for Amlodipine"), not by colour alone.

### 2. Dosage suggestions from a prebuilt reference

- Source of truth is a **prebuilt, versioned reference file**, separate from the name lexicon (`core/lexicon/drugs.json`, which already carries `strengths` per drug, for example Acarbose: 25 mg, 50 mg; 79 of 444 entries have none). Proposed shape, one entry per generic:
  ```json
  {"canonical": "Amlodipine", "form": "Tab.", "strengths": ["2.5 mg","5 mg","10 mg"],
   "adult": {"usual": "5 mg", "freq": "once daily", "max_daily": "10 mg"},
   "source": "...", "reviewed": false}
  ```
  A separate file means the monthly rebuild replaces only dosing data and never touches name matching.
- "Suggested on 10 mg or 20 mg based on the adult dosage" means: the **usual adult strength** is the highlighted chip, other tablet strengths follow it.
- Stage the work so the UI is not blocked on the new data: **UI iteration 1 ships chips from the existing `strengths` list** (no new data needed). The `adult` block adds the highlight and the "far from usual" warning when the reference file lands.
- Every entry carries `source`, `built_at` and `reviewed`. Entries not reviewed by a clinician show the chip but never trigger a dose-range flag (section 2b).
- **Not this iteration:** the monthly rebuild action. Design for it now (idempotent build script, a `version` and `built_at` in the file, shown in a small "Dosage reference: 2026-10" footer) so the action later is just "run the build, swap the file, show the new version". No scheduler, no admin button, no rebuild UI in iteration 1.
- Not verified: which public sources to build from (candidates: India's essential-medicines list, WHO model list, a US drug-label dataset, RxNorm for strengths). Licences and structure are unchecked. LLM-written dosing must not be the source of truth.

### 2b. Dose-range check (moved into Iteration 1)

The same reference file that feeds the chips also drives a check on the **daily total**, because the `adult` block already holds `usual` and `max_daily`. (The current lexicon holds strengths only, no maximum dose, so the `max_daily` values arrive with the reference file in build step 5.)

How a row is checked, with a worked example:

```
row: Tab Paracetamol 650 mg, dose "1-1-1-1", duration 5 days
daily total = 650 mg x (1+1+1+1) = 2600 mg      reference: adult max_daily 4000 mg  -> in range, no flag

row: Tab Paracetamol 1000 mg, dose "1-1-1-1"
daily total = 1000 mg x 4 = 4000 mg             -> at the limit, no flag
row: Tab Paracetamol 1000 mg, dose "2-2-2-2"
daily total = 8000 mg                            -> above max: "Check dose" (amber)
             reason on the row: "8000 mg a day. Usual adult maximum is 4000 mg."
```

- **Pure function, no AI:** a new `core/dosecheck.py` takes strength, dose pattern, the reference entry and the patient age, and returns `in-range`, `above-max` or `cannot-check`. Same inputs always give the same answer, so it is easy to test.
- **Reads the dose pattern the app already stores** (`dose` column, `frontend/app.js:861`): numeric patterns like `1-0-1` and `1/2-0-1/2`, and common words (OD, BD, TDS, QID). SOS or free text returns `cannot-check`.
- **`cannot-check` never looks like a pass.** It shows no "in range" claim. Matched means name and strength match, and the tooltip says dose range was not checked.
- **Adult only.** The patient's age is on the sheet (`pAge`). Under 18, or age not written, the adult range does not apply: no flag, with a note "adult range; age not confirmed". Paediatric ranges are out of scope.
- **Also checks the form:** a strength that does not fit the form (a 500 mg syrup of a tablet-only drug) is flagged with the same amber state.
- **What a flag does:** a flagged row needs one tap (Confirm, or pick a strength chip), like the other amber states. A doctor may legitimately exceed a usual maximum, so it is never a hard stop.
- **Only reviewed entries flag.** Unreviewed reference entries produce `cannot-check`, so a wrong number in the file cannot nag the doctor or hide a real error.
- **Test cases to write first:** paracetamol 4 g boundary; fractions; BD vs `1-0-1` agree; unit mismatch (mcg vs mg); age under 18; unparseable pattern; drug not in reference.

### 2c. Brand policy: print the brand as dictated (decided 2026-10-16)

- The prescription prints the name the doctor said. "Tab Zyloric 100" prints as "Tab Zyloric 100", not "Tab Allopurinol 100".
- `correct_drugs` stops rewriting a brand into its generic (`core/determinism.py:107-114`, `:178-180`). It still fixes misheard spellings of the brand ("zyloric" heard as "zylorik").
- The generic is kept in `lexicon_match` and used for everything behind the scenes: verification, the look-alike guard, strength chips and the dose-range check all look the brand up through its generic.
- **On screen only**, the row shows the generic as a small second line ("generic: Allopurinol"). It never prints. This gives the doctor the safety of seeing the generic without changing the printout. (If "both" was meant to print too, say so; it would be a setting, not a code rewrite.)
- Test cases: a brand with one generic; a brand shared by two generics (a combination product) flags for confirmation instead of guessing; a brand not in the list stays as dictated and is flagged unknown, as today.

### 2d. Larger lexicon and clinic formulary (added to Iteration 1, after the UI steps)

Larger lexicon:
- Import a public Indian brand-to-generic dataset through `build.py --merge`, aiming for about 5,000 brands. Check the licence first; nothing is imported until that is confirmed.
- Imported entries carry `source` and appear in the reference as `reviewed: false` for dosing, so they get name matching but no dose-range flags.
- Ships **with or after** the look-alike guard, never before, because more drugs means more look-alike pairs.

Clinic formulary (each clinic's own drug list):
- A drug the doctor confirms on two separate saved prescriptions is added to that clinic's list. A new table keyed by clinic holds name, optional generic, confirm count, who added it and when.
- The list feeds the name matcher (a per-clinic layer in `_alias_map`), the speech hints and verification. Another clinic never sees it (the clinic scoping from M1 applies).
- Learned drugs show a lighter state, "Known to your clinic", not the green Matched, because it means "seen and confirmed before", not "in the reference". They get no dose-range check (`cannot-check`) until a reference entry exists.
- The look-alike guard also runs against the learned list, so a learned name cannot silently match a lexicon twin.
- A clinic admin can remove an entry (on the Team screen, `frontend/team.js`). A wrongly confirmed name would otherwise be learned too; removal and the "confirm twice" rule are the safeguards.

### 3. Row-level "Spell it"

A button on any row that needs a decision. It changes **only that row**; no other row, and not the transcript, is touched.

```
 Spell it  ->  [ type here: p r e d n i s o l o n e ]   or   🎤 say the letters
               Suggestions: Prednisolone · Prednisone · Prednisolone-acetate
               [ Use this ]
```

- Three ways in, in order of speed: tap a suggestion (sound-alikes come from the lexicon matcher that already powers repair suggestions), type the name, or hold the mic and spell it aloud.
- After a choice, the row is **re-checked on its own**: a new small endpoint (working name `POST /api/v1/rx/check-row`, takes one row plus the transcript, returns the status and suggestions) reuses `_ground_row` (`core/determinism.py:247`). Today no per-row check exists; `/api/format` (`api/format.py:80`) re-grounds the whole sheet.
- A name the doctor spelled is marked **Confirmed by doctor**, so it is not blocked at save (same mechanism as `state.confirmed`).
- Undo stays available through the existing undo button.
- Voice spelling is the riskiest part: letter names transcribe badly ("b" versus "d"). Ship type and suggestions first; add voice spelling only if the benchmark shows it works.

### 4. Profile and upload: show the steps

The current Profile dialog (`frontend/index.html:122-165`) and Letterhead panel (`frontend/index.html:168-235`) are good. Make the order visible without changing the content.

- **Profile**: add a three-step header, `1 Clinic · 2 My details · 3 Letterhead`, each marked done once its fields are valid. The existing hint "Save your profile changes first, then upload a letterhead" (`index.html:157`) becomes the natural step 3 gate instead of a hint.
- **Letterhead**: add a four-step header, `1 Upload · 2 Reading · 3 Review · 4 Accept`.
  - Step 2 replaces the one indeterminate `<progress>` (`index.html:180`) with plain stage text. The reading call is a single request (`letterhead.js` uses one 120 s upload call), so the app cannot know "page 2 of 3". Say only what is true: "Sending the picture", then "Reading the pad (about 30 seconds)", with a cancel button.
  - Step 3 keeps the existing "Check every line" warning (`index.html:197`).
- **Main screen**: grow the three-step bar `Listening, Working, Ready` (`frontend/app.js:92-93`) to `Listening, Transcribing, Structuring, Checking medicines, Ready`. This stays truthful because the client already makes two separate calls, `POST /api/transcribe` (`app.js:504`) and `POST /api/format`; the only new stage, "Checking medicines", happens inside the format call, so it must only be shown if the server reports it (or the format and check calls are split). Do not fake progress with timers.
- Same-row feedback: when a row re-checks after Spell it, show a brief "Checking this medicine..." state on that row only.

### 5. Claude Design pass (visual polish)

**First pass done 2026-10-16:** a whole-app Claude Design canvas (workspace with the new row states, dictation steps, Profile and Letterhead steppers, sign-in, Team): https://claude.ai/artifact/W48RNxGR2mjHT5W1h9GMjD (private to the owner). It is a suggestion to react to, not an approved design. Brief used:
- Surfaces: the medication row in its four states; the Spell it popover; the stepper for Profile, Letterhead and the main screen; empty, loading and error states.
- Wanted: clear icons for each state (not only colour), small motion that explains what happened (a row settling to green after a confirm, a chip filling the strength, a step ticking over), and a calm, clinic-appropriate look.
- Constraints: vanilla JS and CSS, no framework and no build step (`frontend/app.js:4`); must print cleanly (everything on screen only is `no-print`; ghost chips and Spell it never print); honour `prefers-reduced-motion`; keyboard and screen-reader friendly (`aria-live` as in the current steps); colour never the only signal; works at tablet width.
- Deliverable from design: a prototype to compare against, then re-implemented in `frontend/` by us. The prototype itself is not shipped code.

### 6. Build order for iteration 1

1. Row state model in the UI from existing data (name pill + strength chips from the lexicon `strengths`), no backend change.
2. `POST /api/v1/rx/check-row` and the Spell it popover (type + suggestions).
3. Steppers for Profile, Letterhead and the main screen.
4. Claude Design pass, then apply it.
5. Dosing reference file (`adult` block, with `max_daily`), reviewed by a clinician, then `core/dosecheck.py` and the dose-range flag (section 2b).
6. Brand as dictated (section 2c). Can move earlier: it is small and independent.
7. Larger lexicon, then clinic formulary (section 2d), after the look-alike guard.
8. Voice spelling, only if justified.

P1 look-alike guard slots into step 1 as the "Confirm medicine" reason for twins, and should be planned together with it, not after.

### Iteration 1 is not doing

- The monthly rebuild action or any rebuild UI.
- The speech-engine change (P2).
- Paediatric dose ranges, weight-based dosing and drug-interaction checks.

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
| Iter. 1 | **Dose sanity:** moved into Iteration 1, section 2b (daily total against a reference maximum, plus a form check). | 6 | M | `core/dosecheck.py`, reference file |
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

1. Approve Iteration 1 (UI first) plus P1 (look-alike guard, "heard" text) as the first plan to write in detail. The indication check can follow.
2. ~~Brand policy~~ Decided: print the brand as dictated, show the generic on screen only (section 2c). Open point: should "both" also print?
3. Can 50-100 consented dictations be collected for the benchmark?
4. Dosage reference: which source, and who is the clinician who reviews it? (Section 2 of Iteration 1.)
5. Run Claude Design now on the row states, or after step 3 of the build order?

## Not done or not verified

- No code was changed.
- Dataset licences were not checked.
- ElevenLabs and OpenAI pricing was not checked.
- The pair count (about 120) uses spelling ratio and phonetic key only. A clinical look-alike list would add more pairs.
