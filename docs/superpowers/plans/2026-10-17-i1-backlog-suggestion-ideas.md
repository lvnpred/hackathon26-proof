# Iteration 1 Backlog: Suggestion Ideas and Deferred Items

> **For agentic workers:** this is a BACKLOG, not an execution plan. Do not implement a card from this file. A card becomes work only after the owner approves it and a plan in the sibling format (`2026-10-17-i1-r1-usage-ranking.md`) is written for it.

**Summary.** The owner chose rows 1 and 3 of the usage-ranking brainstorm (plan I1-r1). This file keeps the other ideas as cards (a) to (i) and (k), every item deferred during Iteration 1 that is still open (j), the items the lexicon plan `2026-10-17-i1-g-lexicon-simple.md` defers (l) to (s), clinic-facing ideas for the medicine lists (t) to (ab), and follow-ups from the lexicon implementation review (ac) to (ak). Worth doing next: (h) arrow keys in the Team tabs, (o) a clinician review of today's wrong rewrites (with its extension (ad)), (aa) the lexicon version on the Team page, (ac) a runtime dictionary guard, (ae) atomic lexicon writes and (aj) the `.venv` ignore rule. Never build: (c), boosting the clinic's names in Spell it. The rest wait for real usage data or for a product decision.

**Owner decision (recorded 2026-10-17).** Card (f) stays in the backlog for now: the owner wants no extra restriction on learning in the first pass. A name is still learned after two saved documents confirm it; the person-like and patient-word rules from I1-h1 stay. Reopen (f) after the first real clinic data shows whether patient names leak into the list. It would close the open owner risk (c) from the I1-h1 review (`.superpowers/sdd/2026-10-16-i1-h-formulary/progress.md`). Card (h) needs no decision; it is plain accessibility work. Also decided: clinic names DO appear in Spell it suggestions at plain score (plan I1-r1, Decision 3: yes).

**Owner decisions (recorded 2026-10-17, lexicon).** PROMOTION of a name many clinics learned into the core list IS in scope now: it is built by plan `2026-10-17-i1-g-lexicon-simple.md` Task 4 (offline, operator + clinician, five checks), so it is not a backlog card; only its bulk review page is, card (p). A promoted brand must name a generic, else it stays clinic-only (decided). The CDCI licence wording is used as proposed for the first import and revisited later, card (s). The broad A3 suggestion list, new generics, forms and strengths are deferred: cards (l), (m), (n).

**Goal:** Record each idea with its value, risk, size and dependencies, so that it can be picked up or rejected later without re-deriving it.

**Scope:** The ideas from the brainstorm, and the "Deferred from ..." items in the project memory file `project_medication_accuracy_plan.md`. Out of scope: anything already in a plan (I1-a to I1-h4, I1-r1), and the open decisions in `2026-10-16-i1-00-index-and-contracts.md` section 5 (dosing source, dose vocabulary, printing both names; the lexicon licence is now decided for the first import, card (s) tracks the revisit). Also out of scope: anything built by `2026-10-17-i1-g-lexicon-simple.md` (denylist, five-check import, lineage, promotion).

**Sizes:** S = under a day, one plan task. M = one plan with 2-3 tasks. L = several plans or a schema and page change together.

---

## (a) "Your clinic's top medicines" quick-pick on an empty row

- **Value.** A doctor taps a common local drug instead of dictating or typing it. This saves time on repeat prescriptions.
- **Risk.** A list of names invites a mis-tap between neighbours that look alike. A tapped name was not dictated, so it grounds as `unverified-name` and blocks Save until the doctor confirms it (contract 4.2; save gate `api/persistence.py:195`). So a mis-tap cannot save silently. It can still be confirmed carelessly. Never put two sound-alike names next to each other.
- **Work.** Page: a chip strip on an empty row in `frontend/rxview.js` (257 lines) and its state in `frontend/rxstate.js` (163 lines). Data: `GET /api/v1/formulary` returns recency order (`db/formulary.py:26-30`), so the page needs the I1-r1 usage order, which only the server layer has. A small read route or an `order=usage` option is needed.
- **Product decisions first.** Where it goes (empty row only, or inside Spell it). Who sees it (every doctor of the clinic, or only doctors with their own history; single-database mode has no Team screen). How many names (5 fit one line). Whether lexicon names from the doctor's own history (`db/__init__.py:378-403`) join the clinic's names.
- **Size.** M. **Depends on:** I1-r1, I1-h3, I1-e3.
- **Recommendation.** Later. Decide the product questions after a month of real usage data.

## (b) Per-doctor popularity instead of per-clinic

- **Value.** Small. The doctor's own most-used medicines already lead the speech hints (`api/stt.py:20-30` calls `top_medicines(conn, ..., doctor_id=...)`, `db/__init__.py:378-403`; `core/hints.py:44` puts them first). This covers learned clinic names too (`core/hints.py:32-33`).
- **Risk.** Sparse data: a name needs two documents clinic-wide (`core/formulary.py:15`), and per doctor it needs even more. Privacy: per-doctor counts are a prescribing profile. They must never reach the Team tab or another doctor.
- **Schema.** No change needed for a read: the ledger `clinic_formulary_docs(formulary_id, document_id)` (migration 009) joins to `documents` and then to `encounters.doctor_id`. Storing it per doctor would mean a new column and migration.
- **Size.** M. **Depends on:** I1-r1.
- **Recommendation.** Never for hints, because the doctor's own history already does the job. Revisit only if card (a) ships and doctors ask for "my list".

## (c) Boosting the clinic's names in Spell it beyond a tie-break

- **Value.** The popular local drug appears first more often.
- **Why it is dangerous.** Spell it exists for the case where the sound was unclear. The first button reads "Did you mean" (`frontend/rxview.js:140`), and doctors tap it quickly. A boost makes the POPULAR drug the default tap even when the dictated sound is closer to another drug. That is a look-alike/sound-alike (LASA) error, a leading cause of medication errors. Example with the real scorer: the doctor says "Zorbexem". The new clinic drug Zorbexim scores 1.0 and the popular Zorbexin (200 uses) scores 0.79. A boost of +0.25 would put Zorbexin first, and the wrong drug becomes one tap away. After Spell it, the row reads "Confirmed by you", so the error is no longer visible on the sheet. A boost can also push a lexicon drug out of the five slots (`core/rowcheck.py:7`). I1-r1 avoids all of this: usage only reorders clinic names that are within 0.03 of the top score, and lexicon names keep their slots.
- **Size.** S to build. The cost is in safety, not in code.
- **Recommendation.** Never.

## (d) Usage-aware hints per specialty or per time of day

- **Value.** Small. The clinic's share of the speech hints is 10 names and 150 characters (`core/formulary.py:17`) inside a 500-character prompt (`core/hints.py:14`). Re-ordering inside it is a small lever.
- **Risk.** No specialty field exists (no match for "specialty" in `doctor_dictation/` or `frontend/`). Time of day needs a timestamp per confirmation: the ledger has none, so it would need a join to `documents`. It splits sparse data further. It also makes the hints change during the day, which makes a speech-recognition problem harder to reproduce.
- **Size.** M (time of day) to L (specialty: schema, Profile UI, per-doctor data).
- **Recommendation.** Never for time of day. Specialty: later, and only if a specialty field is added for another reason.

## (e) "Do not learn" and "pin to top" admin controls in the Team "Clinic medicines" tab

- **Value.** "Do not learn" stops a junk name from coming back. Today a removed name is learned again after two NEW prescriptions (I1-h1 decision 4; `db/formulary.py:19`, `:33-41`). "Pin to top" lets an admin keep a stocked drug in the speech hints.
- **Risk.** A wrongly blocked real drug stays `unknown-medicine`. That is the safe direction: the doctor still confirms it. A pinned name takes a hint slot for ever, so cap pins at 3 of the 10 slots.
- **Work.** Migration 010 (`blocked_at`, `pinned` columns). `learnable` or `record_confirmation` skips a blocked name. `ranked_layer` (I1-r1) puts pinned names first. Two admin-only routes behind `formulary.manage` (I1-h3). Two buttons per row in the tab (I1-h4). Isolation tests for both routes.
- **Size.** M. **Depends on:** I1-h3, I1-h4, I1-r1.
- **Recommendation.** "Do not learn": later, and do it next if admins report a removed name coming back. "Pin to top": never, unless (a) ships and needs it.

## (f) Two different patients (or users) before a name is learned

- **Value.** It closes open owner risk (c) (`progress.md:17`). Today two documents are enough (`db/formulary.py:15-21`). A follow-up visit of the same patient, or one doctor repeating the same typo, teaches a name. The name then shows as "Known to your clinic" for every doctor.
- **Choice.** Count distinct PATIENTS, not distinct users. A one-doctor clinic could never meet a "two users" rule, but every clinic sees two patients. Distinct patients come from a join (ledger, then `documents.encounter_id`, then `encounters.patient_id`). No schema change.
- **Risk.** A rare drug used for one long-term patient is never learned. It stays `unknown-medicine`, which is safe. Old ledger rows are re-counted under the new rule, so a few names could drop out of the active list once. Say so in the release note.
- **Size.** S to M (one SQL change in `record_confirmation`, plus tests for same-patient re-saves).
- **Depends on:** I1-h1 to I1-h3.
- **Recommendation.** Do next, after the owner's yes.

## (g) Learning two-word brands that look like a person's name

- **Value.** "Zorbexin Forte" is never learned today. `person_like` rejects 2-3 Capitalised, letters-only words (`core/formulary.py:39-47`), so the brand looks like "Rahul Sharma". "Zorbexin SR" and "Zorbexin-Forte Plus" are learned (`tests/test_formulary.py:52-53`).
- **Option.** A short suffix allow-list (Forte, Plus, Duo, Max, Kid, Junior, Mini). A name whose last word is on it is not person-like.
- **Risk.** A patient's surname on that list. Other guards still apply: the patient's own name words (`core/formulary.py:64`), the clinic's patient words (`:66`), two documents, and admin removal. The person-like rule is a heuristic, not a guarantee (`progress.md:17`).
- **Size.** S. **Depends on:** I1-h1.
- **Recommendation.** Later. The failure today is safe (the name stays `unknown-medicine`). Act when a clinic reports a real brand that is never learned.

## (h) Arrow-key support for the Team tablist

- **Value.** Keyboard and screen-reader users expect the WAI-ARIA tabs pattern. I1-h4 builds `role="tablist"` with click handlers only (I1-h4 Task 2; arrow keys deferred by ruling R16, `progress.md:15`).
- **Work.** Left and Right move between tabs; Home and End jump to the first and last tab. Use a roving `tabindex` (0 on the selected tab, -1 on the others). Add one fake-DOM test in the I1-h4 node script.
- **Risk.** Low. The tabs show only for admins.
- **Size.** S. **Depends on:** I1-h4.
- **Recommendation.** Do next.

## (i) Public Sans bundling (self-hosted fonts)

- **Value.** The same type on every machine. Today "Public Sans" is listed first (`frontend/styles.css:8`, `frontend/login.css:4`), but no `@font-face` exists in `frontend/*.css`, so most machines fall back to system fonts.
- **Work.** Add `woff2` files for the weights in use under `frontend/fonts/`, with `@font-face` and `font-display: swap`. Do the same for Source Serif 4. Ship each font's licence file. Bump the CSS cache pins.
- **Risk.** Page weight (one file per weight) and a licence check before shipping.
- **Size.** S. **Depends on:** I1-f2.
- **Recommendation.** Later. The owner ruled it a follow-up outside Iteration 1 (index section 7, item 4).

## (k) Real RBAC (roles and permissions)

- **Value.** Different people get different rights: a doctor writes prescriptions, an admin manages people, letterheads and the clinic medicine list, an assistant (the third role that exists today) gets its own limits.
- **Today (owner decision, 2026-10-17).** The final review of the formulary work found that a doctor could create users, disable an admin and reset an admin's password (`policy.py` allowed `user.create`, `user.disable` and `user.reset_password` for everyone). The owner chose: those three actions are admin-only on the server, and every newly created user gets the role `admin` by default until RBAC exists. So in practice every user is an admin for now.
- **Work.** Define the role list and a permission table per action. Add a role field to the Team "add user" form and a "change role" action. Make `DEFAULT_ROLE` `doctor` again. Guard against removing the last admin. Add a migration for existing users. Extend the isolation sweep to cover each role. Decide what an assistant may do.
- **Risk.** Locking a clinic out if the last admin is demoted. Changing the default role silently changes who can remove formulary names and manage people.
- **Size.** L. **Depends on:** the owner's role model.
- **Recommendation.** Later, as its own iteration. Reopen before any clinic with more than a few users goes live.

## Deferred by the lexicon plan (I1-g simple, 2026-10-17)

Evidence: preflight `.superpowers/sdd/2026-10-17-lexicon-g/preflight.md` (A.x, B.x) and measurements made for `2026-10-17-i1-g-lexicon-simple.md`.

## (l) Broad A3 suggestion list in Spell it (23,821 NLEM brands)

- **Value.** Spell it can offer a correctly spelled brand the core list lacks (A.5: 93 of 193 well-known OPD brands are in A3).
- **Risk.** It must never feed a rewrite or a status: not `candidates._rows` (`core/candidates.py:62-75`), not `formulary._twin` (with A3 there, 392 of 400 clinic names turn `lookalike-check`, B.3.2), not the LLM repair list (`repair.py:37-54`). Only `rowcheck.suggestions` (`core/rowcheck.py:77-92`), in a lower slot after clinic and lexicon names. A tapped A3 brand must return the lexicon generic or "not in medicine list". Naive scoring costs 180 ms per call; a first-letter, length +-3 bucketed scorer measured 22 ms (A.9). Needs a CC BY 4.0 notice file (source, date, sha256, "brand names are their owners' trademarks") and its own index version in `/api/health`.
- **Size.** M-L. **Depends on:** card (s); the first core import (plan I1-g simple, Task 5).
- **Recommendation.** Later, after a month with the first import. Write it as its own plan (g3).

## (m) New generics (105, mostly hospital, oncology and HIV) with curated look-alike pairs

- **Value.** Clinics that use these drugs get recognition and, once a dosing reference exists, a dose check.
- **Risk.** 24 of 104 new canonicals have a computed twin, several on high-alert lists (Daunorubicin/Doxorubicin, Dopamine/Dobutamine, Dolutegravir/Raltegravir, Thalidomide/Lenalidomide, B.3.4). The curated pairs (`core/lexicon/lasa_pairs.json`, `core/lasa.py:85-94`) do not cover them. Salt words and sentence case would become canonical names (A.3).
- **Work.** A clinician adds curated pairs first; then build `--allow-new-generics` with Title Case and salt stripping, and bring back g2 Task 2 (the look-alike share check).
- **Size.** M. **Depends on:** a clinician reviewer.
- **Recommendation.** Later, only if a clinic uses these drugs in OPD.

## (n) CDCI form map, strengths and percent concentrations

- **Value.** Strength chips and form checks for imported brands.
- **Risk.** 737 of 738 CDCI forms match no lexicon form word (A.4). Strengths are aggregated across all SKUs (injection strengths join tablet lists), `1 g` and `1000 mg` become two strengths, and percent products became mass (Dextrose and Dex "0.25 g", sodium chloride drops "6.5 mg", A.2). The first import is brands only on purpose.
- **Work.** A form map (Oral tablet -> `Tab.`, injection/infusion -> `Inj.`, ...), per-form strengths, a unit-aware strength key, and percent kept as percent.
- **Size.** M. **Depends on:** I1-g simple Task 5; the dosing reference (index section 5, item 1).
- **Recommendation.** Later, together with the first real dosing data.

## (o) Clinician review of the near-collision rewrites that happen today

- **Value.** Safety. `correct_drugs` rewrites a dictated brand it does not know into a near brand of another drug: preflight A.7 counted 410 NLEM brands today and 621 after a naive A1 merge (Famcin (rifampicin) -> Amcin (amikacin), Clopin (clomipramine) -> Clozapine). Measured for I1-g simple with a stricter count (`tablet <brand> 500 mg`, another generic only): 194 today, 194 after the five-check import (313 if check 5 ignored the CDCI map). `tab clopin 25` -> `tab Clozapine 25` today.
- **Risk.** Low to review; any fix (a "do not fuzz" list, or a higher cutoff for brands) changes recognition and needs its own tests.
- **Size.** M (the list exists in the measurement script output; the clinician's time is the cost).
- **Recommendation.** Do next, before the first real import is deployed.

## (p) Bulk review page for promotion

- **Value.** The clinician reviews the promotion CSV in a page (approve, reject, generic picker that only offers names that resolve) instead of a spreadsheet.
- **Risk.** The review data is clinic-derived; the page must run on the operator machine only, never in the clinic app. A generic picker that offers fuzzy matches would undo check 1.
- **Size.** M. **Depends on:** I1-g simple Task 4.
- **Recommendation.** Later, after the CSV flow has run twice.

## (q) Clinician re-ranking of the A1 top three per generic

- **Value.** Small. A1 ranks by pack variants, a proxy; Crocin, Dolo and Calpol sit 4th to 6th for Paracetamol but are already in the core list (A.5).
- **Risk.** None to the sheet; time only.
- **Size.** S-M. **Depends on:** I1-g simple Task 5.
- **Recommendation.** Later. Promotion (built) brings in the brands clinics really use.

## (r) Per-clinic autoformat from the clinic list

- **Value.** A clinic's own brand, misheard, would be rewritten to the clinic's spelling.
- **Risk.** A wrong rewrite (Famcin -> Amcin) would exist in one clinic only, hard to find and review; clinic names have no trusted generic link, so no dose check (`core/formulary.py:211-213`). It needs an admin-approved flag per clinic and its own five checks.
- **Size.** M. **Depends on:** I1-h, (o).
- **Recommendation.** Later, only if a clinic asks. Promotion covers the shared case.

## (s) Revisit the CDCI licence wording and hosting

- **Value.** Legal certainty before a wider release.
- **Risk.** CC BY 4.0 has no territory limit; "redistribution within India" (CDCI `License.txt`) may be a separate condition. The owner accepted the working wording on 2026-10-17 for the first import ("use as proposed, revisit later").
- **Work.** Read the CDCI terms again; decide before the repository or a deployment is hosted outside India; update the `sources` record wording by a new import id if it changes.
- **Size.** S (owner time). **Depends on:** none.
- **Recommendation.** Do before any hosting outside India or a wider release.

## Clinic-facing ideas for the medicine lists (owner request, 2026-10-17)

## (t) Audit view: what the clinic learned, when, and from whose confirmation

- **Value.** An admin sees why a name is "Known to your clinic" and spots a patient name early. The data exists: `added_by`, `first_seen_at`, `last_seen_at` (`db/formulary.py:5`, migration 009).
- **Risk.** Per-doctor attribution is a small prescribing profile: show it to admins only.
- **Size.** S-M. **Depends on:** I1-h4 (Team tab), card (k) for real roles.
- **Recommendation.** Later; first after (k) or with the first clinic that has several doctors.

## (u) Restore a removed clinic name

- **Value.** An admin undoes a wrong removal at once instead of waiting for two new prescriptions (removal resets the count, `db/formulary.py:39`).
- **Risk.** Low; restore only names this clinic learned; recount from `clinic_formulary_docs`.
- **Size.** S. **Depends on:** I1-h3, I1-h4.
- **Recommendation.** Later; bundle with card (e).

## (v) "New this week" list for the admin

- **Value.** The admin reviews newly learned names weekly; the cheapest guard against a patient name or a typo that slipped past the rules (owner risk (c)). An in-app list on the Team tab, not an email: no mail system exists.
- **Risk.** Low.
- **Size.** S. **Depends on:** I1-h4.
- **Recommendation.** Do soon after the first clinic goes live; it replaces most of the need for (f).

## (w) Usage report for the admin (top 20 medicines)

- **Value.** Stock and formulary planning; `top_medicines` already exists (`db/__init__.py:378-403`).
- **Risk.** Low per clinic; never per doctor (see (b)).
- **Size.** S. **Depends on:** I1-h4.
- **Recommendation.** Later, when a clinic asks.

## (x) Admin-set generic on a clinic-learned brand

- **Value.** A clinic name gets a generic link, so promotion has it pre-filled; the column exists (`clinic_formulary.generic`, migration 009).
- **Risk.** A wrong link would give a wrong dose check if the clinic list ever used it; keep it display-only, and accept only a generic that resolves exactly (check 1).
- **Size.** S-M. **Depends on:** I1-h4, I1-g simple Task 4.
- **Recommendation.** Later; useful once promotion runs.

## (y) Near-duplicate spellings inside the clinic list

- **Value.** "Zorbexin" and "Zorbexine" both learned: the Team tab marks the pair so the admin removes one.
- **Risk.** None if it only marks; never merge automatically.
- **Size.** S. **Depends on:** I1-h4.
- **Recommendation.** Later.

## (z) Second-source check of imported brands

- **Value.** Catches wrong CDCI mappings (Heparin -> HCG, Humatrope -> Somatostatin, A.2). NPPA price lists are the only legitimate second source (brand, generic, strength; price-controlled drugs only).
- **Risk.** Partial coverage; a disagreement needs a clinician, not code.
- **Size.** M. **Depends on:** card (s) for that source's licence.
- **Recommendation.** Later. The 60-row clinician sample (I1-g simple Task 5) is the stopgap.

## (aa) Lexicon version and sources on the Team page

- **Value.** Support and trust: "which medicine list is this clinic on". `/api/health` already reports `lexicon_version` (`tests/test_determinism.py:140-145`); add the `sources` names and dates.
- **Risk.** None.
- **Size.** S. **Depends on:** I1-g simple Task 3.
- **Recommendation.** Do next, with (h).

## (ab) Per-clinic "do not suggest" list for Spell it

- **Value.** A clinic hides a suggestion it never uses.
- **Risk.** Hides a correct answer in exactly the unclear-sound case Spell it exists for.
- **Size.** S-M. **Depends on:** card (e).
- **Recommendation.** Never on its own; if needed, fold into (e) "do not learn".

**Considered and not added:** export/import of a clinic list between clinics of one owner (a cross-clinic data flow with no owner grouping in the directory; promotion covers the shared need; never for now); the generic on the printout (already open decision 3 in the index section 5); a brand-to-generic tooltip (the generic already shows on screen, contract 4.1).

## Follow-ups from the lexicon implementation review (I1-g simple, 2026-10-17)

Evidence: `.superpowers/sdd/2026-10-17-i1-g-lexicon-simple/task-1-report.md` to `task-4-report.md` and the final review. Code is uncommitted on `iteration-1`.

## (ac) Runtime English/clinical dictionary guard for `correct_drugs`

- **Value.** Safety. The fuzzy pass rewrites any 5+ letter token within 0.84 of a lexicon key unless it is ambiguous or one of the 603 denylist words (`core/determinism.py:191`). So "garden" -> Arden, "epigastrium" -> Gastrium, "singular" -> Singulair. A guard skips the fuzzy rewrite of any token that is itself a dictionary word; an exact lexicon hit still applies.
- **Today.** The 40 brands of the curated class `english-or-clinical-word-rewritten-in-transcripts` (`core/lexicon/import_rules.json`) are only a stopgap: they cover just the words found by the 320-sentence OPD set and the macOS web2 scan (204,880 words). A future import can bring a new collision.
- **Risk.** A misheard drug that happens to be a dictionary word stays as heard and becomes `unknown-medicine` (the safe direction). Needs a word list with a clean licence and a size check against the `core/` purity rule (data files only).
- **Size.** M. **Depends on:** a word list choice.
- **Recommendation.** Do next, before a second import and before any curated skip is removed.

## (ad) Scan the existing 508 brands, and review the 364 pre-existing wrong-drug rewrites

- **Value.** Safety. The seed brands never went through checks 4 and 5, so an existing brand may be one slip from an ordinary word, as Arden was. Measured on the imported copy: over 23,610 distinct A3 brands, `tablet <brand> 500 mg` rewrites into a DIFFERENT drug 364 times, all pre-existing (the 444-entry lexicon alone), for example Famcin -> Amcin and Clopin -> Clozapine. This extends card (o), whose 194 used a stricter count.
- **Work.** Run the sentence set and the dictionary scan against the 508 seed brands; hand the 364 rows to a clinician with card (o).
- **Risk.** Removing or renaming a seed brand changes recognition for every clinic; needs tests per change.
- **Size.** M (clinician time). **Depends on:** (o).
- **Recommendation.** Do next, folded into (o).

## (ae) Atomic writes of `drugs.json` and `imported.json`

- **Value.** A failed run never leaves the two files out of step. Today `build.write_drugs` (`core/lexicon/build.py:60-67`) and the `imported.json` write in `apply_import` (`:210-211`) use plain `write_text`, `imported.json` first. A crash between them makes `--check` fail.
- **Today.** Workaround in plan I1-g simple Task 5 Step 7: restore both from git and re-run.
- **Work.** Temp file plus `os.replace`, as `promotion.write_atomic` does (`doctor_dictation/promotion.py:87-95`); a test that a failed replace leaves both files intact.
- **Risk.** Low. **Size.** S.
- **Recommendation.** Do next, before a second import or the first promotion.

## (af) Four brands lose speech-split recovery: Amlong, Fortum, Forcan, Losar

- **Value.** Speech-to-text can split a brand into two words ("am long", "for tum", "for can", "lo sar"). The split join now skips a pair when BOTH words are ordinary (`core/determinism.py:178`), so these four existing brands are no longer rejoined.
- **Option.** An allow-list of brand keys that may be joined from two ordinary words, perhaps only when a strength or dose follows.
- **Risk.** Joining two ordinary words is exactly what the rule stops ("for can" in plain speech).
- **Size.** S. **Depends on:** real clips showing the split.
- **Recommendation.** Later, only if doctors report one of the four.

## (ag) Same-drug near-brand skips (about 68 rows)

- **Value.** More brands. Check 5 exempts a near GENERIC or alias of the same drug, and a near word of the same drug's multi-word names, but not a near BRAND of the same drug (`core/lexicon/lexicon_import.py:148-150`). The final review measured about 68 A1 rows that a looser rule (same-drug brands exempt too) would admit.
- **Risk.** A same-drug rewrite keeps the drug and the dose check, but the sheet prints a sibling brand, not the dictated one (against the brand-as-dictated rule, I1-b).
- **Size.** S (one condition and tests). **Depends on:** an owner ruling on printing a sibling brand.
- **Recommendation.** Later; decide after the first import is in use.

## (ah) A `clinician-rejected` skip class workflow

- **Value.** Fewer hand edits and an audit trail. Today every 'n' on the clinician sheet becomes a hand-added `skip_brands` entry in a new class `clinician-rejected`, the `49` pin in `tests/test_lexicon_import.py:342` is raised, and the dry run is repeated (plan I1-g simple, Task 5 Step 5). The class itself needs no code: `load_rules` flattens any class (`core/lexicon/lexicon_import.py:58-64`).
- **Work.** A small script that reads the sheet's `clinician_ok (y/n)` column and writes the class with the reviewer and date in `_comment`; replace the fixed `49` pin by a per-class check.
- **Risk.** Low (licensed data only, no clinic data). **Size.** S.
- **Recommendation.** Later, after the first manual review shows the volume.

## (ai) Memory cap for `read_csv`

- **Value.** Robustness. `read_csv` reads the whole file into memory (`core/lexicon/lexicon_import.py:69`); `MAX_ROWS` (200,000, `:30`) caps rows, not bytes. The final review measured about 211 MB extra for a 1e6-row file.
- **Work.** A byte cap before the read (or a streamed read) with a clean error.
- **Risk.** None. **Size.** S.
- **Recommendation.** Later; the input is the operator's own file.

## (aj) `.venv` symlink shows as untracked

- **Value.** Hygiene. `.gitignore:2` has `.venv/`, which matches only a directory. The worktree's `.venv` is a symlink to the main checkout's venv, so `git status` shows `?? .venv`, and a careless `git add -A` would commit it.
- **Work.** Add a `.venv` line (no slash) to `.gitignore`.
- **Risk.** None. **Size.** S.
- **Recommendation.** Do next (one line; owner approval, because it changes `.gitignore`).

## (ak) Review CSV on a shared or synced drive

- **Value.** Privacy. The promotion review CSV is clinic-derived. `write_review` refuses only paths inside the repository other than `doctor_dictation/data/` (`doctor_dictation/promotion.py:156-159`); an operator could write it to a synced folder (Dropbox, OneDrive, a network share), where it persists and is shared.
- **Option.** Accept `--out` only under `DATA_DIR`, or warn on a known sync folder; the runbook rule stays (keep it under `$DATA_DIR/promotion/<batch>/`, delete after the apply).
- **Risk.** False warnings; an operator who needs another path. **Size.** S.
- **Recommendation.** Later; before promotion runs on more than one operator machine.

---

## (j) Deferred items still open (from the project memory, 2026-10-17)

One line each, grouped by area, with the plan they came from. Dropped as closed by a later plan: the correction-path five-letter floor (I1-a), heard/lookalike lost after correct (I1-e2 `RxView.meta`), "?" in the PDF (Check column removed, I1-e2), the test key guard (`tests/conftest.py`, I1-e3), and "Public Sans not first" (I1-f2). The other items are as recorded and were not re-verified one by one. Spot-checked as still open: the broad `except ValueError` (`api/rx.py:66-69`), the vacuous `or True` (`tests/test_rx_check_row.py:149`) and no `@font-face`.

**Matching, hints and the LLM**
- Hints map a brand back to its generic (`core/hints.py:33`). (I1-b)
- LLM repair suggestions are generics only. (I1-b)
- "Zyloric (Allopurinol)" from the LLM becomes `unknown-medicine`; needs one live-LLM check. (I1-b)
- Omega-3 displays as "Acids" on the rules path. (I1-b)
- A clinic drug spelled within 0.84 of a lexicon word is read as that lexicon drug (ruling R4, owner flag; `tests/test_formulary.py:191-204`). (I1-h2)

**Look-alike guard**
- A voice rename between twins flags the new row with the rejected drug. (I1-a)
- The curated look-alike list flags brands too; a clinician decides whether brands are exempt. (I1-a)
- The five-letter evidence floor loses short co-dictations (omez + razo, ismo + isdn, avil + cpm); replace it with a common-word list. (I1-a)
- `heard_as` should prefer alias stretches through `ix["exact"]`. (I1-a)

**Dose check**
- A hand-typed age like "45M" silently skips the dose check. (I1-c)
- `dose-check` hides the look-alike question on the same row. (I1-c)
- The LLM path always supplies a form (default `Tab.`), and the page cannot mark a defaulted form. So about 22% of drugs would false-flag `form-mismatch` once a real reference ships. (I1-c, I1-d, I1-e2)
- Strength chips come from the reference, but strength grounding uses the lexicon. (I1-d, owner)

**Check-row route and API robustness**
- Narrow `except ValueError` in `api/rx.py:66-69` to the `ground_one` call. (I1-d)
- Remove the vacuous `or True` at `tests/test_rx_check_row.py:149`. (I1-d)
- A lone surrogate, or a non-list `rx`, gives a 500 on format, correct and save. (I1-d)
- The 8-word worst case takes about 0.5 s through the route. (I1-d)

**Rx row, Spell it and the page**
- Legacy missing-status wording, raw status text, view-only Save label, blank-server-row label. (I1-e)
- Duplicate live regions: about 16 with 6 rows. (I1-e, I1-e2)
- `Authorship.clear()` is safe only by call order. (I1-e2)
- Stale plan line-number comments in `app.js`; dead `confirmAllBtn` code in `authorship.js:80,108`. (I1-e2)
- `#grounding` is stale after New patient (hidden). (I1-e2)
- Chips on a view-only sheet rely on a CSS and JS click guard. (I1-e2)
- Saving an all-blank sheet leaves an empty table without a placeholder (pre-existing). (I1-e2)
- "Use this" keeps the typed casing. (I1-e3)
- View-only hides Spell and chips but sets no `disabled` attribute. (I1-e3)
- No Spell button on `verified`, `unverified-strength` or `dose-check` rows. (I1-e3)
- A late check answer during `/correct` is silently lost; focus jumps when a second row's check lands. (I1-e3)
- Instructions near 600 characters plus the marker can make the next Spell a 400. (I1-e3)
- Spell on an unknown name appends "[unverified: confirm with doctor]". (I1-e3)

**Steppers**
- The stepper stays "Problem" after a failed correction while the sheet is live. (I1-f)
- Step 4 stays "Ready to save" after Save; step 3 says "checked" for hand-edited rows. (I1-f)
- The chip and `#status` both announce each stage. (I1-f)
- A `useClinic` failure at `letterhead.js:83/85` overwrites `#profLhMine`. (I1-f)
- "All medicines are ready. You can Save." reads oddly with zero rows. (I1-f)

**Layout and visual polish**
- `.sidebar` / `.middle` `top:70px` in `styles.css` is not tied to `--topbar-h`; the width test guards only the old 250 px. (I1-e2)
- `app.js` is 1221 lines (over 500 since before Iteration 1). (I1-f)
- The 1024 px sheet pane is cramped; the Spell input focus ring overlaps the last hint. (I1-f2)
- The Print button is an emoji, not an SVG; the print token pin covers only `--ink` and `--muted`. (I1-f2)
- Today scope is 34 px and Team row actions are 37 px (under 44 px targets); the top bar wraps at 390 px. (I1-f2)
- `outline:none` remains on contenteditable and `.field` inputs. (I1-f2)

**Tests and developer tooling**
- Non-key `.env` values still load in tests (Whisper download risk). (I1-e3)
- `.venv/bin/python -c` probes in the worktree need `PYTHONPATH=.`. (I1-c)

---

## Priority table

| Card | Value | Risk | Size | Depends on | Recommendation |
|---|---|---|---|---|---|
| (f) two different patients | Closes owner risk (c) | Rare drugs learn later (safe) | S-M | I1-h1..h3 | **Backlog** (owner: no extra restriction in first pass; revisit with real data) |
| (h) tablist arrow keys | Accessibility | Low | S | I1-h4 | **Do next** |
| (j) `except ValueError`, `or True` | Code hygiene | None | S | none | Do next (bundle with (h)) |
| (e) "do not learn" | Stops a junk name returning | Blocks a real drug (safe) | M | I1-h3, h4, r1 | Later |
| (a) top-medicines quick-pick | Faster repeat Rx | Mis-tap between neighbours | M | I1-r1, h3, e3 | Later (product decision) |
| (g) two-word brands | Learns "Zorbexin Forte" | A surname on the list | S | I1-h1 | Later |
| (i) self-hosted fonts | Same type everywhere | Page weight, licence | S | I1-f2 | Later |
| (j) the other deferred items | Varies | Varies | S each | varies | Later, by area |
| (b) per-doctor popularity | Small (already in hints) | Privacy, sparse data | M | I1-r1 | Never |
| (d) specialty / time-of-day hints | Small | Sparse, hard to reproduce | M-L | schema | Never |
| (c) boost beyond tie-break | Popular first | LASA error one tap away | S | I1-r1 | **Never** |
| (k) real RBAC | Right rights per role; ends "everyone is admin" | Lock-out, silent default change | L | owner's role model | Later, own iteration (before a larger clinic goes live) |
| (o) review today's near-collision rewrites | Fewer wrong-drug rewrites | Recognition changes | M | clinician | **Do next** (before the first import is deployed) |
| (aa) lexicon version on the Team page | Support, trust | None | S | I1-g simple T3 | **Do next** (with (h)) |
| (s) revisit CDCI licence and hosting | Legal certainty | Hosting outside India | S | owner | Before hosting outside India or a wider release |
| (v) "new this week" list | Early catch of a patient name | Low | S | I1-h4 | Soon after the first clinic goes live |
| (l) broad A3 list in Spell it | More correct spellings offered | Must never rewrite or flag | M-L | (s), first import | Later, own plan (g3) |
| (m) new generics + look-alike pairs | Hospital drugs recognised | High-alert twins | M | clinician | Later, only if OPD needs them |
| (n) forms, strengths, percent | Chips for imported brands | Wrong strengths | M | dosing reference | Later |
| (p) bulk promotion review page | Faster clinician review | Clinic data on a page | M | I1-g T4 | Later (after two CSV runs) |
| (q) re-rank A1 top three | Small | None | S-M | first import | Later |
| (r) per-clinic autoformat | Clinic spelling restored | Unreviewed wrong rewrites | M | I1-h, (o) | Later, only if a clinic asks |
| (t) audit view | Why a name is known | Per-doctor profile | S-M | I1-h4, (k) | Later |
| (u) restore a removed name | Undo a mistake | Low | S | I1-h3, h4 | Later (with (e)) |
| (w) top-20 usage report | Stock planning | Low | S | I1-h4 | Later, on request |
| (x) admin-set generic | Pre-filled promotion | Wrong link | S-M | I1-h4, I1-g T4 | Later |
| (y) near-duplicate spellings | Cleaner clinic list | None (mark only) | S | I1-h4 | Later |
| (z) second-source check (NPPA) | Catches wrong mappings | Partial coverage | M | (s) | Later |
| (ab) "do not suggest" list | Hide unused suggestions | Hides a right answer | S-M | (e) | Never alone; fold into (e) |
| (ac) runtime dictionary guard | No ordinary word rewritten to a brand | A misheard drug stays as heard (safe) | M | word list | **Do next** (before a second import) |
| (ad) scan 508 seed brands, 364 wrong-drug rewrites | Fewer wrong-drug rewrites | Recognition changes | M | (o) | **Do next** (fold into (o)) |
| (ae) atomic `drugs.json` / `imported.json` writes | No half-written lexicon | Low | S | none | **Do next** (before a second import) |
| (af) four brands lose split recovery | Amlong, Fortum, Forcan, Losar rejoined | Joins ordinary words | S | real clips | Later, on report |
| (ag) same-drug near-brand skips (~68) | More brands | Prints a sibling brand | S | owner ruling | Later |
| (ah) `clinician-rejected` workflow | Fewer hand edits, audit trail | Low | S | first review | Later |
| (ai) `read_csv` memory cap | Robustness | None | S | none | Later |
| (aj) `.venv` symlink ignore | Hygiene | None | S | owner | **Do next** (one line) |
| (ak) review CSV on a shared drive | Privacy | False warnings | S | none | Later (before a second operator) |

**Decision needed:** approve (o) with (ad), (aa), (ac), (ae) and (aj) as the next items. Card (f) stays deferred by the owner. Not decided here on purpose: the product questions of card (a), and the open decisions in the index section 5.
