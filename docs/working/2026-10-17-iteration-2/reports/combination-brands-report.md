# Combination brands (owner option (d)) report

Status: DONE, uncommitted. Suite: 1992 passed, 1 skipped (baseline 1982; +10 in tests/test_combination_brands.py).

New canonicals (seed_extra.json, brand under each, forms [] and strengths [] because no source data exists for the products, single alias "<a> + <b>", no component alias):
`Tramadol + Paracetamol` (Ultracet), `Chlorhexidine + Cetrimide` (Savlon), `Doxylamine + Pyridoxine` (Doxinate), `Calcium Carbonate + Cholecalciferol` (Shelcal; the alias `shelcal` moved with it).
Hidden (key `generic_hidden` on the entry, seed_extra.json): Neopeptine (Simethicone), Fefol (Ferrous Sulfate), Autrin (Ferrous Fumarate), Calcimax (Calcium Citrate), Nurokind (Methylcobalamin), Adzolex-Plus (Lactulose), Feronia-XT (Ferrous Ascorbate: entry copied from drugs.json into seed_extra.json because it existed nowhere else).

Files: core/lexicon/seed_extra.json, imported.json (Ultracet from Tramadol, Shelcal brand and alias from Calcium Carbonate), drugs.json (regenerated once by `build.py --merge`, v1.3.0 -> v1.4.0, 444 -> 448 entries), core/surface.py (`generic_hidden`, docstring documents the key), core/dosing.py (`ground_extra(..., name="")` skips hidden brands), core/rowcheck.py (passes the name), core/lasa.py (a combination and one of its own components are never twins), tests/test_combination_brands.py, .superpowers/sdd/2026-10-17-i2/lexicon-audit.md (section 2 Decision column). `--check` exit 0; a second --merge is a no-change (sha256 8451b270...). tests/data/lexicon_frozen.json unchanged (sha 7a6963cd..., pinned by a test).

Sweep (2226 old canonicals, aliases and brands, grounded on the v1.3.0 and v1.4.0 lexicon with the row's own transcript): 12 differ: the 11 brands plus the lowercase alias `shelcal`. 0 other names changed status, match, generic, lookalike or heard; every status stayed `verified`.
Look-alike: Tramadol, Paracetamol, Chlorhexidine, Pyridoxine, Calcium Carbonate give the same status, lookalike and heard as before (values pinned); twins of those and of Doxylamine unchanged; the 16 curated names (8 pairs) unchanged.

Mutations (12 on scratch copies): 12 killed. Two lasa mutations initially survived because the real combination names are too long to reach 0.75 against a component (the exclusion guards SHORT combinations): a synthetic-lexicon test now covers both directions (component first or second in the name).

Decisions and concerns:
- A hidden brand still shows its row status from the single entry (e.g. unverified-strength against Ferrous Sulfate 200 mg): "grounding as today". Strength chips for it are empty.
- Spell it's "matched" option for a hidden-brand row still lists the single generic name as a suggestion (a name, not a claim about the product).
- No-space aliases ("tramadol+paracetamol") were dropped: they join the known unfixed round-trip class (tests/test_brand_as_dictated KNOWN_UNFIXED); the spaced alias round-trips.
- Combination entries have no strengths, so a strength typed for Ultracet/Shelcal is never flagged unverified-strength; add reviewed strengths only from a clinician-approved source.
- The first merge run was repeated while iterating (version went 1.5.0); I restored the v1.3.0 drugs.json and merged once, so the final bump is 1.3.0 -> 1.4.0.
