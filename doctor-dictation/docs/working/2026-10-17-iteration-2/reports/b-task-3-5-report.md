# I2-b Tasks 3-5 report
Status: DONE, uncommitted. Full suite 1749 passed, 1 skipped (baseline 1730 + 4 tests that appeared in tests/test_followup.py during my run, not mine + 15 mine: 8 plan + 7 added). Netguard run of both new test files: 15 passed, 0 attempts.

Files: NEW core/prose.py (52), frontend/sections.js (60), tests/test_sections_prose.py (10 tests), tests/test_frontend_sections.py (5 tests).
Modified: pdf/sheet.py (332), api/format.py (226), core/fallback.py (229), frontend/index.html, styles.css (v10->11), app.js (v31->32), sections.js?v=1 added before app.js.
RED in the real repo: prose file failed at collection (no core.prose), sections file failed 2/2 (no sections.js). GREEN after the apply script (dry-run on scratch i2b3 first: ALL ANCHORS OK, scratch suite 1737 passed + 1 deselected test_package_install, which fails there only because the editable install points at the real repo).

Anchor adaptations (nothing loosened)
1. Plan says styles.css?v=11 / "bump by one": real value was v=10 -> 11; app.js v=31 -> 32.
2. Line numbers all drifted (sheet.py review :260 not :258, sections :302-305, fallback block ~:124-128, app.js renderSheet :884, formatTranscript :505, applyCorrection :541, fixLists :807, newPatient :1163/:1188); anchors matched by text.
3. _answer: Task 2 already had _answer(structured, normalized, **rest) + normalized_transcript; I re-added a `raw` positional (needed for prose.unheard) and kept normalized_transcript. All 4 call sites updated.
4. Removed the dead `rx_keywords` variable with the old complaints block in fallback.py.
5. cap_items / unheard hardened: non-list values (str, None) ignored/untouched instead of iterated; /correct passes {f: patch2.get(f)} (None safe).
6. sections.js: init default waitMs 400 only when hooks.waitMs is null (test passes 0); onReviewInput clears the date at once, a failed call leaves date empty and never touches pRev.
7. Added 7 tests beyond the plan's 8: speech spellings not flagged / invented phrase flagged, cap leaves non-lists alone, old saved document reprints in new order with no date (and a fresh save prints its date) via the real reprint route, /correct checks only replaced lists, rules path cut at drug name + cap on rules and error-fallback paths, failed review-date route call + blank answer, app.js wiring pins.

Section order: screen index.html pCc < pDx < pIx; PDF html and pdftotext both complaints first. Old docs (lists of strings, no review_date) open and print in new order with no date.

Mutations: 36 on a fresh scratch copy (i2b3m). First pass 9 survivors: cap on rules path, cap on error-fallback path, drug-name cut in rules history, 5 app.js wiring mutants. Added tests; second pass 0 survivors, except M36 (drop _esc around the date label), an equivalent mutant (label is digits/letters only from date.fromisoformat).

Real PDF (repo Chromium renderer, offline, pdftotext -layout), owner example via rules path, review_date stamped for Sat 17 Oct 2026:
  CHIEF COMPLAINTS & BRIEF HISTORY
  C/o fever with chills for 3 days, associated body aches, no vomiting
  No h/o similar episodes
  DIAGNOSIS / CLINICAL IMPRESSION
  Viral fever
  ...
  REVIEW / FOLLOW-UP
  Review after 1 week (Sat 24 Oct 2026)
Old document: review prints "1 week" with no date. Review "Review if fever persists": no date.
Rules path now: patient/age sentence dropped, "Diagnosis viral fever" -> diagnosis ["Viral fever"] (before: both in history).

Concerns
- unheard flags true synonyms the doctor never said (e.g. "febrile" for "fever"); only speech spellings and plurals pass (difflib 0.8). By design: information only, never blocks or rewrites.
- /api/v1/correct does not cap prose items over 400 chars (cap_items would also cut doctor-typed text in unchanged lists); only the /api/format paths cap.
- Rules-path history keeps dictated case ("C/o", no trailing period); sentences with a dose or a lexicon drug name are cut/dropped by design.
- app.js page wiring is pinned by string tests only; the live browser check (plan Task 6 Step 3) is still needed.
- tests/test_followup.py gained 4 tests mid-run from another edit (not mine).

## Fix round (review of the rules-only path)
Status: DONE, uncommitted. Full suite 1825 passed, 1 skipped; new/changed test files under netguard: 91 passed, 0 attempts.
New: core/rulesplit.py (134 lines, pure), tests/test_rules_split.py (74 cases: 32 probes x 2 + gate and no-keyword tests). Changed: core/fallback.py (195), core/prose.py, frontend/sections.js, index.html (sections.js ?v=2, notes role="status" aria-live="polite").

What changed
- C1: the seeded ureteric note needs ALL of ureteric, calculus, tamsulosin, deflazacort, citrate in the dictation (the demo only). A UTI line or a partial stone dictation gets no seeded history, diagnosis, review, tests, advice or rows.
- C2: no keyword inference. Diagnosis only from a dictated marker (diagnosis, dx, impression, provisional/final/clinical/working diagnosis, diagnosed as/with); the diagnosis phrase ends at the next clause.
- I1: age is identity only as "<N> years old", "aged <N>", "<N> years/yrs <sex>", "<N>M", "<N>/M". "since 3 years", "for 5 years", "10 yrs" stay in history. Clinical words before an age phrase stay.
- I2/I3: each clause goes to one list (history, diagnosis, advice, investigations, review) or is dropped (name, age, sex, OP number, medicine lines). Sentences are never merged. Advice/test/review lists now come from the classifier (the old keyword scans for tests, advice and review are removed).
- I4: a negation word (no, not, without, denies, denied, nil, absent, negative, never, none) is flagged when a prose line has more negations than the dictation (any negation word counts alike; "denies" covers "no"). Flagged as words ["no"].
- I5: note reads "Line 2: not heard in the dictation: w1, w2. Check this line." (one sentence per flagged line), role="status" aria-live="polite", screen only, cleared on edit of that list.

Existing expectations changed (each with reason)
1. tests/golden.json noisy-stt-splits: removed Tamsulosin 0-0-1 from the expected rx. It was only produced by the seeded note (any 'flank pain'). The dictation says "tam sulosin 0 point 4 mg"; the rules row parser reads "Point 4 mg" (row parsing, backlog). Paracetamol SOS stays pinned.
2. tests/test_determinism.py test_seeded_shortcut_rows_get_flagged replaced by test_a_partial_flank_pain_dictation_gets_no_seeded_rows: it pinned the invented Deflazacort row (flagged unverified); now asserts no Deflazacort/Potassium Magnesium Citrate, and no seeded review/tests/advice for that dictation.
3. tests/test_sections_prose.py (my plan test): "gastritis with vomiting ..." diagnosis ["Gastritis"] -> [] with history ["Gastritis with vomiting"] (C2: no keyword diagnosis); sections.js ?v=1 pin -> ?v=2.
4. tests/test_frontend_sections.py: note text "Not heard in the dictation: ..." -> "Line 2: not heard in the dictation: ... Check this line." (I5).

Probe table: 26 review probes + 6 extra (years in history, identity clauses, dose line of an unknown medicine, history after a diagnosis, diagnosis and advice lists) each with hand-written expected history/diagnosis/advice/tests/review, plus a property test: every word of history, diagnosis, advice and tests is in the raw dictation or its deterministic normalisation (number words to digits, lexicon spellings, e.g. three -> 3).

Mutations (fresh scratch, 31): seed gate any/4-of-5/old keywords, keyword diagnosis restored, years-without-sex widened, identity not stripped, identity prefix rule dropped, advice start list off, advice merge off, dx marker/dx cut off, filler trim, drug-name cut, dose guard, rx marker, review marker, weak cue, inheritance, test split, history cap, 4 negation mutants, note role removed, line number removed/off by one, innerHTML, not unhidden, sections v1. First pass 6 survivors (4-of-5 gate, identity prefix rule, dose guard, rx marker, weak cue after dx, inheritance); I added probes; second pass 0 survivors.

Concerns
- The classifier is marker-based: a history clause that starts with a plan word (rest, drink, avoid, apply, steam, continue, admit, refer) goes to advice; a history clause that is exactly "once/twice/daily/after food/at night" is dropped as medicine instructions; a clause starting with a test abbreviation (CBC, ECG, USG...) goes to tests.
- A lowercase name before an age without "patient/name/Mr" ("rahul 45 m cough") is not recognised as a name; it stays in history as dictated.
- The Task-5 rules row parser still reads "0 point 4 mg" as a row named "Point" (backlog, row parsing).
- Seed gate: someone who dictates all five demo words gets the demo note (dictated words, but static advice/review text). Rare, accepted.
- /correct and Save still do not cap prose items (known gap, skipped).
