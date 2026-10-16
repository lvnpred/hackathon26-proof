# Lexicon Import, Part 2: Merge Wiring, Look-alike Guard and the Real Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `build.py --merge FILE.csv` merge the adapter's entries idempotently, record the source and licence, keep the existing seed flow from undoing an import, refuse imports that raise look-alike risk past 10% (or arrive before the look-alike guard), then measure and run the real import under human review.

**Architecture:** `plan_merge` feeds adapter entries to the existing `compute_merged`. Every imported change is also recorded in `core/lexicon/imported.json`, which the default seed merge lays on top of `seed_extra.json` (additively), so a bare `--merge`/`--check` never reverts an import. `lookalike_problem` loads `core.lasa.twins` over the in-memory merged lexicon.

**Tech Stack:** Python 3 stdlib (`csv`, `difflib`, `json`, `unicodedata`), pytest. No new dependency.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` section 2d ("Larger lexicon") and table row "Bigger lexicon"; contracts in `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` (facts 5 and 8, section 4.3, open decision 4).

**Assumptions about earlier plans:**
- Plan I1-g1 is applied (run it first). From it this part uses exactly: `require_source(args, parser) -> dict | None`; flags `--source-name --licence --source-url --attribution --allow-new-generics --report`; `do_merge(seed_path, source=None, allow_new=False, report_path=None, now=None)` and `do_check(seed_path, source=None, allow_new=False)` (currently they ignore the extra parameters); `lexicon_import.import_rows(path, entries, source_name, allow_new_generics=False) -> (list[dict], dict)`, `alias_map`, `_extend`, `strength_key`; `tests/data/brands_fixture.csv`; and in `tests/test_lexicon_import.py` the helpers `load`, `build`, `run`, `exit_code`, `read`, `adapter`, and the constants `FIXTURE`, `SOURCE`, `MERGE`.
- Plan I1-a delivers `core/lasa.py` with `twins(canonical) -> list[str]` (contract 4.3) and its threshold "at most 10% of canonicals" (the I1-a file did not exist when this was written; 10% is the number from the task brief, kept in one constant `LOOKALIKE_MAX_SHARE`). I1-a does define it more narrowly: 35% of canonicals have a computed twin but only the 16 curated ones (3.6%) flag unconditionally, so `load_twins` below returns twins for those only (dry-run 2026-10-16: with every twin counted, a bare `--check` fails at 35.4%). Until `core/lasa.py` exists, no import can land (Task 2) but the bare `--check` still works.

**Produces:** a working `build.py --merge FILE.csv --source-name N --licence L [--allow-new-generics] [--report PATH]`; `layered_seed`, `plan_merge`, `lexicon_import.overlay`, `lookalike_share`, `load_twins`, `lookalike_problem`, `LOOKALIKE_MAX_SHARE = 0.10`; `core/lexicon/imported.json` (written by the first real import); `sources` records in `drugs.json`.

## Global Constraints

- No network access and no licence decision by code or by the executor: a human fills plan I1-g1 Task 1's checklist; nothing is downloaded by this plan.
- `--merge` of anything except the repo's own `seed_extra.json` needs `--source-name` (3+ chars) and `--licence` (10+ chars); both are written to `drugs.json` under `sources`.
- Never change: existing canonical names and their order, existing aliases, the order of existing brands/forms/strengths (additions go last), sorted entry keys, LF line endings, `indent=2` serialization. Output is byte-identical on a second identical run.
- A brand that collides with an existing canonical, alias or brand is skipped; so is one a single slip away (fuzzy cutoff 0.84) from a different drug's name. A brand the CSV maps to two generics is rejected. Nothing is guessed; everything skipped is in the report.
- Tests use only the synthetic `tests/data/brands_fixture.csv` and a COPY of `drugs.json`; offline; test command `.venv/bin/python -m pytest tests/ -q`. No commits: every "commit" step is "leave uncommitted".
- Source files stay under 500 lines (`tests/test_file_sizes.py:15-22` counts only `*.py` under `doctor_dictation/`, so `drugs.json` has no line limit; after 5,000 brands it is about 12,700 lines and 214 KB, parsed once at start-up by `core/determinism.py:66`).

## Review Focus

- A brand the dataset lists for two generics, or one that collides with an existing name, must never change what an existing name resolves to. Pinned in Task 1 (`test_existing_entries_and_names_are_never_changed_or_stolen`).
- Running the same import twice, or `build.py --merge` / `--check` with no arguments after an import, must not change or undo a byte. Pinned in Task 1.
- An import that pushes the share of look-alike drugs past 10%, or that arrives before the look-alike guard exists, must be refused and write nothing. Pinned in Task 2.
- A real import must be reviewable: every skipped brand and every fuzzy generic match is in the report, and nothing existing changed. Task 3.
- A larger lexicon must not make the request path slow. Task 3 measures it.

## How `--merge` works today (read from `build.py`, run on a copy)

`load_seed` (`build.py:88-104`) accepts a top-level JSON array and fails on a duplicate `canonical`. `compute_merged` (`:107-128`) unions by case-insensitive canonical and **the seed entry replaces the whole existing entry** (`:117`): merging `[{"canonical":"Paracetamol","brands":["ZZBrand",...]}]` into a copy gave "entries 444 -> 444, version 1.1.0 -> 1.2.0" and Paracetamol lost Crocin, Dolo, Calpol and its four aliases. So the adapter must emit COMPLETE entries (existing lists plus additions). The minor version is bumped only when the sorted entry list changed (`:120-123`, `bump_minor` `:74-85`); a bare `--merge` twice is byte-identical; `--check` (`:148-178`) re-computes in memory and compares bytes. Second finding: the bare `--merge`/`--check` re-applies `seed_extra.json`, which holds 403 of the 444 canonicals, so it would silently revert an import for all of them: hence `imported.json` (Task 3). Names resolve in `core/determinism.py:_alias_map` (`:90`): canonicals and aliases claim names first (sorted by canonical), then brands; the first claimant keeps a name. Generic lookup is exact, then `difflib.get_close_matches(..., cutoff=0.84)` over keys of 5+ letters (`_canonical_lookup`, `:226-244`); the adapter reuses exactly that rule.

**Version rule:** one minor bump per merge run that changes any entry (`1.1.0 -> 1.2.0`), however many brands it adds; no bump on a no-op run; a major bump is reserved for removing or renaming a canonical, which an import never does. `sources` gets one record per run that changed something.

**Performance** (this machine, `exp` script in Task 3; today's lexicon vs one grown to 5,000 brands with synthetic names): `_alias_map()` 0.2 -> 0.6 ms; a missed `_canonical_lookup` 1.3 -> 5.0 ms; `normalize_transcript` on an 80-word dictation 10 -> 45 ms (called once per `/api/format` inside `asyncio.to_thread`, `api/format.py:70-72`); `validate_structured` on 5 rows 2.5 -> 7.5 ms; `suggest_candidates` 16 -> 63 ms per unknown row and its one-time index build 3 -> 12 ms (`core/candidates.py:62-75`, cached by lexicon identity). Nothing is too slow for the request path. One flag: `build_repair_message` looks up candidates for up to 5 unknown rows per repair round (`core/determinism.py` `MAX_CANDIDATE_ROWS`), about 0.3 s of thread time on the big lexicon, small next to the LLM call it sits between. Import itself: 9.5 s for 5,000 rows, 0.7 s when re-run (everything already present).

## File Structure

| File | Change |
|---|---|
| `doctor_dictation/core/lexicon/build.py` | CSV dispatch, `sources`, `imported.json` overlay, look-alike check |
| `doctor_dictation/core/lexicon/lexicon_import.py` | add `overlay` |
| `doctor_dictation/core/lexicon/imported.json` | NEW, written by the first real import, not by this plan |
| `tests/test_lexicon_import.py` | 5 more tests (10 in all) |

Adds 5 tests. Baseline: the suite as it stands after I1-g1 (944 + 5 when written), expect that count + 5.

---

### Task 1: Merge wiring, the `sources` record, `imported.json` and idempotency

**Files:** Modify `doctor_dictation/core/lexicon/build.py`, `doctor_dictation/core/lexicon/lexicon_import.py`, `tests/test_lexicon_import.py`.

**Interfaces:** Consumes `import_rows`. Produces `layered_seed(seed_path)`, `plan_merge(seed_path, source, allow_new) -> (entries, report | None)`, `lexicon_import.overlay(seed, imported)`, the `sources` record `{name, licence, [url], [attribution], merged_at, entries_added, [brands_added, input_sha256]}` and `imported.json`.

- [ ] **Step 1: Append the failing tests.**

```python
def test_merge_records_the_source_bumps_the_minor_once_and_is_idempotent(build, monkeypatch, tmp_path):
    run(build, monkeypatch, *MERGE, "--report", str(tmp_path / "report.json"))
    first = build.DRUGS_JSON.read_bytes()
    data = json.loads(first)
    (src,) = data["sources"]
    assert data["version"] == "1.2.0"
    assert (src["name"], src["entries_added"], src["brands_added"]) == ("Fixture Brands 2026", 0, 5)
    assert src["licence"].startswith("Synthetic test data") and len(src["input_sha256"]) == 64
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", src["merged_at"]) and list(src) == sorted(src)
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["brands_added"] == 5
    run(build, monkeypatch, *MERGE)
    assert build.DRUGS_JSON.read_bytes() == first            # the same merge again: byte-identical, one source, same version


def test_check_fails_before_the_merge_and_passes_after_and_the_default_seed_never_undoes_an_import(build, monkeypatch):
    assert exit_code(build, monkeypatch, "--check", *MERGE) == 1
    run(build, monkeypatch, *MERGE)
    merged = build.DRUGS_JSON.read_bytes()
    assert exit_code(build, monkeypatch, "--check", *MERGE) == 0
    assert exit_code(build, monkeypatch, "--check") == 0          # the CI gate: seed_extra.json plus imported.json == drugs.json
    run(build, monkeypatch, "--merge")                            # re-merging the authored seed keeps the imported brands
    assert build.DRUGS_JSON.read_bytes() == merged
    imported = json.loads(build.IMPORTED_JSON.read_text(encoding="utf-8"))
    assert [e["canonical"] for e in imported] == ["Amoxicillin", "Atorvastatin", "Levodopa + Carbidopa", "Paracetamol"]


def test_existing_entries_and_names_are_never_changed_or_stolen(build, monkeypatch):
    lex, old = load("lexicon_import"), read(build)["entries"]
    run(build, monkeypatch, *MERGE, "--allow-new-generics")
    data = read(build)
    new = data["entries"]
    kept = {e["canonical"] for e in old}
    assert [e["canonical"] for e in new if e["canonical"] in kept] == [e["canonical"] for e in old]   # names and order
    by_new = {e["canonical"]: e for e in new}
    for e in old:
        for field in ("aliases", "brands", "forms", "strengths"):
            assert by_new[e["canonical"]][field][:len(e[field])] == e[field], (e["canonical"], field)   # additions go last
        assert by_new[e["canonical"]]["aliases"] == e["aliases"]
    assert all(list(e) == sorted(e) for e in new)                                  # keys stay in sorted order
    old_map, new_map = lex.alias_map(old), lex.alias_map(new)
    assert all(new_map[key] == canonical for key, canonical in old_map.items())    # no existing name changed hands
    assert new_map["pantocid"] == "Pantoprazole" and "glycomat" not in new_map and "quorabex" not in new_map
    assert data["sources"][0]["entries_added"] == 1 and "Zorlexin" in by_new
    from doctor_dictation.core import determinism as D                             # the new top-level key breaks no reader
    monkeypatch.setattr(D, "LEXICON_PATH", build.DRUGS_JSON)
    monkeypatch.setattr(D, "_lexicon_cache", None)
    assert D._canonical_lookup("Plantiva") == "Zorlexin" and D.lexicon_version() == "1.2.0"
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_lexicon_import.py -q`. Expected: 3 FAIL (the CSV is still read as JSON).

- [ ] **Step 3: Add `overlay`** to `lexicon_import.py`, directly above `def import_rows(`:

```python
def overlay(seed, imported):
    """``seed`` entries with the recorded imports laid on top: brands, forms and strengths are only ever appended."""
    by_key = {e["canonical"].casefold(): e for e in seed}
    for imp in imported:
        base = by_key.get(imp["canonical"].casefold())
        by_key[imp["canonical"].casefold()] = imp if base is None else dict(sorted({
            **base, "brands": _extend(base["brands"], imp["brands"]), "forms": _extend(base["forms"], imp["forms"]),
            "strengths": _extend(base["strengths"], imp["strengths"], key=strength_key)}.items()))
    return list(by_key.values())
```

- [ ] **Step 4: Wire `build.py`.** (a) constant after `DEFAULT_SEED`; (b) imports; (c) the module docstring: replace the paragraph starting "Verify the on-disk drugs.json is in sync" (`build.py:13-15`) with the block below; (d) replace the whole `do_merge` with `layered_seed`, `plan_merge` and the new `do_merge`; (e) in `do_check` read the seed through `plan_merge`.

```diff
- MIN_SOURCE_NAME, MIN_LICENCE = 3, 10
+ IMPORTED_JSON = HERE / "imported.json"   # every entry an import changed, complete; laid over the seed
+ MIN_SOURCE_NAME, MIN_LICENCE = 3, 10
```
```python
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))      # run as a script, the sibling module is imported by name
import lexicon_import  # noqa: E402
```
```python
Import a brand-to-generic CSV (columns brand, generic, strength, form). Any merge except the default seed
MUST name its data and licence; both are recorded in drugs.json under "sources":
    python doctor_dictation/core/lexicon/build.py --merge brands.csv --source-name "NAME" --licence "LICENCE TEXT" \
        [--source-url URL] [--attribution TEXT] [--allow-new-generics] [--report report.json]

Verify the on-disk drugs.json is in sync (offline, never writes):
    python doctor_dictation/core/lexicon/build.py --check [--merge SEED_FILE [--source-name N --licence L]]
Exits 0 when in sync, 1 when the bytes differ or the look-alike share is over its limit.
```
```python
def layered_seed(seed_path):
    """The seed's entries; for the default seed, with the recorded imports laid on top (additions only), so a
    plain --merge or --check never undoes an import."""
    entries = load_seed(seed_path)
    if seed_path.resolve() == DEFAULT_SEED.resolve() and IMPORTED_JSON.exists():
        entries = lexicon_import.overlay(entries, load_seed(IMPORTED_JSON))
    return entries


def plan_merge(seed_path, source, allow_new):
    """(seed_entries, report). A .csv goes through the import adapter; anything else is a JSON seed array."""
    if seed_path.suffix.lower() == ".csv":
        if not seed_path.is_file():
            raise SystemExit(f"ERROR: CSV file not found: {seed_path}")
        return lexicon_import.import_rows(seed_path, load_drugs().get("entries", []), source["name"], allow_new)
    return layered_seed(seed_path), None


def do_merge(seed_path, source=None, allow_new=False, report_path=None, now=None):
    current = load_drugs()
    before = len(current.get("entries", []))
    version_before = current.get("version")
    seed, report = plan_merge(seed_path, source, allow_new)
    data, changed = compute_merged(current, seed)         # the minor version is bumped once, and only on a change
    if source and changed:
        recorded = {e["canonical"]: e for e in load_seed(IMPORTED_JSON)} if IMPORTED_JSON.exists() else {}
        recorded.update((e["canonical"], e) for e in seed)       # imported.json: every entry an import changed, complete
        IMPORTED_JSON.write_text(json.dumps(sort_entries(recorded.values()), indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8", newline="\n")
        old = {e["canonical"] for e in current.get("entries", [])}
        data["sources"] = [*current.get("sources", []), dict(sorted({
            **source, "merged_at": now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "entries_added": len({e["canonical"] for e in data["entries"]} - old),
            **({"brands_added": report["brands_added"], "input_sha256": report["input_sha256"]} if report else {}),
        }.items()))]
    if report is not None and report_path:
        Path(report_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    after = len(data["entries"])

    write_drugs(data)
    note = "version bumped" if changed else "no change (version unchanged)"
    print(
        f"merge {seed_path.name}: entries {before} -> {after}, "
        f"version {version_before} -> {data.get('version')} [{note}]"
    )
    if report is not None:
        print("import: " + ", ".join(f"{k}={report[k] if isinstance(report[k], int) else len(report[k])}" for k in (
            "rows_read", "brands_added", "brands_already_present", "new_generics", "collisions",
            "near_collisions", "conflicts", "unmapped_generics")))
    print(f"wrote {DRUGS_JSON} (sorted by canonical, offline)")
```
```python
    seed, _report = plan_merge(seed_path, source, allow_new)
    data, _ = compute_merged(current, seed)
    expected
```

- [ ] **Step 5: Run them.** Run: `.venv/bin/python -m pytest tests/test_lexicon_import.py -q`. Expected: `8 passed`.
- [ ] **Step 6: Leave uncommitted.**

---

### Task 2: The look-alike guard on import and on `--check`

**Files:** Modify `doctor_dictation/core/lexicon/build.py`, `tests/test_lexicon_import.py`.

**Interfaces:** Consumes `core.lasa.twins` (contract 4.3). Produces `lookalike_share(entries, twins) -> float`, `load_twins(entries) -> callable | None`, `lookalike_problem(entries, required) -> str`, `LOOKALIKE_MAX_SHARE = 0.10`. An import (`source` given) with no `core/lasa.py`, or a share over 10%, raises `SystemExit` and writes nothing; `--check` exits 1 when the share is over 10%.

- [ ] **Step 1: Append the failing tests.**

```python
def test_import_is_refused_without_the_lookalike_guard_or_over_its_limit(build, monkeypatch):
    before = build.DRUGS_JSON.read_bytes()
    monkeypatch.setattr(build, "load_twins", lambda entries: None)                 # core/lasa.py absent
    with pytest.raises(SystemExit, match="core/lasa.py"):
        run(build, monkeypatch, *MERGE)
    monkeypatch.setattr(build, "load_twins", lambda entries: (lambda name: ["Other"]))   # every drug has a twin
    with pytest.raises(SystemExit, match="look-alike twin"):
        run(build, monkeypatch, *MERGE)
    assert build.DRUGS_JSON.read_bytes() == before
    assert build.lookalike_share([{"canonical": c} for c in "ABCDEFGHIJ"], lambda n: ["x"] if n in "AB" else []) == 0.2


def test_check_fails_when_the_lookalike_share_is_over_ten_percent(build, monkeypatch, capsys):
    run(build, monkeypatch, *MERGE)
    names = [e["canonical"] for e in read(build)["entries"]]
    flagged = set(names[: len(names) // 8])                                        # 12.5%
    monkeypatch.setattr(build, "load_twins", lambda entries: (lambda name: ["x"] if name in flagged else []))
    assert exit_code(build, monkeypatch, "--check", *MERGE) == 1
    assert "look-alike twin" in capsys.readouterr().err
    flagged = set(names[: len(names) // 20])                                       # 5%
    assert exit_code(build, monkeypatch, "--check", *MERGE) == 0
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_lexicon_import.py -q`. Expected: 2 FAIL (`DID NOT RAISE SystemExit`).

- [ ] **Step 3: Implement.** In `build.py`: (a) the constant; (b) the three functions above `def do_merge(`; (c) the gate at the top of `do_merge` after `compute_merged`; (d) in `do_check` the docstring, the two lines after `compute_merged`, and `return 1 if problem else 0` for the in-sync exit.

```diff
- MIN_SOURCE_NAME, MIN_LICENCE = 3, 10
+ LOOKALIKE_MAX_SHARE = 0.10   # plan I1-a: at most 10% of canonicals may have a look-alike twin
+ MIN_SOURCE_NAME, MIN_LICENCE = 3, 10
```
```python
def lookalike_share(entries, twins):
    """Share of canonicals with at least one look-alike twin (``twins(canonical) -> list``)."""
    names = [e["canonical"] for e in entries if e.get("canonical")]
    return sum(1 for n in names if twins(n)) / len(names) if names else 0.0


def load_twins(entries):
    """``core.lasa.twins`` (for the always-flag canonicals only) reading ``entries`` as the lexicon, or None while core/lasa.py does not exist."""
    sys.path.insert(0, str(HERE.parents[2]))
    try:
        from doctor_dictation.core import determinism, lasa
    except ImportError:
        return None
    determinism._lexicon_cache = entries           # lasa reads the lexicon through load_lexicon()
    always = lasa.always_flag_names()              # only the curated pairs flag unconditionally (I1-a); computed twins need evidence
    return lambda name: lasa.twins(name) if name in always else []


def lookalike_problem(entries, required):
    """Why these entries may not ship ('' when fine): too many canonicals with a twin, or (``required``,
    an import) the guard module core/lasa.py is missing."""
    twins = load_twins(entries)
    if twins is None:
        return "core/lasa.py (the look-alike guard, plan I1-a) is missing" if required else ""
    share = lookalike_share(entries, twins)
    print(f"look-alike share: {share:.1%} (limit {LOOKALIKE_MAX_SHARE:.0%})")
    return f"{share:.1%} of canonicals have a look-alike twin (limit {LOOKALIKE_MAX_SHARE:.0%})" \
        if share > LOOKALIKE_MAX_SHARE else ""


```
```diff
-     data, changed = compute_merged(current, seed)         # the minor version is bumped once, and only on a change
+     data, changed = compute_merged(current, seed)         # the minor version is bumped once, and only on a change
+     if source:                      # an import never lands without the look-alike guard, nor past its limit
+         problem = lookalike_problem(data["entries"], required=True)
+         if problem:
+             raise SystemExit(f"ERROR: {problem}. Nothing was written.")
```
```diff
-     """Recompute in memory and compare bytes; never writes. 0 in sync, 1 drift."""
+     """Recompute in memory and compare bytes; never writes. 0 in sync, 1 drift or look-alike share over its limit."""
```
```diff
-     data, _ = compute_merged(current, seed)
-     expected
+     data, _ = compute_merged(current, seed)
+     problem = lookalike_problem(data["entries"], required=bool(source))
+     if problem:
+         print(f"check FAILED: {problem}.", file=sys.stderr)
+     expected
```
```diff
-         )
-         return 0
+         )
+         return 1 if problem else 0
```

- [ ] **Step 4: Run them.** Run: `.venv/bin/python -m pytest tests/test_lexicon_import.py -q`. Expected: `10 passed`.
- [ ] **Step 5: Baseline check on the real lexicon.** Run: `.venv/bin/python doctor_dictation/core/lexicon/build.py --check`. Expected before I1-a exists: `check OK: drugs.json in sync (v1.1.0, 444 entries).` and exit 0. After I1-a: an extra line `look-alike share: 3.6% (limit 10%)`. **If X is already above 10 today, stop:** no import can pass; settle I1-a's definition of "flags unconditionally" first. (A rough stand-in, canonicals with another canonical at difflib ratio 0.8 or more, measured 17% on today's lexicon, so the definition matters.)
- [ ] **Step 6: Leave uncommitted.**

---

### Task 3: Measure, run the real import (human), review

**Files:** none changed by this task except `drugs.json`, `imported.json` and the report when the human runs the import.

- [ ] **Step 1: Measure the request path** (re-run after the real import with `D._lexicon_cache = None`). Save as `$SCRATCH/exp_perf.py` (outside the repo) and run `.venv/bin/python $SCRATCH/exp_perf.py` from the repo root (`PYTHONPATH=.`). Expected shape (numbers vary by machine; every column must stay under about 150 ms except `suggest_candidates` under 150 ms per row):

```python
"""Time the request-path lexicon steps on today's lexicon and on one grown to about 5,000 brands (synthetic names)."""
import random
import time

from doctor_dictation.core import candidates as C
from doctor_dictation.core import determinism as D

TEXT = ("Patient Ramesh Kumar 46 year old male with fever and cough since three days. Tablet Paracetamol 650 mg twice daily "
        "after food for five days, tablet Azithromycin 500 mg once daily for three days, syrup Ambroxol 5 ml thrice daily, "
        "tablet Pantoprazole 40 mg before food, review after one week. Advice: rest, plenty of fluids.")
ROWS = [{"name": n, "strength": "", "form": "Tab."} for n in ("Paracetamol", "Azithromycin", "Ambroxol", "Zorbixil", "Crocin")]


def ms(fn, n):
    start = time.perf_counter()
    for _ in range(n):
        fn()
    return f"{(time.perf_counter() - start) / n * 1000:7.1f} ms"


def measure(label, entries):
    D._lexicon_cache, C._index = entries, (None, ())
    print(f"{label:9} brands={sum(len(e['brands']) for e in entries):5}  _alias_map {ms(D._alias_map, 20)}"
          f"  lookup(miss) {ms(lambda: D._canonical_lookup('zzqxyplo'), 5)}  normalize_transcript {ms(lambda: D.normalize_transcript(TEXT), 5)}"
          f"  validate(5 rows) {ms(lambda: D.validate_structured({'rx': ROWS}, TEXT), 5)}"
          f"  suggest_candidates {ms(lambda: C.suggest_candidates('prednisolon'), 3)}")


random.seed(7)
real = [dict(e) for e in D.load_lexicon()]
measure("today", real)
grown = [{**e, "brands": list(e["brands"])} for e in real]
have = {b.lower() for e in grown for b in e["brands"]} | {e["canonical"].lower() for e in grown}
while sum(len(e["brands"]) for e in grown) < 5000:
    name = random.choice("BCDFGHJKLMNPRSTVZ") + random.choice("aeiou") + "".join(
        random.choice("bcdfghjklmnprstvz") + random.choice("aeiou") for _ in range(random.choice((2, 3, 3, 4)) - 1)) + random.choice(("", "x", "n", "l", "ol", "in"))
    if name.lower() not in have:
        have.add(name.lower())
        random.choice(grown)["brands"].append(name)
measure("5k brands", grown)

```
```
today     brands=  508  _alias_map     0.2 ms  lookup(miss)     1.3 ms  normalize_transcript    10.0 ms  validate(5 rows)     2.5 ms  suggest_candidates    16.0 ms
5k brands brands= 5000  _alias_map     0.6 ms  lookup(miss)     5.0 ms  normalize_transcript    45.1 ms  validate(5 rows)     7.5 ms  suggest_candidates    62.6 ms
```

- [ ] **Step 2: Run the import (only after plan I1-g1 Task 1's checklist is complete and `core/lasa.py` exists).** Copy `drugs.json` first, then:

```bash
cp doctor_dictation/core/lexicon/drugs.json $SCRATCH/drugs.before.json
.venv/bin/python doctor_dictation/core/lexicon/build.py --merge /path/to/brands.csv --source-name "<name>" --licence "<licence text>" \
  --source-url "<url>" --attribution "<text>" --report $SCRATCH/import_report.json
```
Expected: `look-alike share: ...`, `merge brands.csv: entries 444 -> 444, version 1.1.0 -> 1.2.0 [version bumped]`, `import: rows_read=..., brands_added=...`. Add `--allow-new-generics` only after reading `unmapped_generics` in the report.

- [ ] **Step 3: Review the report, then the diff.** Read `$SCRATCH/import_report.json`: `conflicts`, `collisions`, `near_collisions` (skipped on purpose), `generic_fuzzy` (each fuzzy generic match: confirm every one by eye), `unmapped_generics`, `new_generics`, `rows_rejected`. Then prove nothing existing changed:

```bash
.venv/bin/python - "$SCRATCH/drugs.before.json" <<'EOF'
import json, sys
old = json.load(open(sys.argv[1]))["entries"]
new = json.load(open("doctor_dictation/core/lexicon/drugs.json"))["entries"]
by = {e["canonical"]: e for e in new}
assert [e["canonical"] for e in new if e["canonical"] in {o["canonical"] for o in old}] == [o["canonical"] for o in old]
for o in old:
    for f in ("aliases", "brands", "forms", "strengths"):
        assert by[o["canonical"]][f][:len(o[f])] == o[f], (o["canonical"], f)
print("existing entries intact:", len(old), "-> total", len(new), "entries,", sum(len(e["brands"]) for e in new), "brands")
EOF
git diff -U0 -- doctor_dictation/core/lexicon/drugs.json | grep -c '^-[^-]'
```
Expected: the script prints "existing entries intact: 444 -> total ... entries, ... brands"; the `grep -c` count is small (one removed line per touched list whose last item gained a comma, plus the version line). Review `drugs.json` with `git diff -U0 ... | grep '^+ '` (additions, one brand per line) and read `sources` at the file's end; review `imported.json` as the compact list of touched entries.

- [ ] **Step 4: Verify the gates.** Run: `.venv/bin/python doctor_dictation/core/lexicon/build.py --check` (expect `check OK ...` and the share line), then `.venv/bin/python doctor_dictation/core/lexicon/build.py --merge /path/to/brands.csv --source-name "<name>" --licence "<licence>"` a second time (expect `no change (version unchanged)`; `git diff --stat` unchanged).
- [ ] **Step 5: Full suite.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: baseline + 10 passed, 1 skipped. `tests/golden.json` case `hinglish-mix` may change only if an imported brand collides with its words; if a golden case changes, read why before touching it.
- [ ] **Step 6: Leave everything uncommitted.** Changed files: `build.py`, `lexicon_import.py`, `tests/test_lexicon_import.py`, `tests/data/brands_fixture.csv`, and after the real import `drugs.json` and `imported.json`.

## Self-review

Merge, metadata, idempotency and version (Task 1), look-alike (Task 2), performance and review (Task 3). Names match part 1's Produces block: `require_source`, `import_rows`, `plan_merge`, `layered_seed`, `overlay`, `lookalike_problem`, `load_twins`, `IMPORTED_JSON`. Not done, on purpose: downloading anything, choosing a licence, per-brand provenance (brands stay plain strings; only new canonicals carry `source`), dosing data for imported drugs (they stay `cannot-check`, I1-c), a scheduler.
