# B1a: Package Rename and Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `backend/` into the installable package `doctor_dictation` at the repo root, with one import style and a `pyproject.toml`, without changing any behaviour.

**Architecture:** Flat layout (`doctor_dictation/` beside `frontend/`, `tests/`, `docs/`), so `FRONTEND_DIR`, `data/` and `secrets.json` keep resolving relative to the package. All dual `try/except ImportError` imports collapse to `from doctor_dictation.x import ...`; the `sys.path` hacks go. `pyproject.toml` reads dependencies from the requirements files that move with the package, so there is one list of dependencies, not two.

**Tech Stack:** Python 3.12 (venv `.venv`), setuptools >= 68, FastAPI, pytest. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` (package layout section, deviations paragraph) and `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` section 3 "After B1a". Plan 3 of 15. **Prerequisite: B0a and B0b are applied** (140 tests passing). **Adds 1 test** (`tests/test_package_install.py`). Run the suite first, note the count (expected 140), and expect count + 1 at the end (141).

## Assumptions about earlier plans

- B0a and B0b only add code to existing files (`correction.py`, `main.py`, `config.py`, tests, `.env.example`, `frontend/app.js`). Their new tests import `backend.main`, `backend.config`, `backend.correction`; Task 1's sweep rewrites those too, so this plan does not depend on their exact text.
- B0a changed the `correction` import block in `main.py` (it now also imports `resolve_blank_names`). Task 2 collapses blocks with a script that keeps whatever names the `except` branch lists, so it does not matter which names are there.

## Global Constraints

- "Pure rename and rewiring, no logic changes." No function body changes. HTTP status codes and JSON shapes do not change.
- Only strings that name a file path change text: the 501 `hint` in `/api/transcribe` and the `onnx_stt.detail` text in `/api/health` now say `doctor_dictation/requirements-onnx.txt` instead of `backend/requirements-onnx.txt`. No test asserts either string (verified by grep).
- When a test changes only because a path or patch target moved, change only its import or setup line, never an assertion on behaviour. The one exception is `tests/test_db.py`, which asserts the physical path of the package; its expected path changes to `doctor_dictation`.
- No file over 500 lines after the plan (`main.py` stays about 1,000 lines until B1e; it is not made larger).
- **Do not run `git commit` or `git push`.** The directory is untracked in git, so use plain `mv`, not `git mv`. Leave everything in the working tree and list changed files at the end.
- Tests never call OpenAI. The new test only imports the app (no request is made).
- Run tests with `.venv/bin/python -m pytest tests/ -q`.

## Review Focus

1. No `backend` path or import survives outside `docs/` (Task 1 grep and Task 2 grep, with the exact expected leftovers listed).
2. `pip install -e .` works in the real `.venv`, and `import doctor_dictation` works from a directory outside the repo (Task 4).
3. The dev database moved with the package and the server still finds `data/app.db`, `lexicon/drugs.json`, `db/migrations/` and `frontend/` (Task 6).
4. Genuine optional-dependency guards (`except ImportError` around `faster_whisper`, `onnxruntime`) were NOT collapsed (Task 2 grep).

---

### Task 1: Move the package and rewrite path references

**Files:**
- Move: `backend/` to `doctor_dictation/` (everything inside it, including untracked `data/app.db`)
- Create: `doctor_dictation/__init__.py`
- Modify (by sweep): every file under `doctor_dictation/`, `tests/`, plus `.gitignore`, `.env.example`, `README.md`

- [ ] **Step 1: Baseline.** Stop any running server that was started from `backend.main` (it holds `data/app.db` open). Then:

```bash
.venv/bin/python -m pytest tests/ -q | tail -2
```

Expected: `140 passed`. Write the number down as N0.

- [ ] **Step 2: Move it.** Stale bytecode goes first so nothing imports the old name from a cache.

```bash
find backend -name __pycache__ -type d -prune -exec rm -rf {} +
mv backend doctor_dictation
ls doctor_dictation doctor_dictation/data
```

Expected: `config.py correction.py data db determinism.py lexicon main.py pdf.py requirements-onnx.txt requirements-stt.txt requirements.txt safety.py secret_loader.py stt_onnx.py` (`secrets.json` and `stt_models/` appear only if you have them) and `app.db` under `data`. The dev database now lives at `doctor_dictation/data/app.db`.

- [ ] **Step 3: Make it a package.** Create `doctor_dictation/__init__.py` with exactly this one line:

```python
"""Doctor Dictation: voice-to-prescription service (FastAPI app, rules engine, PDF)."""
```

- [ ] **Step 4: Sweep the path and import references.** The pattern touches only `backend.`, `backend/`, `backend\` and `from backend import`; plain words such as "backend offline" in `frontend/app.js` are untouched (`frontend/` is not in the sweep).

```bash
grep -rlI --exclude='*.db' --exclude-dir=__pycache__ "backend" doctor_dictation tests .gitignore .env.example README.md | wc -l
grep -rlI --exclude='*.db' --exclude-dir=__pycache__ "backend" doctor_dictation tests .gitignore .env.example README.md \
  | xargs perl -pi -e 's/\bfrom backend import\b/from doctor_dictation import/g; s/\bbackend([\/\\.])/doctor_dictation$1/g'
perl -pi -e 's/"backend"/"doctor_dictation"/g' tests/test_db.py
```

The first command counts the files that mention `backend`; expect about 21 (on the original tree: 10 package files, 8 test files, `.gitignore`, `.env.example`, `README.md`; more if B0 tests mention it). The file list is piped, not stored in a shell variable, because zsh does not split an unquoted variable into words.

- [ ] **Step 5: Check what is left.**

```bash
grep -rnI --exclude='*.db' --exclude-dir=__pycache__ "backend" doctor_dictation tests .gitignore .env.example README.md | cut -c1-110
```

Expected exactly these leftovers, all plain English and not paths:

```
doctor_dictation/main.py:1:"""Doctor dictation backend: local faster-whisper STT + DeepSeek structuring."""
doctor_dictation/requirements.txt:1:# Doctor Dictation Demo — backend (base, works on Python 3.15)
doctor_dictation/requirements-onnx.txt:10:# QNN GPU backend runs fp16 with NO quantization; HTP/NPU needs QDQ export
doctor_dictation/db/__init__.py:20:# (``doctor_dictation/db``) and its parent (``backend``) explicitly so both paths match
README.md:112:- LLM: ... Without any key, backend uses rule fallback ...
```

Fix the `db/__init__.py` one, which names a directory that no longer exists. In `doctor_dictation/db/__init__.py` replace

```
# (``doctor_dictation/db``) and its parent (``backend``) explicitly so both paths match
```

with

```
# (``doctor_dictation/db``) and its parent (``doctor_dictation``) explicitly so both paths match
```

- [ ] **Step 6: Review the `test_db.py` change.** `tests/test_db.py` now expects `repo_root / "doctor_dictation" / "db" / "__init__.py"` and `repo_root / "doctor_dictation" / "data" / "app.db"`:

```bash
grep -n "doctor_dictation" tests/test_db.py
```

Expected: the import `from doctor_dictation import db as dbmod` (line 15), the `from doctor_dictation.main import app` inside the fixture (line 31), the docstring lines 40-43, the two path asserts at lines 49 and 59, and the comment at line 54 and 57. No assertion text changed except those two physical paths.

- [ ] **Step 7: Leave uncommitted.** The suite is red until Task 2 (the old `try` branches import bare `determinism`, `db`, and so on, which no longer resolve). Do not run it yet.

---

### Task 2: One import style, no `sys.path` hacks

**Files:**
- Modify: `doctor_dictation/main.py` (import block at the top; `onnx_stt_status`), `doctor_dictation/config.py` (import block)

**Interfaces:**
- Produces: `from doctor_dictation.<module> import ...` in `main.py` and `config.py`. Module names and public names are unchanged.

- [ ] **Step 1: Collapse the dual-import blocks with a script.** It rewrites only a `try:` block whose `except ImportError:` branch contains `from backend` (now `from doctor_dictation`, after Task 1), keeps that branch, de-indents it, and drops `# type: ignore`. Blocks without it, such as the `faster_whisper` guard, are returned unchanged. Because Task 1 already renamed `backend.` to `doctor_dictation.`, the script's marker is the new name.

```bash
python3 - doctor_dictation/main.py doctor_dictation/config.py <<'PY'
import re
import sys
from pathlib import Path

pat = re.compile(
    r"^(?P<ind>[ ]*)try:\n(?:(?P=ind)    .*\n|\n)+?(?P=ind)except ImportError:[^\n]*\n"
    r"(?P<body>(?:(?P=ind)    .*\n|\n(?=(?P=ind)    ))+)",
    re.M,
)


def fix(m):
    if "from doctor_dictation" not in m.group("body"):
        return m.group(0)  # a genuine optional-dependency guard: leave it alone
    body = "".join(l[4:] if l.strip() else l for l in m.group("body").splitlines(True))
    return body.replace("  # type: ignore", "")


for name in sys.argv[1:]:
    p = Path(name)
    text, n = pat.subn(fix, p.read_text())
    p.write_text(text)
    print(name, "matched", n)
PY
```

Expected: `doctor_dictation/main.py matched 8` and `doctor_dictation/config.py matched 1`. The eight in `main.py` are six top-of-file import blocks, the nested `stt_onnx` block, and the `faster_whisper` guard, which is matched but returned unchanged.

- [ ] **Step 2: Remove the `sys.path` hacks, the unused `import sys`, and two stale comments.** The two hacks are the top-level `sys.path.insert(...)` line before the first import and the indented one inside `onnx_stt_status`. The asserts stop the script if the file is not what this plan expects.

```bash
python3 - <<'PY'
from pathlib import Path

p = Path("doctor_dictation/main.py")
s = p.read_text()
hack = "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
assert s.count(hack) == 2, s.count(hack)
s = s.replace("        " + hack, "").replace(hack, "")
assert "sys." not in s
s = s.replace("import sys\n", "", 1)
comments = {
    "# Persistence layer (P0-4): stdlib sqlite3. Same dual-import style as above so\n"
    "# the app runs both as a package (doctor_dictation.main) and standalone (main.py).\n":
    "# Persistence layer (P0-4): stdlib sqlite3.\n",
    "# Central settings (P0-2): same dual-import style. Non-secret settings keep the\n":
    "# Central settings (P0-2). Non-secret settings keep the\n",
}
for old, new in comments.items():
    assert s.count(old) == 1, old
    s = s.replace(old, new)
p.write_text(s)
PY
```

- [ ] **Step 3: Check the result.**

```bash
grep -n "sys\.\|^import sys\|dual-import\|type: ignore" doctor_dictation/main.py doctor_dictation/config.py
grep -rn "except ImportError" doctor_dictation tests --include='*.py'
sed -n '/^def onnx_stt_status/,/^def active_stt_engine/p' doctor_dictation/main.py
```

Expected: the first command prints nothing. The second prints exactly two lines, `doctor_dictation/main.py:<n>:    except ImportError:` (the `faster_whisper` guard) and `doctor_dictation/stt_onnx.py:<n>:    except ImportError:`. The third prints:

```python
def onnx_stt_status():
    """(available, detail) for the Snapdragon ONNX engine. Never raises."""
    try:
        from doctor_dictation.stt_onnx import status as _onnx_status
        return _onnx_status()
    except Exception as e:
        return False, f"onnx module error: {e}"


```

- [ ] **Step 4: Read the top of `main.py`.** Lines 1 to about 60 must read: standard-library and third-party imports, then `from doctor_dictation.determinism import (...)`, `from doctor_dictation import db as dbmod`, `from doctor_dictation.correction import (...)`, `from doctor_dictation.safety import screen_unverified`, `from doctor_dictation.pdf import build_sheet_html, render_pdf`, `from doctor_dictation.config import get_settings, secret_presence`, then `load_dotenv()`. Each name list is the one that was in the old `except` branch.

- [ ] **Step 5: Run the suite.** The tests import the same module objects the app uses now (before, `backend.determinism` and the bare `determinism` were two separate copies).

```bash
.venv/bin/python -m pytest tests/ -q | tail -2
```

Expected: `140 passed` (equal to N0). If a test fails with `ModuleNotFoundError: No module named 'backend'`, the Task 1 sweep missed a file: `grep -rn "backend" tests`.

- [ ] **Step 6: Leave uncommitted.**

---

### Task 3: `pyproject.toml`, dependency files, `.gitignore`

**Files:**
- Create: `pyproject.toml`, `doctor_dictation/requirements-pdf.txt`, `doctor_dictation/requirements-dev.txt`
- Modify: `doctor_dictation/requirements-stt.txt`, `.gitignore`

**Interfaces:**
- Produces: project `doctor-dictation` 0.1.0 with extras `stt`, `onnx`, `pdf`, `dev`. The requirements files keep working with `pip install -r`; `pyproject.toml` reads them, so there is one dependency list.

- [ ] **Step 1: Fix a latent bug the extras would expose.** `doctor_dictation/requirements-stt.txt` has the line `"av>=11,<15"` with literal quote characters, which pip rejects (`Invalid requirement: '"av>=11,<15"'`, verified). Replace that one line with:

```
av>=11,<15
```

- [ ] **Step 2: Create the two small extras files.**

`doctor_dictation/requirements-pdf.txt`:

```
# Optional: server-side PDF rendering (doctor_dictation/pdf.py). After installing, run:
#   python -m playwright install chromium
playwright>=1.40
```

`doctor_dictation/requirements-dev.txt`:

```
# Test and development tools (pip install -e ".[dev]").
pytest>=8
```

- [ ] **Step 3: Create `pyproject.toml`** at the repo root. `include` keeps setuptools from treating `frontend/`, `tests/`, `docs/` as packages; `package-data` ships the lexicon, the migrations and the requirements files (`lexicon/` and `db/migrations/` are data directories, not packages).

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "doctor-dictation"
version = "0.1.0"
description = "Voice-to-prescription service: dictation, STT, rules-checked structuring, PDF."
readme = "README.md"
requires-python = ">=3.11"
# Single source of truth stays in the requirements files next to the code.
dynamic = ["dependencies", "optional-dependencies"]

[tool.setuptools.dynamic]
dependencies = { file = ["doctor_dictation/requirements.txt"] }

[tool.setuptools.dynamic.optional-dependencies]
stt = { file = ["doctor_dictation/requirements-stt.txt"] }
onnx = { file = ["doctor_dictation/requirements-onnx.txt"] }
pdf = { file = ["doctor_dictation/requirements-pdf.txt"] }
dev = { file = ["doctor_dictation/requirements-dev.txt"] }

[tool.setuptools.packages.find]
include = ["doctor_dictation*"]

[tool.setuptools.package-data]
doctor_dictation = ["lexicon/*.json", "db/migrations/*.sql", "requirements*.txt"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 4: Ignore build output.** Task 1's sweep already turned the four `backend/` lines in `.gitignore` into `doctor_dictation/secrets.json`, `doctor_dictation/stt_models/`, `doctor_dictation/lexicon/rxnav_cache.json`, `doctor_dictation/data/`. Add these two lines under the `*.egg-info/` line:

```
build/
dist/
```

```bash
grep -n "doctor_dictation\|build/\|dist/" .gitignore
```

Expected: six lines (the four paths and the two new ones).

- [ ] **Step 5: Prove the package data is complete** (builds a wheel into a scratch directory; needs network for setuptools):

```bash
.venv/bin/python -m pip wheel -q --no-deps -w /tmp/dd-wheel . && unzip -l /tmp/dd-wheel/*.whl | grep -c "migrations/.*sql\|lexicon/.*json\|requirements"; rm -rf build /tmp/dd-wheel
```

Expected: `10` (three migrations, `drugs.json`, `seed_extra.json`, five requirements files). Also confirm `unzip -l` shows no `app.db` (the dev database must never ship in a wheel). `pip wheel` leaves a `doctor_dictation.egg-info/` directory in the repo; delete it: `rm -rf doctor_dictation.egg-info`.

- [ ] **Step 6: Leave uncommitted.**

---

### Task 4: Install, and prove it works from outside the repo

**Files:**
- Create: `tests/test_package_install.py`

- [ ] **Step 1: Write the test first.** It runs a fresh interpreter in an empty directory with `-I` (isolated: no cwd, no `PYTHON*` variables on `sys.path`), so only a real installation can answer.

```python
"""The package is importable from outside the repo root (pip install -e .).

Run:  .venv/bin/python -m pytest tests/test_package_install.py -q
"""
import subprocess
import sys
from pathlib import Path

import doctor_dictation

PACKAGE_DIR = Path(doctor_dictation.__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent


def test_package_imports_from_outside_the_repo_root(tmp_path):
    """-I drops the cwd and PYTHON* env vars, so only the installed package can answer."""
    code = (
        "import doctor_dictation, doctor_dictation.main as m;"
        "print(doctor_dictation.__file__);"
        "print(m.app.title)"
    )
    done = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=tmp_path, capture_output=True, text=True, timeout=60,
    )
    assert done.returncode == 0, done.stderr
    printed = done.stdout.splitlines()[0]
    assert Path(printed).resolve() == PACKAGE_DIR / "__init__.py"
    assert (REPO_ROOT / "pyproject.toml").is_file()
```

- [ ] **Step 2: Run it before installing; it must fail.**

```bash
.venv/bin/python -m pytest tests/test_package_install.py -q 2>&1 | grep -E "ModuleNotFoundError|failed|passed"
```

Expected: a line containing `ModuleNotFoundError: No module named 'doctor_dictation'` (raised in the child process) and `1 failed`.

- [ ] **Step 3: Install into `.venv`** (editable; needs network once, to fetch setuptools for the build):

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pip show doctor-dictation | grep -E "^(Name|Version|Editable)"
```

Expected: the install output ends with `Successfully installed doctor-dictation-0.1.0` (other packages may be listed before it), and `pip show` prints `Name: doctor-dictation`, `Version: 0.1.0` and an `Editable project location` line. Editable is the supported mode: `main.py` finds `frontend/` as a sibling of the package (`Path(__file__).resolve().parent.parent / "frontend"`), and `data/` and `secrets.json` live inside the package directory. A non-editable (wheel) install would not find `frontend/`; D0b deals with that.

- [ ] **Step 4: Prove the import from `/tmp`.**

```bash
REPO=$PWD; (cd /tmp && "$REPO/.venv/bin/python" -c "import doctor_dictation; print(doctor_dictation.__file__)")
```

Expected: a path ending in `/doctor_dictation/__init__.py` under the repo.

- [ ] **Step 5: Run the suite.**

```bash
.venv/bin/python -m pytest tests/ -q | tail -2
```

Expected: `141 passed` (N0 + 1). Plain `.venv/bin/pytest -q` from the repo root gives the same count (the `testpaths` setting).

- [ ] **Step 6: Leave uncommitted.**

---

### Task 5: README and `.env.example`

**Files:**
- Modify: `README.md`, `.env.example`

Task 1's sweep already rewrote `backend\requirements.txt`, `backend.main:app`, `backend/pdf.py`, `backend/main.py`, `backend/lexicon/drugs.json`, `backend/stt_onnx.py` in `README.md` and the `backend/secrets.json` and `backend/requirements-onnx.txt` mentions in `.env.example`.

- [ ] **Step 1: Switch the install command to the package install.** In `README.md`, replace

```
.\.venv-arm64\Scripts\python -m pip install -r doctor_dictation\requirements.txt
```

with

```
.\.venv-arm64\Scripts\python -m pip install -e .
# extras: ".[stt]" local faster-whisper, ".[pdf]" PDF render, ".[dev]" tests
```

The `-r doctor_dictation\requirements*.txt` lines inside `requirements-stt.txt` and `requirements-onnx.txt` stay as they are: those files still work with `pip install -r`.

- [ ] **Step 2: Check the run commands.**

```bash
grep -n "uvicorn\|pip install" README.md
grep -n "doctor_dictation" .env.example
```

Expected in `README.md`: `-m pip install -e .`, and both `uvicorn doctor_dictation.main:app --port 8000` lines (the `--reload` one and the `.venv-stt` one). Expected in `.env.example`: lines 3, 5, 8 and 14 mention `doctor_dictation/secrets.json` and line 23 mentions `doctor_dictation/requirements-onnx.txt`.

- [ ] **Step 3: Confirm the secret loader doc agrees.**

```bash
grep -n "secrets.json" doctor_dictation/secret_loader.py
```

Expected: the docstring and the comment both say `doctor_dictation/secrets.json`; the code `Path(__file__).resolve().parent / "secrets.json"` is unchanged and still points inside the package.

- [ ] **Step 4: Leave uncommitted.**

---

### Task 6: Final verification

- [ ] **Step 1: Full suite.**

```bash
.venv/bin/python -m pytest tests/ -q | tail -2
```

Expected: `141 passed` (N0 140 + 1).

- [ ] **Step 2: No stale names, no hacks.**

```bash
grep -rnI --exclude='*.db' --exclude-dir=__pycache__ --exclude-dir=docs --exclude-dir=.venv --exclude-dir='*.egg-info' "backend\.\|backend/\|from backend\|sys\.path" . | grep -v "^./tests/test_db.py:43"
ls -d backend 2>&1
```

Expected: the `grep` prints nothing (the one excluded line is a docstring that mentions `sys.path`). `ls` prints `ls: backend: No such file or directory`.

- [ ] **Step 3: Run the app the new way, from outside the repo.** If port 8001 is busy, pick any free port and use it in all three commands.

```bash
REPO=$PWD; (cd /tmp && "$REPO/.venv/bin/uvicorn" doctor_dictation.main:app --port 8001 > /tmp/dd-uvicorn.log 2>&1 &)
sleep 3
curl -s localhost:8001/api/health | head -c 400; echo
curl -s -o /dev/null -w "%{http_code}\n" localhost:8001/
```

Expected: JSON starting `{"ok":true,"whisper_model":"small.en",` and containing `"onnx_stt":{"available":false,"detail":"onnxruntime not installed (see doctor_dictation/requirements-onnx.txt)"}`, then `200` for the page (proves `frontend/` resolves). If the first line is some other JSON, another server owns that port; stop it or pick another port.

- [ ] **Step 4: Exercise the database and lexicon once, then stop the server.**

```bash
curl -s -w "\n%{http_code}\n" localhost:8001/api/v1/profile
curl -s localhost:8001/api/health | grep -o '"lexicon_entries":[0-9]*'
ls -la doctor_dictation/data/app.db
pkill -f "uvicorn doctor_dictation.main:app --port 8001"; rm -f /tmp/dd-uvicorn.log
```

Expected: the profile JSON `{"doctor_name":"",...}` (or your saved profile) with `200`; `"lexicon_entries":444`; the moved `app.db` listed (the dev database is the file in use). Verified on a scratch copy of the original tree.

- [ ] **Step 5: Report the changed files.** List: the whole `backend/` to `doctor_dictation/` move; edited `doctor_dictation/main.py`, `config.py`, `db/__init__.py`, `secret_loader.py`, `stt_onnx.py`, `pdf.py`, `lexicon/build.py`, `requirements*.txt`; new `doctor_dictation/__init__.py`, `requirements-pdf.txt`, `requirements-dev.txt`, `pyproject.toml`, `tests/test_package_install.py`; edited tests (`test_correction.py`, `test_db.py`, `test_determinism.py`, `test_pdf.py`, `test_profile.py`, `test_safety.py`, `test_secrets.py`, `test_today.py`, plus the B0 test files `test_event_loop.py` and any others the sweep touched); `.gitignore`, `.env.example`, `README.md`. Nothing is committed.

- [ ] **Step 6: Self-review.** Spec coverage: rename and flat layout (Task 1), single imports (Task 2), pyproject with extras (Task 3), editable install and out-of-repo import (Task 4), docs (Task 5). Not done on purpose: no `src/` layout, no module moves into `core/` (B1b), no wheel-mode frontend serving (D0b), no committed lockfile.
