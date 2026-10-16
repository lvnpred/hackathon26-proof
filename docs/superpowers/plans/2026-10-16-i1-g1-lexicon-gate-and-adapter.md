# Lexicon Import, Part 1: Licence Gate and CSV Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the licence gate in front of `build.py --merge` and write the local-CSV adapter that turns a public Indian brand-to-generic dataset into complete lexicon entries, without ever importing anything yet. Part 2 (`2026-10-16-i1-g2-lexicon-merge-and-checks.md`) wires the adapter into the merge and adds the checks.

**Architecture:** The gate lives in `build.py` (`require_source`, new flags). The adapter is a new stdlib-only module `core/lexicon/lexicon_import.py` that reads a CSV and returns the COMPLETE entries that change plus a report; it never touches `drugs.json`. No network, nothing at request time.

**Tech Stack:** Python 3 stdlib (`csv`, `difflib`, `json`, `unicodedata`), pytest. No new dependency.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` section 2d ("Larger lexicon") and table row "Bigger lexicon"; contracts in `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` (facts 5 and 8, section 4.3, open decision 4).

**Assumptions about earlier plans:** none besides the baseline suite. (Part 2 needs plan I1-a's `core/lasa.py`; this part does not.) This is part 1 of 2: run it first.

**Produces (consumed by I1-g2):** in `build.py`, `require_source(args, parser) -> dict | None`, the flags `--source-name --licence --source-url --attribution --allow-new-generics --report`, `do_merge(seed_path, source=None, allow_new=False, report_path=None, now=None)` and `do_check(seed_path, source=None, allow_new=False)` (extra parameters accepted, not yet used); in `core/lexicon/lexicon_import.py`, `import_rows(path, entries, source_name, allow_new_generics=False) -> (list[dict], dict)`, `alias_map(entries)`, `Resolver`, `_extend`, `strength_key`; `tests/data/brands_fixture.csv`; and `tests/test_lexicon_import.py` with the helpers `load`, `build` (fixture), `run`, `exit_code`, `read`, `adapter` and the constants `FIXTURE`, `SOURCE`, `MERGE`.

## Global Constraints

- No network access and no licence decision by code or by the executor: a human fills Task 1's checklist; nothing is downloaded by this plan.
- `--merge` of anything except the repo's own `seed_extra.json` needs `--source-name` (3+ chars) and `--licence` (10+ chars); both are written to `drugs.json` under `sources`.
- Never change: existing canonical names and their order, existing aliases, the order of existing brands/forms/strengths (additions go last), sorted entry keys, LF line endings, `indent=2` serialization. Output is byte-identical on a second identical run.
- A brand that collides with an existing canonical, alias or brand is skipped; so is one a single slip away (fuzzy cutoff 0.84) from a different drug's name. A brand the CSV maps to two generics is rejected. Nothing is guessed; everything skipped is in the report.
- Tests use only the synthetic `tests/data/brands_fixture.csv` and a COPY of `drugs.json`; offline; test command `.venv/bin/python -m pytest tests/ -q`. No commits: every "commit" step is "leave uncommitted".
- Source files stay under 500 lines (`tests/test_file_sizes.py:15-22` counts only `*.py` under `doctor_dictation/`, so `drugs.json` has no line limit; after 5,000 brands it is about 12,700 lines and 214 KB, parsed once at start-up by `core/determinism.py:66`).

## Review Focus

- A brand the dataset lists for two generics (Quorabex) must be rejected and reported, never resolved by row order. Pinned in Task 2 (`test_adapter_rules_on_the_fixture`).
- An imported brand equal to, or one letter from, another drug's name (Pantocid, Glycomat) must not be added. Pinned in Task 2.
- A CSV with ALL CAPS names, "Tab." prefixes, "500mg" strengths, blank generics or a missing column must not crash or pollute the lexicon. Pinned in Task 2.
- A merge without a stated source and licence must be refused before anything is read or written. Pinned in Task 1.

## How `--merge` works today (read from `build.py`, run on a copy)

`load_seed` (`build.py:88-104`) accepts a top-level JSON array and fails on a duplicate `canonical`. `compute_merged` (`:107-128`) unions by case-insensitive canonical and **the seed entry replaces the whole existing entry** (`:117`): merging `[{"canonical":"Paracetamol","brands":["ZZBrand",...]}]` into a copy gave "entries 444 -> 444, version 1.1.0 -> 1.2.0" and Paracetamol lost Crocin, Dolo, Calpol and its four aliases. So the adapter must emit COMPLETE entries (existing lists plus additions). The minor version is bumped only when the sorted entry list changed (`:120-123`, `bump_minor` `:74-85`); a bare `--merge` twice is byte-identical; `--check` (`:148-178`) re-computes in memory and compares bytes. Second finding: the bare `--merge`/`--check` re-applies `seed_extra.json`, which holds 403 of the 444 canonicals, so it would silently revert an import for all of them: hence `imported.json` (Task 3). Names resolve in `core/determinism.py:_alias_map` (`:90`): canonicals and aliases claim names first (sorted by canonical), then brands; the first claimant keeps a name. Generic lookup is exact, then `difflib.get_close_matches(..., cutoff=0.84)` over keys of 5+ letters (`_canonical_lookup`, `:226-244`); the adapter reuses exactly that rule.

## File Structure

| File | Change |
|---|---|
| `doctor_dictation/core/lexicon/build.py` (241 lines now) | the gate, flags, widened signatures |
| `doctor_dictation/core/lexicon/lexicon_import.py` | NEW: the CSV adapter (about 200 lines) |
| `tests/data/brands_fixture.csv` | NEW: 14-row synthetic CSV |
| `tests/test_lexicon_import.py` | NEW: 5 tests here, 5 more in part 2 |

Adds 5 tests. Baseline: run the suite first, note the count (944 passed, 1 skipped when this was written), expect baseline + 5.

---

### Task 1: The licence gate

**Files:** Modify `doctor_dictation/core/lexicon/build.py`; Create `tests/test_lexicon_import.py` (head and first test).

**Interfaces:** Produces `require_source(args, parser) -> dict | None` (the record fields `name`, `licence`, optional `url`, `attribution`; None for the default seed) and the CLI flags `--source-name --licence --source-url --attribution --allow-new-generics --report`. `do_merge` and `do_check` take the new parameters now; Tasks 3 and 4 use them.

- [ ] **Step 1: A human fills this checklist BEFORE any import. Stop here until it is done.** Keep the answers in the PR description; the code records the first two in `drugs.json`.

```
[ ] Dataset name and version/date:            ______________________  (--source-name)
[ ] URL it was obtained from:                 ______________________  (--source-url)
[ ] Licence text or its URL, copied verbatim: ______________________  (--licence)
[ ] Permitted use covers: a commercial clinical product, committing a derived list into our repository, redistribution
    to clinics.  Written answer from the licence or its owner: yes / no / unclear (unclear = do not import)
[ ] Attribution required?  Exact wording:     ______________________  (--attribution)
[ ] Personal or confidential data in the file? (must be none)
[ ] Who confirmed this, and the date:         ______________________
[ ] The CSV was saved LOCALLY as UTF-8 with the header row  brand,generic,strength,form
```

- [ ] **Step 2: Write the failing test.** Create `tests/test_lexicon_import.py` with the head below and the first test (later tasks append to it). The test also pins that the repo's own seed still needs no source.

```python
"""CSV brand import (plan I1-g): licence gate, adapter rules, idempotency, look-alike limit. Offline; build.py works on a
COPY of drugs.json in tmp_path, never the real file."""
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

LEX = Path(__file__).resolve().parents[1] / "doctor_dictation" / "core" / "lexicon"
FIXTURE = Path(__file__).parent / "data" / "brands_fixture.csv"
SOURCE = ("--source-name", "Fixture Brands 2026", "--licence", "Synthetic test data, public domain (test only)")
MERGE = ("--merge", str(FIXTURE), *SOURCE)


def load(name):
    spec = importlib.util.spec_from_file_location(name, LEX / f"{name.split('_under')[0]}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def build(tmp_path, monkeypatch):
    mod = load("build_under_test")
    shutil.copy(LEX / "drugs.json", tmp_path / "drugs.json")
    monkeypatch.setattr(mod, "DRUGS_JSON", tmp_path / "drugs.json")
    monkeypatch.setattr(mod, "IMPORTED_JSON", tmp_path / "imported.json", raising=False)
    monkeypatch.setattr(mod, "load_twins", lambda entries: (lambda name: []), raising=False)   # no look-alikes
    return mod


def run(build, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["build.py", *argv])
    build.main()


def exit_code(build, monkeypatch, *argv):
    with pytest.raises(SystemExit) as exc:
        run(build, monkeypatch, *argv)
    return exc.value.code


def read(build):
    return json.loads(build.DRUGS_JSON.read_text(encoding="utf-8"))


def test_merge_of_a_csv_refuses_without_source_name_and_licence(build, monkeypatch, capsys):
    before = build.DRUGS_JSON.read_bytes()
    for extra in ([], ["--source-name", "Some Dataset"], ["--licence", "CC BY 4.0 https://example.org/l"],
                  ["--source-name", "ab", "--licence", "CC BY 4.0 https://example.org/l"],
                  ["--source-name", "Some Dataset", "--licence", "short"]):
        assert exit_code(build, monkeypatch, "--merge", str(FIXTURE), *extra) == 2, extra
        assert exit_code(build, monkeypatch, "--check", "--merge", str(FIXTURE), *extra) == 2, extra
    err = capsys.readouterr().err
    assert "--source-name" in err and "--licence" in err and "Nothing was read or written" in err
    assert build.DRUGS_JSON.read_bytes() == before
    run(build, monkeypatch, "--merge")                       # the repo's own seed needs no source and changes nothing
    assert build.DRUGS_JSON.read_bytes() == before and exit_code(build, monkeypatch, "--check") == 0
```

- [ ] **Step 3: Run it to see it fail.** Run: `.venv/bin/python -m pytest tests/test_lexicon_import.py -q`. Expected: FAIL (`json.decoder.JSONDecodeError`: today the CSV is read as a JSON seed).

- [ ] **Step 4: Implement the gate.** In `build.py`: (a) add the constant after `DEFAULT_SEED = ...`; (b) insert `require_source` and widen the signature of `do_merge`, replacing `def do_merge(seed_path):`; (c) widen `do_check`; (d) add the flags before `args = ap.parse_args()`; (e) replace the `if args.check:` and `if args.merge is not None:` blocks in `main`.

```diff
- DEFAULT_SEED = HERE / "seed_extra.json"
+ DEFAULT_SEED = HERE / "seed_extra.json"
+ MIN_SOURCE_NAME, MIN_LICENCE = 3, 10
```
```python
def require_source(args, parser):
    """The licence gate: every merge except the repo's own seed_extra.json must name its data and licence.
    Returns the fields to record, or None for the default seed."""
    if Path(args.merge).resolve() == DEFAULT_SEED.resolve():
        return None
    name, licence = (args.source_name or "").strip(), (args.licence or "").strip()
    if len(name) < MIN_SOURCE_NAME or len(licence) < MIN_LICENCE:
        parser.error(
            f"merging {Path(args.merge).name} needs --source-name (the dataset's name, {MIN_SOURCE_NAME}+ chars) "
            f"and --licence (the licence text or URL, {MIN_LICENCE}+ chars). Nothing was read or written. "
            "See plan I1-g1 Task 1: confirm the licence first.")
    optional = (("url", args.source_url), ("attribution", args.attribution))
    return {"name": name, "licence": licence, **{k: v.strip() for k, v in optional if v and v.strip()}}


def do_merge(seed_path, source=None, allow_new=False, report_path=None, now=None):   # extra arguments: used from plan I1-g2
```
```diff
- def do_check(seed_path):
+ def do_check(seed_path, source=None, allow_new=False):
```
```python
    ap.add_argument("--source-name", help="REQUIRED to merge any file but seed_extra.json: the dataset's name")
    ap.add_argument("--licence", help="REQUIRED with --source-name: the licence text or URL (recorded)")
    ap.add_argument("--source-url", help="where the dataset came from (recorded)")
    ap.add_argument("--attribution", help="attribution text the licence requires (recorded)")
    ap.add_argument("--allow-new-generics", action="store_true",
                    help="CSV import: create a canonical for a generic the lexicon lacks (default: skip its brands)")
    ap.add_argument("--report", metavar="PATH", help="CSV import: write the import report (JSON) here")
    args = ap.parse_args()
```
```python
    if args.check:
        args.merge = args.merge or str(DEFAULT_SEED)
        sys.exit(do_check(Path(args.merge), require_source(args, ap), args.allow_new_generics))

    if args.merge is not None:
        do_merge(Path(args.merge), require_source(args, ap), args.allow_new_generics, args.report)
        return
```

- [ ] **Step 5: Run the test.** Run: `.venv/bin/python -m pytest tests/test_lexicon_import.py -q`. Expected: `1 passed`. The refusal exits with code 2 and prints "build.py: error: merging brands_fixture.csv needs --source-name ... Nothing was read or written."
- [ ] **Step 6: Leave uncommitted.** Changed: `build.py`, `tests/test_lexicon_import.py`.

---

### Task 2: The CSV adapter

**Files:** Create `doctor_dictation/core/lexicon/lexicon_import.py`, `tests/data/brands_fixture.csv`; Modify `tests/test_lexicon_import.py`.

**Interfaces:** Produces `import_rows(path: Path, entries: list[dict], source_name: str, allow_new_generics: bool = False) -> (list[dict], dict)`: the COMPLETE entries that change (sorted by canonical, keys sorted) and the report dict. Also `alias_map(entries)`, `Resolver(entries).resolve(name) -> (canonical, "exact"|"fuzzy") | None`. CSV columns: `brand` (required text; leading Rx/Tab./Cap./Syp/Inj... words are stripped and hint the form; ALL CAPS or all lower becomes Capitalised; 2-40 chars with a letter), `generic` ("A / B", "A & B", "A, B" become "A + B"; "(IP)" notes dropped), `strength` (blank, or values split by `;` or `|`; "500mg" becomes "500 mg"), `form` (tablet, capsule, syrup, injection, cream... mapped to the lexicon's `Tab.`, `Cap.`, `Syr.`, `Inj.`, `Cream`...; unknown words are reported, not stored).

- [ ] **Step 1: Create the fixture** `tests/data/brands_fixture.csv` (every row is a case the tests assert; all brand names are invented):

```csv
brand,generic,strength,form
TAB. ZENTRAMOL,PARACETAMOL (IP),500mg,Tablet
Zentramol,Paracetamol,650 MG,Tab
CROCIN,Paracetamol,500 mg,Tab
Pantocid,Paracetamol,40 mg,Tablet
Quorabex,Amoxicillin,500mg,Capsule
Quorabex,Metformin,500mg,Tablet
Vexorin,Amoxycillin,250 mg,Cap
Glycomat,Atorvastatin,10 mg,Tablet
Novakind,Amoxicilin,125 mg/5ml,Syrup
Zibrelon,Levodopa / Carbidopa,25 mg,Tablet
Plantiva,Zorlexin,10mg,Tablet
Lunexa,,10 mg,Tablet
X,Paracetamol,500 mg,Tablet
Rx Mirtavel,Atorvastatin,20 mg; 40 mg,Pill
```

- [ ] **Step 2: Append the failing tests** to `tests/test_lexicon_import.py`.

```python
def adapter(allow_new=False):
    lex = load("lexicon_import")
    changed, report = lex.import_rows(FIXTURE, load("build_under_test").load_drugs()["entries"], "Fixture", allow_new)
    return {e["canonical"]: e for e in changed}, report


def test_adapter_rules_on_the_fixture():
    changed, rep = adapter()
    assert set(changed) == {"Amoxicillin", "Atorvastatin", "Levodopa + Carbidopa", "Paracetamol"}   # only what changes
    assert changed["Paracetamol"]["brands"] == ["Crocin", "Dolo", "Calpol", "Zentramol"]   # existing order kept, "Tab." and CAPS gone
    assert changed["Paracetamol"]["strengths"] == ["500 mg", "650 mg", "120 mg/5ml"]       # "500mg" and "500 mg" are one strength
    assert changed["Paracetamol"]["aliases"] == ["paracetamol", "paracetmol", "paracitamol", "para cetamol"]
    assert {"Vexorin", "Novakind"} <= set(changed["Amoxicillin"]["brands"])         # exact alias, then the fixed fuzzy rule
    assert "Zibrelon" in changed["Levodopa + Carbidopa"]["brands"]                  # "A / B" is written "A + B"
    assert changed["Atorvastatin"]["strengths"] == ["10 mg", "20 mg", "40 mg"]      # "20 mg; 40 mg" split, "Rx" prefix gone
    assert rep["unmapped_generics"] == ["Zorlexin"] and rep["unknown_forms"] == ["Pill"] and rep["new_generics"] == []
    assert rep["generic_fuzzy"] == [{"csv": "Amoxicilin", "mapped_to": "Amoxicillin"}]
    assert rep["conflicts"] == [{"brand": "Quorabex", "generics": ["Amoxicillin", "Metformin"]}]   # two generics: not guessed
    assert rep["collisions"] == [{"brand": "Pantocid", "kept_for": "Pantoprazole", "csv_generic": "Paracetamol"}]
    assert [n["brand"] for n in rep["near_collisions"]] == ["Glycomat"]             # one letter from Glycomet (Metformin)
    assert [(r["line"], r["reason"]) for r in rep["rows_rejected"]] == [(13, "missing generic"), (14, "bad brand")]
    assert (rep["brands_added"], rep["brands_already_present"]) == (5, 1)           # Crocin was already there


def test_new_generics_are_created_only_when_asked_and_carry_their_source():
    changed, rep = adapter(allow_new=True)
    assert changed["Zorlexin"] == {"aliases": ["zorlexin"], "brands": ["Plantiva"], "canonical": "Zorlexin",
                                   "forms": ["Tab."], "source": "Fixture", "strengths": ["10 mg"]}
    assert rep["new_generics"] == ["Zorlexin"] and rep["unmapped_generics"] == []


def test_adapter_lookups_follow_the_runtime_rules():
    from doctor_dictation.core import determinism as D
    lex, entries = load("lexicon_import"), D.load_lexicon()
    assert lex.alias_map(entries) == D._alias_map()
    resolver = lex.Resolver(entries)
    for name in ("Crocin", "amoxycillin", "Amoxicilin", "Pantoprazol", "Zorlexin", "paracetmol"):
        assert (resolver.resolve(name) or ("",))[0] == D._canonical_lookup(name), name


def test_a_csv_without_the_required_columns_is_refused(tmp_path):
    (tmp_path / "bad.csv").write_text("brand,strength\nCrocin,500 mg\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="needs the columns"):
        load("lexicon_import").import_rows(tmp_path / "bad.csv", [], "x")
```

- [ ] **Step 3: Run them.** Run: `.venv/bin/python -m pytest tests/test_lexicon_import.py -q`. Expected: FAIL (`FileNotFoundError: ... lexicon_import.py`).

- [ ] **Step 4: Write the adapter.**

```python
"""CSV brand-to-generic import for ``build.py --merge FILE.csv`` (offline, deterministic, stdlib only).

CSV: UTF-8, header row naming ``brand, generic, strength, form`` (any order or case; extra columns ignored;
strength may hold several values split by ; or |; strength and form may be blank).
``import_rows`` returns ``(entries, report)``: ONLY the entries that change, each COMPLETE (build.py's merge
replaces a whole entry on a canonical match). Existing names, aliases, brands, strengths and their order stay.
"""
import csv
import difflib
import hashlib
import re
import unicodedata
from bisect import insort
from collections import defaultdict

CSV_COLUMNS = ("brand", "generic", "strength", "form")
FUZZY_CUTOFF, FUZZY_MIN_LEN = 0.84, 5       # exactly determinism._canonical_lookup
MIN_BRAND_LEN, MAX_BRAND_LEN, MAX_ROWS = 2, 40, 200_000
_FORM_WORDS = {"Tab.": "tab tablet", "Cap.": "cap capsule", "Syr.": "syr syp syrup liquid", "Inj.": "inj injection",
               "Susp.": "susp suspension", "Cream": "cream", "Drops": "drop drops", "Oint.": "oint ointment",
               "Inhaler": "inhaler"}
FORMS = {w: form for form, words in _FORM_WORDS.items() for w in words.split()}     # "tablet" -> "Tab."
RX_WORDS = {"rx", "tablets", "capsules", *FORMS}                                    # words stripped before a brand
_STRENGTH = re.compile(r"^(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu|%)$", re.I)


def clean(text) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(text or "")).split())


def capitalise_flat(text: str) -> str:
    """ALL CAPS or all lower becomes Capitalised words; a mixed-case spelling is kept."""
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), text) if text.isupper() or text.islower() else text


def strip_rx_prefix(brand: str):
    """('Crocin', 'Tab.') from 'Tab. Crocin': leading Rx/Tab/Cap/... words go, never the last word."""
    words, hint = brand.split(" "), ""
    while len(words) > 1 and words[0].lower().rstrip(".:") in RX_WORDS:
        hint = hint or FORMS.get(words[0].lower().rstrip(".:"), "")
        words.pop(0)
    return " ".join(words), hint


def norm_generic(text: str) -> str:
    """Drop (...) notes; a combination split on + / & , is rejoined as 'A + B'."""
    parts = [capitalise_flat(clean(p)) for p in re.split(r"[+/&,]", re.sub(r"\([^)]*\)", " ", clean(text)))]
    return " + ".join(p for p in parts if p)


def norm_strength(text: str) -> str:
    text = clean(text).replace("µ", "mc")
    m = _STRENGTH.match(text)
    return f"{m.group(1)} {m.group(2).lower()}" if m else text


def strength_key(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())                    # determinism._norm_strength


def alias_map(entries) -> dict:
    """determinism._alias_map over ``entries``: canonicals and aliases claim names first, then brands."""
    m: dict = {}
    ordered = sorted(entries, key=lambda e: e.get("canonical", ""))
    for field in ("aliases", "brands"):
        for e in ordered:
            canon = e.get("canonical", "")
            for a in ([canon] if field == "aliases" else []) + list(e.get(field, [])):
                if canon and a.strip() and a.strip().lower() not in m:
                    m[a.strip().lower()] = canon
    return m


class Resolver:
    """Name -> canonical: exact, then the fixed fuzzy rule (a combination in another order is a NEW generic)."""

    def __init__(self, entries):
        self.amap = alias_map(entries)
        self.keys = sorted(k for k in self.amap if len(k) >= FUZZY_MIN_LEN)

    def add(self, name: str, canonical: str):
        key = name.strip().lower()
        if key and key not in self.amap:
            self.amap[key] = canonical
            if len(key) >= FUZZY_MIN_LEN:
                insort(self.keys, key)

    def near(self, low: str) -> str:
        best = difflib.get_close_matches(low, self.keys, n=1, cutoff=FUZZY_CUTOFF)
        return best[0] if best else ""

    def resolve(self, name: str):
        """(canonical, 'exact' | 'fuzzy') or None."""
        if name.lower() in self.amap:
            return self.amap[name.lower()], "exact"
        best = self.near(name.lower())
        return (self.amap[best], "fuzzy") if best else None


def read_rows(path, report):
    raw = path.read_bytes()
    report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    reader = csv.DictReader(raw.decode("utf-8-sig").splitlines())
    col = {(f or "").strip().lower(): f for f in (reader.fieldnames or [])}
    if [c for c in CSV_COLUMNS if c not in col]:
        raise SystemExit(f"ERROR: CSV {path} needs the columns {list(CSV_COLUMNS)}; found {list(col)}")
    rows = []
    for line, rec in enumerate(reader, start=2):
        if line > MAX_ROWS + 1:
            raise SystemExit(f"ERROR: CSV {path} has more than {MAX_ROWS} rows")
        brand, hint = strip_rx_prefix(clean(rec.get(col["brand"])))
        generic, word = norm_generic(rec.get(col["generic"])), clean(rec.get(col["form"]))
        if not (MIN_BRAND_LEN <= len(brand) <= MAX_BRAND_LEN and re.search(r"[A-Za-z]", brand)):
            report["rows_rejected"].append({"line": line, "reason": "bad brand", "value": brand[:60]})
        elif not re.search(r"[A-Za-z]", generic):
            report["rows_rejected"].append({"line": line, "reason": "missing generic", "value": brand})
        else:
            if word and word.lower().rstrip(".") not in FORMS:
                report["unknown_forms"].append(word)
            strengths = [norm_strength(s) for s in re.split(r"[;|]", rec.get(col["strength"]) or "") if clean(s)]
            rows.append({"brand": capitalise_flat(brand), "generic": generic, "strengths": strengths,
                         "form": FORMS.get(word.lower().rstrip("."), hint)})
    return rows


def _extend(existing, additions, key=lambda s: s.casefold()):
    have = {key(x) for x in existing}
    return [*existing, *sorted({key(a): a for a in additions if key(a) not in have}.values(), key=key)]


def import_rows(path, entries, source_name, allow_new_generics=False):
    """Plan the import; reads ``path`` only. Returns (changed_entries, report)."""
    report = {"source": source_name, "rows_rejected": [], "unknown_forms": [], "collisions": [],
              "near_collisions": [], "conflicts": [], "unmapped_generics": [], "generic_fuzzy": [],
              "new_generics": [], "brands_added": 0, "brands_already_present": 0, "strengths_added": 0}
    rows = read_rows(path, report)
    report["rows_read"] = len(rows) + len(report["rows_rejected"])
    res, existing, new, target = Resolver(entries), {e["canonical"]: e for e in entries}, {}, {}
    for generic in sorted({r["generic"] for r in rows}, key=lambda g: (g.casefold(), g)):
        hit = res.resolve(generic)
        if hit:
            target[generic] = hit[0]
            if hit[1] == "fuzzy":
                report["generic_fuzzy"].append({"csv": generic, "mapped_to": hit[0]})
        elif allow_new_generics:           # a new canonical joins the resolver, so a later misspelling maps to it
            target[generic] = generic
            new[generic] = {"aliases": [generic.lower()], "brands": [], "canonical": generic, "forms": [],
                            "source": source_name, "strengths": []}
            res.add(generic, generic)
        else:
            target[generic] = None
            report["unmapped_generics"].append(generic)
    by_brand = defaultdict(list)
    for r in rows:
        if target[r["generic"]]:
            by_brand[r["brand"].casefold()].append(r)
    add = defaultdict(lambda: {"brands": [], "strengths": [], "forms": []})
    for bkey in sorted(by_brand):
        group = by_brand[bkey]
        canon, brand = {target[r["generic"]] for r in group}, sorted({r["brand"] for r in group})[0]
        if len(canon) > 1:                 # two generics for one brand: record it, never guess
            report["conflicts"].append({"brand": brand, "generics": sorted(canon)})
            continue
        canon = canon.pop()
        owner = res.amap.get(brand.lower())
        near = "" if owner or len(brand) < FUZZY_MIN_LEN else res.near(brand.lower())
        if owner and owner != canon:
            report["collisions"].append({"brand": brand, "kept_for": owner, "csv_generic": canon})
            continue
        if near and res.amap[near] != canon:   # one slip from another drug's name: fuzzy matching would steal it
            report["near_collisions"].append({"brand": brand, "near": near, "kept_for": res.amap[near],
                                              "csv_generic": canon})
            continue
        if owner:
            report["brands_already_present"] += 1
        else:
            add[canon]["brands"].append(brand)
            res.add(brand, canon)
            report["brands_added"] += 1
        for r in group:
            add[canon]["strengths"] += r["strengths"]
            add[canon]["forms"] += [r["form"]] if r["form"] else []
    changed = []
    for canon in sorted(add):
        base = existing.get(canon) or new[canon]
        entry = {**base, "brands": _extend(base["brands"], add[canon]["brands"]),
                 "forms": _extend(base["forms"], add[canon]["forms"]),
                 "strengths": _extend(base["strengths"], add[canon]["strengths"], key=strength_key)}
        if entry != base or canon in new:
            report["new_generics"] += [canon] if canon in new else []
            report["strengths_added"] += len(entry["strengths"]) - len(base["strengths"])
            changed.append(dict(sorted(entry.items())))
    return changed, report
```

- [ ] **Step 5: Run them.** Run: `.venv/bin/python -m pytest tests/test_lexicon_import.py -q`. Expected: `5 passed`.
- [ ] **Step 6: Leave uncommitted.**

---

## Self-review

Gate (Task 1) and adapter rules (Task 2) are covered by tests; names match part 2's Assumptions block. Not done here, on purpose: wiring into `do_merge`, `sources`, `imported.json`, the look-alike check, the real import (all in I1-g2); downloading anything; choosing a licence.
