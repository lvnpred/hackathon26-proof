# B1b: `core/` Subpackage Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the pure modules (`determinism` with its `lexicon/`, `correction`, `safety`) into `doctor_dictation/core/`, extract `fallback_format` into `core/fallback.py`, and enforce purity with a test. Behaviour does not change.

**Architecture:** A pure `git mv`-style relocation plus one function extraction. `determinism.py` finds `lexicon/drugs.json` through `Path(__file__).parent / "lexicon"`, so moving the module and the directory together keeps that working with zero code change. `main.py` imports `fallback_format` by name, so the format route and the two tests that touch it (`M.fallback_format`, `from ...main import fallback_format`) keep working untouched. An `ast`-based test fails if anything under `core/` imports a web, HTTP, database or sibling-layer module.

**Tech Stack:** Python 3.12 (venv `.venv`), pytest, `ast`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` (layout at line 83, rule at line 98: "`core/` imports nothing from `providers/`, `store/` or `api/`"); contracts in `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` (section 3 "After B1b"). Plan 4 of the sequence. **Adds 4 tests.**

**Baseline rule:** run `.venv/bin/python -m pytest tests/ -q` first and note the count (140 if B0a, B0b and B1a are applied cleanly). The final count must be that count + 4.

## Assumptions about earlier plans

- **B1a is applied:** the package is `doctor_dictation/` at the repo root with flat modules `main.py`, `determinism.py`, `correction.py`, `safety.py`, `config.py`, `lexicon/`; imports are absolute (`from doctor_dictation.determinism import ...`), no `try/except ImportError` pairs; tests import `doctor_dictation.*`; `.gitignore` already says `doctor_dictation/lexicon/rxnav_cache.json`; `pyproject.toml` exists with a setuptools `[tool.setuptools.package-data]` table that lists the lexicon JSON.
- **B0a and B0b are applied** (`correct()` calls `_validate`/`_ground`). They touch none of the code this plan moves, except that line numbers in `main.py` have shifted: **locate everything with `grep -n`, never by number.**
- Line numbers quoted below were read on the repo before B0a/B0b/B1a (package then named `backend/`); they are orientation only.

## Global Constraints

- "`core/` imports nothing from `providers/`, `store/` or `api/`" (spec line 98); contracts add `fastapi`, `httpx`, `sqlite3`, `doctor_dictation.pdf` and `doctor_dictation.db` to the forbidden list.
- `correction.py` is "pure and deterministic: no network, no time, no randomness, stdlib only" (its own docstring). Every module in `core/` is stdlib-only; verified by reading the code: `determinism` imports `difflib, hashlib, json, re, pathlib`; `correction` imports `json`; `safety` has no imports; `fallback` needs `re`. No function-level imports exist in any of the four.
- HTTP status codes and JSON shapes do not change. When a test changes only because an import path moved, change only its import line, never an assertion.
- No file over 500 lines (`determinism.py` is 450; `main.py` shrinks by about 172).
- Tests are offline; `main.py` calls `load_dotenv()`, so real keys exist in a developer's `.env`. Tests here stub nothing and call no network.
- Test command: `.venv/bin/python -m pytest tests/ -q`. **Do not run `git commit` or `git push`** (user rule): leave every change in the working tree and list the changed files at the end.

## Review Focus

1. A lazy `import httpx` or `import sqlite3` inside a function body in `core/` must still fail the purity test (a top-level-only check would miss it). Task 1 test 2 pins this.
2. The lexicon must still load after the move (a wrong relative path degrades silently to an empty lexicon only if the loader swallows errors; assert size >= 300 and the exact path). Task 1 test 3.
3. The wheel/package must still ship `drugs.json`: the stale `lexicon/*.json` package-data glob matches nothing after the move and the app would fail only when installed, not in the repo. Task 4 proves this with a build.
4. `main.fallback_format` and `core.fallback.fallback_format` must be the same object, so monkeypatching `M.fallback_format` keeps affecting the route. Task 1 test 4.
5. Byte-for-byte output of `fallback_format` and the validation pipeline over every golden transcript is unchanged. Task 2 and Task 3 snapshot comparison.

## File Structure

| Path | Change |
|---|---|
| `doctor_dictation/core/__init__.py` | create (docstring only) |
| `doctor_dictation/core/{determinism,correction,safety}.py` | moved from `doctor_dictation/`, content unchanged |
| `doctor_dictation/core/lexicon/{drugs.json,seed_extra.json,build.py}` | moved from `doctor_dictation/lexicon/`; `build.py` docstring paths updated, no logic change |
| `doctor_dictation/core/fallback.py` | create: `fallback_format` (about 172 lines), cut from `main.py` |
| `doctor_dictation/main.py` | imports re-pointed at `core.*`; `fallback_format` body removed, imported instead |
| `tests/test_core_purity.py` | create (4 tests) |
| `tests/test_determinism.py`, `tests/test_correction.py`, `tests/test_safety.py` | import lines only |
| `.gitignore`, `README.md`, `pyproject.toml` | lexicon path updates |

---

### Task 1: Purity and wiring tests (written first, fail first)

**Files:**
- Create: `tests/test_core_purity.py`

**Interfaces:**
- Consumes: `doctor_dictation.core` (package), `doctor_dictation.core.determinism.{LEXICON_PATH, lexicon_size}`, `doctor_dictation.core.fallback.fallback_format`, `doctor_dictation.main.fallback_format`. None exist yet.
- Produces: the four tests that gate Tasks 2-3.

- [ ] **Step 1: Write the tests** — create `tests/test_core_purity.py`:

```python
"""`doctor_dictation.core` stays pure: stdlib only, no I/O layers.

Parses every module's source with `ast`, so imports inside functions (lazy
imports) are caught as well as top-level ones.

Run:  .venv/bin/python -m pytest tests/test_core_purity.py -q
"""
import ast
import sys
from pathlib import Path

import doctor_dictation.core as core_pkg
import doctor_dictation.core.determinism as determinism
import doctor_dictation.main as main_mod
from doctor_dictation.core import fallback

CORE_DIR = Path(core_pkg.__file__).resolve().parent
FORBIDDEN = (
    "fastapi",
    "httpx",
    "sqlite3",
    "doctor_dictation.providers",
    "doctor_dictation.db",
    "doctor_dictation.api",
    "doctor_dictation.pdf",
)
DYNAMIC_IMPORTERS = {"__import__", "import_module"}


def _imported_names(source: str) -> list[str]:
    """Absolute dotted names imported anywhere in `source`; relative imports are skipped."""
    names: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
            names += [f"{node.module}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Call):
            fn = node.func
            called = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if called in DYNAMIC_IMPORTERS:
                names.append(f"<dynamic import via {called}>")
    return names


def _violations(source: str) -> list[str]:
    bad = []
    for name in _imported_names(source):
        if name.startswith("<dynamic"):
            bad.append(name)
        elif any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
            bad.append(name)
        elif name.split(".")[0] not in sys.stdlib_module_names and not name.startswith("doctor_dictation.core"):
            bad.append(name)
    return bad


def _core_sources() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(CORE_DIR.glob("*.py"))}


def test_core_modules_import_no_io_layer_and_only_stdlib():
    sources = _core_sources()
    assert {"determinism.py", "correction.py", "safety.py", "fallback.py"} <= set(sources)
    found = {name: _violations(src) for name, src in sources.items()}
    assert {k: v for k, v in found.items() if v} == {}


def test_checker_catches_lazy_forbidden_and_non_stdlib_imports():
    lazy = "def f():\n    import httpx\n    from doctor_dictation.db import connect\n"
    assert _violations(lazy) == ["httpx", "doctor_dictation.db", "doctor_dictation.db.connect"]
    assert _violations("import json\nfrom pathlib import Path\nfrom . import sibling\n") == []
    assert _violations("import requests\n") == ["requests"]
    assert _violations("import importlib\nimportlib.import_module('sqlite3')\n") == [
        "<dynamic import via import_module>"
    ]


def test_lexicon_lives_inside_core_and_loads():
    assert determinism.LEXICON_PATH == CORE_DIR / "lexicon" / "drugs.json"
    assert determinism.LEXICON_PATH.is_file()
    assert determinism.lexicon_size() >= 300


def test_main_exposes_the_core_fallback_format():
    assert main_mod.fallback_format is fallback.fallback_format
    assert fallback.fallback_format("").get("rx") == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core_purity.py -q`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'doctor_dictation.core'`.

- [ ] **Step 3: Leave it uncommitted.** Tasks 2-3 make it pass.

---

### Task 2: Move `determinism`, `correction`, `safety` and `lexicon/` into `core/`

**Files:**
- Create: `doctor_dictation/core/__init__.py`
- Move: `doctor_dictation/{determinism,correction,safety}.py` and the whole `doctor_dictation/lexicon/` directory into `doctor_dictation/core/`
- Modify: `doctor_dictation/main.py` (the three import blocks: grep `doctor_dictation.determinism`, `doctor_dictation.correction`, `doctor_dictation.safety`), `tests/test_determinism.py` (grep `doctor_dictation.determinism`, 2 lines), `tests/test_correction.py` (1 line), `tests/test_safety.py` (1 line)

**Interfaces:**
- Consumes: Task 1's test file (ignored in this task's runs).
- Produces: importable `doctor_dictation.core.{determinism,correction,safety}`; `LEXICON_PATH == doctor_dictation/core/lexicon/drugs.json`.

- [ ] **Step 1: Snapshot behaviour before touching anything.** Write `$TMPDIR/b1b_snap.py` (outside the repo) and run it from the repo root. It imports only through `doctor_dictation.main`, so the same file works before and after the move:

```python
import json, sys
from pathlib import Path
from doctor_dictation.main import (fallback_format, lexicon_size, lexicon_version,
                                   normalize_transcript, validate_structured)

golden = json.loads(Path("tests/golden.json").read_text(encoding="utf-8"))
extra = ["", "   ",
         "op 4521 patient name Ravi 52 year old male cough and fever. Take Paracetamol 500 mg twice a day for 3 days. Review next week.",
         "open the window",
         "Mrs Lakshmi 61/F, Metformin 500 mg after food thrice daily for two weeks, avoid sugar, blood test hba1c"]
out = {"lexicon": [lexicon_size(), lexicon_version()], "cases": []}
for t in [g["transcript"] for g in golden] + extra:
    n = normalize_transcript(t)
    out["cases"].append({"raw": fallback_format(t), "pipeline": validate_structured(fallback_format(n), n)})
Path(sys.argv[1]).write_text(json.dumps(out, sort_keys=True, indent=1), encoding="utf-8")
print(len(out["cases"]), "cases ->", sys.argv[1])
```

Run: `PYTHONPATH=. .venv/bin/python $TMPDIR/b1b_snap.py $TMPDIR/b1b_before.json`
Expected: `13 cases -> .../b1b_before.json` (golden has 8 entries plus 5 extras; if golden has changed, the number differs, which is fine).

- [ ] **Step 2: Move the files** (plain `mv`; the repo has no commits, so `git mv` is not needed):

```bash
mkdir doctor_dictation/core
mv doctor_dictation/determinism.py doctor_dictation/correction.py doctor_dictation/safety.py doctor_dictation/core/
mv doctor_dictation/lexicon doctor_dictation/core/lexicon
cat > doctor_dictation/core/__init__.py <<'EOF'
"""Pure domain logic: no web framework, no network clients, no database.

`tests/test_core_purity.py` enforces that nothing in this package imports
fastapi, httpx, sqlite3, or doctor_dictation.{providers,db,api,pdf}.
"""
EOF
ls doctor_dictation/core doctor_dictation/core/lexicon
```

Expected: `__init__.py correction.py determinism.py lexicon safety.py` then `build.py drugs.json seed_extra.json`. No code edit is needed for the lexicon: `LEXICON_PATH = Path(__file__).resolve().parent / "lexicon" / "drugs.json"` in `determinism.py` and `HERE = Path(__file__).resolve().parent` in `lexicon/build.py` are both relative to their own file, and the two moved together.

- [ ] **Step 3: Re-point imports.** Only the import lines change. Run from the repo root:

```bash
.venv/bin/python - <<'EOF'
import pathlib
files = ["doctor_dictation/main.py", "tests/test_determinism.py", "tests/test_correction.py", "tests/test_safety.py"]
for f in files:
    p = pathlib.Path(f); s = p.read_text()
    for m in ("determinism", "correction", "safety"):
        s = s.replace(f"from doctor_dictation.{m} import", f"from doctor_dictation.core.{m} import")
        s = s.replace(f"import doctor_dictation.{m} as", f"import doctor_dictation.core.{m} as")
    p.write_text(s)
EOF
grep -rnE "doctor_dictation\.(determinism|correction|safety)\b" doctor_dictation tests --include='*.py'
```

Expected: the grep prints nothing. If it prints a line (an import form the script did not cover, e.g. `from doctor_dictation import determinism`), edit that line by hand to `from doctor_dictation.core import determinism`.

- [ ] **Step 4: Run the suite without the purity test**

Run: `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_core_purity.py`
Expected: `<baseline> passed` (same count as before the plan; zero failures).

- [ ] **Step 5: Compare the snapshot**

Run: `PYTHONPATH=. .venv/bin/python $TMPDIR/b1b_snap.py $TMPDIR/b1b_after.json && cmp $TMPDIR/b1b_before.json $TMPDIR/b1b_after.json && echo IDENTICAL`
Expected: `IDENTICAL`. Leave uncommitted.

---

### Task 3: Extract `fallback_format` into `core/fallback.py`

**Files:**
- Create: `doctor_dictation/core/fallback.py`
- Modify: `doctor_dictation/main.py` (remove `def fallback_format` through the line before `class FormatRequest(BaseModel):`; add one import)

**Interfaces:**
- Consumes: `fallback_format(transcript: str) -> dict` as it exists in `main.py`: one self-contained function, whose only dependency is `re` (imported inside it), with a nested helper `clean_name` and a local `STOP` set that travel with it. Nothing else in `main.py` is used by it.
- Produces: `doctor_dictation.core.fallback.fallback_format`, re-exported by name from `doctor_dictation.main` (the format route calls `fallback_format(...)` through `main`'s namespace; `tests/test_determinism.py` does `from doctor_dictation.main import fallback_format` and `M.fallback_format(...)`).

- [ ] **Step 1: Cut and paste mechanically.** The script moves the function verbatim (the function-local `import re` becomes a module-level one; nothing else changes) and inserts the import after the `core.safety` import. It raises if an anchor is missing:

```bash
.venv/bin/python - <<'EOF'
import pathlib, re
p = pathlib.Path("doctor_dictation/main.py"); s = p.read_text()
start = s.index("def fallback_format(transcript: str) -> dict:")
end = s.index("class FormatRequest(BaseModel):")
func = s[start:end].rstrip() + "\n"
assert func.count("\n    import re\n\n") == 1, "expected exactly one local 'import re'"
func = func.replace("    import re\n\n", "", 1)
header = ('"""Rule-based structuring used when no LLM is configured or the LLM fails.\n\n'
          'Pure and offline: stdlib `re` only. `main.fallback_format` re-exports this name.\n"""\n'
          'import re\n\n\n')
pathlib.Path("doctor_dictation/core/fallback.py").write_text(header + func, encoding="utf-8")
s = s[:start] + s[end:]
s, n = re.subn(r"(?m)^(from doctor_dictation\.core\.safety import .*\n)",
               r"\1from doctor_dictation.core.fallback import fallback_format\n", s)
assert n == 1, "core.safety import line not found"
p.write_text(s)
EOF
wc -l doctor_dictation/core/fallback.py doctor_dictation/main.py
grep -n "fallback_format" doctor_dictation/main.py
```

Expected: `fallback.py` about 172 lines; `main.py` about 172 lines shorter than before; the grep shows the new import line plus the call sites in the format route (`validate_structured(fallback_format(normalized), normalized)`, twice). No `def fallback_format` remains in `main.py`. Do not edit the call sites.

- [ ] **Step 2: Run the purity tests**

Run: `.venv/bin/python -m pytest tests/test_core_purity.py -q`
Expected: `4 passed`.

- [ ] **Step 3: Prove the guard bites.** Append a lazy forbidden import, expect failure, then restore:

```bash
cp doctor_dictation/core/safety.py $TMPDIR/safety.bak
printf '\n\ndef _oops():\n    import sqlite3\n    return sqlite3\n' >> doctor_dictation/core/safety.py
.venv/bin/python -m pytest tests/test_core_purity.py -q 2>&1 | grep -E "AssertionError|passed|failed"
cp $TMPDIR/safety.bak doctor_dictation/core/safety.py
```

Expected: `AssertionError: assert {'safety.py': ['sqlite3']} == {}` and `1 failed, 3 passed`. After the restore, `.venv/bin/python -m pytest tests/test_core_purity.py -q` prints `4 passed`.

- [ ] **Step 4: Full suite and snapshot**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `<baseline + 4> passed`.
Run: `PYTHONPATH=. .venv/bin/python $TMPDIR/b1b_snap.py $TMPDIR/b1b_after.json && cmp $TMPDIR/b1b_before.json $TMPDIR/b1b_after.json && echo IDENTICAL`
Expected: `IDENTICAL`. Leave uncommitted.

---

### Task 4: Lexicon tooling paths: `.gitignore`, `build.py` docs, README, package-data

**Files:**
- Modify: `.gitignore`, `doctor_dictation/core/lexicon/build.py` (docstring only), `README.md`, `pyproject.toml`

**Interfaces:**
- Consumes: the moved `core/lexicon/` directory from Task 2.
- Produces: an ignored cache path at the new location, a lexicon that ships in built wheels, and correct usage text.

- [ ] **Step 1: Prove the old package-data glob ships nothing** (this is the failure the edit prevents). Find the entry:

Run: `grep -n -B2 -A4 "package-data" pyproject.toml`
Expected (B1a's form; the exact list may carry more globs):

```toml
[tool.setuptools.package-data]
doctor_dictation = ["lexicon/*.json", "db/migrations/*.sql"]
```

Setuptools resolves package-data globs relative to the package directory, so `lexicon/*.json` now matches nothing (the directory is `core/lexicon/`). Change only that glob:

```toml
doctor_dictation = ["core/lexicon/*.json", "db/migrations/*.sql"]
```

If B1a used another mechanism (a `MANIFEST.in` line `recursive-include doctor_dictation/lexicon *.json`, or `include-package-data`), apply the same path change `lexicon` to `core/lexicon` there. Keep every other glob as it is.

- [ ] **Step 2: Verify with a build.** Needs `setuptools` (not in `.venv`; use `uv run --with setuptools` or any interpreter that has it):

```bash
rm -rf build && uv run --no-project --with "setuptools>=61" python -c "
from setuptools import setup; setup(script_args=['-q','build_py'])" 2>&1 | tail -2
find build -name '*.json'; rm -rf build
```

Expected: `build/lib/doctor_dictation/core/lexicon/drugs.json` and `.../seed_extra.json`. (If `pyproject.toml` is the only metadata and this one-liner cannot read it, use `.venv/bin/python -m pip wheel . --no-deps --no-build-isolation -w $TMPDIR/wheel` where setuptools is installed, then `unzip -l $TMPDIR/wheel/*.whl | grep drugs.json`; expect `doctor_dictation/core/lexicon/drugs.json`.) With the stale `lexicon/*.json` glob the `find` prints nothing; that was confirmed on the same tree while writing this plan with setuptools 58.

- [ ] **Step 3: `.gitignore`.** Change the one entry (B1a left it as `doctor_dictation/lexicon/rxnav_cache.json`):

```
doctor_dictation/core/lexicon/rxnav_cache.json
```

Verify: `touch doctor_dictation/core/lexicon/rxnav_cache.json && git check-ignore -v doctor_dictation/core/lexicon/rxnav_cache.json; rm doctor_dictation/core/lexicon/rxnav_cache.json`
Expected: one line starting with `.gitignore:<n>:doctor_dictation/core/lexicon/rxnav_cache.json`.

- [ ] **Step 4: `build.py` paths.** `HERE`, `DRUGS_JSON`, `CACHE_JSON` and `DEFAULT_SEED` are all `Path(__file__)`-relative and **need no code change**. Only the module docstring (lines 1-21) mentions the old location; update it:

```bash
sed -i.bak 's#doctor_dictation/lexicon/#doctor_dictation/core/lexicon/#g; s#doctor_dictation/determinism.py#doctor_dictation/core/determinism.py#g' doctor_dictation/core/lexicon/build.py
rm doctor_dictation/core/lexicon/build.py.bak
grep -n "lexicon/\|determinism.py" doctor_dictation/core/lexicon/build.py
```

Expected: lines 7, 9, 14, 18, 19, 20 all read `doctor_dictation/core/lexicon/...` or `doctor_dictation/core/determinism.py`. (If B1a was run with the older name, the same sed with `backend/` as the source works; the grep must show no `backend/` left.) Then run the tool, which must report in-sync and write nothing:

Run: `.venv/bin/python doctor_dictation/core/lexicon/build.py --check`
Expected: `check OK: drugs.json in sync (v1.1.0, 444 entries).` and exit code 0.

- [ ] **Step 5: README.** Find the line: `grep -n "lexicon/drugs.json" README.md` (one hit, in the determinism section, currently `` `doctor_dictation/lexicon/drugs.json` ``). Replace only the path with `doctor_dictation/core/lexicon/drugs.json`. Do not touch other README text. Old plan documents under `docs/` (`plan-determinism-finish.md`, `plan-phase0-hardening.md`) record history and keep their old paths.

- [ ] **Step 6: Run the suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `<baseline + 4> passed`. Leave uncommitted.

---

### Task 5: Final verification

**Files:** none modified.

- [ ] **Step 1: Full suite.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: `<baseline + 4> passed` (140 + 4 = 144 if the baseline was 140), zero failures.
- [ ] **Step 2: No stale references.** Run: `grep -rnE "doctor_dictation(/|\.)(determinism|correction|safety|lexicon)\b|backend[/.](determinism|correction|safety|lexicon)" doctor_dictation tests README.md .gitignore pyproject.toml`. Expected: no output (only `docs/plan-*.md` history files may still say `backend/`, and they are outside this grep).
- [ ] **Step 3: Size rule.** Run: `wc -l doctor_dictation/main.py doctor_dictation/core/*.py`. Expected: every file under 500 lines (`determinism.py` 450).
- [ ] **Step 4: Run the app with keys neutralised** (empty env vars beat `.env` for `load_dotenv()`, so nothing calls OpenAI):

```bash
OPENAI_API_KEY= DEEPSEEK_API_KEY= .venv/bin/python -m uvicorn doctor_dictation.main:app --port 8001 &
sleep 4
curl -s localhost:8001/api/health | grep -o '"lexicon_version":"[^"]*","lexicon_entries":[0-9]*'
curl -s -X POST localhost:8001/api/format -H 'content-type: application/json' \
  -d '{"transcript":"patient name Anita 45 year old female OP 1234 have paracetamol 500 mg twice a day for 3 days"}' | head -c 400
kill %1
```

Expected: `"lexicon_version":"1.1.0","lexicon_entries":444`, then JSON beginning `{"structured":{"patientName":"Anita","ageSex":"45 / F","opNo":"1234",...` with an `rx` row `Paracetamol`, `500 mg`, `1-0-1`, `3 days`, `status":"verified"` and an `engine` starting `fallback-rules+lexicon v1.1.0`.
- [ ] **Step 5: Changed-file list.** Run `git status --short -- doctor_dictation tests .gitignore README.md pyproject.toml`. Expected changes: `core/` (new, six files plus `lexicon/`), `main.py`, three test files, `tests/test_core_purity.py`, `.gitignore`, `README.md`, `pyproject.toml`. Report the list; do not commit.

**Not done (out of scope):** no compatibility shims at the old import paths (nothing outside this repo imports them); `fallback_format` is not renamed and `main.py` is not split further (B1e); old `docs/plan-*.md` history files keep their `backend/` paths.
