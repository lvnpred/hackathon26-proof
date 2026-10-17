# Working folder: clinic formulary, usage ranking, admin stopgap, lexicon import

**What this is.** The working record of Iteration 1, second half (2026-10-16 to 2026-10-17): the clinic formulary, the usage ranking, the admin-only stopgap, and the lexicon import with promotion tools. It keeps the context that the plans do not carry: the implementation reports, the review findings, the measurements, the owner decisions and the scripts that made the numbers.

**Status when this folder was written.** Everything is built and reviewed in the `iteration-1` worktree. The formulary, ranking and admin work is committed (`c2c2e97`). The lexicon work (denylist, importer, promotion tools, plan and backlog updates) is uncommitted. The real A1 import has NOT been run: it is a manual runbook step (Task 5 of the lexicon plan) that waits for the clinician review and the owner's "go".

## Where things are

| Folder or file | What it holds |
|---|---|
| `formulary/` | Reports for plans I1-h1 to h4, the usage ranking (r1) and the admin-only stopgap (rbac), the live browser check of the Team tab, the preflight that ruled on the plans, and the ledger `progress.md` with every ruling |
| `lexicon/progress.md` | Ledger for the simplified lexicon plan: owner rulings and scope |
| `lexicon/preflight-data-review.md` | The measured review of the data (`a1_top_brands.csv`, `a3_nlem_brands.csv`) and of the older g1 and g2 plans |
| `lexicon/task-1-report.md` to `task-4-report.md` | Implementation reports with every fix round (denylist, importer, merge wiring, promotion tools) |
| `lexicon/independent-reverification.md` | A fresh reviewer's from-scratch measurements of the fixed import (verdict: safe to proceed to the clinician review) |
| `lexicon/clinician-review/` | `clinician_review_sheet.csv` (155 brands the import would add) and `clinician_sample_60.csv` (60-row sample), regenerated after fix round 3 |
| `lexicon/tools/` | Measurement scripts and outputs (see "Re-running the tools") |

The plans themselves stay in `docs/superpowers/plans/`: `2026-10-17-i1-g-lexicon-simple.md` (the plan and the import runbook), `2026-10-17-i1-r1-usage-ranking.md`, and `2026-10-17-i1-backlog-suggestion-ideas.md` (the backlog). The raw CDCI data and the tiers plan are in the main checkout only (`data-draft/`, `docs/superpowers/plans/2026-10-17-lexicon-tiers-a1-a2-a3.md`, untracked).

## Owner decisions (2026-10-16 and 2026-10-17)

| Decision | Detail |
|---|---|
| Brand-first | Doctors use brands. The brand is the unit; the generic is only a link used for dose check, look-alike check and grounding. A brand prints as dictated |
| One core list per application | `drugs.json` is built offline, loaded once, identical for every clinic, changed only by an operator plus a deploy |
| Clinic list per clinic | The formulary, learned from doctors (a name confirmed on 2 saved documents), removable by a clinic admin, never rewrites text |
| Rule: autoformat vs suggest | A name may change the sheet only if it is on the reviewed core list with a recorded source and passes all five checks (exact generic or synonym table; one generic per brand; 5+ letters; not an ordinary word; not one slip from another name). Failing names are written to a skipped-row report and are suggestion-only |
| Broad A3 list deferred | 23,821 brands, suggestions only, in the backlog |
| First import | Exact-match generics only, no `--allow-new-generics`, brands only (no strengths or forms) |
| Promotion in scope | Names learned in 3 or more clinics go to a clinician review CSV (counts only), then `promote-apply` merges approved rows through the same gates. A promoted brand must name a generic that resolves, else it stays clinic-only |
| Usage ranking | Hints ranked by `log2(1+count) * 0.5**(days/30)`. Clinic names appear in Spell it at plain score; usage reorders only clinic names inside a 0.03 band. Card (f), two different patients before learning, is backlog |
| Admin stopgap | `user.create`, `user.disable`, `user.reset_password` and `formulary.manage` are admin-only. Every newly created user gets role `admin` until real RBAC (backlog card k). The letterhead doctor list includes admins |
| Zero medicines | A prescription may have no medications; Save stays enabled |
| Licence | Keep the proposed wording for now and revisit later: `CC BY 4.0 https://creativecommons.org/licenses/by/4.0/ — C-DAC/NRCeS; redistribution within India`. The importer still requires the flags; code never decides a licence. Hosting question deferred (see backlog) |

## What was built (all reviewed with task reviews, mutation checks and live browser checks where it touches the page)

| Piece | Where | Notes |
|---|---|---|
| Clinic formulary | `core/formulary.py`, `db/formulary.py`, migration `009_clinic_formulary.sql`, `api/formulary.py` | Learn rules (letters, person-like and patient-word rejection), a ledger of documents so a re-save never double-counts, soft removal resets the count |
| Grounding and hints | `core/rowcheck.py`, `core/correction.py`, `core/hints.py` | A clinic name is "Known to your clinic"; no dose check; a restored `verified` row must be backed or it regrades to unknown-medicine |
| Layer per request | async dependency `use_clinic_layer` on exactly five routes | A pin test enforces the list; a once-per-process warning covers an empty layer |
| Team "Clinic medicines" tab | `frontend/team.js`, `team.css` (`?v=2`) | Admin-only construction, text-only rendering, confirm-before-remove, stale-list guard, stacked rows at 520 px |
| Usage ranking | `core/formulary.py` (`ranked_layer`, `tie_break`), `api/formulary.py` | Report in `formulary/r1-report.md` |
| Admin-only stopgap | `policy.py`, `accounts.DEFAULT_ROLE`, `db/templates.py` | Report in `formulary/rbac-report.md` |
| Denylist | `core/commonwords.py` (603 words), two hooks in `core/determinism.py` | A transcript word on the list is never rewritten; a two-word split is skipped only when both words are ordinary |
| Importer | `core/lexicon/lexicon_import.py`, `import_rules.json`, `build.py` | Five checks, synonym table, curated `skip_brands` classes, lineage per brand, skipped-row report, licence gate, `imported.json` |
| Promotion tools | `doctor_dictation/promotion.py`, `admin.py` (`promote-candidates`, `promote-apply`), `core/lexicon/promotion_ledger.json` | Read-only clinic access, HMAC ledger keyed by `PROMOTION_LEDGER_PEPPER` (32+ characters, outside git, fail closed), `.INCOMPLETE` marker |
| Test hygiene | `tests/conftest.py` | Blank provider keys, settings cache reset, per-test temp `DB_PATH` |

## Review findings that changed the work

| Finding | Where found | Resolution |
|---|---|---|
| A doctor could create users, disable an admin and reset an admin's password (policy allowed all three for everyone), then act as that admin | Formulary final review, live run | Admin-only, default role admin until RBAC |
| A new user (default admin) vanished from the letterhead doctor list | RBAC implementation | `clinic_doctors` includes doctor and admin |
| One test used `monkeypatch.undo()` and opened the dev database | Formulary final review | `monkeypatch.context()` plus a guard |
| The importer's fuzzy generic match put 18 brands under the wrong drug (Cisplatin to Cyproheptadine) | Data preflight | Exact generic or synonym table only; fuzzy generics are reported |
| The tiers plan's "A3 replaces `_rows`" would drop 294 lexicon drugs and flag 392 of 400 clinic names as look-alikes | Data preflight | A3 deferred; if built, a separate Spell-it-only scorer |
| Imported brands one slip from ordinary words became drugs ("garden" to "Arden", a phantom verified row) | Lexicon final review (Critical) | 49 curated skips, ordinary-sentence gate on the live lexicon (103 sentences, 105 tests in `tests/test_ordinary_sentences.py`), dictionary scan |
| Imported brands made other brands rewrite to a different drug (Amozid-CV to Amzid-CV) | Fix round 3 | Check 5 compares every 5+ letter word of hyphenated and spaced names |
| The ledger hash was effectively unsalted and committed to git | Task 4 review | HMAC with a pepper kept outside git |
| The CSV reader split quoted multi-line cells | Task 4 review | Read with `newline=""` semantics |

## Final measurements (simulated import on a copy; the live `drugs.json` was never touched)

- 738 A1 rows read: **155 added, 58 already present, 525 skipped**. Skips by first failed check: 299 generic, 130 one slip, 49 curated, 28 too short, 12 two generics, 5 shape, 2 ordinary word. Lexicon v1.1.0 to v1.2.0. A second run changes nothing and `--check` passes.
- 320 outpatient sentences: 0 new rewrites. 204,880 dictionary words: 0 new near any new brand.
- 23,610 A3 brands as "tablet X 500 mg": wrong-drug rewrites 365 before, 364 after, 0 new.
- Speed: `correct_drugs` median 1.9 ms to 2.2 ms; `suggest_candidates` 11.7 ms to 13.5 ms.
- Full suite: 1693 passed, 1 skipped, 1 deselected on the worktree and on the imported copy (baseline before the lexicon work: 1536).

## Re-running the tools

The scripts in `lexicon/tools/` were written against a scratch layout and still hold absolute scratchpad paths (the copied worktree, the CSV copies). Read them for the method, then edit the paths. Never run an import against the live `drugs.json` from them.

| Script | What it measures |
|---|---|
| `measure.py`, `measure2.py`, `measure_out.json` | Autoformat rewrites before and after the import (A3 brands, A1 brands, 320 sentences) |
| `opd_sentences.py` | The outpatient sentence set |
| `dictscan.py`, `dictscan_out.json` | Dictionary words that rewrite near a new brand (macOS `/usr/share/dict/words`) |
| `e2e.py` | Promotion end to end on three temporary clinics |
| `sheet.py` | Builds the clinician review sheets from the dry run |
| `mutate.py`, `perf.py`, `sec.py` | Mutation checks, speed and security probes |

## Open items

- **Manual step:** the real A1 import (Task 5 runbook): clinician reviews the 60-row sample, the owner says go, the gates must pass, then commit.
- **Pepper:** set `PROMOTION_LEDGER_PEPPER` before the first promotion run.
- **Backlog** (`docs/superpowers/plans/2026-10-17-i1-backlog-suggestion-ideas.md`): runtime dictionary guard, scan of the existing 508 brands, atomic writes of `drugs.json` and `imported.json`, four brands that lose split-dictation recovery (Amlong, Fortum, Forcan, Losar), real RBAC, the broad A3 list, licence and hosting wording, and the clinic-facing ideas.
- **Older items:** dosing reference (needs a source and a clinician reviewer), the printed generic, hand-typed ages like "45M", dictated brands in the look-alike list, the "form defaulted" marker, the server 500 on malformed input.
