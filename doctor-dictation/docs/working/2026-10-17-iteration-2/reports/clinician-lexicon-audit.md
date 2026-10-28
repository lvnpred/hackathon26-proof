# Lexicon audit for a clinician (report only, nothing changed by this file)

Scope: `doctor_dictation/core/lexicon/drugs.json` v1.3.0 (after the Combiflam/Ciplar fix), 444 canonicals, 661 brands; section 2 updated for v1.4.0 (448 canonicals).
Method: programmatic scan (company names, a brand equal to another entry's canonical or alias, an alias equal to another canonical, odd brand shapes, generic stems used as brands) plus the author's pharmacology knowledge for combinations. Knowledge-based rows carry a confidence; a clinician must confirm before any change. A printed `generic: X` under a wrong link now reaches a pharmacist, so combinations matter most.

## 1. Programmatic results
| Check | Result |
|---|---|
| Company names (Cipla, Sun, Mankind, Lupin, Zydus, Alkem, Torrent, Glenmark, Cadila, Abbott, Pfizer, Ipca, Intas, Macleods, Micro Labs, Biocon, Dr Reddy) as canonical, alias or brand | 0 hits (pinned by `tests/test_lexicon_company_names.py`) |
| A brand equal to another entry's canonical or alias | 0 |
| An alias equal to a different entry's canonical | 0 |
| Names that two generics claim (`ambiguous_names`) | 0 |
| Generic stems stored as brands (Atorva, Losar, Aten, Pan, Warf, Baclof, ... 31 names) | 31, informational: short stems of their own generic, which `correct_drugs` and the short-name rules already handle (not a wrong link) |
| "Cipla" verifying as Propranolol | Cause: a near-spelling match (cutoff 0.84, `determinism._canonical_lookup`) to the real brand `Ciplar`, not an alias. Fixed by removing brand `Ciplar` (see report). The same mechanism can turn any company name into a drug if a brand is one letter away: not scanned for exhaustively |

## 2. Brands that are known combination products mapped to ONE generic (11 candidates): DECIDED (owner option (d), lexicon v1.4.0)
Checklist for the clinician: confirm each "modelled" row's contents, and for each "hidden" row either supply the real components (then it becomes a combination entry) or leave it hidden.
| Brand | Was mapped to | What it really contains | Confidence | Decision |
|---|---|---|---|---|
| Ultracet | Tramadol | tramadol + paracetamol | high | MODELLED: entry `Tramadol + Paracetamol` |
| Savlon | Chlorhexidine | chlorhexidine + cetrimide | high | MODELLED: entry `Chlorhexidine + Cetrimide` |
| Doxinate | Doxylamine | doxylamine + pyridoxine | high | MODELLED: entry `Doxylamine + Pyridoxine` |
| Shelcal | Calcium Carbonate | calcium carbonate + vitamin D3 | high | MODELLED: entry `Calcium Carbonate + Cholecalciferol` (the alias `shelcal` moved with it) |
| Neopeptine | Simethicone | enzymes (alpha-amylase, papain) + simethicone | medium | HIDDEN pending clinician |
| Fefol | Ferrous Sulfate | ferrous sulfate + folic acid | medium | HIDDEN pending clinician |
| Autrin | Ferrous Fumarate | iron + folic acid + B12 | medium | HIDDEN pending clinician |
| Feronia-XT | Ferrous Ascorbate | ferrous ascorbate + folic acid + zinc | medium | HIDDEN pending clinician |
| Calcimax | Calcium Citrate | calcium citrate + vitamin D3 (+ others) | medium | HIDDEN pending clinician |
| Nurokind | Methylcobalamin | methylcobalamin plus other B vitamins in common variants | low | HIDDEN pending clinician |
| Adzolex-Plus | Lactulose | the "Plus" suffix suggests a combination | low | HIDDEN pending clinician |

How the decisions are stored (so the checklist can be actioned):
- MODELLED: new canonicals in `core/lexicon/seed_extra.json` with the brand under them; empty `forms` and `strengths` (no source data for the product); the only alias is `"<a> + <b>"` (never a component's own name, so "tramadol" still grounds to Tramadol). The brand left the single-generic entry (seed_extra.json or imported.json). The look-alike index ignores a pair when one canonical is a component of the other (`core/lasa.py`).
- HIDDEN: the key `generic_hidden: ["Fefol", ...]` on the entry that still holds the brand (read in `core/surface.py`). The brand is still recognised and spelled as dictated, the row status is as before, but the row's `generic` is "" (so nothing prints and no tag shows) and `dosing.ground_extra` skips the dose check and strength options for it. A near spelling of a hidden brand is hidden too. To un-hide: delete the name from `generic_hidden` (it then shows the single generic again, which is wrong for a combination), or model it as a combination entry as above and move the brand.

## 3. Brand families that span two generics through a suffix (confusion risk)
| Pair | Mapped to | Note |
|---|---|---|
| Orofer / Orofer-S | Ferrous Ascorbate / Iron Sucrose | different drugs, different routes (oral vs IV) |
| Taxim / Taxim-O | Cefotaxime / Cefixime | injection vs oral cephalosporin |
| Monocef / Monocef-O | Ceftriaxone / Cefpodoxime | injection vs oral |
| Moxikind / Moxikind-CV | Amoxicillin / Co-Amoxiclav | clavulanate added |
| Pan / Pantocid / Eracid iv | Pantoprazole | "Pan" is also the stem of Pan-D (pantoprazole + domperidone) combinations |
| Alcorim F | Co-Trimoxazole | suffix F: confirm it is the co-trimoxazole product (low confidence) |

## 4. Brands the author could not place (confirm they exist and map to that generic)
| Brand | Current generic | Concern |
|---|---|---|
| Pilotbg | Pilocarpine | looks like an artefact, not a brand name |
| Jogren | Pilocarpine | unfamiliar |
| Eujenta | Repaglinide | name resembles linagliptin brands; unfamiliar for repaglinide |
| Cinzin, Dulonor, Migazin | Flunarizine | unfamiliar |
| Somacid | Carisoprodol | unfamiliar |
| Amintoz | Thiamine | unfamiliar |
| Actfit | Diclofenac | unfamiliar |
| Amprez | Amlodipine | unfamiliar |
| Abo Pill, Mifegest | Mifepristone | may be mifepristone + misoprostol kits |
| Ston-1, Citralka | Potassium Magnesium Citrate | Citralka is commonly a sodium/potassium citrate product |

## 5. Not found (explicitly checked)
No `Zerodol-SP`, `Dolo` combinations or `Combiflam` remain; `Zerodol` maps to Aceclofenac only (correct as a single-ingredient brand). No generic name is listed as a brand of a different generic. No brand equals another canonical.

## 6. Suggested next step (for the clinician)
Decide per section 2 row: remove the brand (the safe direction, as for Combiflam), or add a combination entry. Section 3 needs no data change but explains why look-alike checks matter. Section 4 needs a one-line confirmation each.
