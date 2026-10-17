# I2-d: Government Generics List, Schedule Marks and the Sync Command Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks 1-5 use fixtures only. Task 6 (the first real sync) is a MANUAL runbook step for the controller and the owner: an agent never runs it.

**Summary.** The owner wants the government's generic-name lists kept in the app and mapped to brands, in both readings: (a) a reference list such as NLEM (Iteration 1 resolved 384 NLEM medicines from the CDCI data: 284 to a CDCI generic, 151 already lexicon canonicals, 133 new; 105-111 generics not in the lexicon were skipped, mostly hospital, oncology and HIV drugs); (b) the Schedule H, H1 and X marks of the Drugs and Cosmetics Rules, shown on the row as a screen badge. The owner supplies the data later, prepared by another tool, as with the CDCI CSVs. This plan builds the pipeline: a CSV contract, an importer with the Iteration 1 gates, an idempotent `sync` with `--check` and a change report, a runtime reader, the row field `schedule` (from the generic, so a brand row gets it too), a gated path for new generics into the lexicon, and the owner's data checklist. Adds 13 tests: **1721** after I2-a only (1708 + 13), **1747** after I2-a, b and c. Needs I2-a.

**Decision needed from the owner.** (1) Confirm index Q10 (no schedule mark on paper), Q11 (a separate `generics.json`) and Q12 (removals only with `--apply-removals`). (2) Before Task 6: supply the CSV and answer the data checklist (section "Owner-supplied data"), including the reuse terms. Code decides no licence.

- **Goal:** A maintained generics list with schedule marks, re-synced from each new publication, that informs the doctor and never changes a row.
- **Architecture:** Offline: `core/lexicon/generics_sync.py` (stdlib; beside `build.py`, reusing `build.check_source`, `build.bump_minor`, `build.apply_import` and `lexicon_import.clean`, `norm_generic`, `load_rules`, `Checker`) reads one CSV per publication and writes `core/lexicon/generics.json` plus a report outside the repository. Runtime: pure `core/generics.py` loads that file once and answers `schedule_of(canonical)`; `rowcheck.ground_with_notes` adds `schedule` from `lexicon_match`; `correction` recomputes it; `rxview.js` shows a badge. New generics enter `drugs.json` only through `generics_sync.py promote` after a clinician review sheet and reviewed look-alike pairs.
- **Tech Stack:** Python 3 stdlib (`csv`, `difflib`, `hashlib`, `json`), pytest, node. No new dependency.
- **Spec:** index `2026-10-17-i2-00-index.md` D3, sections 4.1 (`schedule`), 6 (Q10-Q12), 7 (risks 6, 7). Iteration 1 importer: `2026-10-17-i1-g-lexicon-simple.md` (five checks, licence gate, lineage); backlog card (m).
- **Produces:** `generics_sync.py` commands `sync`, `review-sheet`, `promote`; `generics.json` shape; `core.generics`: `GENERICS_PATH`, `RANK`, `schedule_of`, `generics_version`, `reset`; row field `schedule`; `RxState.META_KEYS` + `schedule`; badge `.rx-sched`. Fixtures `tests/data/generics_nlem_fixture.csv`, `generics_nlem_newer_fixture.csv`, `generics_fixture.json`. Tests: `tests/test_generics_sync.py` (6), `tests/test_generics_runtime.py` (3), `tests/test_frontend_schedule_dom.py` (1), `tests/test_generics_promote.py` (3).

## Global Constraints
- **A schedule is information, never a block.** No status, Save gate (`core/safety.py:9-30`), dose check or name changes because of a schedule. A test pins it.
- **No licence by code.** Every write needs `--source-id`, `--source-name`, `--licence`, `--published`; `--report` must be outside the repository (as `build.py:156-174`). The suite never needs the real data.
- **Never silently delete.** A generic missing from a newer publication is reported and kept unless `--apply-removals` is given; a rename is reported, never linked.
- **A government-only generic never rewrites a transcript.** `generics.json` is not read by `correct_drugs` or `_alias_map`; only `promote` can add a canonical to `drugs.json`, and only through the gates.
- Byte-stable output: sorted entries and keys, `indent=2`, LF, `ensure_ascii=False`; a second identical run writes nothing. No `.py` file over 500 lines. No commits; never commit the owner's CSV or the report.

## Decisions (and why)
1. **A separate `generics.json` (Q11).** `drugs.json` is rebuilt from `seed_extra.json` plus `imported.json` by `build.py --merge` and checked byte for byte by `--check` (`build.py:123-144`, `:246-276`): a key added to `drugs.json` alone would be lost or fail the check. And most listed generics are not lexicon names: putting them in `drugs.json` would make `correct_drugs` rewrite near words to them (`determinism.py:186-199`), the Iteration 1 risk. Every reader of `drugs.json` already ignores unknown keys (`.get` on known keys only: `determinism.py:97-113`, `:291-293`, `candidates.py:62-75`, `lasa.py:46-60`, `hints.py:20-21`, `dosing.py:42`, `:103-130`), which the promote step relies on for its `origin` key.
2. **CSV contract** (one file per publication, UTF-8, BOM allowed, header row, column names case-insensitive, extra columns ignored, at most 20,000 rows):

   | Column | Required | Rule |
   |---|---|---|
   | `generic` | yes | As published (INN). Cleaned by `lexicon_import.clean` and `norm_generic` (`(...)` notes dropped, `A / B` -> `A + B`, flat case -> Capitalised). Shape `[A-Za-z][A-Za-z0-9 -]*` per part, parts joined by ` + `, 80 characters at most |
   | `list` | yes | The list's name WITHOUT its year, the same on every row: `NLEM`, `Schedules`. The edition is the source (`--source-id`, `--published`) |
   | `schedule` | no | `""`, `H`, `H1`, `X` (also `Schedule H1`; case-insensitive) |
   | `source_line` | no | Serial or line in the publication, 20 characters at most (lineage) |
   | `notes` | no | Free text for the operator; never stored |

3. **Gates per row** (report ids; the FIRST row of a generic decides, as in `lexicon_import.py:11-12`): `shape`; `bad-schedule`; `duplicate` (same generic again, with `first_line`); `conflict` (same generic with a different schedule: both lines reported, the membership kept WITHOUT a schedule: never guess); `curated-skip` (`import_rules.json` `skip_generics`, a dict of classes like `skip_brands`). Resolution, not a skip: `linked` (exact canonical or alias, or the synonym table: `Checker.resolve`, `lexicon_import.py:126-134`) or `new` (with `near`: lexicon names one slip away, 0.84; and `twins`: lexicon canonicals or other new generics at difflib ratio >= 0.75, `lasa.MIN_RATIO`).
4. **Entry shape.** `{"generic": "Cetirizine", "lexicon": "Cetirizine", "lists": {"NLEM": {"line": "17.2", "src": "nlem-2022"}, "Schedules": {"line": "45", "schedule": "H", "src": "dcr-2026"}}}`; `lexicon` is `""` for a new generic. Top level: `{"entries", "sources", "version"}`; each source `{id, name, licence, published, list, input_sha256, rows_read, synced_at, [url]}`. A row's `schedule` is the strictest over its lists (`RANK`: H < H1 < X).
5. **Sync semantics for list L.** The file is the whole of L. Added: in the file, not in L. Changed: a schedule that differs (applied; the newer source wins, its lineage recorded). Removed: in L, not in the file: reported and KEPT (old lineage) unless `--apply-removals`, which drops that membership and then any entry left with no list (`dropped`). `possible_renames`: removed x added pairs at ratio >= 0.84 or through the synonym table, reported only. Version: minor bump on any change (`build.bump_minor`; an absent file is `0.0.0`); a reused source id with another input sha256 is refused.
6. **Brand mapping.** A brand row's `lexicon_match` is its generic, so `schedule_of(lexicon_match)` covers brands with no extra table; a combination canonical (`Co-Amoxiclav`) gets a mark only if the list names it (exactly or by synonym), never from its parts.
7. **New generics into the lexicon** (backlog (m)). `review-sheet` writes the `new` entries with `near`, `twins` and `curated_pair` (`y` only when `lasa_pairs.json` holds a pair with `"reviewed": true`). `promote` reads the clinician's sheet (`clinician_ok` = `y`), refuses a row with a twin that has no reviewed pair (`twin-without-reviewed-pair`) or that fails checks 3-5 or shape (`Checker.failures`, `lexicon_import.py:136-151`), and adds the rest as brandless canonicals `{"aliases": [lower], "brands": [], "canonical": G, "forms": [], "origin": {"date", "reviewer", "src"}, "strengths": []}` through `build.apply_import` (so `imported.json`, the `sources` record and the minor bump work as for brands). Such a row grounds as a generic with no strength check and no dose reference.

## Review Focus (inputs most likely to bite)
| Input | Expected | Pinned in |
|---|---|---|
| `PARACETAMOL`, `Amoxicillin + Clavulanic acid`, `Levothyroxine` | Linked: Paracetamol; Co-Amoxiclav (synonym); Thyroxine (synonym) | test 2 |
| Ondansetron listed `H` and `H1` | `conflict`, kept with no schedule | test 2 |
| `Tab. Crocin 500` / schedule `Q` | `shape` / `bad-schedule` | test 2 |
| A newer edition without Zorbexamide, with Zorbexamida | `removed` kept; `possible_renames` | test 5 |
| A schedule H -> H1 | `changed`, applied | test 5 |
| The same CSV twice | `no change`, bytes identical | test 3 |
| A brand row (Crocin) and its generic row | The same badge | test 7 |
| A Schedule X row | Status, Save gate, dose check unchanged | test 7 |
| A name hand-edited after authoring | No badge (the generic guard) | test 8 |
| A missing or broken `generics.json` | No badges, no error | test 9 |
| A new generic with a computed twin (Daunorubicin/Doxorubicin 0.783, Dopamine/Dobutamine 0.778) | Not promoted until a reviewed pair exists | test 12 |

## File Structure and line budgets
| File | Change | Lines (budget) |
|---|---|---|
| `doctor_dictation/core/lexicon/generics_sync.py` | NEW: reader, gates, plan, sync, review sheet, promote, CLI | about 300 (<= 380) |
| `doctor_dictation/core/generics.py` | NEW runtime reader | about 45 (<= 60) |
| `doctor_dictation/core/lexicon/import_rules.json` | `"skip_generics": {}` | +1 |
| `doctor_dictation/core/rowcheck.py`, `correction.py` | `schedule` field, recompute | +2, +3 |
| `frontend/rxstate.js`, `rxview.js`, `rx.css`, `index.html` | meta key, badge, style, `?v=` | +2, +3, +1 |
| `tests/data/*` | three fixtures | small |

---

### Task 1: The CSV contract and the gates (pure)
**Files:** Create `generics_sync.py` (reader and `plan_sync`), the two CSV fixtures, `tests/test_generics_sync.py` (tests 1-2). Modify `import_rules.json`.

- [ ] **Step 1: Fixtures.** `tests/data/generics_nlem_fixture.csv` (TEST DATA ONLY; schedule values invented):
```text
generic,list,schedule,source_line,notes
Cetirizine,NLEM,,17.2,
PARACETAMOL,NLEM,,1.3,flat case is Capitalised
Levothyroxine,NLEM,,18.4,synonym of Thyroxine
Zorbexamide,NLEM,,99.1,invented new generic
Zorbexonide,NLEM,,99.2,invented twin of Zorbexamide (ratio 0.818)
Cetirizine,NLEM,,17.2,repeated row
Ondansetron,NLEM,H,5.1,test value
Ondansetron,NLEM,H1,5.2,conflicting test value
Tab. Crocin 500,NLEM,,1.4,not a generic
Amoxicillin + Clavulanic acid,NLEM,Schedule H,6.2,synonym of Co-Amoxiclav
Zorbetol,NLEM,Q,7.7,bad schedule
```
`tests/data/generics_nlem_newer_fixture.csv`:
```text
generic,list,schedule,source_line,notes
Cetirizine,NLEM,,17.2,
Paracetamol,NLEM,,1.3,
Levothyroxine,NLEM,,18.4,
Zorbexamida,NLEM,,99.1,a renamed spelling of Zorbexamide
Ondansetron,NLEM,H,5.1,
Amoxicillin + Clavulanic acid,NLEM,H1,6.2,schedule H -> H1
```
- [ ] **Step 2: Write the failing tests.**
```python
"""Plan I2-d: the generics list importer and sync. Offline; synthetic fixtures; writes only under tmp_path."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

from test_lexicon_import import FROZEN, build, load      # noqa: F401  (build: a tmp copy of the frozen lexicon)

DATA = Path(__file__).parent / "data"
NLEM, NEWER = DATA / "generics_nlem_fixture.csv", DATA / "generics_nlem_newer_fixture.csv"
SRC = ("--source-name", "NLEM fixture", "--licence", "Synthetic test data, public domain (test only)", "--published", "2022-09-13")

@pytest.fixture()
def gs(build, tmp_path, monkeypatch):
    mod = load("generics_sync")
    monkeypatch.setattr(mod, "build", build)
    monkeypatch.setattr(mod, "GENERICS_JSON", tmp_path / "generics.json")
    monkeypatch.setattr(mod, "PAIRS_JSON", tmp_path / "lasa_pairs.json")
    (tmp_path / "lasa_pairs.json").write_text(json.dumps({"note": "test", "pairs": []}), encoding="utf-8")
    return mod

def sync(gs, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "sync", *argv])
    return gs.main()

def test_the_csv_contract_reads_cleans_and_refuses_bad_files(gs, tmp_path):
    rows = gs.read_csv(NLEM, {})
    assert (len(rows), rows[1], rows[9]["generic"]) == (11, {"line": 3, "generic": "Paracetamol", "list": "NLEM", "schedule": "", "source_line": "1.3"},
                                                      "Amoxicillin + Clavulanic acid")
    assert rows[9]["schedule"] == "H" and rows[10]["schedule"] == "Q"           # checked later, by the gates
    p = tmp_path / "c.csv"
    for text, why in [("generic,schedule\nX,\n", "needs the columns"), ("generic,list\nA,NLEM\nB,NLEM 2025\n", "one list per file")]:
        p.write_text(text, encoding="utf-8")
        with pytest.raises(SystemExit, match=why):
            gs.read_csv(p, {})
    p.write_bytes("﻿GENERIC,List\nCetirizine,NLEM\n".encode("utf-8"))           # a BOM and upper-case column names
    assert gs.read_csv(p, {}) == [{"line": 2, "generic": "Cetirizine", "list": "NLEM", "schedule": "", "source_line": ""}]
    (tmp_path / "bad.csv").write_bytes(b"generic,list\n\xff,NLEM\n")
    with pytest.raises(SystemExit, match="not UTF-8"):
        gs.read_csv(tmp_path / "bad.csv", {})

def test_the_gates_link_exact_and_synonym_and_report_new_duplicate_conflict_shape_and_schedule(gs):
    data, rep = gs.plan_sync(gs.read_csv(NLEM, {}), {}, gs.build.load_drugs()["entries"], gs.load_rules(), "nlem-2022")
    by = {e["generic"]: e for e in data["entries"]}
    assert {g: e["lexicon"] for g, e in by.items()} == {"Amoxicillin + Clavulanic acid": "Co-Amoxiclav", "Cetirizine": "Cetirizine",
        "Levothyroxine": "Thyroxine", "Ondansetron": "Ondansetron", "Paracetamol": "Paracetamol", "Zorbexamide": "", "Zorbexonide": ""}
    assert by["Amoxicillin + Clavulanic acid"]["lists"]["NLEM"] == {"line": "6.2", "schedule": "H", "src": "nlem-2022"}
    assert "schedule" not in by["Ondansetron"]["lists"]["NLEM"]                                # a conflict is never guessed
    assert rep["linked"] == {"exact": 3, "synonym": 2} and rep["new"] == 2 and rep["rows_read"] == 11
    assert [(s["line"], s["checks"]) for s in rep["skipped"]] == [(7, ["duplicate"]), (10, ["shape"]), (12, ["bad-schedule"])]
    assert rep["conflicts"] == [{"generic": "Ondansetron", "lines": [8, 9], "schedules": ["H", "H1"]}]
    assert rep["new_generics"] == [{"generic": "Zorbexamide", "near": [], "twins": ["Zorbexonide"]},
                                   {"generic": "Zorbexonide", "near": [], "twins": ["Zorbexamide"]}]
```
- [ ] **Step 3: Run them.** Run: `.venv/bin/python -m pytest tests/test_generics_sync.py -q`. Expected: 2 FAIL (`FileNotFoundError: ... generics_sync.py`).
- [ ] **Step 4: `import_rules.json`.** Add `"skip_generics": {}` (sorted position). `lexicon_import.load_rules` reads only its known keys (`lexicon_import.py:58-64`), so brand imports are unaffected; `generics_sync.load_rules` returns those plus `skip_generics` flattened and casefolded.
- [ ] **Step 5: `generics_sync.py`: the reader and the plan.** The module starts like `build.py` (`:38-41`): `HERE`, `REPO_ROOT`, `sys.path[:0] = [str(HERE), str(HERE.parents[2])]`, then `import build`, `import lexicon_import as LI`; `GENERICS_JSON = HERE / "generics.json"`, `PAIRS_JSON = HERE / "lasa_pairs.json"`, `MAX_ROWS = 20_000`, `SCHEDULES = ("", "H", "H1", "X")`, `RANK = {"H": 1, "H1": 2, "X": 3}`, `PART = re.compile(r"[A-Za-z][A-Za-z0-9 -]*")`.
```python
def read_csv(path, report) -> list:
    """[{line, generic, list, schedule, source_line}] from one publication's CSV (contract: plan I2-d Decision 2)."""
    raw = Path(path).read_bytes()
    report["input_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"ERROR: CSV {path} is not UTF-8 ({exc.reason} at byte {exc.start}). Nothing was written.") from None
    reader = csv.DictReader(io.StringIO(text, newline=""))
    col = {(f or "").strip().lower(): f for f in (reader.fieldnames or [])}
    if not {"generic", "list"} <= set(col):
        raise SystemExit(f"ERROR: CSV {path} needs the columns ['generic', 'list']; found {list(col)}")
    get = lambda rec, k: LI.clean(rec.get(col[k]) if k in col else "")          # noqa: E731
    rows = []
    for line, rec in enumerate(reader, start=2):
        if line > MAX_ROWS + 1:
            raise SystemExit(f"ERROR: CSV {path} has more than {MAX_ROWS} rows")
        sched = re.sub(r"(?i)^schedule\s+", "", get(rec, "schedule")).upper()
        rows.append({"line": line, "generic": LI.norm_generic(get(rec, "generic")), "list": get(rec, "list"),
                     "schedule": sched, "source_line": get(rec, "source_line")[:20]})
    if len({r["list"] for r in rows}) > 1:
        raise SystemExit(f"ERROR: CSV {path} names more than one list; one list per file. Nothing was written.")
    return rows

def plan_sync(rows, current, entries, rules, source_id, apply_removals=False):
    """(new generics.json data, report) for one publication; pure: reads nothing, never decides a licence."""
```
`plan_sync` walks the rows in order with `LI.Checker(entries, [], [], rules)` for `resolve` and the `near` pool: shape (`all(PART.fullmatch(p) for p in g.split(" + "))` and `len(g) <= 80`), `bad-schedule` (`not in SCHEDULES`), `curated-skip`, `duplicate`/`conflict` by `generic.casefold()`; then builds the membership `{"line", "src", ["schedule"]}` per generic, merges into `current` per Decision 5 (added, changed, removed, `possible_renames`, `dropped`), computes `twins` with `difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio() >= 0.75` against lexicon canonicals and the other new generics (closest first), and returns entries sorted by `generic.casefold()` with keys sorted. Report keys: `source, rows_read, input_sha256, linked {exact, synonym}, new, new_generics [{generic, near, twins}], skipped [{line, generic, checks, [first_line]}], conflicts [{generic, lines, schedules}], added, changed [{generic, list, old, new}], removed, possible_renames [{removed, added}], dropped, removals_applied`.
- [ ] **Step 6: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_generics_sync.py tests/test_lexicon_import.py -q`. Expected: all pass (2 new).

---

### Task 2: The sync command: licence gate, lineage, idempotence, `--check`, the change report
**Files:** Modify `generics_sync.py` (`main`, `do_sync`); append tests 3-6 to `tests/test_generics_sync.py`.

- [ ] **Step 1: Append the failing tests.**
```python
def test_the_sync_writes_lineage_and_a_second_run_is_byte_identical(gs, monkeypatch, tmp_path, capsys):
    argv = ("--csv", str(NLEM), "--source-id", "nlem-2022", *SRC, "--report", str(tmp_path / "r.json"))
    sync(gs, monkeypatch, *argv)
    first = gs.GENERICS_JSON.read_bytes()
    data = json.loads(first)
    assert data["version"] == "0.1.0" and len(data["entries"]) == 7 and first.endswith(b"}\n") and b"\r\n" not in first
    (src,) = data["sources"]
    assert {k: src[k] for k in ("id", "list", "published", "rows_read")} == {"id": "nlem-2022", "list": "NLEM", "published": "2022-09-13", "rows_read": 11}
    assert src["input_sha256"] == hashlib.sha256(NLEM.read_bytes()).hexdigest() and "notes" not in first.decode()
    sync(gs, monkeypatch, *argv)
    assert gs.GENERICS_JSON.read_bytes() == first and "no change" in capsys.readouterr().out
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "sync", "--check", "--csv", str(NLEM), "--source-id", "nlem-2022", *SRC])
    assert gs.main() == 0

def test_the_licence_gate_refuses_before_reading_anything(gs, monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "read_csv", lambda *a: pytest.fail("read before the gate"))
    good = {"--source-id": "nlem-2022", "--source-name": "NLEM fixture", "--licence": "Synthetic test data, public domain (test only)",
            "--published": "2022-09-13", "--report": str(tmp_path / "r.json")}
    cases = [{k: v for k, v in good.items() if k != drop} for drop in good] + [
        {**good, "--published": "13-09-2022"}, {**good, "--source-id": "promoted-x"}, {**good, "--licence": "short"},
        {**good, "--report": str(Path(gs.HERE) / "r.json")}]                         # a report inside the repository
    for argv in cases:
        with pytest.raises(SystemExit) as exc:
            sync(gs, monkeypatch, "--csv", str(NLEM), *[x for kv in argv.items() for x in kv])
        assert exc.value.code == 2, argv
    assert not gs.GENERICS_JSON.exists()

def test_a_newer_list_reports_added_changed_removed_and_renames_and_keeps_what_was_removed(gs, monkeypatch, tmp_path):
    sync(gs, monkeypatch, "--csv", str(NLEM), "--source-id", "nlem-2022", *SRC, "--report", str(tmp_path / "a.json"))
    newer = ("--csv", str(NEWER), "--source-id", "nlem-2025", "--source-name", "NLEM newer fixture", "--licence",
             "Synthetic test data, public domain (test only)", "--published", "2025-01-01")
    sync(gs, monkeypatch, *newer, "--report", str(tmp_path / "b.json"))
    rep, data = json.loads((tmp_path / "b.json").read_text()), json.loads(gs.GENERICS_JSON.read_text())
    assert rep["added"] == ["Zorbexamida"] and rep["removed"] == ["Zorbexamide", "Zorbexonide"] and rep["removals_applied"] is False
    assert rep["changed"] == [{"generic": "Amoxicillin + Clavulanic acid", "list": "NLEM", "new": "H1", "old": "H"},
                              {"generic": "Ondansetron", "list": "NLEM", "new": "H", "old": ""}]
    assert rep["possible_renames"] == [{"added": "Zorbexamida", "removed": "Zorbexamide"}]
    by = {e["generic"]: e for e in data["entries"]}
    assert by["Zorbexamide"]["lists"]["NLEM"]["src"] == "nlem-2022" and data["version"] == "0.2.0"     # kept, old lineage
    sync(gs, monkeypatch, *newer[:3], "nlem-2025b", *newer[4:], "--apply-removals", "--report", str(tmp_path / "c.json"))
    rep = json.loads((tmp_path / "c.json").read_text())
    assert rep["dropped"] == ["Zorbexamide", "Zorbexonide"] and rep["removals_applied"] is True
    assert {e["generic"] for e in json.loads(gs.GENERICS_JSON.read_text())["entries"]} >= {"Zorbexamida"}

def test_check_mode_reports_drift_and_writes_nothing(gs, monkeypatch, tmp_path, capsys):
    sync(gs, monkeypatch, "--csv", str(NLEM), "--source-id", "nlem-2022", *SRC, "--report", str(tmp_path / "a.json"))
    before = gs.GENERICS_JSON.read_bytes()
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "sync", "--check", "--csv", str(NEWER), "--source-id", "nlem-2025", *SRC])
    assert gs.main() == 1 and gs.GENERICS_JSON.read_bytes() == before
    out = capsys.readouterr().out
    assert "check FAILED" in out and "added=1 changed=2 removed=2 (kept)" in out
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_generics_sync.py -q`. Expected: tests 3-6 FAIL (`main` missing).
- [ ] **Step 3: `main` and `do_sync`.** `argparse` with subcommands `sync`, `review-sheet`, `promote`. `sync`: `--csv` (required), `--source-id`, `--source-name`, `--licence`, `--published`, `--source-url`, `--report` (required unless `--check`), `--check`, `--apply-removals`. The gate runs FIRST and exits 2 with "Nothing was read or written": `build.check_source(...)` (`ValueError` -> `parser.error`), the id not starting with `build.RESERVED_IDS`, `--published` parsed by `date.fromisoformat`, the report path not inside `REPO_ROOT`. Then: read the current `GENERICS_JSON` (absent -> `{"entries": [], "sources": [], "version": "0.0.0"}`); refuse a source id already in `sources` with another `input_sha256` ("pick a new id"); `plan_sync`; if the entries are unchanged and the id is already recorded: print `no change: generics.json and the report were not rewritten` and return 0; `--check`: print `check OK` or `check FAILED: ... added=N changed=N removed=N (kept|applied)` and return 0 or 1; else bump the minor, append the source record (sorted keys, `synced_at` UTC), write `json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"` with `newline="\n"` through a temp file and `os.replace` (atomic: backlog (ae) lesson), write the report, print one summary line.
- [ ] **Step 4: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_generics_sync.py -q`. Expected: 6 passed.

---

### Task 3: The runtime reader and the row field `schedule`
**Files:** Create `doctor_dictation/core/generics.py`, `tests/data/generics_fixture.json`, `tests/test_generics_runtime.py`; Modify `core/rowcheck.py`, `core/correction.py`.

- [ ] **Step 1: The fixture** `tests/data/generics_fixture.json`:
```json
{"_comment": "TEST DATA ONLY: invented schedule values, not the legal schedule.",
 "entries": [
  {"generic": "Paracetamol", "lexicon": "Paracetamol", "lists": {"NLEM": {"line": "1.3", "src": "fx-1"}, "Schedules": {"line": "9", "schedule": "H", "src": "fx-2"}}},
  {"generic": "Prednisolone", "lexicon": "Prednisolone", "lists": {"Other": {"line": "1", "schedule": "X", "src": "fx-3"}, "Schedules": {"line": "4", "schedule": "H1", "src": "fx-2"}}},
  {"generic": "Zorbexamide", "lexicon": "", "lists": {"NLEM": {"line": "99.1", "src": "fx-1"}}}],
 "sources": [], "version": "0.1.0"}
```
- [ ] **Step 2: Write the failing tests.**
```python
"""Plan I2-d: the schedule mark reaches brand and generic rows from generics.json; information only. Offline."""
from pathlib import Path

import pytest

from doctor_dictation.core import generics, rowcheck
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.safety import screen_unverified

FIX = Path(__file__).parent / "data" / "generics_fixture.json"
T = "tab crocin 500 mg sos, tab paracetamol 500 mg, tab prednisolone 5 mg, tab cetirizine 10 mg"

@pytest.fixture()
def fixture_list(monkeypatch):
    monkeypatch.setattr(generics, "GENERICS_PATH", FIX)
    generics.reset()
    yield
    generics.reset()

def _rows(names):
    s, _w = validate_structured({"rx": [{"form": "Tab.", "name": n} for n in names]}, T, T)
    return s

def test_the_schedule_reaches_brand_and_generic_rows_and_is_information_only(fixture_list, monkeypatch):
    s = _rows(["Crocin", "Paracetamol", "Prednisolone", "Cetirizine", "Zzqxwv"])
    assert [(r["name"], r["schedule"]) for r in s["rx"]] == [("Crocin", "H"), ("Paracetamol", "H"), ("Prednisolone", "X"), ("Cetirizine", ""), ("Zzqxwv", "")]
    with_marks = [(r["status"], r["instructions"]) for r in s["rx"]]
    monkeypatch.setattr(generics, "GENERICS_PATH", FIX.with_name("absent.json"))
    generics.reset()
    assert [(r["status"], r["instructions"]) for r in _rows(["Crocin", "Paracetamol", "Prednisolone", "Cetirizine", "Zzqxwv"])["rx"]] == with_marks
    assert screen_unverified({"rx": [r for r in s["rx"] if r["status"] == "verified"]}, []) == []      # a mark never blocks Save
    assert generics.generics_version() == "" and generics.RANK == {"H": 1, "H1": 2, "X": 3}

def test_the_schedule_is_recomputed_on_correct_and_save_and_follows_a_hand_edit(fixture_list):
    cur = {"rx": [{"name": "Crocin", "status": "verified", "lexicon_match": "Paracetamol", "instructions": ""},
                  {"name": "Febuxostat", "status": "", "lexicon_match": "Paracetamol", "instructions": ""}]}   # renamed by hand
    fresh = [dict(r, status="x", lexicon_match="x", schedule="STALE") for r in cur["rx"]]
    rows = preserve_untouched_rx_status(cur, {}, {"rx": fresh})["rx"]
    assert [r["schedule"] for r in rows] == ["H", ""]
    assert "schedule" in rowcheck.ground_one({"name": "Crocin"}, T, T)

def test_a_missing_or_broken_generics_file_means_no_schedule(monkeypatch, tmp_path):
    for content in (None, "{not json", '{"entries": "x"}', '{"entries": [{"lexicon": "Paracetamol", "lists": {"L": {"schedule": "Q"}}}]}'):
        path = tmp_path / "g.json"
        if content is not None:
            path.write_text(content, encoding="utf-8")
        monkeypatch.setattr(generics, "GENERICS_PATH", path if content is not None else tmp_path / "none.json")
        generics.reset()
        assert generics.schedule_of("Paracetamol") == "" and generics.schedule_of("") == ""
    generics.reset()
```
- [ ] **Step 3: Run them.** Run: `.venv/bin/python -m pytest tests/test_generics_runtime.py -q`. Expected: 3 FAIL (`ImportError: cannot import name 'generics'`).
- [ ] **Step 4: `core/generics.py`.**
```python
"""The government generics list at run time (plan I2-d): a pure reader of core/lexicon/generics.json, loaded once.

It only informs: ``schedule_of`` never changes a row's name, status or the Save gate. A missing or broken file means
no marks. The file is written offline by core/lexicon/generics_sync.py; correct_drugs never reads it."""
import json
from pathlib import Path

GENERICS_PATH = Path(__file__).resolve().parent / "lexicon" / "generics.json"
RANK = {"H": 1, "H1": 2, "X": 3}
_cache = None

def _load():
    global _cache
    if _cache is None:
        try:
            data = json.loads(GENERICS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data = data if isinstance(data, dict) else {}
        marks = {}
        for e in data.get("entries") if isinstance(data.get("entries"), list) else []:
            lex = str(e.get("lexicon") or "").casefold() if isinstance(e, dict) else ""
            lists = e.get("lists") if lex and isinstance(e.get("lists"), dict) else {}
            for m in lists.values():
                s = m.get("schedule", "") if isinstance(m, dict) else ""
                if s in RANK and RANK[s] > RANK.get(marks.get(lex, ""), 0):
                    marks[lex] = s                                   # the strictest mark over every list
        _cache = (str(data.get("version") or ""), marks)
    return _cache

def schedule_of(canonical) -> str:
    """"H", "H1", "X" or "" for a lexicon canonical (a brand row passes its lexicon_match)."""
    return _load()[1].get(str(canonical or "").casefold(), "")

def generics_version() -> str:
    return _load()[0]

def reset():
    """Forget the loaded file (tests, and a deploy that replaces it)."""
    global _cache
    _cache = None
```
(`generics_version` returns `""` for an unreadable file; for the fixture it returns `"0.1.0"`.)

- [ ] **Step 5: Wire the row field.** `core/rowcheck.py`: `from . import dosing, formulary, generics` and in the row dict `"schedule": generics.schedule_of(match),`. `core/correction.py`: add `"schedule"` to `DERIVED_ROW_FIELDS` and to `RECOMPUTED_ROW_FIELDS` as `"schedule": lambda row: schedule_of(_recomputed_generic(row))` (import `from .generics import schedule_of`), so a hand-edited name gets no mark, like its generic.
- [ ] **Step 6: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_generics_runtime.py tests/test_rowcheck.py tests/test_correction.py tests/test_core_purity.py tests/test_safety.py -q`. Expected: all pass.

---

### Task 4: The screen badge
**Files:** Modify `frontend/rxstate.js` (`META_KEYS` + `"schedule"`; `afterEdit` name clears it), `frontend/rxview.js`, `frontend/rx.css`, `frontend/index.html` (`?v=` bumps and the pins in `tests/test_frontend_rxspell.py`); Create `tests/test_frontend_schedule_dom.py`.

- [ ] **Step 1: Write the failing test.**
```python
"""Plan I2-d: the schedule badge is screen-only text, information only."""
from test_frontend_rxspell_dom import _run

def test_the_schedule_badge_is_screen_only_text_and_a_name_edit_clears_it():
    r = _run("""
      const a = mkRow("s1", "verified", { name: "Crocin" }, { generic: "Paracetamol", schedule: "H1" });
      const b = mkRow("s2", "verified", { name: "Cetirizine" }, { generic: "Cetirizine", schedule: "" });
      const badge = (tr) => tr.querySelectorAll(".rx-sched").map((n) => [n.textContent, n.className, n.attrs.title]);
      const before = [badge(a), badge(b), a.dataset.rxstate];
      RxView.onEdit(a, cell(a, "name")); RxView.renderRow(a);
      console.log(JSON.stringify({ before, after: badge(a) }));""")
    title = "Schedule H1 medicine (Drugs and Cosmetics Rules). Information only: nothing on this row changes."
    assert r["before"] == [[["Sch H1", "rx-extra rx-sched no-print", title]], [], "ok"] and r["after"] == []
```
- [ ] **Step 2: Run it.** Expected: FAIL (no `.rx-sched`).
- [ ] **Step 3: `rxview.js` `renderRow`**, after the generic line: `if (!blank && r.meta.schedule) { const s = el("span", "rx-extra rx-sched no-print", "Sch " + r.meta.schedule); s.setAttribute("title", "Schedule " + r.meta.schedule + " medicine (Drugs and Cosmetics Rules). Information only: nothing on this row changes."); med.appendChild(s); }`. `rx.css`: `.rx-sched { margin-left:6px; font-size:11px; font-weight:600; color:#3a3ea6; border:1px solid #bcbdf0; border-radius:4px; padding:0 4px; }`. Not printed (Q10).
- [ ] **Step 4: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_frontend_schedule_dom.py tests/test_frontend_rxrow.py tests/test_frontend_rxspell.py tests/test_frontend_generic_dom.py -q`. Expected: all pass.

---

### Task 5: The review sheet and the gated promotion of new generics
**Files:** Modify `generics_sync.py` (`review-sheet`, `promote`); Create `tests/test_generics_promote.py`.

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-d: new generics reach the lexicon only after a clinician review and reviewed look-alike pairs."""
import csv
import json
import sys

import pytest

from test_generics_sync import NLEM, SRC, gs, sync          # noqa: F401
from test_lexicon_import import build, read                 # noqa: F401

PROMO = ("--source-id", "generics-2026-11", "--reviewer", "Dr. Test Reviewer")

def _sheet(gs, monkeypatch, tmp_path):
    sync(gs, monkeypatch, "--csv", str(NLEM), "--source-id", "nlem-2022", *SRC, "--report", str(tmp_path / "r.json"))
    monkeypatch.setattr(sys, "argv", ["generics_sync.py", "review-sheet", "--out", str(tmp_path / "sheet.csv")])
    gs.main()
    with open(tmp_path / "sheet.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def test_the_review_sheet_lists_new_generics_with_their_twins_and_pair_status(gs, monkeypatch, tmp_path):
    rows = _sheet(gs, monkeypatch, tmp_path)
    assert [(r["generic"], r["twins"], r["curated_pair"], r["clinician_ok"]) for r in rows] == [
        ("Zorbexamide", "Zorbexonide", "n", ""), ("Zorbexonide", "Zorbexamide", "n", "")]
    assert list(rows[0]) == ["generic", "lists", "schedule", "near", "twins", "curated_pair", "clinician_ok", "notes"]

def test_promote_refuses_a_twin_without_a_reviewed_pair_and_adds_a_brandless_canonical(gs, build, monkeypatch, tmp_path, capsys):
    rows = _sheet(gs, monkeypatch, tmp_path)
    with open(tmp_path / "ok.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(dict(r, clinician_ok="y") for r in rows)
    before = build.DRUGS_JSON.read_bytes()
    argv = ["generics_sync.py", "promote", "--review", str(tmp_path / "ok.csv"), *PROMO, "--report", str(tmp_path / "p.json")]
    monkeypatch.setattr(sys, "argv", argv)
    gs.main()
    assert build.DRUGS_JSON.read_bytes() == before and "twin-without-reviewed-pair" in capsys.readouterr().out
    gs.PAIRS_JSON.write_text(json.dumps({"note": "test", "pairs": [{"a": "Zorbexamide", "b": "Zorbexonide", "reviewed": True,
                                                                   "source": "clinician test"}]}), encoding="utf-8")
    gs.main()
    lex = read(build)
    added = [e for e in lex["entries"] if e["canonical"] in ("Zorbexamide", "Zorbexonide")]
    assert [(e["canonical"], e["aliases"], e["brands"], e["strengths"], e["origin"]["reviewer"]) for e in added] == [
        ("Zorbexamide", ["zorbexamide"], [], [], "Dr. Test Reviewer"), ("Zorbexonide", ["zorbexonide"], [], [], "Dr. Test Reviewer")]
    assert lex["version"] == "1.2.0" and lex["sources"][-1]["id"] == "generics-2026-11"
    monkeypatch.setattr(sys, "argv", ["build.py", "--check"])
    with pytest.raises(SystemExit) as exc:                                     # build.py:333 exits with do_check's code
        build.main()
    assert exc.value.code == 0                                                 # drugs.json is in sync with seed + imported.json

def test_a_promoted_generic_grounds_as_itself_with_no_dose_reference(gs, build, monkeypatch, tmp_path):
    from doctor_dictation.core import determinism as D
    _sheet(gs, monkeypatch, tmp_path)
    gs.PAIRS_JSON.write_text(json.dumps({"pairs": [{"a": "Zorbexamide", "b": "Zorbexonide", "reviewed": True}]}), encoding="utf-8")
    gs.promote_rows([{"generic": "Zorbexamide", "clinician_ok": "y"}], "generics-2026-11", "Dr. Test Reviewer")
    monkeypatch.setattr(D, "LEXICON_VERSION", D.lexicon_version())             # restored, with the cache, after the test
    monkeypatch.setattr(D, "LEXICON_PATH", build.DRUGS_JSON)
    monkeypatch.setattr(D, "_lexicon_cache", None)
    s, _w = D.validate_structured({"rx": [{"form": "Tab.", "name": "Zorbexamide", "strength": "10 mg"}]}, "tab zorbexamide 10 mg")
    row = s["rx"][0]
    assert (row["status"], row["lexicon_match"], row["generic"], row["strength_options"]) == ("verified", "Zorbexamide", "Zorbexamide", [])
```
`promote_rows(rows, source_id, reviewer, sheet_sha="")` trusts only `generic` and `clinician_ok` from the sheet; it recomputes the twins from `GENERICS_JSON` and the lexicon, so a hand-edited `twins` cell cannot skip the pair check. Test 13 promotes Zorbexamide only, so its twin is not a lexicon name and the row grounds `verified` (the real `lasa_pairs.json` has no Zorbex pair).

- [ ] **Step 2: Run them.** Expected: 3 FAIL (`invalid choice: 'review-sheet'`).
- [ ] **Step 3: `review-sheet`** writes the `new` entries (`lexicon == ""`) of `GENERICS_JSON` to `--out` (refused inside `REPO_ROOT` except `doctor_dictation/data/`, as `promotion.write_review`, `promotion.py:156-165`; cells starting with `= + - @` get a leading apostrophe, `promotion.py:168-170`), columns `generic, lists, schedule, near, twins, curated_pair, clinician_ok, notes`; `twins` and `near` joined by `; `; `curated_pair` = `y` when every twin has a pair with `"reviewed": true` in `PAIRS_JSON`.
- [ ] **Step 4: `promote`** (`--review`, `--source-id` pattern `generics-[a-z0-9-]{3,30}`, `--reviewer` 3+ characters, `--report` outside the repository): `promote_rows(rows, source_id, reviewer)` keeps rows with `clinician_ok == "y"`, refuses `twin-without-reviewed-pair`, `in-lexicon` and every `LI.Checker(entries, [], [{"brand": g, "generic": g} for g in approved], rules).failures(g)` failure (shape, five letters, ordinary word, one slip), prints one line per outcome, and passes the rest as complete entries to `build.apply_import(changed, {"id": source_id, "name": f"generics promoted {source_id}", "licence": "internal: generics from the government list, approved by a clinician", "reviewer": reviewer}, {"brands_added": 0, "input_sha256": <sheet sha>, "rules": rules["version"]})`. Nothing to add: `no change`.
- [ ] **Step 5: Run.** Run: `.venv/bin/python -m pytest tests/test_generics_promote.py tests/test_generics_sync.py tests/test_lexicon_import.py tests/test_lasa.py -q`. Expected: all pass.
- [ ] **Step 6: Mutations** (apply alone, see a failure, revert): drop the `conflict` rule (test 2); write without `sort_keys` (test 3); gate after the read (test 4); delete removed members without the flag (test 5); `--check` writes (test 6); `schedule_of` takes the first list instead of the strictest (test 7); `RECOMPUTED` schedule from `lexicon_match` without the guard (test 8); badge without `no-print` (test 10); promote without the twin check (test 12).
- [ ] **Step 7: Whole suite.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: the count before Task 1 plus 13: **1747 passed, 1 skipped** after I2-a, b and c, or **1721** after I2-a only.
- [ ] **Step 8: Live browser check** (after Task 6 provides a real `generics.json`, or now from a scratch COPY of the repository with the fixture written as `doctor_dictation/core/lexicon/generics.json` and `PYTHONPATH=<copy>`; never in the main checkout): server on 8801, temp `DB_PATH`, blank keys, stub speech. `formatTranscript("tab crocin 500 mg sos. tab paracetamol 500 mg")`: both rows show the same badge; the row state and the Save button are as without the file; the PDF has no mark. Stop the server, `lsof -i :8801` empty, delete the copy; commit nothing.
- [ ] **Step 9: Leave uncommitted.**

---

### Task 6: The first real sync (MANUAL runbook; the controller with the owner)
**Do not run without the owner's data and "go".**

- [ ] **Step 1: Owner-supplied data checklist** (the owner answers in writing; code decides nothing):
  1. Source name and edition, as published (for example "National List of Essential Medicines 2022", Ministry of Health and Family Welfare; "Drugs and Cosmetics Rules, 1945, Schedules H, H1 and X, as amended to <date>").
  2. Publication date and the URL or Gazette reference of the copy used.
  3. Reuse terms: the owner confirms the licence text to pass with `--licence` (for example the Government Open Data License - India, if the copy came from data.gov.in), whether attribution is required, and any territory limit. Backlog card (s) style: revisit before any hosting outside India.
  4. The tool that made the CSV, its version, and who checked its output.
  5. One CSV per list, in the contract of Decision 2; `list` without the year.
- [ ] **Step 2: Dry run on a copy:** `--check` first; read `added`, `conflicts`, `skipped`, `new_generics`.
- [ ] **Step 3: Sync** with the owner's flags; report under `$SCRATCH`, never in the repository. Gates: a second run says `no change`; `--check` exits 0; the full suite passes.
- [ ] **Step 4: New generics:** `review-sheet` -> clinician -> curated pairs in `lasa_pairs.json` (`reviewed: true`) for every twin -> `promote` -> `build.py --check`, `tests/test_ordinary_sentences.py`, `tests/test_candidates.py` and the full suite. Any failure: restore `drugs.json`, `imported.json` and `generics.json` from git.
- [ ] **Step 4b: Restart the server.** `core/generics.py` reads `generics.json` once per process; a sync or promote only reloads the process it ran in. Restart the app server after Step 3 and after Step 4, then look at one brand row's badge. A crash during `promote` after the ledger write is finished by running the same command again.
- [ ] **Step 5: Commit** only `generics.json` (and, after a promotion, `drugs.json`, `imported.json`, `lasa_pairs.json`) with the owner's word. Never the CSV or the report.

## Regression list (must stay green)
Brand import (`tests/test_lexicon_import.py`, the 49 curated skips pin), live gates (`test_candidates.py:85`, `test_ordinary_sentences.py`, `test_commonwords.py`, `test_brand_as_dictated.py:58`, `:307`), look-alike guard (`test_lasa.py`), Save gate (`test_safety.py`), print (`test_pdf_sheet.py`: no schedule printed), Spell it (`test_frontend_rxspell*.py`).

## Self-Review
- D3 (a): contract, gates, sync, lineage, renames, removals, licence gate (Tasks 1-2), new generics with the review sheet and reviewed pairs (Task 5), the data checklist (Task 6). D3 (b): schedule per membership, strictest per row, brands through their generic (Task 3), screen badge, print as a question (Task 4, Q10). Information only: test 7.
- Test count: 2 + 4 + 3 + 1 + 3 = 13.
- Assumes I2-a (`generic` for generic-named rows, test 13) and the `_run` harness of `tests/test_frontend_rxspell_dom.py` as I2-c leaves it (test 10).
- Out of scope: printing the mark; a scheduled sync; forms and strengths of new generics (backlog (n)); a dosing reference for them.

**Decision needed:** the owner's yes on Q10-Q12, then the Task 6 data checklist.
