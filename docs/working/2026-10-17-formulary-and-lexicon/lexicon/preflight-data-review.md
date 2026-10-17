# Lexicon g1 + g2 preflight and dataset review (2026-10-17)

Read-only review. No code, plan or data file was edited; nothing committed. Every number below was
measured by a script; scripts, raw outputs and the scratch trees are under
`/private/tmp/claude-502/-Users-narenlingala-Documents-workspace-work-Zebra-doctor-dic-doctor-dictation-main/8c2f5579-3a7d-4332-8c1b-5748dbc166ef/scratchpad/lexpre/`
(`stats.py`, `risk.py`, `perf.py`, `perf2.py`, `nearcsv.py`, `apply_plans.py`; outputs `*_out.json`, `risk_*.json`,
`a1_report_*.json`, `*_tests.txt`). Scratch trees: `base` (worktree copy), `g` (g1+g2 applied), `imp`/`imp2`
(g1+g2 plus a DRY-RUN A1 import with a placeholder licence), `a3t` (A3 naively merged into suggestions).

## Summary (decisions first)

**Verdict: g1 and g2 apply cleanly to the real code (10/10 new tests pass, full suite 1545 passed), but the
data and two adapter rules are not ready for the real import. Do not run the real A1 import yet.**

Blocking before the real import:

1. **The adapter's fuzzy generic match maps 6 NLEM generics onto the WRONG drug** and merges their brands
   silently (dry run): Cisplatin -> Cyproheptadine (via the brand key `ciplactin`), Clotrimazole -> Co-Trimoxazole,
   Cycloserine -> Cyclosporine, Noradrenaline -> Epinephrine, Valganciclovir -> Valacyclovir, Ampicillin ->
   Amoxicillin. 18 brands and their strengths (e.g. Cyproheptadine gains 10 mg / 50 mg from cisplatin vials).
   Rule change: a generic resolves only by exact canonical/alias (never via brand keys) or an explicit synonym
   table; a fuzzy generic is reported, never merged.
2. **Synonym/combination table needed before `--allow-new-generics`.** Without it the import creates duplicate
   drugs: `Amoxicillin + Clavulanic acid` beside `Co-Amoxiclav`, `Levothyroxine` beside `Thyroxine`
   (lasa then calls them twins), `Ascorbic acid` beside `Vitamin C`. Only this one combination needs mapping;
   `Co-trimoxazole` and `Levodopa + Carbidopa` already resolve exactly.
3. **Owner's counts do not match the files.** Both CSVs hold 264 distinct generics, not 284; by the adapter rule
   150 resolve exactly, 6 fuzzy (all wrong), 108 unresolved (105 after the 3 synonyms). `a1_summary.json` says
   151 + 133 = 284.
4. **Licence checklist (I1-g1 Task 1) is unanswered.** The proposed strings pass the gate's length check, but
   "redistribution within India" vs a repo/CI/hosting outside India, and committing a derived list, are the
   owner's call. Code must not decide it.
5. **The tiers plan's A3 design ("`_rows` loads [the A3 index] instead") is wrong on three counts**: it would drop
   294 of the 444 lexicon drugs from suggestions; `suggest_candidates` is also the clinic look-alike detector
   (`formulary._twin`), so 98% of clinic names would turn `lookalike-check` (392/400 sampled vs 117/400 today) and
   18 tests fail; and naive scoring costs 180 ms per call (target < 50 ms), 877 ms per 5-row repair message.
   A3 must be a separate function used only by Spell it (`rowcheck.suggestions`).

Not blocking but must be planned: 28 existing tests break after the real A1 import (they pin live lexicon data);
g2 Task 3 Step 5 says "baseline + 10 passed", which is false.

---

## PART A: data review

### A.1 Shape of the two files

| Measure | A1 `a1_top_brands.csv` | A3 `a3_nlem_brands.csv` |
|---|---|---|
| Rows / distinct brands (casefold) | 738 / 736 | 23,821 / 23,610 |
| Blank brand / generic / strength / form | 0 / 0 / 26 / 0 | 0 / 0 / 133 / 0 |
| Duplicate brand rows (casefold) | 2 (Daruvir, Efavir) | 204 |
| Brand mapped to 2+ generics (reject class) | 2 (Daruvir: Darunavir vs Darunavir + Ritonavir; Efavir) | 202 (e.g. `Ac`: Amox+Clav vs Paracetamol; `Alcef`: 3 cephalosporins; `Aldo`: Albendazole vs Amlodipine) |
| ALL CAPS / all lower / mixed case | 11 / 3 / 57 | 224 / 12 / 3,536 |
| Brand under 5 letters / under 3 letters | 54 / 5 (`6 MP`, `Fa`, `GP`, `25 D`, `5A`) | 1,484 / 78 |
| Brand with digit / punctuation / space / hyphen | 11 / 25 / 49 / 23 | 152 / 1,308 / 2,729 / 1,284 |
| Brand with a unit / starting with Tab./Cap. | 0 / 0 | 3 (`MG Clave`, `Mg-Nate`, `Gramocef-2G`) / 0 |
| Brand over 40 chars (adapter rejects) | 1 (`Lamivudine Zidovudine & Nevirapine Tablets`) | 2 |
| Strength values / rows joined with `;` | 1,429 / 404 | 32,603 / 6,689 |
| Strength shapes | `N mg` 1,345, `N g` 70, `N mcg` 14 | + 1 `20 mg/1 g` |
| A1 brands per generic | 3 for 232 generics, 2 for 10, 1 for 22 | - |

Every A1 brand is also in A3. Both files cover the same 264 generics.

### A.2 Data that looks wrong (reported, not fixed)

| Row(s) | Problem |
|---|---|
| `Heparin` -> Human chorionic gonadotropin (A1 line 371) | brand is another drug's generic name; wrong mapping |
| `Humatrope` -> Somatostatin | Humatrope is somatropin (growth hormone) |
| `Ferrous Sulphate` -> Ferrous Ascorbate | brand is a generic; lexicon has Ferrous Sulfate |
| `Dextrose`, `Dex`, `25 D` -> Glucose "0.25 g"; `Musing`, `Libna`, `Nasiwar S` -> Sodium chloride "6.5 mg" nasal drops; `Dns` "50 mg" | percent concentrations turned into mass; IU/% products (heparin, EPO, insulin, factor VIII) have blank strength: `IU` and `%` never appear |
| `Gris ODT` -> Terbinafine; `Fin` -> Terbinafine; `Dub` -> Norethisterone (A3 also says Medroxyprogesterone) | doubtful pairs |
| `Motilium-M`, A3 `Taurcip TZ`, 317 A3 names with combination-style suffixes (DS, M, P, D, PLUS, Z, AT) | fixed-dose combinations appear flattened to one ingredient |
| `Neulastim`, `Neupeg` -> Filgrastim | pegfilgrastim products |
| A3 exact collisions with the lexicon: `Mobic` -> Amoxicillin (lexicon Meloxicam), `Pepcid` -> Omeprazole (Famotidine), `Levitra` -> Levetiracetam (Vardenafil), `Deltacortril` -> Prednisolone (lexicon Prednisone, a curated look-alike pair), `Mino` -> Paracetamol, `Omnatax` -> Cefixime, `Mpa`, `Levolin`, `Valprol` | 15 A3 names already belong to a different lexicon drug |
| 16 A1 brands that CDCI also lists under another generic (A3): `Amicon` (Amitriptyline / Amikacin), `Banocide` (DEC / Albendazole), `Clear`, `Don`, `Fa`, `Anzy`, `Lofh`, `Biocarb`, `Celomide`, `D Worm`, `M cin`, `Zin`, `Lazid`, `Dub`, `Daruvir`, `Efavir` | A1 is a top-3 extract, so the adapter's "2 generics = reject" rule cannot see these; the conflict check must run against the full A3/CDCI map |

### A.3 Generic naming vs the lexicon

- 264 generics: 150 exact (case-insensitive), 6 fuzzy (all wrong, see Summary 1), 108 not in the lexicon.
- Synonyms the adapter cannot see: `Amoxicillin + Clavulanic acid` = lexicon `Co-Amoxiclav` (`Clavam`, `Augmentin`,
  `Moxikind-CV` collide); `Levothyroxine` = `Thyroxine` (`Thyronorm` collides); `Ascorbic acid` = `Vitamin C`
  (`Celin` collides). `Noradrenaline` is NOT `Adrenaline`/Epinephrine.
- Combinations: the lexicon writes `A + B` (`Levodopa + Carbidopa`, `Imipenem + Cilastatin`) but also `Co-Amoxiclav`,
  `Co-Trimoxazole`. CSV `Co-trimoxazole` and `Levodopa + Carbidopa` resolve exactly; 14 CSV combinations total,
  12 are new (HIV and others), 3 three-drug.
- Case: the lexicon is Title Case (`Folic Acid`); 12 new canonicals would be created in sentence case
  (`Amoxicillin + Clavulanic acid`, `Calcium gluconate`, `Sodium chloride`, `Human chorionic gonadotropin`...), because
  `capitalise_flat` keeps a mixed-case string.
- Salt forms: 12 generics carry a salt word; `Bendamustine Hydrochloride`, `Leuprolide acetate`,
  `Tenofovir Alafenamide Fumarate`, `Clomiphene citrate` would become canonicals with the salt in the name.

First 40 of the 108 new generics: 5-Fluorouracil, 6-Mercaptopurine, Abacavir, Abacavir + Lamivudine, Acetazolamide,
Actinomycin D, Adenosine, Alprostadil, Amoxicillin + Clavulanic acid, Amphotericin B, Arsenic trioxide, Artesunate,
Ascorbic acid, Atazanavir + Ritonavir, Atracurium, Atropine, Bedaquiline, Bendamustine Hydrochloride,
Benzylpenicillin, Bicalutamide, Bleomycin, Bortezomib, Budesonide + Formoterol, Bupivacaine, Calcium folinate,
Calcium gluconate, Capecitabine, Carboplatin, Cefazolin, Chlorambucil, Clofazimine, Clomiphene citrate, Coagulation
factor IX, Coagulation factor VIII, Cyclophosphamide, Cytosine arabinoside, Dacarbazine, Daclatasvir, Darunavir,
Darunavir + Ritonavir. (Full list: `stats_out.json` key `A1.generics_new`.) Most are hospital, oncology and HIV drugs.

### A.4 A1 new vs present, and what the dry-run import did

- A1 brands already a lexicon key: 59 (55 same drug, 4 another drug); new: 679.
- Dry run without `--allow-new-generics`: 387 brands added, 108 generics unmapped, 1 collision, 7 near-collisions,
  737 of 738 forms "unknown". With it: 548 entries (+104), 656 brands added, 5 collisions, 17 near-collisions,
  2 conflicts; a second run is byte-identical; `--check` passes; look-alike share 3.6% -> 2.9%.
- **Forms:** CDCI dose-form text (`Oral tablet` 322, `Solution for injection` 81, `Powder for solution for injection`
  65, `;`-joined lists) matches none of the adapter's single words (`tab`, `tablet`...), so no form is stored. A
  CDCI form map is needed (Oral/Film-coated/Dispersible/Orodispersible/Chewable/Sublingual tablet -> `Tab.`,
  Oral capsule -> `Cap.`, Oral syrup/solution -> `Syr.`, Oral suspension -> `Susp.`, ... injection/infusion ->
  `Inj.`, Nasal/Oral drops -> `Drops`), or forms are left out on purpose.
- **Strengths:** clean `mg/g/mcg`; the adapter splits `;`. But strengths are aggregated across all SKUs, so
  injection strengths join tablet lists (Paracetamol gains 80/120/125/150/170/250/325 mg and 1 g), and
  `1 g` vs `1000 mg` become two strengths (Metformin) because `strength_key` does not convert units.

### A.5 Well-known Indian brands

193 well-known OPD brands checked: 116 already in the lexicon, 35 in A1, 93 in A3. **A1 adds only 5 of them that
the lexicon lacks** (Azee, Emeset, Prodep, Falcigo, Myambutol). Crocin, Dolo, Calpol, Augmentin, Septran,
Bactrim, Pantocid, Zyloric, Glycomet, Telma, Ecosprin, Amlong, Thyronorm are already in `drugs.json` (Thyronorm and
Augmentin under Thyroxine / Co-Amoxiclav; A3 maps them to Levothyroxine / Amox+Clav). In none of the three:
Dolo 650, Pan 40, Combiflam-type FDCs, Neurobion, Zincovit, Sinarest, Ascoril, Lyrica, Zoloft, Cyclopam,
Sporlac (non-NLEM generics or combinations). A1's 679 new brands are mostly hospital/oncology/HIV products, so
A1 adds little recognition value for these clinics and most of the risk.

### A.6 Ordinary words and short names

- A1 brands equal to a common English/Hinglish word (603-word list `common_words.py`): 1 (`Clear`, Levonorgestrel).
  Equal to a lower-case `/usr/share/dict/words` entry: 22 (Belar, Cardin, Clear, Dextrose, Don, Dub, Duet, Enam,
  Faze, Fin, Heparin, ISO, Levin, Mem, Musing, Neve, Zac, ...).
- A3: 22 brands equal a common word: AN, April, Back, Band, Came, Care, Clear (x2), Daily (Cetirizine), Day (x2),
  Fine, Leave, Level, Low, Must, Nine, Once (Omeprazole), One, Open, Out, She; 42 multi-word brands start with one
  (`Day One`, `Morning Pill`, `Evening Pill`, `Fever X`, `Constipation Relief`); 440 equal a dictionary word.
- With A1 merged, `correct_drugs` rewrote none of the 603 words by fuzzy match, but `"Advised clear fluids"` became
  `"Advised Clear fluids"` (exact brand). "twice daily after food" stays intact at A1 size (the measured
  `Twicef`/`Af-ter` case needs the 52,000-brand file).
- Short brands: `Dex` -> Glucose, `Don` -> Risperidone, `ISO` -> Isoniazid, `GP` -> Glimepiride, `LCD` ->
  Levodopa + Carbidopa, `Mem`, `Zin`, `Fa`, `5A` would become exact aliases; `_canonical_lookup("Dex")` returns
  Glucose (doctors say "dex" for dexamethasone). `fallback_format` loses or renames the rows for `25 d`, `5a`,
  `6 mp`, `fa` (`Tab Fa`), `gp` (`Tab Gp`).

### A.7 One slip from another drug (difflib 0.84, keys of 5+ letters)

- A1 vs lexicon: 8 brands (Clopin~clozapin, Doxina~doxinate, Doxicip~moxicip, Anoxilin~amoxilin, Thyrox,
  Alltera~allegra, Alphalan~alphagan, Biotocin~biotin). Inside A1: 10 pairs (Garamycin~Adriamycin,
  Famcin~Amcin, Elpred~Elopred, Mezolam~Emzolam, Linox~Lignox, Heparin~Hetparin...). A1 vs A3: 152 A1 brands.
  Inside A3: 3,893 brands, 2,919 pairs.
- **The near-collision "skip" does not protect a dictated brand; it guarantees the wrong rewrite.** Real
  `correct_drugs` on `"tablet <brand> 500 mg"` for every distinct A3 brand: **410 brands are rewritten into a
  different drug today, 621 after the A1 merge** (e.g. `Rocin`/`Cromycin` (amikacin) -> `Crocin`; `Famcin`
  (rifampicin) -> `Amcin` (amikacin); `Clopin` (clomipramine) -> Clozapine; `Doxina` (doxycycline) -> `Doxinate`).
  16 A1 brands themselves get rewritten to another drug after the merge.
- **Brand-as-dictated regression:** after A1, `"tab 1 25 dihydroxy vitamin d3"` (a Calcitriol alias) becomes
  `"... Vitamin D3"`, the new Cholecalciferol brand; `decdak` becomes `Decdak.`.

### A.8 Random samples (seed 20261017; full rows in `stats_out.json`)

- A1 (60 rows): 52 plausible; wrong or doubtful: `Heparin` -> HCG, `Gris ODT` -> Terbinafine, `Dex`/`25 D` ->
  Glucose 0.25 g, `Fa` -> Folic Acid (2 letters), `Dub`, `Neve` (Nevirapine, a dictionary word), `Cislee` ->
  Cisplatin (would be merged into Cyproheptadine). No invented-looking names.
- A3 (60 rows): 56 plausible; doubtful: `SPY` -> Artesunate, `Dompus P` -> Domperidone (FDC suffix), `Ssn`, `Cefoxim`
  -> Cefuroxime (name reads as cefotaxime/cefixime).

### A.9 A3 size: cost for suggestions

| Measure | Value |
|---|---|
| Names kept (single generic) / dropped (2+ generics) | 23,408 / 202 |
| Rows that reach the scorer (single word, 4+ letters) | 20,338 (lexicon today: 1,364) |
| Index file: compact `{generics:[], names:{name: id}}` | 323 KB one line; 417 KB with `indent=1` (23,677 lines) |
| Index file: name -> generic text / full rows with phonetic keys | 676 KB / 826 KB (CSV itself 1.33 MB) |
| JSON load / build rows (phonetic keys) / memory | 2.5 ms / 117 ms / 2.4 MB |
| `suggest_candidates` median: today / lexicon + A3 naive | 12.9 ms / 180.6 ms (max 216 ms) |
| Exact length upper-bound prefilter | no gain (179.8 ms, same results) |
| A3 bucketed by first phonetic letter, length +-3 (A3 part only) | median 22 ms, max 66 ms (results change slightly) |
| A3 exact phonetic-key lookup | under 0.1 ms (lower recall) |
| `build_repair_message`, 5 unknown rows: today / with A3 | 61 ms / 877 ms |
| Clinic names with a "lexicon twin": today / with A3 in `suggest_candidates` | 117 of 400 / 392 of 400 |
| After A1 (plan's perf script): `normalize_transcript`, `validate` 5 rows, `suggest_candidates` | 10.8 -> 18.1 ms, 23.3 -> 34.0 ms, 15.9 -> 23.0 ms |

Ruling: use the compact form; build the rows lazily on the first Spell it call (117 ms once), not at import time;
the naive union does not meet 50 ms. A bucketed scorer is borderline; budget it with the r1 22 ms clinic pass.

---

## PART B: plan preflight

Applied on a scratch copy in order g1 T1, T2, then g2 T1, T2, verbatim from the plan code blocks
(`apply_plans.py`). Result: every anchor matched except one partial-line anchor; tests 1 -> 5 -> 8 -> 10 passed as
the plans predict; full suite 1545 passed, 1 skipped, plus 2 failures that also fail on the untouched copy (copy
artefacts: no `.gitignore`, editable install points at the main checkout). Baseline in the plans (944) is stale:
real baseline 1535.

### B.1 One row per task

| Task | Self-consistent? | Maps to tiers plan | Ruling |
|---|---|---|---|
| g1 T1 licence gate | Yes; 1 test passes | Unchanged; prerequisite for A1 | Keep. Checklist must be filled by the owner first (blocks the real run only) |
| g1 T2 adapter | Yes; 5 tests pass | A1 import path | **Change text**: (a) generics resolve via canonicals/aliases only plus an explicit synonym table (Amox+Clav -> Co-Amoxiclav, Levothyroxine -> Thyroxine, Ascorbic acid -> Vitamin C); fuzzy generic is report-only; (b) conflicts checked against the full A3 map, not only the A1 rows; (c) CDCI form map or "forms not imported" stated; (d) `MIN_BRAND_LEN` 2 -> brands under 5 letters skipped unless owner-listed; (e) Title-case new canonicals |
| g1 Review Focus / Global constraints line 22 | Claims a one-slip brand "must not be added" protects it | - | **Add**: a skipped near-collision brand is still rewritten into the other drug when dictated (A.7); the report must list it as "will be rewritten to X" |
| g2 T1 merge, `sources`, `imported.json` | Yes; 8 pass; idempotent; `--check` passes after the import | A1 merge | Keep. Tests copy the LIVE `drugs.json` and pin its content (Paracetamol brands/strengths): 5 of the 10 new tests fail once the real import lands. **Change**: freeze a fixture lexicon under `tests/data/` |
| g2 T2 look-alike share | Yes after one fix; 10 pass; share 3.6% | - | **Change text**: anchor `-     expected` (plan line 307) is a partial line; write the full line. The share counts curated pairs only, so imports LOWER it (3.6% -> 2.9%); it cannot see the 24 new computed twins (Daunorubicin/Doxorubicin, Dopamine/Dobutamine, Dolutegravir/Raltegravir, Thalidomide/Lenalidomide...) |
| g2 T3 measure + real import | Perf numbers reproduce (5k synthetic); validate(5 rows) is now 23 ms, not 2.5 | A1 real run | **Change text**: Step 5 "baseline + 10 passed" is false: after A1, 28 tests fail (test_dosing x18, dosing_grounding, brand_as_dictated x2, candidates garbage, health version pin, lexicon_import x5). Add a task to update these deliberately or move them to fixtures |
| (new) Denylist | Not in g1/g2 worktree copies | Tiers gap 4: prerequisite | **Add** as g2 Task 0 (see B.3 item 5) |
| (new) Synonym/combination table | Not in g1/g2 | Tiers "combination-table extension" | **Add** to g1 T2: one file, 3 rows today |
| (new) A3 suggest index builder + loader | Not in g1/g2 | Tiers A3 | **Add** as new plan g3 (separate from g2): builder script, committed index, separate scorer, NOTICE |
| (new) `--allow-new-generics` | Flag exists | Tiers gap 2 | Owner decision; recommend NO for the first import (105 new generics are hospital drugs; with it, 2 duplicates appear unless the synonym table lands first) |

### B.2 Shared interfaces and anchors vs the real code

| Name | Plan assumes | Real code | Ruling |
|---|---|---|---|
| Plan copies | One text | Worktree g1/g2/i1-00 lack the "Dataset findings" and "Safety finding" sections that the MAIN checkout copies have; main i1-00 lacks worktree amendments (4.1 `RECOMPUTED_ROW_FIELDS`, 4.4 errors) and says determinism is 411 lines | **Reconcile the two copies before executing** |
| `build.py` lines | 241 lines; `load_seed` 88-104, `compute_merged` 107-128, `do_check` 148-178 | Same (`build.py:88-104`, `:107-128`, `:148-178`) | OK; after g1+g2 `build.py` is 346 lines |
| `_alias_map`, `_canonical_lookup`, parse line | `:90`, `:226-244`, `:66` | `determinism.py:88-113`, `:239-253`, `:64` | Stale line numbers only |
| determinism.py size | fact 1: 482; amendment 11: 408 (main copy: 411) | 408 (`wc -l`) | Use 408; denylist hook must be net +2 lines or less |
| Fuzzy rewrite | fact 9 (main): `:181-190` | `determinism.py:185-197`; tokens `[A-Za-z]{5,}` `:187`, keys `len>=5` `:186`, cutoff 0.84 `:195`; multi-word aliases are exact-replaced with NO length floor `:164-165` | Denylist goes at `:189` |
| `MIN_ALIAS_LETTERS` | five-letter floor on the correction path | `correction.py:136` (=5), used by `correction.py:170` and `ops.py:47` only; `_canonical_lookup` exact path has no floor (`determinism.py:249-250`) | Short brands (`Dex`) resolve exactly; floor must be applied at import |
| `core.lasa` | `twins`, `always_flag_names` | `lasa.py:85-89`, `:92-94`; 8 curated pairs = 16 canonicals | OK |
| `candidates._rows` | Tiers: "loads [A3] instead" | `candidates.py:62-75` builds from `_alias_map()`; contract `test_suggest_only_returns_lexicon_canonicals` | **Ruling: never "instead", never inside `_rows`**: separate `suggest_extra(name)` used only by `rowcheck.suggestions` |
| Format cache key | change invalidates caches? | `api/format.py:93` key = clinic : layer version : normalized sha : raw sha, no lexicon version; cache is in-memory (`determinism.py:55-56`) and the lexicon loads once per process (`:59-70`) | Safe today (a new lexicon needs a restart, which empties the cache). Optional: add `lexicon_version()` to the key. `formulary._twin` lru_cache (`formulary.py:196-199`) keys on lexicon version; it must never read A3 |
| Version | one minor bump | 1.1.0 -> 1.2.0 confirmed; `tests/test_determinism.py:144` pins "1.1.0" | Update the pin in the import task |
| File sizes | `test_file_sizes.py:15-22` counts `*.py` only | Same | `drugs.json` after A1: 9,935 lines / 166 KB / 1,164 brands (without new generics 8,249 / 136 KB / 895); `imported.json` 5,012 lines / 75 KB. Plan's "~800 brands" means ~800 ADDED; total is ~1,164 |

### B.3 The ten questions

1. **Tiers vs g1/g2.** g1 T1/T2 and g2 T1/T2 are the A1 path and stay. Superseded: g2's "~5,000 brands" target
   (tiers: A1 = 738 rows). Added: denylist (g2 Task 0, prerequisite), synonym/combination table (g1 T2), conflict
   check against A3 (g1 T2), fixture lexicon for tests (g2 T1), A3 builder + loader as a separate plan g3. The
   `--allow-new-generics` decision belongs to the owner (recommend off for the first run).
2. **Callers of `suggest_candidates`. Only one can change a prescription without the doctor:**

   | Caller | Use | Can it rewrite a transcript or auto-pick? |
   |---|---|---|
   | `repair.build_repair_message` (`repair.py:37-42`, prompt `:48-54`) | lists sound-alikes to the LLM | **Yes: the LLM may pick one and rename the row.** Must stay lexicon-only; A3 excluded |
   | `formulary._twin` / `ground_clinic` (`formulary.py:196-220`) | look-alike test for clinic names | Changes a row's STATUS; A3 here flags 98% of clinic names. Must stay lexicon-only |
   | `rowcheck.suggestions` (`rowcheck.py:77-92`) | Spell it list | No; buttons only (`api/rx.py:51`, `frontend/rxview.js:149-152`, tap at `:202`). The only safe home for A3 |
   | `formulary.sound_alikes` (`formulary.py:156-163`) | Spell it list for unknown names | No; A3 would crowd clinic names out of the 3-name pool |
   | `hints`, `lasa` | do not call it (`hints.py:11`, `lasa.py:12` imports `phonetic_key` only) | No |
   | `correct_drugs` / `_canonical_lookup` | do not call it; read `drugs.json` only | No, provided A3 never enters `drugs.json` |

   A3 must also return only names that ground: an A3 generic not in `drugs.json` (e.g. Cisplatin) comes back
   `unknown-medicine` after a tap; an A3 brand tapped would be fuzzy-grounded into another drug (`Rocin` -> Crocin).
   Return the lexicon generic, or mark "not in medicine list".
3. **Formulary and r1.** If A3 were folded into `scored_candidates`, A3 names count as lexicon names (fixed slots,
   no usage), the band is computed from the top score of any source, so clinic names leave the 0.03 band more
   often and the tie-break fires less; with POOL = 3 (`formulary.py:22`) clinic sound-alikes are pushed out. The
   clinic's exact name survives (it is put first, `rowcheck.py:86`). Keep A3 in a lower, separate slot after
   clinic and lexicon names; a lexicon/A3 name with usage 0 then never moves. Measured: naive A3 breaks 18 tests
   (`test_formulary*`, `test_isolation_formulary`, `test_rowcheck`, `test_rx_check_row`, `test_candidates`).
4. **Look-alike guard and brand as dictated.** The 8 curated pairs do not cover the new canonicals; 24 of 104 new
   canonicals have computed twins, several on ISMP high-alert lists (Daunorubicin/Doxorubicin,
   Dopamine/Dobutamine). A clinician should add curated pairs before `--allow-new-generics`. Brand as dictated:
   A1 brands print in their stored spelling (`surface.py:50-61`); the adapter changes `CAVIBUTOL` -> `Cavibutol`,
   `DECDAK.` -> `Decdak.`, and `Vitamin D3` captures the Calcitriol alias phrase (A.7). `test_every_lexicon_name_round_trips`
   catches three of these; the import must reject brands that break it.
5. **Denylist.** New module `doctor_dictation/core/commonwords.py` (pure, a frozenset; or a JSON under
   `core/lexicon/` read once). Semantics: a transcript token in the list is skipped by `correct_drugs` pass 2
   (exact AND fuzzy, `determinism.py:189`) and by the two-word split (`:174-183`); never by grounding of a row the LLM
   produced. Test (I1-g2): a copy lexicon with brands `Twicef` and `Af-ter`; `normalize_transcript("Tab
   Paracetamol 650 mg twice daily after food")` is unchanged. A brand that equals a denylist word (`Clear`; A3's
   `Daily`, `Once`, `Care`...) is refused by the adapter (reported), so it never becomes an alias.
6. **Five-letter floor vs short brands.** The floor guards free-text rewriting only; exact aliases have no floor.
   54 A1 brands are under 5 letters. Ruling: skip them at import (report), or import only an owner-approved list.
   `Ac`, `Asp`, `Tram` are not in A1 (A3 only), where `MIN_LEN = 4` (`candidates.py:11`) already ignores keys
   under 4.
7. **Line counts.** determinism.py 408; denylist hook +2 lines. `build.py` 346, `lexicon_import.py` 204, tests 179.
   `candidates.py` 121 + about 40 for an A3 scorer stays far under 500; a new `core/suggest_extra.py` is cleaner.
8. **Where the data lives.** Do not package the CSVs. Recommend `data/lexicon-sources/cdci-2026-08-31/` at the repo
   root: track `a1_top_brands.csv` (46 KB, the merge input, its sha256 is recorded in `sources`) and the README;
   do not track the 1.3 MB A3 CSV. Commit the generated `doctor_dictation/core/lexicon/suggest_index.json`
   (compact, 323 KB; `pyproject.toml` already packages `core/lexicon/*.json`) with its builder
   `core/lexicon/build_suggest.py` (`--check` like `build.py`) and `core/lexicon/NOTICE-CDCI.md` carrying the
   CC BY 4.0 attribution, source URL, release date, sha256 and "brand names are their owners' trademarks". The
   index file itself carries a `source` block (name, licence, url, sha256, built_at). Whether a derived list may
   sit in a repository hosted outside India is the owner's licence question.
9. **Offline tests.** g1/g2 tests use the synthetic fixture CSV: good. Two gaps: they copy the live `drugs.json`
   (fix: frozen fixture), and the A3 loader needs a synthetic index fixture; with no index file the loader must
   fall back to lexicon-only (as `lasa.py:33-43` does for a broken pairs file). The real import stays a manual
   step after licence sign-off.
10. **Version and caches.** One minor bump per import (verified). The A3 index needs its own version, reported in
    `/api/health` next to `lexicon_version`, and used in any cache that reads it. The format cache needs no change
    while the lexicon is loaded once per process.

### B.4 What blocks starting

- Code work (g1 T1, g1 T2 with the rule changes, g2 T1/T2, denylist) can start now: anchors hold, tests are offline.
- The real A1 import cannot start: licence checklist, synonym table, fuzzy-generic rule, conflict check against A3,
  short-brand rule, and the 28 test updates come first.
- A3 cannot start as written: it needs a decision to make it a separate Spell-it-only scorer (not `_rows`).

Decision needed: approve the five rule changes to g1 T2, the denylist as g2 Task 0, and A3 as a separate plan g3
used only by Spell it. Not done here: no plan text edited, no fix to the data, no real import, no licence choice.
