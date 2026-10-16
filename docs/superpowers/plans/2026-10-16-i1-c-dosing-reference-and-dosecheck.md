# Dosing Reference and Dose Check Implementation Plan (I1-c)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A prebuilt, versioned adult-dosing reference with a pure dose-range check and strength chips (contract 4.3, `core/dosing.py`), giving rows the status `dose-check` and the fields `strength_options`, `usual_strength`, `dose_note`.

**Architecture:** `core/dosing.py` reads `core/lexicon/dosing.json` (separate from the name lexicon) and exposes `strength_options`, `check_dose`, `dosing_version` and one grounding hook, `ground_extra`, which `validate_structured` calls right after `_ground_row` (so `dose-check` ranks after unverified-strength, before lookalike-check; contract 4.2). `lexicon/build_dosing.py` rebuilds the file from a local CSV: no scheduler, button or UI. Two choices: (1) a form a *reviewed* entry does not allow is flagged `dose-check` (spec 2b) via a fourth `DoseVerdict.state`, `form-mismatch`, and an optional `form=""` argument, a small deviation from contract 4.3's three states; (2) no age plumbing from `api/format.py`: `ageSex` already travels in the extracted form and in `current_form`, so `validate_structured` falls back to `out["ageSex"]` (the `age_sex` keyword is for I1-d).

**Tech Stack:** Python stdlib (`decimal`, `re`, `json`, `csv`), pytest, FastAPI TestClient.

**Spec:** "Iteration 1" sections 2 and 2b of `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md`; contracts in `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` (its section 4 wins).

**Assumptions about earlier plans:** I1-a adds status `lookalike-check` and may restructure the status branch of `validate_structured`; I1-b may have moved code out of `determinism.py`. Line numbers below are today's (482 lines): re-find each anchor with `grep -n` before editing.

> **No clinical data ships** (index, open decision 1: no source or clinician reviewer chosen). `dosing.json` ships with an empty `entries` list, so **until real data is added every drug is `cannot-check` and chips fall back to the lexicon `strengths`.** Tests use an invented fixture whose numbers are meaningless.

## Global Constraints

- Test command `.venv/bin/python -m pytest tests/ -q`, offline. Never commit or push; "leave uncommitted" means that.
- No file over 500 lines; `core/` stays pure (stdlib, reads only `dosing.json`). Existing row fields never change; the three new ones are always present (contract 4.1).
- `determinism.py` edit: at most 3 net lines; this plan adds **net +2** (482 to 484).
- Dose codes stay the five of `ALLOWED_DOSES` (`core/determinism.py:20`); `SOS` is not countable, and canvas rows like "2-2-2-2" cannot be produced (index fact 3).
- Code blocks use one blank line between top-level definitions to save space; the repo uses two, either runs.
- Baseline: run the suite first and note the count (944 passed, 1 skipped when written); expect baseline + **31** at the end.

## Review Focus

- Float rounding at the limit: Decimal; `test_in_range_at_max_and_above_max` (digoxin 0.75, which floats would flag).
- A child, blank age or "6 months" never gets an adult flag: `test_cannot_check_never_flags`; a corrupt `dosing.json` neither crashes nor invents data: `test_an_unreadable_reference_is_reported_not_trusted`.
- `dose-check` adds no `[unverified...]` marker or warning: `test_above_max_is_dose_check_ranked_by_contract_and_age_aware`.
- A correction that does not name a row keeps its `dose_note` with its restored status: `test_preserve_untouched_rows_keep_their_dose_note`.

## File Structure

Create (under `doctor_dictation/`) `core/dosing.py`, `core/lexicon/dosing.json`, `core/lexicon/build_dosing.py`; (under `tests/`) `dosing_fixtures.py`, `test_dosing.py`, `test_dosing_build.py`, `test_dosing_grounding.py`. Modify `core/determinism.py` (`:12`, `:384`, `:454-455`, `:470`), `core/correction.py` (`:273-278`), `api/health.py` (`:5`, `:49`).

### Task 1: Reference loader, strength chips and `check_dose`

**Interfaces:** Produces `check_dose(canonical, strength, dose, age_sex, form="") -> DoseVerdict`, `strength_options(canonical) -> (list[str], str)`, `dosing_version() -> str`, `parse_strength_mg(str) -> Decimal | None`, `ground_extra(status, match, form, strength, dose, age_sex) -> (status, dict)`, `DOSE_CHECK`, `DOSING_PATH`.

- [ ] **Step 1: Write the synthetic fixture and the failing tests.** `tests/dosing_fixtures.py`:
```python
"""SYNTHETIC dosing reference for tests: invented, clinically meaningless numbers. Never copy into dosing.json."""
import json

def _e(name, strengths, forms, usual, cap, reviewed=True):
    return {"canonical": name, "strengths": strengths, "forms": forms, "source": "SYNTHETIC TEST DATA",
            "reviewed": reviewed, "adult": {"usual": usual, "freq": "once daily", "max_daily_mg": cap}}

FIXTURE = {"version": "test-1", "built_at": "2026-01-01", "entries": [
    _e("Paracetamol", ["500 mg", "650 mg", "1 g"], ["Tab.", "Syr."], "650 mg", 1500),
    _e("Prednisolone", ["5 mg", "10 mg", "20 mg"], ["Tab."], "10 mg", 30),
    _e("Digoxin", ["0.25 mg"], ["Tab."], "0.25 mg", 0.75),
    _e("Amlodipine", ["2.5 mg", "5 mg", "10 mg"], ["Tab."], "5 mg", 10, reviewed=False)]}

def use_fixture(monkeypatch, tmp_path, data=FIXTURE):
    """Point the dosing loader at a temp copy of ``data`` (it re-reads when the path changes)."""
    from doctor_dictation.core import dosing
    (tmp_path / "dosing.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(dosing, "DOSING_PATH", tmp_path / "dosing.json")
```
`tests/test_dosing.py`:
```python
"""core/dosing.py: strength chips and the daily-total check, against a synthetic reference. Offline."""
import pytest

from doctor_dictation.core import dosing
from doctor_dictation.core.determinism import ALLOWED_DOSES
from doctor_dictation.core.dosing import check_dose, strength_options
from dosing_fixtures import use_fixture

@pytest.fixture()
def ref(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)

def _state(*args, **kw):
    return check_dose(*args, **kw).state

def test_shipped_reference_is_empty_so_every_drug_is_cannot_check():
    assert dosing.dosing_version() == "none" and dosing._load()["entries"] == {}       # Delete this line when real data ships
    assert _state("Paracetamol", "500 mg", "1-1-1", "45 / M") == "cannot-check"
    assert strength_options("Paracetamol") == (["500 mg", "650 mg", "120 mg/5ml"], "")
    assert set(dosing.DAILY_UNITS) == set(ALLOWED_DOSES) - {"SOS"}

def test_in_range_at_max_and_above_max(ref):
    ok = check_dose("Paracetamol", "500 mg", "1-0-1", "45 / M")
    assert (ok.state, ok.daily_mg, ok.max_daily_mg, ok.note) == ("in-range", 1000.0, 1500.0, "")
    assert _state("Paracetamol", "500 mg", "1-1-1", "18 / M") == "in-range"            # exactly 1500, age 18
    assert _state("Digoxin", "0.25 mg", "1-1-1", "70 / F") == "in-range"               # 0.75: no float noise
    v = check_dose("Paracetamol", "650 mg", "1-1-1", "45 / M")
    assert (v.state, v.daily_mg, v.note) == ("above-max", 1950.0, "1950 mg a day; usual adult maximum 1500 mg")

@pytest.mark.parametrize("args", [
    ("Paracetamol", "650 mg", "SOS", "45 / M"), ("Paracetamol", "650 mg", "2-2-2-2", "45 / M"),
    ("Amlodipine", "10 mg", "1-1-1", "45 / M"),                                          # unreviewed: 30 > 10
    ("Metformin", "500 mg", "1-1-1", "45 / M"), ("", "500 mg", "1-1-1", "45 / M"),       # not in the reference
    ("Paracetamol", "650 mg", "1-1-1", "8 / F"), ("Paracetamol", "650 mg", "1-1-1", "17 / M"),
    ("Paracetamol", "650 mg", "1-1-1", "6 months"), ("Paracetamol", "650 mg", "1-1-1", ""),
    ("Paracetamol", "120 mg/5ml", "1-1-1", "45 / M"), ("Paracetamol", "100 IU", "1-1-1", "45 / M"),
])
def test_cannot_check_never_flags(ref, args):
    v = check_dose(*args)
    assert (v.state, v.note) == ("cannot-check", "")

def test_unit_conversion(ref):
    assert check_dose("Paracetamol", "1000 mg", "1-0-1", "45 / M").daily_mg == 2000.0
    assert _state("Paracetamol", "0.5 g", "1-1-1", "45 / M") == "in-range"                # 1500 mg
    assert check_dose("Digoxin", "250 mcg", "1-0-0", "45 / M").daily_mg == 0.25

def test_form_mismatch_flags_only_a_reviewed_entry_and_an_adult(ref):
    v = check_dose("Prednisolone", "10 mg", "1-0-0", "45 / M", form="Syr.")
    assert (v.state, v.note) == ("form-mismatch", "Syr. is not a usual form of Prednisolone (usual: Tab.)")
    assert _state("Prednisolone", "10 mg", "1-0-0", "45 / M", form="Tab.") == "in-range"
    assert _state("Prednisolone", "10 mg", "1-0-0", "45 / M") == "in-range"                # no form given
    assert _state("Amlodipine", "5 mg", "1-0-0", "45 / M", form="Syr.") == "cannot-check"
    assert _state("Prednisolone", "10 mg", "1-0-0", "8 / F", form="Syr.") == "cannot-check"

def test_strength_options_usual_first_else_the_lexicon_never_made_up(ref):
    assert strength_options("Paracetamol") == (["650 mg", "500 mg", "1 g"], "650 mg")
    assert strength_options("Metformin") == (["500 mg", "850 mg", "1000 mg"], "")
    assert strength_options("Not A Drug") == ([], "")

def test_an_unreadable_reference_is_reported_not_trusted(monkeypatch, tmp_path):
    (tmp_path / "dosing.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(dosing, "DOSING_PATH", tmp_path / "dosing.json")
    assert dosing.dosing_version() == "unreadable" and _state("Paracetamol", "650 mg", "1-1-1", "45 / M") == "cannot-check"
```
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_dosing.py -q`. Expected: `ImportError: cannot import name 'dosing' from 'doctor_dictation.core'`.
- [ ] **Step 3: Create the empty reference** `doctor_dictation/core/lexicon/dosing.json`:
```json
{
  "version": "none",
  "built_at": "",
  "entries": []
}
```
- [ ] **Step 4: Write `doctor_dictation/core/dosing.py`.** It is "cannot-check" unless every input is certain: unreviewed entries never flag, under-18 or unknown age never flags, `Decimal` makes "exactly at max" exact, and strengths like `120 mg/5ml`, `5 ml`, `100 IU`, `0.1%` have no mg total so they are not guessed.
```python
"""Adult dosing reference: strength chips and the daily-total check. Pure, no AI. Whatever cannot be
computed is ``cannot-check`` (no claim, no flag); only ``reviewed`` entries can flag a row."""
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

DOSING_PATH = Path(__file__).resolve().parent / "lexicon" / "dosing.json"
DOSE_CHECK = "dose-check"
DAILY_UNITS = {"1-0-0": 1, "1-0-1": 2, "1-1-1": 3, "0-0-1": 1}      # ALLOWED_DOSES minus "SOS"
_MG = {"mg": Decimal(1), "g": Decimal(1000), "mcg": Decimal("0.001"), "ug": Decimal("0.001"),
       "µg": Decimal("0.001"), "μg": Decimal("0.001")}
_STRENGTH = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(mg|g|mcg|ug|µg|μg)\s*$", re.I)
_cache = (None, {})                                                   # (path read, {"version", "entries"})

@dataclass(frozen=True)
class DoseVerdict:
    state: str          # in-range | above-max | form-mismatch | cannot-check
    daily_mg: float | None
    max_daily_mg: float | None
    note: str           # "" unless above-max or form-mismatch

_CANNOT = DoseVerdict("cannot-check", None, None, "")

def _load() -> dict:
    # Re-read when DOSING_PATH changes; a broken file means no entries and version "unreadable".
    global _cache
    if _cache[0] != DOSING_PATH:
        try:
            raw = json.loads(DOSING_PATH.read_text(encoding="utf-8"))
            data = {"version": str(raw["version"]), "entries": {e["canonical"].casefold(): e for e in raw["entries"]}}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            data = {"version": "unreadable", "entries": {}}
        _cache = (DOSING_PATH, data)
    return _cache[1]

def dosing_version() -> str:
    return _load()["version"]            # "none" while the shipped file is empty

def parse_strength_mg(strength: str):
    """Decimal mg for '5 mg', '1 g', '250 mcg'; None for anything else (ml, IU, %, 'mg/5ml')."""
    m = _STRENGTH.match(strength or "")
    return Decimal(m.group(1)) * _MG[m.group(2).lower()] if m else None

def age_years(age_sex: str):
    """Years from '45 / M', '45', '45Y/M'; 0 for months, weeks or days; None when blank, unclear or over 120."""
    m = re.match(r"\s*(\d{1,3})\s*(mo|w|d)?", age_sex or "", re.I)
    return None if not m or int(m.group(1)) > 120 else (0 if m.group(2) else int(m.group(1)))

def strength_options(canonical: str) -> tuple:
    """(options, usual): reference strengths with the usual adult one first; else the lexicon list, ''."""
    entry = _load()["entries"].get((canonical or "").casefold())
    if entry and entry.get("strengths"):
        usual = str((entry.get("adult") or {}).get("usual") or "")
        return ([usual] if usual else []) + [s for s in entry["strengths"] if s != usual], usual
    from .determinism import load_lexicon
    return next((list(e.get("strengths", [])) for e in load_lexicon() if e.get("canonical") == canonical), []), ""

def check_dose(canonical: str, strength: str, dose: str, age_sex: str, form: str = "") -> DoseVerdict:
    """Daily total against the reviewed adult maximum; a given ``form`` is also checked against the entry."""
    entry = _load()["entries"].get((canonical or "").casefold())
    age = age_years(age_sex)
    if not entry or entry.get("reviewed") is not True or age is None or age < 18:
        return _CANNOT
    forms = entry.get("forms") or []
    if form and forms and form not in forms:
        return DoseVerdict("form-mismatch", None, None,
                           f"{form} is not a usual form of {entry['canonical']} (usual: {', '.join(forms)})")
    units, mg, cap = DAILY_UNITS.get(dose), parse_strength_mg(strength), (entry.get("adult") or {}).get("max_daily_mg")
    if units is None or mg is None or isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap <= 0:
        return _CANNOT
    daily, top = mg * units, Decimal(str(cap))
    fmt = lambda d: format(d.normalize(), "f")                                 # noqa: E731
    note = f"{fmt(daily)} mg a day; usual adult maximum {fmt(top)} mg" if daily > top else ""
    return DoseVerdict("above-max" if note else "in-range", float(daily), float(top), note)

def ground_extra(status: str, match: str, form: str, strength: str, dose: str, age_sex: str) -> tuple:
    """Grounding hook: (status, the three row fields of contract 4.1).

    Only a ``verified`` or ``lookalike-check`` row (both rank below dose-check) can become ``dose-check``.
    """
    options, usual = strength_options(match)
    note = ""
    if match and status in ("verified", "lookalike-check"):
        v = check_dose(match, strength, dose, age_sex, form)
        if v.state in ("above-max", "form-mismatch"):
            status, note = DOSE_CHECK, v.note
    return status, {"strength_options": options, "usual_strength": usual, "dose_note": note}
```
- [ ] **Step 5: Run** `.venv/bin/python -m pytest tests/test_dosing.py -q`. Expected: `17 passed`. Leave uncommitted.

### Task 2: `build_dosing.py`, the offline rebuild script

**Interfaces:** Consumes `parse_strength_mg`. Produces CLI `build_dosing.py CSV --version V [--built-at D] [--out PATH]`, `build_entries(path) -> list[dict]` (raises `ValueError` listing every problem), `main(argv) -> int`. The later monthly rebuild is this script; nothing here schedules it.

- [ ] **Step 1: Write the failing tests** `tests/test_dosing_build.py` (loaded by path because `lexicon/` has no `__init__`, like `tests/test_demo_script.py:32`):
```python
"""lexicon/build_dosing.py: validation, refusal of unknown canonicals, atomic and idempotent output. Offline."""
import importlib.util
import json
from pathlib import Path

import pytest

from doctor_dictation.core.determinism import ALLOWED_FORMS

SCRIPT = Path(__file__).resolve().parents[1] / "doctor_dictation" / "core" / "lexicon" / "build_dosing.py"
HEADER = "canonical,strengths,forms,usual,freq,max_daily_mg,source,reviewed\n"
GOOD = ("Paracetamol,500 mg;650 mg;1 g,Tab.;Syr.,650 mg,three times daily,1500,SYNTHETIC TEST DATA,yes\n"
        "amlodipine,2.5 mg;5 mg,Tab.,5 mg,once daily,10,SYNTHETIC TEST DATA,no\n")
OK = "Amlodipine,5 mg,Tab.,5 mg,od,10,S,yes"

@pytest.fixture(scope="module")
def build():
    spec = importlib.util.spec_from_file_location("build_dosing", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _run(build, tmp_path, body, header=HEADER):
    (tmp_path / "in.csv").write_text(header + body, encoding="utf-8")
    out = tmp_path / "dosing.json"
    return build.main([str(tmp_path / "in.csv"), "--version", "t-1", "--built-at", "2026-01-01", "--out", str(out)]), out

def test_good_csv_is_sorted_with_lexicon_spelling_and_a_rerun_is_byte_identical(build, tmp_path):
    assert build.FORMS == ALLOWED_FORMS
    code, out = _run(build, tmp_path, GOOD)
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0 and (doc["version"], doc["built_at"]) == ("t-1", "2026-01-01")
    assert [(e["canonical"], e["reviewed"]) for e in doc["entries"]] == [("Amlodipine", False), ("Paracetamol", True)]
    assert doc["entries"][1]["adult"] == {"usual": "650 mg", "freq": "three times daily", "max_daily_mg": 1500}
    first = out.read_bytes()
    assert _run(build, tmp_path, GOOD)[0] == 0 and out.read_bytes() == first
    assert not list(tmp_path.glob("*.tmp"))

@pytest.mark.parametrize("row,why", [
    ("Notadrugxyz,5 mg,Tab.,5 mg,od,10,S,yes", "is not in drugs.json"),
    ("Amlodipine,5 tabs,Tab.,5 tabs,od,10,S,yes", "strengths must be like"),
    ("Amlodipine,5 mg,Tab.,10 mg,od,10,S,yes", "usual '10 mg' is not one of the strengths"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,0,S,yes", "not a positive number"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,lots,S,yes", "not a positive number"),
    ("Amlodipine,5 mg,Tablet,5 mg,od,10,S,yes", "forms must be"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,10,,yes", "source is blank"),
    ("Amlodipine,5 mg,Tab.,5 mg,od,10,S,maybe", "reviewed must be yes or no"),
    (OK + "\n" + OK, "duplicate canonical"),
])
def test_a_bad_row_is_refused_and_the_previous_file_is_kept(build, tmp_path, row, why, capsys):
    _, out = _run(build, tmp_path, GOOD)
    before = out.read_bytes()
    assert _run(build, tmp_path, GOOD + row + "\n")[0] == 1
    assert why in capsys.readouterr().err and out.read_bytes() == before
```
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_dosing_build.py -q`. Expected: errors, `FileNotFoundError ... build_dosing.py`.
- [ ] **Step 3: Write `doctor_dictation/core/lexicon/build_dosing.py`** (run it with the project `.venv`, where the package is installed):
```python
"""Rebuild lexicon/dosing.json from a LOCAL CSV (offline, no scheduler): build_dosing.py in.csv --version 2026-10.

Header: canonical,strengths,forms,usual,freq,max_daily_mg,source,reviewed (';' separates list cells). An invalid
row lists every problem, exits 1 and leaves the existing file alone. Same CSV and flags give the same bytes.
"""
import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

from doctor_dictation.core.dosing import parse_strength_mg

HERE = Path(__file__).resolve().parent
DRUGS_JSON, DOSING_JSON = HERE / "drugs.json", HERE / "dosing.json"
COLUMNS = ["canonical", "strengths", "forms", "usual", "freq", "max_daily_mg", "source", "reviewed"]
FORMS = ("Tab.", "Cap.", "Syr.", "Inj.")   # a test pins this to determinism.ALLOWED_FORMS

def _entry(row: dict, canon: dict) -> tuple:
    """(entry, []) or (None, problems)."""
    g = lambda k: (row.get(k) or "").strip()                                   # noqa: E731
    cells = lambda k: [c.strip() for c in g(k).split(";") if c.strip()]       # noqa: E731
    name, strengths, forms = canon.get(g("canonical").casefold()), cells("strengths"), cells("forms")
    try:
        cap = float(g("max_daily_mg"))
    except ValueError:
        cap = 0.0
    bad = [msg for ok, msg in [
        (name, f"canonical {g('canonical')!r} is not in drugs.json"),
        (strengths and all(parse_strength_mg(s) is not None for s in strengths), "strengths must be like '5 mg', '1 g', '250 mcg'"),
        (forms and all(f in FORMS for f in forms), f"forms must be a ';' list of {', '.join(FORMS)}"),
        (g("usual") in strengths, f"usual {g('usual')!r} is not one of the strengths"),
        (0 < cap < float("inf"), f"max_daily_mg {g('max_daily_mg')!r} is not a positive number"),
        (g("source"), "source is blank"),
        (g("reviewed").lower() in ("yes", "no"), "reviewed must be yes or no"),
    ] if not ok]
    if bad:
        return None, bad
    adult = {"usual": g("usual"), "freq": g("freq"), "max_daily_mg": int(cap) if cap == int(cap) else cap}
    return {"canonical": name, "strengths": strengths, "forms": forms, "adult": adult,
            "source": g("source"), "reviewed": g("reviewed").lower() == "yes"}, []

def build_entries(csv_path: Path) -> list:
    """Validated entries sorted by canonical; ValueError lists every problem."""
    canon = {e["canonical"].casefold(): e["canonical"] for e in json.loads(DRUGS_JSON.read_text("utf-8"))["entries"]}
    problems, entries = [], {}
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f"CSV header must be exactly: {','.join(COLUMNS)}")
        for n, row in enumerate(reader, start=2):
            entry, errs = _entry(row, canon)
            if entry and entry["canonical"] in entries:
                errs = [f"duplicate canonical {entry['canonical']!r}"]
            problems += [f"row {n}: {e}" for e in errs]
            if not errs:
                entries[entry["canonical"]] = entry
    if problems:
        raise ValueError("\n".join(problems))
    return sorted(entries.values(), key=lambda e: e["canonical"].casefold())

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("--version", required=True, help="footer label, for example 2026-10")
    ap.add_argument("--built-at", default=date.today().isoformat(), help="pass it for a byte-identical rerun")
    ap.add_argument("--out", type=Path, default=DOSING_JSON)
    args = ap.parse_args(argv)
    try:
        entries = build_entries(args.csv)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    doc = {"version": args.version, "built_at": args.built_at, "entries": entries}
    tmp = args.out.with_name(args.out.name + ".tmp")        # write beside the target, then replace: never half a file
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, args.out)
    print(f"wrote {args.out}: {len(entries)} entries")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_dosing_build.py -q`. Expected: `10 passed`. Leave uncommitted. (`test_shipped_reference_is_empty...` in `tests/test_dosing.py` pins the shipped file to empty; the change that adds real reviewed data deletes that one assertion.)

### Task 3: Grounding hook, ranking and `preserve_untouched_rx_status`

**Interfaces:** Consumes `dosing.ground_extra`, `dosing.DOSE_CHECK`. Produces `validate_structured(data, transcript, age_sex="")` and rows carrying `strength_options`, `usual_strength`, `dose_note`.

- [ ] **Step 1: Write the failing tests** `tests/test_dosing_grounding.py` (Task 4 appends the last test, so write only up to `test_preserve_untouched_rows_keep_their_dose_note`):
```python
"""dose-check inside grounding: ranking, the new row fields, preserve_untouched, the routes and /api/health."""
import json

from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.core import determinism, dosing
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import validate_structured
from dosing_fixtures import use_fixture

TEXT = "paracetamol 650 mg three times daily, prednisolone 10 mg syrup once daily"
NOTE = "1950 mg a day; usual adult maximum 1500 mg"

def _row(age="45 / M", transcript=TEXT, **row):
    base = {"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1", "duration": "3 days"}
    out, warnings = validate_structured({"ageSex": age, "rx": [{**base, **row}]}, transcript)
    return out["rx"][0], warnings

def test_above_max_is_dose_check_ranked_by_contract_and_age_aware(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    row, warnings = _row()                                                     # 650 x 3 = 1950 > 1500
    assert (row["status"], row["lexicon_match"], row["dose_note"]) == ("dose-check", "Paracetamol", NOTE)
    assert (row["strength_options"], row["usual_strength"]) == (["650 mg", "500 mg", "1 g"], "650 mg")
    assert row["instructions"] == "" and warnings == []
    assert [_row(strength="500 mg")[0]["status"], _row(age="8 / F")[0]["status"]] == ["verified"] * 2
    assert _row(strength="1 g")[0]["status"] == "unverified-strength"          # a higher-ranked status wins
    assert _row(transcript="no medicines")[0]["status"] == "unverified-name"
    assert _row(name="Zzqxwv")[0]["status"] == "unknown-medicine"
    kw, _ = validate_structured({"ageSex": "8 / F", "rx": [{"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1"}]},
                                TEXT, age_sex="45 / M")                        # the keyword overrides the form
    assert kw["rx"][0]["status"] == "dose-check"

def test_hook_ranking_form_mismatch_and_fields_on_unknown_rows(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    hook = lambda status, strength="650 mg", dose="1-1-1": dosing.ground_extra(          # noqa: E731
        status, "Paracetamol", "Tab.", strength, dose, "45 / M")[0]
    assert [hook(s) for s in ("unverified-name", "unverified-strength", "unknown-medicine")] == [
        "unverified-name", "unverified-strength", "unknown-medicine"]
    assert (hook("lookalike-check"), hook("lookalike-check", "500 mg", "1-0-0")) == ("dose-check", "lookalike-check")
    row, _ = _row(name="Prednisolone", form="Syr.", strength="10 mg", dose="1-0-0")
    assert (row["status"], row["dose_note"]) == ("dose-check", "Syr. is not a usual form of Prednisolone (usual: Tab.)")
    assert _row(name="Zzqxwv")[0]["strength_options"] == []

def test_preserve_untouched_rows_keep_their_dose_note():
    cur = {"rx": [{"name": "Paracetamol", "status": "dose-check", "lexicon_match": "Paracetamol", "dose_note": NOTE},
                  {"name": "Prednisolone", "status": "verified", "lexicon_match": "Prednisolone"}]}
    new = {"rx": [{"name": "Paracetamol", "status": "verified", "lexicon_match": "Paracetamol", "dose_note": ""},
                  {"name": "Prednisolone", "status": "dose-check", "lexicon_match": "Prednisolone", "dose_note": "stale"}]}
    out = preserve_untouched_rx_status(cur, {}, new)["rx"]
    assert [(r["status"], r["dose_note"]) for r in out] == [("dose-check", NOTE), ("verified", "")]
```
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_dosing_grounding.py -q`. Expected: `3 failed` (`KeyError: 'strength_options'`, `KeyError: 'dose_note'`).
- [ ] **Step 3: Edit `core/determinism.py`.** Add above `:12`; change `:384`; add one line after `:454`, make the quiet branch at `:455` accept `dose-check`; append `**extra` at `:470`. If I1-a restructured the branch, keep the hook right after `_ground_row(...)` and keep `dose-check` out of the final `else`, which adds an `[unverified...]` marker.
```python
from . import dosing
from .candidates import suggest_candidates
# ...
def validate_structured(data: dict, transcript: str, age_sex: str = ""):
# ...
        status, match, issue = _ground_row(name, strength, tl)
        status, extra = dosing.ground_extra(status, match, form, strength, dose, age_sex or out["ageSex"])
        if status in (RX_VERIFIED, dosing.DOSE_CHECK):
# ...
            "lexicon_match": match, **extra,
```
- [ ] **Step 4: Edit `core/correction.py`**: after the `for field in (...)` loop at `:273-277`, still inside the row loop, add one line so an untouched row's note travels with its restored status (`strength_options` and `usual_strength` depend only on the unchanged name):
```python
        row["dose_note"] = prev.get("dose_note", "")   # "" when the prior row had none
```
- [ ] **Step 5: Run** `.venv/bin/python -m pytest tests/test_dosing_grounding.py tests/test_determinism.py tests/test_correction.py tests/test_correction_ops.py tests/test_file_sizes.py tests/test_core_purity.py -q`. Expected: all pass; `wc -l doctor_dictation/core/determinism.py` prints 484. Leave uncommitted.

### Task 4: Health key, route-level test and full suite

**Files:** Modify `api/health.py`; append to `tests/test_dosing_grounding.py`.

- [ ] **Step 1: Append the route test** to `tests/test_dosing_grounding.py` (its imports are already at the top of the file):
```python
def test_routes_end_to_end_and_health(monkeypatch, tmp_path):
    client = TestClient(M.app)
    assert client.get("/api/health").json()["dosing_version"] == "none"
    use_fixture(monkeypatch, tmp_path)
    assert client.get("/api/health").json()["dosing_version"] == "test-1"
    monkeypatch.setattr(determinism, "_FORMAT_CACHE", {})
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    said = "patient Rahul Sharma 45 year old male. tablet paracetamol 650 mg thrice daily for 3 days"
    row = client.post("/api/format", json={"transcript": said}).json()["structured"]["rx"][0]
    assert (row["status"], row["dose_note"]) == ("dose-check", NOTE)
    monkeypatch.setenv("ALLOW_STUB_PROVIDERS", "1")
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps({"rx": [{"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1"}]}))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    form = {"ageSex": "45 / M", "rx": [{"form": "Tab.", "name": "Paracetamol", "strength": "500 mg", "dose": "1-0-0"}]}
    body = {"transcript": "make paracetamol 650 mg thrice daily", "current_form": form}
    assert client.post("/api/v1/correct", json=body).json()["structured"]["rx"][0]["status"] == "dose-check"
```
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_dosing_grounding.py -q`. Expected: the new test fails with `KeyError: 'dosing_version'`.
- [ ] **Step 3: Expose the version.** An additive key is safe: health tests read named keys only (`tests/test_api_app.py:51`, `tests/test_determinism.py:140`) and `tests/test_secrets.py:143` only forbids secret values; the version is a label. In `api/health.py` add after `:5`, and after `:49` (`"lexicon_entries": lexicon_size(),`):
```python
from doctor_dictation.core.dosing import dosing_version
        "dosing_version": dosing_version(),
```
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/ -q`. Expected: `975 passed, 1 skipped`. Leave uncommitted; changed files are the ten in File Structure.

## Self-Review

Spec 2 is Tasks 1-2; spec 2b (Decimal totals, five codes, adult only, reviewed only, form check, `cannot-check` never claims a pass) is Task 1, with ranking and fields in Task 3 and the version in Task 4. `ground_extra` returns `(status, dict)` in Task 1 and is unpacked so in Task 3. `/api/format` caches by transcript (`determinism.py:475`), so a cached result keeps its reference until restart; not changed.

**Not done:** real clinical data, paediatric ranges, a wider dose vocabulary, per-row re-check (I1-d), UI (I1-e), cache keyed by reference version. **Decision needed:** approve the `form-mismatch` deviation from contract 4.3's three states, or drop the form check.
