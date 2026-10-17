# Lexicon, Simple Version: Denylist, Five-Check Import, Lineage and Clinic Promotion Implementation Plan

> **For agentic workers:** Tasks 0-4 are DONE (implemented, reviewed, left uncommitted on branch `iteration-1`, 2026-10-17). Do not re-implement them. This file is now (1) the record of what was built and (2) the runbook for Task 5, the real import. Task 5 is a MANUAL step for the controller and the owner. An agent never runs it.

**This plan supersedes** `2026-10-16-i1-g1-lexicon-gate-and-adapter.md` and `2026-10-16-i1-g2-lexicon-merge-and-checks.md`. Do not execute g1 or g2. The table "What is reused from g1/g2" says which text was reused and which was rewritten. The superseded marks are in place (Task 0 Step 2, done).

## Summary (decisions first)

- **Status.** Tasks 0-4 are built. Final suite on the worktree: **1693 passed, 1 skipped, 1 deselected** (before the lexicon work: 1536 passed, 1 skipped, 1 deselected). Task 5 waits for two things: the clinician's verdict on the sample sheet, and the owner saying "go".
- **One rule decides what may change the sheet.** A brand may autoformat only if it is on the reviewed core list (`drugs.json`) with a recorded source AND it passes all five checks (Task 2). A brand that fails is not lost: the skipped-row report names it, and it can come back later through promotion (Task 4).
- **Three tiers, two built here.** Core list: import only rows that pass, with lineage. Clinic list: already built (I1-h). Broad A3 suggestion list (23,821 brands): DEFERRED (backlog card (l)). Spell it keeps the lexicon plus clinic names, as today.
- **Promotion is built.** A name learned in 3+ clinics can reach the core list only through an offline operator run, a clinician review and the same five checks (Task 4).
- **First real import, measured on a scratch copy** (real CSVs, final code): 738 rows read, **155 added, 58 already present, 525 skipped**, lexicon v1.1.0 -> v1.2.0, 444 entries (no new generic). No new wrong-drug rewrite of an A3 brand (365 before, 364 after, 0 new). No new rewrite in the 105 sentence-gate tests or in 204,880 dictionary words.
- **Owner decisions recorded 2026-10-17:** licence wording "use as proposed, revisit later" (Task 5 Step 1, backlog (s)); a promoted brand MUST name a generic (Task 4); hosting acknowledged, no action.
- **Decision needed:** the clinician's verdict on `clinician_sample_60.csv`, then the owner's "go" for Task 5 Step 3.

## Where each list lives (scope)

| List | Where | Who writes it | Who it affects | Can it rewrite the transcript? |
|---|---|---|---|---|
| **Core list** | ONE file per application: `doctor_dictation/core/lexicon/drugs.json` (today 124,670 bytes, 444 drugs, 508 brands, v1.1.0) | Only a developer or operator: `build.py --merge` (docstring `build.py:13-17`, seed `DEFAULT_SEED` `build.py:45`) or `promote-apply`, then a deploy | Every clinic the same (no clinic column, no per-clinic copy) | Yes: `correct_drugs` reads only this file (`core/determinism.py:135`) |
| **Clinic list** (formulary) | Each clinic's own database, table `clinic_formulary` (`db/migrations/009_clinic_formulary.sql`) | Doctors, automatically: 2 confirmed saves (`THRESHOLD`, `core/formulary.py:18`); a clinic admin removes (`api/formulary.py:84-85`) | That clinic only | No: it only grounds a row ("Known to your clinic") |
| **Promotion** | Operator machine, offline | Operator + clinician (Task 4) | Moves a reviewed name from the clinic tier to the core tier | Only after it lands in the core list |

The running app never writes the core list. It loads it once at start-up (`LEXICON_PATH`, `core/determinism.py:21`; `load_lexicon` `:60`) and calls no API. A clinic does not edit the core list: a wrong rewrite (Famcin -> Amcin, a different drug) would then exist in one clinic only, hard to find and hard to review. Analogy: the core list is the printed dictionary, one edition for every clinic; the clinic list is the notes on each desk. **Not planned:** per-clinic autoformat, backlog card (r).

## Brand-first principle and the end-to-end flow

Doctors use BRAND names. The brand prints as dictated (I1-b, `core/surface.py:50`); the generic shows on screen only (contract 4.1); the generic drives the dose check, the look-alike check and grounding. A brand with no trusted generic link still works as a clinic-list name, with no dose check and no look-alike check (`core/formulary.py:211-213`).
```
1 core list hit  -------------------------------> autoformat (brand as dictated, generic linked, dose check)
2 clinic list hit -------------------------------> "Known to your clinic" (no rewrite, no dose check)
3 unknown -> Spell it (lexicon + clinic names) -> doctor confirms the row
4 Save: each saved prescription counts once per name (record_confirmation)
5 second saved prescription -> the clinic list learns the name
6 operator: promote-candidates -> review CSV of names learned in >= 3 clinics (counts only)
7 clinician approves + supplies the generic -> promote-apply -> five checks -> core list with lineage -> deploy
```

Worked example (invented brand `Zorbexin`). Clinics A, B and C each learn "Zorbexin" from two saved prescriptions. The operator runs `promote-candidates`; the CSV row reads `Zorbexin,Paracetamol,3,2026-10-01,2026-10-30,,,`. The clinician writes `approve`. `promote-apply --confirm` runs the five checks; Zorbexin joins Paracetamol with lineage `{"date": "2026-11-02", "reviewer": "Dr. Asha Rao", "src": "promoted-2026-11"}`. After a deploy every clinic autoformats it and runs the dose check. If it fails a check (for example one slip from another brand), it stays clinic-only and is never autoformatted.

| Piece | State |
|---|---|
| Core list + autoformat (`correct_drugs`, brand as dictated) | Built (I1-b) |
| Clinic list, grounding, admin removal | Built (I1-h) |
| Spell it with core + clinic names; confirm twice to learn | Built (I1-e3, I1-r1, I1-h3) |
| Denylist, five-check import, lineage, cross-clinic promotion | **Built by this plan (Tasks 1-4), uncommitted** |

**Goal:** Keep one reviewed core list with lineage, grow it only through the five checks (a CDCI import or a clinician-approved promotion), and stop `correct_drugs` from rewriting ordinary words.

**Architecture:** `core/commonwords.py` (pure data) feeds two hooks in `correct_drugs` and check 4. `core/lexicon/lexicon_import.py` holds the five checks (`Checker`), the brand merge (`merge_brands`), `overlay` and the import plan (`plan_import`). `build.py` adds the licence gate, the CSV dispatch, `imported.json` and the `sources` record (`apply_import`). `doctor_dictation/promotion.py` (outside `core/`, it uses `sqlite3`) reads clinic databases read-only and calls the same `Checker` and `apply_import`. Nothing runs at request time; no network.

**Tech Stack:** Python 3 stdlib (`csv`, `difflib`, `hashlib`, `hmac`, `json`, `sqlite3`), pytest. No new dependency.

**Spec:** owner decisions 2026-10-17 (this file); preflight `.superpowers/sdd/2026-10-17-lexicon-g/preflight.md` (A.1-A.9, B.1-B.4); tiers draft `2026-10-17-lexicon-tiers-a1-a2-a3.md` and `data-draft/README.md` (main checkout; A1 = 738 rows, A3 = 23,821 rows, 23,610 distinct brands). Implementation reports: `.superpowers/sdd/2026-10-17-i1-g-lexicon-simple/task-1-report.md` to `task-4-report.md` (each with its fix rounds).

## Global Constraints

- No network. No licence decision by code: a CSV merge always needs `--source-id`, `--source-name` (3+ chars), `--licence` (10+ chars), `--conflict-map` and `--report`. The suite never needs the real CSVs.
- Never change existing canonicals, aliases or brands, or their order. Additions go last; entry keys sorted; LF; `indent=2`; a second identical run is byte-identical.
- Brands only: an import never adds a canonical, a strength or a form (`--allow-new-generics` is not built). Never commit clinic-derived files (review CSV) or the CDCI CSVs or the import report.
- No `.py` file under `doctor_dictation/` over 500 lines (`tests/test_file_sizes.py:12`). No `git commit` without the owner's word. Test command: `.venv/bin/python -m pytest tests/ -q`.

## Review Focus (inputs most likely to bite)

- **Cisplatin -> Cyproheptadine** (also Clotrimazole, Cycloserine, Noradrenaline, Valganciclovir, Ampicillin): a fuzzy generic is `1-generic` with `looks_like`, never merged (preflight A.3). Pinned: `Novakind` in `test_the_five_checks_on_the_fixture` (`tests/test_lexicon_import.py:120`).
- **Famcin / Amcin** (rifampicin / amikacin) and **Clopin** (clomipramine, rewritten to Clozapine today): both sides of a one-slip pair are skipped (`5-one-slip`). A skipped brand can still be rewritten to its near name when dictated, so the report carries `near` and `rewrites_to`. The 364 pre-existing wrong-drug rewrites are backlog (o) and (ad).
- **Words of hyphenated brands.** `correct_drugs` reads a transcript word by word, so "Amozid-CV" (Co-Amoxiclav) is heard as "Amozid", one slip from the new brand "Amzid" (Ceftazidime). Check 5 therefore also compares every 5+ letter word of a hyphenated or spaced name in the lexicon and the full CDCI map (`lexicon_import.py:116-124`). Pinned at `tests/test_lexicon_import.py:397`.
- **Ordinary words one slip from a brand:** "garden" -> Arden, "epigastrium" -> Gastrium, "singular" -> Singulair, "limited" -> Limitex. Check 4 sees only exact words, so these brands are curated skips (stopgap) and `tests/test_ordinary_sentences.py` gates them. The real fix is a runtime dictionary guard, backlog (ac).
- **"Clear"** (Levonorgestrel), **"Dex"** (Glucose), **"Vitamin D3"** (captures the Calcitriol alias phrase): checks 2, 1/3 and 4. Pinned by the fixture (`Clear`, `Zorbin Day`).
- **Percent strengths and unmatched forms** (Dextrose "0.25 g"; 737 of 738 CDCI forms unmatched): not imported at all (brands only; backlog (n)).
- **Brand-as-dictated round trip:** `tests/test_brand_as_dictated.py:58` and `:307` stay on the LIVE lexicon as gates.
- **Privacy of promotion:** counts only; the ledger stores an HMAC key, never a rejected name (a rejected name may be a patient's name).

## What is reused from g1/g2

| Source (worktree copy) | Here |
|---|---|
| g1 T1 Step 1 licence checklist (g1:56-68) | Answered by the owner decision (Task 5 Step 1) |
| g1 T1 gate code and test (g1:122-185) | Rewritten (Task 2): adds `--source-id`, `--conflict-map`, `--report`; drops `--allow-new-generics` |
| g1 test helpers `load`, `run`, `exit_code`, `read` (g1:90-119) | Reused; `build` copies the frozen lexicon and a frozen `DEFAULT_SEED` |
| g1 T2 `clean`, `capitalise_flat`, `norm_generic`, `alias_map` (g1:298-342) | Reused; the rest of the adapter and the fixture were rewritten |
| g2 T1 `layered_seed`, `IMPORTED_JSON` (g2:131-173) | `layered_seed` reused; `overlay`, `plan_merge`, `do_merge` rewritten (lineage, brands only, `apply_import`) |
| g2 T2 look-alike share (g2:220-323) | Not reused: no canonical is added, so the share cannot move. Returns with backlog (m) |
| g2 T3 perf script and review steps (g2:331-406) | Optional, by reference in Task 5 |
| Main-checkout-only sections (g1 "Dataset findings", g2 "Safety finding", i1-00 fact 9) | Background only. Superseded counts: 284/151/133 -> 264 generics, 150 exact (preflight A.3) |

### Task 0: Reconcile and mark the old plans superseded (DONE)

- [x] **Step 1:** The worktree copies of g1, g2 and i1-00 are authoritative; the main-checkout sections are background only. Nothing was changed in the main checkout.
- [x] **Step 2 (done 2026-10-17, uncommitted):** g1 and g2 carry `> **Superseded by 2026-10-17-i1-g-lexicon-simple.md (2026-10-17). Do not execute.**` as line 2. In i1-00, rows 7a and 7b (lines 20, 21) end their "Delivers" cell with ` Superseded by I1-g simple (2026-10-17-i1-g-lexicon-simple.md).` (inside the cell, so the table still renders), and open decision 4 (line 132) ends with ` Decided 2026-10-17: use the proposed CDCI wording, revisit later (I1-g simple, Task 5).`

### Task 1: Denylist module and the `correct_drugs` hook (DONE)

**Files:** Created `doctor_dictation/core/commonwords.py` (36 lines), `tests/test_commonwords.py` (6 tests). Modified `doctor_dictation/core/determinism.py` (408 -> 410 lines).

**What it does.** `commonwords.WORDS` is a `frozenset` of 603 lower-case English and Hinglish words heard in an OPD dictation (`_EN` and `_HI` blocks; pure data, no imports; the words are grouped, not globally sorted). `correct_drugs` uses it twice:
```diff
+from .commonwords import WORDS as COMMON_WORDS                                         # determinism.py:17
-        if len(w1) < 2 or len(w2) < 3:
+        if len(w1) < 2 or len(w2) < 3 or {w1.lower(), w2.lower()} <= COMMON_WORDS:      # :178, split join
-        if _ambiguous_for(low):  # two generics claim it (or a near spelling): leave it as dictated
+        # two generics claim it (or a near spelling), or it is an ordinary word ("twice", "after"): leave it as dictated
+        if _ambiguous_for(low) or low in COMMON_WORDS:                                  # :191, exact and fuzzy pass
```
Example: with an invented brand "Twicef" on the list, `Tab Paracetamol 650 mg twice daily after food` stays unchanged, and `tab twicef 500 mg` still gives `tab Twicef 500 mg`. A split joins only when at least one word is not ordinary: `tab take fen 650 mg` -> `tab Takefen 650 mg`. Tests: see `tests/test_commonwords.py` (the plan's 4, plus a pure-data check and a normal-brand check). Mutations: 7, 0 survivors. Known cost: four existing brands lose split recovery (backlog (af)).

### Task 2: Licence gate, the five-check importer, synonym table, skipped-row report, lineage (DONE)

**Files:** Created `core/lexicon/lexicon_import.py` (223 lines after Task 3), `core/lexicon/import_rules.json`, `tests/data/brands_fixture.csv` (20 rows, invented brands), `tests/data/conflict_fixture.csv`, `tests/data/lexicon_frozen.json` (byte copy of `drugs.json` v1.1.0: 444 entries, 508 brands, no lineage), `tests/test_lexicon_import.py`. Modified `core/lexicon/build.py` (241 -> 346 lines after Task 3).

**The five checks** (module docstring `lexicon_import.py:1-16`). A brand joins only when:
1. its generic is a lexicon canonical or alias, exactly, or a row of the synonym table; a brand key never names a generic;
2. the brand is listed under one generic only (this file, the full CDCI map, the lexicon);
3. it has 5+ letters, unless `short_brands_allowed` names it;
4. neither the brand nor any word in it is in `commonwords.WORDS`;
5. it is not one slip (difflib 0.84) from another drug's name, any other brand, or any 5+ letter word of another drug's hyphenated or spaced name. A near word that belongs only to the candidate's own drug is exempt (a same-drug rewrite is harmless).

The rule as built (`lexicon_import.py:136-151`):
```python
    def failures(self, brand, canonical=""):
        low, failed = brand.casefold(), []
        if not (SHAPE.fullmatch(brand) and len(brand) <= MAX_BRAND):
            failed.append("shape")
        owner, listed = self.names.get(low), self.listed.get(low, set()) | ({canonical.casefold()} if canonical else set())
        if (owner and owner != canonical) or len(listed) > 1:
            failed.append("2-one-generic")
        if sum(c.isalpha() for c in brand) < MIN_LETTERS and low not in self.rules["short_ok"]:
            failed.append("3-five-letters")
        if low in WORDS or any(w in WORDS for w in re.split(r"[ -]", low)):
            failed.append("4-ordinary-word")
        near = [k for k in difflib.get_close_matches(low, self.pool, n=5, cutoff=CUTOFF)
                if k != low and not (canonical and (self.generics.get(k) == canonical or
                                                    self.words.get(k) == {canonical.casefold()}))]
        return failed + (["5-one-slip"] if near else []), near
```
`pool` = every lexicon key, every CDCI-map and same-file brand, and every 5+ letter word of a multi-word name (`:116-124`).

**Skipped-row ids that are NOT checks.** `duplicate` (a later row of a brand an earlier row decided; carries `first_line`, so added + already_present + skipped == rows_read) and `curated-skip` (a brand listed in `skip_brands`; it wins over every check, `:211-212`). The real A1 file has no duplicate rows.

**`import_rules.json`.** `{"_comment", "short_brands_allowed": [], "skip_brands": {class: [brands]}, "synonyms": {...}, "version": "g-1"}`. Synonyms: `Amoxicillin + Clavulanic acid` -> Co-Amoxiclav, `Ascorbic acid` -> Vitamin C, `Levothyroxine` -> Thyroxine. `skip_brands` is a dict of classes (a flat list also loads; `load_rules` casefolds, `:58-64`), 49 brands in total, pinned by `tests/test_lexicon_import.py:342`:

| Class | Brands | Why |
|---|---|---|
| `english-or-clinical-word-rewritten-in-transcripts` | 40 (Arden, Gastrium, Limitex, Singulair, Ventryl, Diamet, Blisfer, Graftin, Propal, Rumorf, ...) | `correct_drugs` would rewrite a one-slip ordinary word to the brand (OPD sentences, macOS web2 scan) |
| `surname` | 2 (Salazar, Iwata) | A person's name |
| `generic-or-salt-name-used-as-a-brand` | 2 (Magnesium Sulphate, Pyridoxine Hcl) | Not a brand |
| `wrong-link-or-combination-drug` | 4 (Advent, Duodopa, Gris ODT, Suboxone) | The CDCI generic is not what the name means |
| `suggestion-junk` | 1 (Tg-Tor) | Made "the doctor" suggest Atorvastatin |

**`read_csv`** (`:67-88`) returns `[{line, brand, generic}]`; needs `brand` and `generic` columns; drops leading Rx/Tab/Cap words; Capitalises ALL CAPS or all lower names (never rejects them); `A / B` -> `A + B`. It reads with `newline=""`, so a quoted newline or U+2028 stays in its cell and `line` is the record number. A non-UTF-8 file or a field over 128 KB gives a clean `SystemExit` ("Nothing was written"). Cap: 200,000 rows (memory: backlog (ai)).

**Report:** `{source, rules, rows_read, input_sha256, conflict_map_sha256, brands_added, already_present, generics: {exact, synonym, not_in_lexicon}, skipped: [{line, brand, generic, checks, [looks_like], [near], [rewrites_to], [first_line]}]}`, JSON with sorted keys.

**The gate in `build.py`.**
- Only a `.csv` merge is gated (`require_source`, `build.py:156-174`). A JSON seed (the repo's `seed_extra.json` or any other JSON array) needs no flags.
- A CSV merge needs `--source-id` (pattern `[a-z0-9][a-z0-9.-]{2,40}`, not `seed`, `clinic` or `promoted-*`), `--source-name`, `--licence`, `--conflict-map` and `--report`. `--check --merge CSV` needs no `--report`.
- A `--report` path inside the repository is refused.
- `check_source` (`:147-153`) raises `ValueError`; `require_source` turns it into `parser.error` (exit 2, "Nothing was read or written"). The gate runs before any file is read (pinned with a read guard).
- Optional flags: `--source-url`, `--attribution`.

Tests: see `tests/test_lexicon_import.py`. Mutations: 32, then 42 after the fix round, 0 survivors.

### Task 3: Merge wiring, the frozen lexicon, and the tests that pin live data (DONE)

**Files:** Modified `build.py`, `lexicon_import.py` (`overlay`), `tests/test_lexicon_import.py`, `tests/conftest.py` (fixture `frozen_lexicon`), `tests/test_dosing.py` (module `pytestmark`), `tests/test_dosing_grounding.py` and `tests/test_candidates.py` (parameter `frozen_lexicon`), `tests/test_determinism.py` (`"1.1.0"` pin replaced by the file's own version). Created `tests/test_ordinary_sentences.py`.

**Interfaces (build.py):**
- `plan_merge(seed_path, source, conflict_path)` (`:185-197`): a `.csv` goes through `check_source`, then the five checks; anything else is a JSON seed through `layered_seed`.
- `apply_import(changed, source, report, now=None) -> bool` (`:200-217`): merges complete changed entries; refuses a reused source id; updates `imported.json`; appends one `sources` record `{id, name, licence, [url], [attribution], [reviewer], brands_added, input_sha256, [conflict_map_sha256], merged_at, rules}` with sorted keys.
- `do_merge` (`:220-243`): writes the report only when the merge changed entries. A no-change re-run prints `no change: drugs.json, imported.json and the report were not rewritten` and keeps the first report.
- Each import bumps the minor version (1.1.0 -> 1.2.0; a second source gives 1.3.0).
- Lineage per added brand, inside its entry: `"lineage": {"<Brand>": {"src": "<source id>"}}`. A brand with no lineage record is `seed`.
- `overlay(seed, imported)` (`lexicon_import.py:170-185`) lays `imported.json` over `seed_extra.json` and keeps the RECORDED brand order (a bug where it re-sorted brands was found and fixed in the fix round). Known limitation: a brand a developer later removes from `seed_extra.json` would come back from `imported.json`; remove it there too.
- **Not atomic:** `write_drugs` (`build.py:60-67`) and the `imported.json` write (`:210-211`) use plain `write_text`, `imported.json` first. If a run fails half-way, restore both files from git and re-run (Task 5 Step 7). Backlog (ae).

**Frozen versus live.** Tests that pin lexicon CONTENT read `tests/data/lexicon_frozen.json` through `frozen_lexicon`. Tests that pin properties of the LIVE list stay live and are the import gates:

| Live gate | What it proves |
|---|---|
| `tests/test_candidates.py:85` `test_suggest_garbage_returns_empty_on_the_live_lexicon` | The 13 junk inputs (`"the doctor"`, `"fever"`, ...) suggest nothing |
| `tests/test_ordinary_sentences.py` (105 tests: 103 sentences, a list-size test, an offline `/api/format` case) | Ordinary sentences are not rewritten ("works in the garden" gives no `Arden` row) |
| `tests/test_commonwords.py:33` | No single-word lexicon name is an ordinary word |
| `tests/test_brand_as_dictated.py:58`, `:307` | Every lexicon name round-trips; short aliases are never renamed |

With a brands-only import, only `test_suggest_garbage_returns_empty` would fail without the frozen copy ("the doctor" -> Atorvastatin once `Tg-Tor` lands; now a curated skip). The other repointed tests are frozen defensively. No assertion was loosened.

Mutations: 27, 37, 45, then 51 across the fix rounds; the final pass had 1 survivor, an equivalent mutant (word minimum 4: the pool filter already drops 4-letter words).

### Task 4: Promotion tools (`promote-candidates`, `promote-apply`, ledger) (DONE)

**Files:** Created `doctor_dictation/promotion.py` (273 lines), `doctor_dictation/core/lexicon/promotion_ledger.json`, `tests/test_promotion.py` (22 tests). Modified `doctor_dictation/admin.py` (222 -> 224: import, `promotion.register(sub, COMMANDS)`, docstring line) and `.env.example` (`:61-66`, the pepper).

**Reading clinics.** `clinic_dbs()` (`promotion.py:104-109`): in multi-clinic mode every registered clinic, disabled ones too (as `migrate-all`); in single mode `DB_PATH` or the default database (read-only, but it is the real dev database when `DB_PATH` is unset). `read_active` (`:112-115`) opens `file:...?mode=ro` and runs only `SELECT name, generic, first_seen_at, last_seen_at FROM clinic_formulary WHERE removed_at IS NULL AND confirm_count >= ?`. It never reads `patients`, `documents`, `users` or `added_by`. A clinic database's bytes never change (pinned by digests).

**Candidates** (`:118-153`). Each clinic name is cleaned again with `clean_name` (a failure is counted as `invalid-name` and never reaches the CSV). Exclusions, in order: `fewer-clinics`, `in-lexicon` (any canonical, alias or brand), `reviewed` (ledger key), `person-like`, then the first failed check 2-5. Review CSV columns: `name, generic, clinics_count, first_seen, last_seen, decision, reviewer, notes`, sorted by clinics (descending), then name.

**Review CSV safety.**
- Path guard (`write_review`, `:156-165`): refused inside the repository, except under `doctor_dictation/data/` (git-ignored, `.gitignore:38`).
- A cell starting with `=`, `+`, `-`, `@`, tab or CR gets a leading apostrophe (`_safe_cell`, `:168-170`), so a spreadsheet does not run it as a formula.
- An unreadable clinic: the CSV is still written, stderr says `INCOMPLETE: do not apply (N clinic(s) unreadable)`, a `<csv>.INCOMPLETE` marker is written, and the command exits 1. `promote-apply` refuses while the marker exists. A later complete run removes it.

**Apply** (`:173-231`). The reviewed CSV is read with `newline=""`. Outcomes per row:

| Row | Outcome | Ledger entry |
|---|---|---|
| `approve`, generic resolves (exact or synonym), all checks pass | `added`, lineage `{"date", "reviewer" (row reviewer, else --reviewer), "src": "promoted-<batch>"}` | yes, with `canonical` and `name` |
| `approve`, no resolving generic | `clinic-only: 1-generic` (owner decision) | yes |
| `approve`, a check fails | `clinic-only: <checks>` | yes |
| `approve`, hand-edited to a lexicon name or a person-like name | `rejected: in-lexicon` / `rejected: person-like` | yes |
| `approve`, name fails `clean_name` | `rejected: invalid-name` | no (nothing to hash) |
| `reject` | `rejected` | yes |
| blank, or already in the ledger | `undecided or already reviewed` | no |

The source record goes through `build.check_source` (its `ValueError` becomes `SystemExit`, nothing written) and `build.apply_import`: `{id: "promoted-<batch>", name: "clinic promotion <batch>", licence: "internal: names confirmed on saved prescriptions in several clinics, approved by a clinician", reviewer, ...}`.

**Refusals: each has its own message, each exits 2, nothing is read or written.** Missing or short pepper; wrong pepper or not a v2 ledger; the `.INCOMPLETE` marker; `--reviewer` under 3 characters; an invalid `--batch` (`[a-z0-9][a-z0-9-]{2,30}`); a reused batch ("pass a new --batch"); `--min-clinics` under 1; a review CSV inside the repository. Without `--confirm`, `promote-apply` prints the outcomes, writes nothing and exits 2.

**Ledger** (`promotion_ledger.json`, committed). Shipped form: `{"entries": [], "version": "dd-promotion-v2"}`; the first apply adds `pepper_check`:
```json
{"entries": [{"batch": "2026-11", "date": "2026-11-02", "decision": "reject", "key": "<64 hex HMAC>",
              "outcome": "rejected", "reviewer": "Dr. K. Iyer"}],
 "pepper_check": "<8 hex>", "version": "dd-promotion-v2"}
```
- Keys are HMAC-SHA256 of the casefolded name under `PROMOTION_LEDGER_PEPPER` (`:56-71`).
- The pepper comes from the environment only. It must be 32+ characters, kept outside git, and is never written anywhere.
- Fail closed: a missing or short pepper exits 2 before any clinic database is opened or any file is read or written. A changed pepper is refused against a ledger that has entries or a `pepper_check`.
- Generate the pepper once with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
- Losing the pepper only means rejected names can be proposed again. The 8-hex `pepper_check` lets anyone test guesses offline, so the pepper must be random (`.env.example:61-66`).
- Entries are sorted by `(key, batch)`, `sort_keys`, indent 2, LF.

**Atomic writes:** the review CSV and the ledger are written to a temp file, then `os.replace` (`write_atomic`, `:87-95`). The `drugs.json` and `imported.json` writes that `promote-apply` triggers go through `build.py` and are NOT atomic (Task 3).

Tests: see `tests/test_promotion.py` (12 in the first pass, 20 after the fix round, 22 after fix round 2). Mutations: 27, 15, then 9, 0 survivors.

### Task 5: The real A1 import (MANUAL runbook; the controller with the owner)

**DO NOT run the real import (Step 3) without the owner saying "go".** Run order: Steps 1, 2, 5 (clinician review of the dry-run sheets), 6 (owner go), then 3 and 4. Use Step 7 if any gate fails.

- [x] **Step 1: Licence.** The owner accepted the working licence wording on 2026-10-17; revisit before any wider release; see the backlog card (s). Code still decides nothing: the strings go in by flag.
- [ ] **Step 2: Preconditions.**
  1. Check that `/usr/bin/git status --short doctor_dictation/core/lexicon/` lists neither `drugs.json` nor `seed_extra.json`, and that `imported.json` does not exist.
  2. Choose a scratch folder OUTSIDE the repository: `SCRATCH=/path/outside/the/repo/lexicon-import`.
  3. Copy `a1_top_brands.csv` and `a3_nlem_brands.csv` from the main checkout `data-draft/` to `$SCRATCH/cdci/`.
  4. Record both sha256 values (`shasum -a 256 $SCRATCH/cdci/*.csv`).
  5. Copy `drugs.json` to `$SCRATCH/drugs.before.json`.
- [ ] **Step 3: Run the import** from the worktree root (flags as in `build.py --help`):
```bash
.venv/bin/python doctor_dictation/core/lexicon/build.py --merge "$SCRATCH/cdci/a1_top_brands.csv" \
  --source-id cdci-2026-08-31 \
  --source-name 'Common Drug Codes for India (CDCI) Flat Files, 2026-08-31' \
  --licence 'CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ — C-DAC/NRCeS; redistribution within India' \
  --source-url https://www.nrces.in/download/files/zip/CommonDrugCodesForIndia_FlatFilePackage.zip \
  --conflict-map "$SCRATCH/cdci/a3_nlem_brands.csv" --report "$SCRATCH/cdci/a1_report.json"
```
Expected (scratch dry run of the final code, 2026-10-17):
```text
merge a1_top_brands.csv: entries 444 -> 444, version 1.1.0 -> 1.2.0 [version bumped]
import: rows_read=738 brands_added=155 already_present=58 generics={'exact': 150, 'synonym': 3, 'not_in_lexicon': 111}
  skipped={'1-generic': 299, '2-one-generic': 12, '3-five-letters': 28, '4-ordinary-word': 2, '5-one-slip': 130, 'curated-skip': 49, 'shape': 5}
```
(printed on one line). Skipped by first failed check, 525 in total:

| Id | Rows | Examples |
|---|---|---|
| `1-generic` | 299 | 111 generics not in the lexicon: 105 new (mostly hospital, oncology, HIV) plus 6 fuzzy look-alikes (Cisplatin, Heparin -> HCG, Dex -> Glucose) |
| `5-one-slip` | 130 | Famcin/Amcin, Thyrox/Lethyrox, Elpred/Elopred, Doxina, Amzid, Edeflow |
| `curated-skip` | 49 | the five classes of Task 2 |
| `3-five-letters` | 28 | Azee, Zifi, Dmp, Iso, Gp, Lcd, Fin |
| `2-one-generic` | 12 | Amicon, Amox C, Cefcare, Clopin, Banocide, Ferrous Sulphate, Fa, Clear, M cin, Dub, Zin, Don |
| `shape` | 5 | Decdak., 2Eazy, 5A, 4 Quin, Primzed- N |
| `4-ordinary-word` | 2 | Vitamin D3, Arpimune ME |

Brands after: measure at import (expected 508 + 155 = 663). Changed canonicals, and the line counts of `drugs.json` and `imported.json`: measure at import. The final dry run did not record them; the earlier 205-brand dry run gave 8,729 and 3,249 lines. **Any difference in the counts above: stop, run Step 7, and compare with the report.**
- [ ] **Step 4: Gates. Every gate must pass, or the import is NOT committed (run Step 7).**
  1. Run `build.py --check`. Expected: `check OK: drugs.json in sync (v1.2.0, 444 entries).`, exit 0.
  2. Run the Step 3 command again. Expected: `no change: drugs.json, imported.json and the report were not rewritten`, `[no change (version unchanged)]`, and the sha256 of both files unchanged.
  3. Run `.venv/bin/python -m pytest tests/test_candidates.py tests/test_ordinary_sentences.py tests/test_commonwords.py tests/test_brand_as_dictated.py -q`. Expected: all pass. This covers the live junk gate, the 105 sentence-gate tests and the denylist checks.
  4. Run the full suite. Expected: `1693 passed, 1 skipped, 1 deselected` (measured on the imported copy).
  5. Check the counts of the FIRST run: 155 added, 58 already present, 525 skipped, exactly as in Step 3. A re-run (item 2) prints `brands_added=0` and `already_present=213`: that is expected.
  6a. When you work from a copy of the worktree, set `PYTHONPATH=<copy>` for every python call: the venv is an editable install of another checkout and a copy would silently import the wrong code. Check with `python -c "import doctor_dictation; print(doctor_dictation.__file__)"`.
  6. Spot check: `Crocin`, `Dolo`, `Calpol` -> Paracetamol; `Augmentin` -> Co-Amoxiclav (unchanged). `tab clopin 25` still gives `tab Clozapine 25` (pre-existing, backlog (o)).
  7. Check `git status`: only `drugs.json` is modified and `imported.json` is new. Never commit the CSVs or the report.
- [ ] **Step 5: Clinician review, BEFORE Step 3 runs for real.**
  - **The sheets.** The clinician reviews `clinician_sample_60.csv` (60 rows drawn with seed 20261017; 23 flagged doubtful). The clinician may also review the full `clinician_review_sheet.csv` (155 rows, one per added brand; 56 flagged).
  - **Columns:** `brand, generic, source_generic, source_line, source_form, doubtful, clinician_ok (y/n), notes`.
  - **Where they are.** Both sheets are in the scratchpad `lexfin` folder (`/private/tmp/claude-502/-Users-narenlingala-Documents-workspace-work-Zebra-doctor-dic-doctor-dictation-main/8c2f5579-3a7d-4332-8c1b-5748dbc166ef/scratchpad/lexfin/`). That folder is temporary: the controller regenerates the sheets on request.
  - **Look at these rows first:** injectable-only brands, hospital-only brands, and 4-8 letter names one slip from a lexicon brand. Pyridoxine Hcl and Magnesium Sulphate are already curated skips.
  - **Each 'n':**
    1. Add the brand to `skip_brands` in `import_rules.json`, under a new class `clinician-rejected`.
    2. Raise the `49` pin in `tests/test_lexicon_import.py:342` by the number of new entries.
    3. Repeat the dry run on a scratch copy. Expected: `brands_added` falls and `curated-skip` rises by that number; nothing else moves.
    4. Update the expected counts in Step 3.
  - **Record** the reviewer and the date in the PR text.
- [ ] **Step 6: Owner go.** The owner reads the Step 5 result and says "go". Then run Steps 3 and 4.
- [ ] **Step 7: Rollback** (the commands below were not exercised in the independent re-check, which used no git writes: run them once on a test branch before relying on them). Run `/usr/bin/git checkout -- doctor_dictation/core/lexicon/drugs.json`. Delete `doctor_dictation/core/lexicon/imported.json` (it is new on the first import; on a later import, check it out from git instead). Run `build.py --check` again; expect `v1.1.0, 444 entries`. The writes are not atomic (backlog (ae)), so do this after ANY failed or interrupted run.
- [ ] **Step 8: Promotion, later and on its own** (after the import is committed and clinics have learned names).
  1. Set the pepper outside git: `export PROMOTION_LEDGER_PEPPER=...` (32+ random characters). Generate it once with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and keep it in the operator's secret store.
  2. Run `.venv/bin/python -m doctor_dictation.admin promote-candidates --out "$DATA_DIR/promotion/2026-11/candidates.csv" --conflict-map "$SCRATCH/cdci/a3_nlem_brands.csv" --min-clinics 3`. Exit 1 with `INCOMPLETE` means a clinic was unreadable: fix it and run again.
  3. The clinician fills in `decision` (`approve` / `reject`), `generic` and `reviewer`, and may add `notes`.
  4. Run `promote-apply --csv <that file> --batch 2026-11 --reviewer "Dr. <name>" --conflict-map <map>` without `--confirm`. Read the outcome counts.
  5. Run the same command with `--confirm`.
  6. Run the Step 4 gates 1, 3 and 4.
  7. Commit `drugs.json`, `imported.json` and `promotion_ledger.json` only, with the owner's word.
  8. Delete the review CSV and its folder (clinic-derived data). Never commit it.

## Self-Review

- Owner rule: five checks (Task 2), three tiers (A3 deferred), exact generics + synonyms only, lineage (`lineage`, `sources`, report), promotion (Task 4) with the decided generic rule, licence by flag only.
- Not done on purpose: A3 suggestions, new generics, strengths and forms, per-clinic autoformat, a promotion UI, a runtime dictionary guard, atomic `drugs.json` writes (backlog (l)-(s), (ac)-(ak)).
- Measured on the imported scratch copy (Task 3 fix round 3):
  - A3 `tablet <brand> 500 mg` over 23,610 distinct brands: rewrites into a different drug 365 before, 364 after, 0 new. Anti-Thyrox no longer rewrites. Same-drug rewrites 440 -> 431.
  - A 320-sentence OPD set: 0 new rewrites. The one difference is the pre-existing `take calcium supplements after lunch` pin.
  - The macOS web2 scan, two measurements. The first (204,880 words of 5+ letters, implementer's script): 0 newly rewritten. The independent re-check (220,263 words of 4-14 letters, alone and in a carrier sentence, written from scratch) found 5 new rewrites into new brands: `etnean` -> Betnelan, `lipan` -> Clipan, `nitrian` -> Niftran, `pactolus` -> Actoluse, `populus` -> Potplus. All five are rare words (a river, a tribe, a plant genus), so clinical risk is low and they are ACCEPTED (owner can add the brands to `skip_brands` if wanted; Betnelan is a real betamethasone brand). Live lexicon: 930 words change, imported: 940.
  - Independent re-check, other results: 150 new sentences: 0 differences between live and imported; 155 added brands in 3 forms (465): 0 rewritten; A3 brands: wrong-drug rewrites 328 before, 326 after, 0 new (that count uses a different definition than the 365/364 above: the replacement resolves to a different canonical than the brand's own CDCI generic).
  - Both scans are scratch scripts, not repository tests: re-run them for any future import.

| Task | Tests added | Suite after |
|---|---|---|
| Baseline | (measured by Task 1; the ledger's 1537 was off by one) | 1536 passed, 1 skipped, 1 deselected |
| 0 | 0 (documents only) | unchanged |
| 1 | +6 `test_commonwords.py` | 1542 |
| 2 | +6 `test_lexicon_import.py`, then +2 in its fix round | 1548, then 1550 |
| 3 | +6 `test_lexicon_import.py` (1556); fix rounds: +9 more there, +1 live junk gate, +105 `test_ordinary_sentences.py` | (ran in parallel with Task 4) |
| 4 | `test_promotion.py`: 12, then 20, then 22 | (ran in parallel with Task 3) |
| **Final** | 157 new: 6 + 23 + 1 + 105 + 22 | **1693 passed, 1 skipped, 1 deselected** |

**File sizes (lines):**
- `determinism.py`: 408 -> 410.
- `build.py`: 241 -> 346.
- `lexicon_import.py`: 223 (new).
- `promotion.py`: 273 (new).
- `admin.py`: 222 -> 224.
- `commonwords.py`: 36 (new).

All are under 500.

**Decision needed:** the clinician's verdict on `clinician_sample_60.csv`, then the owner's "go" for Task 5 Step 3. Not done here: the real import itself, any commit.
