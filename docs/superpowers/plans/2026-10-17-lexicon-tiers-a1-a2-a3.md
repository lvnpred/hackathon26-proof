# Lexicon Tiers A1 / A2 / A3 — Plan and Dataset

**Status:** draft for owner review, 2026-10-17. No code changed; no import run. Datasets are
in `data-draft/` (see its README). This refines the import in
`2026-10-16-i1-g1-lexicon-gate-and-adapter.md` (licence gate + adapter) and
`2026-10-16-i1-g2-lexicon-merge-and-checks.md` (merge + checks) by splitting the single lexicon
into three tiers with different jobs.

**Owner direction (2026-10-17):** import the CDCI → NLEM 2022 subset; keep a small curated
"draft" list, a doctor-approved layer, and a large suggestion list. "Go with A, then A1/A2/A3."

## The three tiers

| Tier | What it is | Data | App component |
|---|---|---|---|
| **A1 — draft** | the small, curated recognition/rewrite list | `data-draft/a1_top_brands.csv` → `drugs.json` | `correct_drugs` (`core/determinism.py`), grounding |
| **A2 — approved** | drugs the doctor confirms on two saved prescriptions, per clinic — learned automatically, not curated | grows at runtime, no file | clinic formulary (`core/formulary.py`, plan I1-h); fed by every confirmed prescription + Spell it (I1-e3) |
| **A3 — suggest** | the large "did you mean" list | `data-draft/a3_nlem_brands.csv` | `suggest_candidates` (`core/candidates.py`) |

The single rule that keeps this safe: **A1 edits the transcript; A3 only suggests; A2 is the
doctor's own explicit choice.** Growing A1 is what risks silent wrong rewrites; growing A3 is
safe because a suggestion is never written without the doctor picking it.

**A2 is automatic, not manual.** There is no "approve the list" step. A2 grows as the doctors work:
when a doctor confirms a drug on two separate saved prescriptions, it is learned to that clinic's
list (plan I1-h, spec `2026-10-16-medication-name-accuracy.md` section 2d — "confirm twice" rule,
table keyed by clinic with confirm count, admin can remove). The only manual step in this whole flow
is the *one-time* curation of A1's top-3 ranking — and that is about which brands seed the draft,
not A2.

## How each tier maps to the existing design

- **A1 → `drugs.json`.** Import `a1_top_brands.csv` through the existing
  `build.py --merge --source-name … --licence …`. Top-3 per generic keeps it ~800 brands, well
  under the ~5,000-brand rewriter ceiling and inside the look-alike and perf envelopes.
- **A2 → plan I1-h (already planned, unchanged).** A drug the doctor confirms on two separate saved
  prescriptions is added to that clinic's list and layered into `_alias_map`. No manual approval:
  prescribing and confirming *is* the approval. No new design: I1-h already covers it, including the
  `source: "clinic"` row field (contracts 4.1) and admin removal.
- **A3 → `core/candidates.py` (one isolated change).** Today `suggest_candidates` reads the same
  `drugs.json` as `correct_drugs` (`candidates.py:_rows` → `determinism._alias_map`). Add a
  separate suggest index (a name→generic map built from `a3_nlem_brands.csv`) that `_rows` loads
  instead. `core/` stays pure (no network); the index is a committed file like the lexicon. This
  is the only new code path, and it lives entirely in `candidates.py` (a new module is fine per
  the file-size contract, `i1-00` fact 1).

## Dataset counts (measured 2026-10-17)

| | |
|---|---|
| CDCI Flat Files brand rows | 93,911 |
| NLEM 2022 medicines | 384 |
| …resolved to a CDCI generic | 284 (151 already in the 444 lexicon, 133 new) |
| **A1 (top 3 / generic)** | **738 brands** |
| **A3 (all NLEM brands)** | **23,821 distinct brands** |
| Combination products resolved | Amoxicillin + Clavulanic acid (2,251), Co-trimoxazole (43), Levodopa + Carbidopa (12) |

**Ranking (A1 = top 3 per generic):** variant count (distinct strength/form SKUs) descending, then
supplier count as tiebreak, then alphabetical. Supplier count alone was tested and rejected — 69,400 of
~72,000 brands have one supplier, and where it fires it surfaces ambiguous short names (`Ac`, `Asp`,
`Tram`). Variant count surfaces recognisable brands. Neither is true prescribing frequency, so A1's
top-3 is only a starting draft; the real signal accumulates automatically as A2 learns what each
clinic actually prescribes.

The CSVs carry six columns: `brand, generic, strength, form, variants, suppliers`. Columns 1–4 are the
import schema; 5–6 are review metadata the adapter ignores.

Known gaps to close before the import (details in `data-draft/README.md`):
1. A1 ranking is a proxy — Crocin/Dolo/Calpol sit 4th–6th for Paracetamol. This is a one-time A1
   curation question (which brands seed the draft), not A2 — A2 still learns them automatically once
   the doctors prescribe them.
2. ~133 NLEM generics are new → `--allow-new-generics` or leave them for the doctor to spell.
3. Three-drug combinations (e.g. Carbidopa + Entacapone + Levodopa) are out of scope.
4. The rewriter denylist (I1-g2 safety finding) is still a prerequisite before any A1 merge.

## Not done / out of scope

- No code written, nothing imported, `drugs.json` unchanged, nothing committed.
- The denylist, the A3 suggest-index loader, and the combination-table extension are the next
  build steps and are not started here.
