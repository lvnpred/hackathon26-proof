# Working folder: Iteration 2 (consistent generics, Spell it modal, sections and prose, follow-up date, government generics list)

**What this is.** The working record of Iteration 2 (2026-10-17). It keeps what the four plans do not carry: what the owner asked, the decisions, what was built, the review findings that changed the work, the measurements, the operator notes and the known limits. The implementation reports are copied verbatim into `reports/`.

**Status.** All four plans (I2-a to I2-d) are built and reviewed on branch `iteration-2` (main checkout, from `0421071`). Nothing is committed. The full suite is **1992 passed, 1 skipped** (baseline 1694). The lexicon is `drugs.json` v1.4.0 with 448 entries. The first real generics sync (I2-d Task 6) has NOT been run: it is a manual step that waits for the owner's CSV and licence answers.

**Model note.** The final whole-branch review ran on the standard model (Sonnet), not on the most capable model. The most capable model hit a weekly usage limit that lasts until 2026-10-21 09:30 IST (`reports/ledger.md`). A second review on the most capable model after that date would be an extra check.

**Decisions needed from the owner** (details under "Operator notes" and "Known limits"):
1. Set `TZ=Asia/Kolkata` in the deployment (recommended).
2. Do the manual check "Print twice in a row".
3. Supply the government generics CSV and the licence answer for the first real sync.
4. Commit split: ruled by the owner on 2026-10-17: ONE commit for all of Iteration 2, then a fast-forward merge to local `main` and a push to origin.
5. Have a clinician review the 7 hidden-generic brands and the other audit items (`reports/clinician-lexicon-audit.md`).

## What the owner asked (live testing, 2026-10-17)

| # | Request | Plan |
|---|---|---|
| 1 | The same generic line on every known medicine, on screen AND on the printed prescription | I2-a |
| 2 | An inline "Did you mean ...?" for an unknown name, one tap to accept | I2-a |
| 3 | Spell it as a pop-up with a paged suggestion list, voice input, and a re-check while typing | I2-c |
| 4 | Brief history first, Diagnosis second, both as short prose | I2-b |
| 5 | A calculated follow-up date next to the review line | I2-b |
| 6 | A government generics list and the Schedule H / H1 / X mark, shown on screen, mapped to brands | I2-d |

## Decisions

| Decision | Detail | Source |
|---|---|---|
| D1 to D6 | Stand as written in `docs/superpowers/plans/2026-10-17-i2-00-index.md` section 2. D2 reverses the I1 rule "brand printed as dictated, generic on screen only": the generic now prints on a second small line | index section 2 |
| Q1 to Q12 | Owner said "go with defaults" on 2026-10-17: every default in index section 6 stands | `reports/ledger.md` |
| Combination brands | Option (d): 4 proper combination entries (`Tramadol + Paracetamol`, `Chlorhexidine + Cetrimide`, `Doxylamine + Pyridoxine`, `Calcium Carbonate + Cholecalciferol`) and 7 hidden-generic interim brands (Neopeptine, Fefol, Autrin, Calcimax, Nurokind, Adzolex-Plus, Feronia-XT) pending a clinician | `reports/combination-brands-report.md` |
| Combiflam and Ciplar | Removed from the lexicon (v1.2.0 to v1.3.0). Combiflam is a combination product. "Cipla" verified as Propranolol through the near-spelling match to the brand `Ciplar` | `reports/a-task-1-2-report.md` (fix round) |
| Follow-up parser policy | "A wrong date is worse than none": a date only for one plain, unconditional interval; anything else gives no date | `reports/b-task-1-2-report.md` (fix round) |
| Schedule never printed | Screen badge only (Q10) | index section 6 |
| Unverified markers | `[unverified: confirm with doctor]` and `[unverified strength: confirm with doctor]` are removed from the instruction text once the doctor confirms the row (page and Save) | `reports/c-task-3-4-report.md` (H), `reports/final-fix-1-report.md` |

## What exists today vs before

| Area | Before (`0421071`) | Now |
|---|---|---|
| Generic of a generic-named row (`Cetirizine`) | `generic: ""`, no mark | `generic` filled; a small screen-only `generic` tag; nothing extra on paper |
| Generic of a brand row | Screen only | Screen and print: `generic: Paracetamol` under the brand in the Medicine cell |
| Unknown name (`citrizene`, `croissin`) | No suggestion until Spell it | Inline "Did you mean Cetirizine?" / "Crocin" (generic Paracetamol); one tap, Undo restores |
| Spell it | Inline panel in the table | Native `<dialog>`, 8 names per page, keyboard, voice input, re-check while typing (350 ms debounce) |
| Section order | Diagnosis, then complaints | Complaints / Brief history, then Diagnosis, as paragraphs |
| Rules-only path history | Sentences from the transcript, including the patient line and the diagnosis sentence | Each clause goes to one list or is dropped; no keyword diagnosis; an "unheard words" note |
| Review line | Text only | Plus `review_date`, computed by the server on format, correct and Save: `1 week (Sat 24 Oct 2026)` |
| Government generics list | None | Pipeline: `generics_sync.py sync`, `review-sheet`, `promote`; row field `schedule`; screen badge (dormant until `generics.json` exists) |
| Lexicon | v1.2.0, 444 entries | v1.4.0, 448 entries |
| Suite | 1694 passed, 1 skipped | 1992 passed, 1 skipped |

## What was built, per plan

Suite counts are from the reports. The plans forecast 1708, 1724, 1734, 1747 (index section 5); reality was larger because every task had a hardening and mutation round.

| Plan | Delivers | Suite after | Main files |
|---|---|---|---|
| I2-a | Generic everywhere, print, Did you mean | 1721 passed, 1 skipped (+27) | `core/surface.py`, `core/candidates.py` (`scored_spellings`), `core/rowcheck.py` (`options`, `did_you_mean`, cache), `core/correction.py`, `pdf/sheet.py`, `frontend/rxview.js`, `rxstate.js`, `suglist.js`, `rx.css` |
| I2-b | Section order, prose, follow-up date | 1825 passed, 1 skipped (+104) | `core/followup.py`, `core/prose.py`, `core/rulesplit.py`, `core/fallback.py`, `api/visit.py`, `api/review.py`, `api/format.py`, `pdf/sheet.py`, `frontend/sections.js` |
| I2-c | Spell it modal, paging, voice, typing re-check | 1886 passed, 1 skipped (+61) | `frontend/spellmodal.js`, `suglist.js`, `rxview.js`, `rx.css`, `index.html`, `app.js`, `api/rx.py` (`options`, `total`) |
| I2-d | Generics list, schedule badge, sync, review sheet, promote | 1931 passed, 1 skipped (+45) | `core/lexicon/generics_sync.py` (370 lines), `generics_promote.py` (219), `core/generics.py` (49), `frontend/rxview.js`, `rxstate.js`, `rx.css` |
| After the plans | Final review fixes (+44 to 1982), combination brands (+10 to 1992); 1931 to 1938 is the I2-d fix batch and is not itemised in the reports | 1992 passed, 1 skipped | `core/safety.py`, `core/correction.py`, `core/rulesplit.py`, `core/lasa.py`, `core/dosing.py`, `seed_extra.json`, `drugs.json` v1.4.0 |

Total: 1694 to 1992 is +298 tests. The plans forecast +53.

New HTTP and data contracts are in the index (`docs/superpowers/plans/2026-10-17-i2-00-index.md` section 4, with a status note on the stale facts).

Facts about the row fields, from the code now:
- `DERIVED_ROW_FIELDS` is `("generic", "schedule", "heard", "lookalike", "dose_note", "source", "did_you_mean", "did_you_mean_generic")` (`core/correction.py:270`). `schedule` is second.
- `generic` and `schedule` are in `RECOMPUTED_ROW_FIELDS` (`core/correction.py:291-294`). The two Did you mean fields are NOT there: they have their own tuple `DID_YOU_MEAN_FIELDS` (`core/correction.py:273`) so one computation serves both (`core/correction.py:404`).

## Review findings that changed the work

| Finding | Severity | Where found | Resolution |
|---|---|---|---|
| Rules path invented a stone note (any "flank pain") and keyword diagnoses | Critical | I2-b review of the rules-only path | The seeded note needs all five demo words; no keyword diagnosis, only a dictated marker (`reports/b-task-3-5-report.md`, fix round) |
| Same-name rows cross-contaminate: two rows with one name took each other's status | Important (I2) | Final review | FIFO pairing per name in `preserve_untouched_rx_status` (`reports/final-fix-1-report.md`) |
| The strength marker `[unverified strength: ...]` printed on paper after the doctor confirmed | Important (I1) | Final review | Page strips both markers on confirm; server `safety.strip_grounding_markers` on Save (`reports/final-fix-1-report.md`) |
| Rules path inverted a negated review ("no follow up needed" became review text with a stray "No" in history) | Important (I3) | Final review | Review takes an optional negation prefix; no date (`reports/final-fix-2-report.md`) |
| Combination suffix dropped ("Moxikind CV 625" became "Moxikind") | Important (I4) | Final review | Optional short suffix captured into the name; unit-less number becomes the strength (`reports/final-fix-2-report.md`) |
| Wrong Did you mean on near-miss typos (for example "hydral" to "Hytrol") | Minor (final review item a) | Final review | Inline rule: score 0.9, gap 0.05, plus text-only ratio 0.7, at least 6 letters, no other-generic name starting with the typed letters. Why not 0.8: it would also drop the required `croissin` to `Crocin` (text ratio 0.714) and `citrizene` (0.737); wrong cases measured 0.5 to 0.667 (`core/rowcheck.py:13-15`, `:159-170`; `reports/final-fix-1-report.md`) |
| Did you mean computed twice per row, 72.6 ms for 8 rows | Review fix | I2-a task review | Bounded cache and one computation for both fields; 8-row /api/format 72.6 ms to 32.6 ms cold, 14.0 ms warm (`reports/a-task-1-2-report.md`, fix round) |
| Mic `aria-label` did not contain the visible text; list item label hid the generic and look-alike warning | Important | I2-c review, live check | "Say it: say the name"; `aria-describedby` for generic and reason (`reports/c-task-3-4-report.md`, fix round B) |
| Typing in the modal did not re-check (one request per open) | Live check | I2-c live report | Debounced re-check, 350 ms, stale answers dropped (`reports/c-task-3-4-report.md`, fix round A) |
| Sentences were merged and the patient line stayed in history | Review fix | I2-b review | `core/rulesplit.py`: each clause goes to one list or is dropped (`reports/b-task-3-5-report.md`) |
| `Combiflam` and "Cipla" verified as wrong drugs | Owner ruling | I2-a review | Both brands removed; audit written (`reports/a-task-1-2-report.md`) |
| 11 combination brands mapped to a single generic | Owner decision | Lexicon audit | Option (d): 4 combination entries, 7 hidden (`reports/combination-brands-report.md`) |
| Follow-up parser dated conditional or open phrases | Review fix | I2-b clinical-safety review | Refuse list: 56 refused and 24 accepted phrases pinned (`reports/b-task-1-2-report.md`) |
| `generics_sync.py` grew to 473 lines | Minor | I2-d task review | Split: `generics_promote.py` (219) and `generics_sync.py` (370) (`reports/d-task-4-5-report.md`) |
| Raw "The server answered 500" on a failed list load | Minor | I2-c | Status 500 and above gives "The medicine check is not available right now." (`reports/final-fix-1-report.md`) |

## Final measurements

| Measure | Value | Source |
|---|---|---|
| Suite | 1992 passed, 1 skipped (baseline 1694) | `reports/combination-brands-report.md` |
| Lexicon | v1.4.0, 448 entries (444 before the 4 combination entries) | `reports/combination-brands-report.md` |
| `/api/format`, 8 rows, cold | 144 ms | Final review (the figure was given with this task; the review text is not in `reports/`) |
| check-row with 1000 clinic names | 49 ms | Final review (same note); the plan bound is 50 ms |
| Earlier timings (before the final fixes) | /api/format 8 rows cold 32.6 ms, warm 14.0 ms; check-row 1000 names 14.0-15.8 ms | `reports/a-task-1-2-report.md`, `reports/c-task-1-2-report.md` |
| Live checks | a: 10 of 10 pass; b: 11 of 11 pass; c: no outright failure (3 low defects, all fixed); combined pass: no defects | `reports/*-live-report.md` |
| Mutation checks | 0 surviving non-equivalent mutants in every task round (counts per report) | `reports/` |

## Operator notes

**Generics sync runbook (summary).** Full text is in I2-d Task 6 (`docs/superpowers/plans/2026-10-17-i2-d-government-generics-list-and-sync.md`).
- CSV columns: `generic,list,schedule,source_line,notes` (`schedule` is H, H1, X or blank; extra columns are ignored). One list per file; a file with a bad list name is refused.
- The owner supplies the licence, the source id and the date by hand. The code never decides a licence (`reports/d-task-1-3-report.md`).
- The report is written outside the repo. A report path inside the repo is refused, except `doctor_dictation/data/`.
- `generics_sync.py sync --check` reports drift with exit codes; use it after every sync.
- Restart the server after a sync or a promote: `core/generics.py` reads the file once (`reload()` refreshes only the running process that called it).
- `review-sheet` writes the clinician sheet; `promote` needs `--reviewer`, `--source-id`, `--report` (outside the repo), `--confirm` and `PROMOTION_LEDGER_PEPPER` of 32 or more characters (kept outside git). Without `--confirm` nothing is written and the exit code is 2.
- A twin without a reviewed look-alike pair is refused; the importer checks still apply to promoted names.

**Time zone (owner decision).** Neither `Dockerfile` nor `docker-compose.yml` sets `TZ`. A UTC container prints the previous day between 00:00 and 05:30 IST for the review date, the OP number and the Today list. Recommendation: set `TZ=Asia/Kolkata`. No code change fixes this.

**Dormant badge.** `core/lexicon/generics.json` does not exist today, so the schedule badge never shows in the real app. The combined live pass saw it only on a copy with synthetic data.

**Manual check not done.** "Print twice in a row": in the live check a second click on Print did nothing after the first native print dialog; calling `printDocument()` directly worked. Not confirmed as an app defect (`reports/a-live-report.md`, concern 5).

## Known limits and backlog

Rules-only path (no LLM):
- "0 point 4 mg" gives a row named "Point" (`reports/b-task-3-5-report.md`).
- A medicine line that cannot be read is reported in warnings, but a clause counts as parsed when any 3-letter word of a row name appears in it. A wrong row from a neighbouring clause could hide a miss.
- A unit-less strength ("625") is kept as dictated, with no unit.
- The classifier is marker-based: a history clause that starts with a plan word (rest, drink, avoid, continue, refer) goes to advice; a clause that starts with a test abbreviation goes to tests.
- The "unheard words" note names the words, not the line, and flags real synonyms ("febrile" for "fever").
- The follow-up parser is broad on purpose: "Review for 1 week" gets no date; Hinglish negations beyond "nahi" and "nahin" are not covered.

Lexicon:
- The 7 hidden brands keep their single-generic row status, and the Spell it "matched" option still lists the single generic name (`reports/combination-brands-report.md`).
- Combination entries have no strengths, so a strength typed for Ultracet or Shelcal is never flagged.
- 18 other audit items need a clinician: section 3 (6 suffix families) and section 4 (12 unplaceable brands) of `reports/clinician-lexicon-audit.md`.
- Ciplar removal drops a real Cipla propranolol brand. Backlog: a fuzzy-match guard for company names, then restore Ciplar. The same near-spelling route could turn any company name into a drug; it was not scanned exhaustively.
- Also in the backlog: a layer-generic for clinic names.

Page:
- Editable cells (history, diagnosis, review, Rx) show only a tint on keyboard focus, no accent outline.
- Chip taps (strength, timing) have no Undo.
- `/api/v1/correct` and Save do not cap long prose items; only `/api/format` does.
- A document re-saved from before Iteration 2 gets its date from the re-save day.
- `app.js` is 1245 lines (over the 500-line rule before this work started).
- Typing "cetr" lists "Potassium Magnesium Citrate" and "Zestril": check-row fuzzy quality, not the modal.

Fixed during Iteration 2 (do not re-open): two rows with the same name no longer share status (`reports/final-fix-1-report.md`).

Not exercised: the real `/api/format` LLM path, a real microphone, Safari and Firefox live-region announcements, the native print dialog (see above), the dose-check row in Spell it (no dosing data in the test lexicon), and the final review on the most capable model.

## Folder map

| Path | What it holds |
|---|---|
| `README.md` | This file |
| `reports/ledger.md` | The coordinator ledger (`progress.md` in `.superpowers/sdd/2026-10-17-i2/`) with every ruling |
| `reports/a-*.md` | I2-a: server (tasks 1-2), page and print (tasks 3-4), live check |
| `reports/b-*.md` | I2-b: follow-up date (tasks 1-2), sections, prose, rules path (tasks 3-5), live check |
| `reports/c-*.md` | I2-c: options and paging (tasks 1-2), modal and voice (tasks 3-4), live check |
| `reports/d-*.md` | I2-d: sync (tasks 1-3), badge and promote (tasks 4-5) |
| `reports/combined-live-report.md` | The combined live pass of a, b, c and the badge |
| `reports/final-fix-1-report.md`, `final-fix-2-report.md` | Fixes from the final review |
| `reports/combination-brands-report.md` | Option (d) for combination brands |
| `reports/clinician-lexicon-audit.md` | The lexicon audit a clinician should work through |

The plans are in `docs/superpowers/plans/2026-10-17-i2-*.md`. The earlier record is `docs/working/2026-10-17-formulary-and-lexicon/README.md`.

**Next step:** the owner rules on the time zone, then runs the manual "Print twice" check. Not done here: any commit, the real generics sync, the clinician review, a second review on the most capable model.
