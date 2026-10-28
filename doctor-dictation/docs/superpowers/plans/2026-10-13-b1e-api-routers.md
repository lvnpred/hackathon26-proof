# B1e: API Routers and Thin Main Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split what is left of `doctor_dictation/main.py` into routers under `doctor_dictation/api/`, build the app in `create_app()`, and reduce `main.py` to three lines, with no change to any endpoint.

**Architecture:** One `APIRouter` per concern (`health`, `stt`, `format`, `profile`, `persistence`). `api/app.py::create_app()` builds the FastAPI app (CORS exactly as today, lifespan with `db.init_db`), includes the routers, and mounts the frontend last. Routers read `get_settings()` at request time and call the PDF renderer through the `doctor_dictation.pdf` module (`pdfmod.render_pdf(...)`), so a test patches `doctor_dictation.pdf.render_pdf`.

**Tech Stack:** Python 3.12 (venv at `.venv`), FastAPI, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 3 (package layout). Contracts: `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 2, 3 and 4.1. Plan 7 of 15; prerequisite: B1d applied and the suite green.

**Baseline and count:** Run `.venv/bin/python -m pytest tests/ -q` first and write down the passing count, call it **N0**. This plan **adds 6 tests** (`tests/test_api_app.py`: 4, `tests/test_file_sizes.py`: 2). Expect **N0 + 6** at the end. Existing tests change only in the setup lines listed in Task 2 and Task 3.

## Assumptions about earlier plans

- B1a: package is `doctor_dictation`, no dual `try/except` imports, run command `uvicorn doctor_dictation.main:app`.
- B1b: `doctor_dictation.core.{determinism,correction,safety,fallback}`; `fallback_format` lives in `core/fallback.py`.
- B1c: `doctor_dictation.config.override_settings(monkeypatch, **fields)` exists (contracts 4.1). The STT chain, the local-model pin and `max_audio_bytes` handling live in `providers/stt/`; `make_stt(settings).active_name()` exists.
- B1d: LLM calls go through `providers/llm/` (`make_llm(settings)`); `llm_config`, `_llm_complete` and the `STT_*`/`LLM_*`/`*_API_KEY` module globals are gone from `main.py`, and the tests that exercised them already use `override_settings`.
- What still sits in `main.py` (found with `grep -n "^@app\|^class \|^def \|^async def \|^[A-Z_]* = " doctor_dictation/main.py`): app creation, CORS, `lifespan`, `health`, `transcribe`, `format_transcript`, `correct`, `FormatRequest`, `CorrectRequest`, `SYSTEM_PROMPT` (if B1d left it here), `_validate`/`_ground` (B0b), the profile/patient/encounter/document endpoints with their request models and `_profile_dict`, and the static mount. If any of these already moved to another module, move it from there instead; the destination does not change.
- Line numbers below are for the current `backend/main.py`; they shift after B1a-B1d. Always locate code with `grep -n`.

## Global Constraints

- Every endpoint keeps its path, methods, status codes and JSON. Function bodies move verbatim; only the edits written in the steps are allowed.
- No source file over 500 lines (user rule; enforced by Task 4's test). `persistence.py` comes to about 255 lines, so it is not split.
- No import-time settings: no module under `doctor_dictation/api/` or `main.py` may assign from `get_settings()` at module level.
- **Do not run `git commit` or `git push`** (user rule). Every task ends with "leave uncommitted".
- Tests are offline. `load_dotenv()` loads a real key, so tests use `override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")` or stub `httpx.AsyncClient`, as the existing tests do.

## Review Focus

1. The route table is identical before and after (Task 1 test written first, green before and after every task).
2. A test that patches the PDF renderer still takes effect (Task 2).
3. `main.py` holds no logic and no settings (Task 4).

---

### Task 1: Guard tests first, inventory the tests that touch `main`

**Files:**
- Create: `tests/test_api_app.py`

**Interfaces:**
- Consumes: `doctor_dictation.main.app` (exists), `doctor_dictation.config.override_settings`.
- Produces: 4 guard tests, kept green by every later task.

- [ ] **Step 1: Run the suite and record N0**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass. Write down the count (N0).

- [ ] **Step 2: Inventory the tests that reach into `main`**

Run:

```bash
grep -n "setattr(M\|M\.[a-z_A-Z]*" tests/*.py | grep -v "M\.app"
```

Expected after B1d: hits only for `"render_pdf"` in `tests/test_safety.py` (4 lines, about 164, 182, 198, 224) and `"validate_structured"` in `tests/test_event_loop.py` (1 line). Any other hit (a settings global such as `OPENAI_API_KEY`, `STT_ENGINE`, `MAX_AUDIO_BYTES`, or `M.llm_config`, `M.get_model`, `M.active_stt_engine`, `M.fallback_format`) is a B1b/B1c/B1d gap. Convert settings-global setups by this table, changing only the setup line:

`monkeypatch.setattr(M, "OPENAI_API_KEY", v)` becomes `override_settings(monkeypatch, openai_api_key=v)`; likewise `DEEPSEEK_API_KEY` to `deepseek_api_key`, `LLM_PROVIDER` to `llm_provider`, `LLM_MODEL` to `llm_model`, `STT_ENGINE` to `stt_engine`, `MAX_AUDIO_BYTES` to `max_audio_bytes`.

Add `from doctor_dictation.config import override_settings` to that test file's imports. If a hit touches STT or LLM internals (`get_model`, `_use_small_model`, `WHISPER_MODEL`, `llm_config`, `_llm_complete`), stop and report it to the user: it belongs to B1c/B1d and this plan does not invent a replacement.

- [ ] **Step 3: Write the guard tests** — create `tests/test_api_app.py`:

```python
"""The API surface is unchanged by the router split.

Run:  .venv/bin/python -m pytest tests/test_api_app.py -q
"""
import ast
from pathlib import Path

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings

EXPECTED_ROUTES = {
    ("GET", "/api/health"), ("GET", "/health"),
    ("POST", "/api/transcribe"), ("POST", "/api/format"), ("POST", "/api/v1/correct"),
    ("GET", "/api/v1/profile"), ("PUT", "/api/v1/profile"),
    ("GET", "/api/v1/patients"), ("POST", "/api/v1/patients"),
    ("GET", "/api/v1/encounters"), ("POST", "/api/v1/encounters"),
    ("GET", "/api/v1/encounters/today"),
    ("POST", "/api/v1/documents"), ("GET", "/api/v1/documents/{document_id}"),
}


def _route_table(app):
    return {(m, r.path) for r in app.routes if isinstance(r, APIRoute) for m in r.methods}


def test_route_table_is_unchanged():
    assert _route_table(M.app) == EXPECTED_ROUTES


def test_create_app_builds_independent_apps_with_static_mount_last():
    from doctor_dictation.api.app import create_app

    a, b = create_app(), create_app()
    assert a is not b
    assert _route_table(a) == EXPECTED_ROUTES
    assert a.routes[-1].name == "frontend"  # mounted last so it cannot shadow /api


def test_health_reads_settings_on_every_request(monkeypatch):
    client = TestClient(M.app)
    override_settings(monkeypatch, openai_api_key="sk-call-time-secret")
    on = client.get("/api/health")
    assert on.json()["openai_configured"] is True
    assert "sk-call-time-secret" not in on.text
    override_settings(monkeypatch, openai_api_key="")
    assert client.get("/api/health").json()["openai_configured"] is False


def test_no_module_level_settings_in_api_or_main():
    root = Path(M.__file__).parent
    offenders = []
    for path in [root / "main.py", *sorted((root / "api").glob("*.py"))]:
        for node in ast.parse(path.read_text()).body:
            value = getattr(node, "value", None)
            if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)) and value is not None:
                for sub in ast.walk(value):
                    if isinstance(sub, ast.Call):
                        fn = getattr(sub.func, "id", getattr(sub.func, "attr", ""))
                        if fn == "get_settings":
                            offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
```

- [ ] **Step 4: Run**

Run: `.venv/bin/python -m pytest tests/test_api_app.py -q`
Expected today: `test_create_app_builds_independent_apps_with_static_mount_last` FAILS (`ModuleNotFoundError: doctor_dictation.api`). `test_no_module_level_settings_in_api_or_main` passes only if B1d removed `_settings = get_settings()`; if it fails now, it names the line that Task 4 deletes with the rest of `main.py`. The other two pass. (A scratch check against the pre-B1 `backend/main.py` flagged exactly `main.py:94`, `_settings = get_settings()`, confirming the AST walk works.)

- [ ] **Step 5: Leave uncommitted.**

---

### Task 2: `profile` and `persistence` routers

**Files:**
- Create: `doctor_dictation/api/__init__.py`, `doctor_dictation/api/profile.py`, `doctor_dictation/api/persistence.py`
- Modify: `doctor_dictation/main.py` (delete the moved code, include the two routers), `tests/test_safety.py` (4 setup lines)

**Interfaces:**
- Consumes: `doctor_dictation.db` (`get_conn`, `get_profile`, `save_profile`, `list_patients`, `create_patient`, `get_patient`, `list_encounters`, `create_encounter`, `get_encounter`, `local_day_bounds_utc`, `list_documents_between`, `get_document`, `upsert_patient`, `update_document`, `save_document`, `log_audit`, `pdf_dir`, `_utcnow`); `core.determinism.validate_structured`; `core.safety.screen_unverified`; `core.correction.preserve_untouched_rx_status`; `doctor_dictation.pdf` module.
- Produces: `profile.router`, `profile.profile_dict(row)`, `persistence.router`.

- [ ] **Step 1: Create the package marker**

Create `doctor_dictation/api/__init__.py` containing exactly:

```python
"""HTTP layer: one router per concern, assembled by api.app.create_app()."""
```

- [ ] **Step 2: Create `doctor_dictation/api/profile.py`** by extracting the profile block from `main.py` (`ProfileBody`, `_profile_dict`, both routes) under a new header; `_profile_dict` is renamed `profile_dict` because `persistence` imports it:

```bash
F=doctor_dictation/main.py; Q=doctor_dictation/api/profile.py
cat > $Q <<'EOF'
"""Clinic profile endpoints (the six fields printed on the sheet)."""
from fastapi import APIRouter
from pydantic import BaseModel

from doctor_dictation import db as dbmod

router = APIRouter()


EOF
awk '/^class ProfileBody/{p=1} /^@app.get\("\/api\/v1\/patients"\)/{p=0} p' $F | sed -e 's/^@app\./@router./' >> $Q
perl -pi -e 's/\b_profile_dict\b/profile_dict/g' $Q
perl -0pi -e 's/\n+\z/\n/' $Q
grep -n "^@router\|^def \|^class " $Q
```

Expected (verified on the pre-B1 file, 51 lines): `ProfileBody` (line 10), `profile_dict` (19), `@router.get("/api/v1/profile")` `get_profile` (27), `@router.put("/api/v1/profile")` `put_profile` (36).

- [ ] **Step 3: Build `persistence.py` mechanically from `main.py`**

Start the file with this header (the imports are the only new text):

```bash
cat > doctor_dictation/api/persistence.py <<'EOF'
"""Patients, encounters, today list and documents (verify gate + fail-soft PDF)."""
import json
import sqlite3

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doctor_dictation import db as dbmod
from doctor_dictation import pdf as pdfmod  # looked up at call time: tests patch doctor_dictation.pdf.render_pdf
from doctor_dictation.api.profile import profile_dict
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.safety import screen_unverified

router = APIRouter()


EOF
```

Append the body: everything from `class PatientCreate` up to (not including) `# Serve frontend`, with the profile block dropped and three mechanical renames. Run exactly (macOS `sed` has no `\b`, so `perl` does the renames):

```bash
F=doctor_dictation/main.py; P=doctor_dictation/api/persistence.py
awk '/^class PatientCreate/{p=1} /^# Serve frontend/{p=0} p' $F | sed -e 's/^@app\./@router./' >> $P
sed -i '' '/^class ProfileBody/,/^@router.get("\/api\/v1\/patients")/{/^@router.get("\/api\/v1\/patients")/!d;}' $P
perl -pi -e 's/\b_profile_dict\(/profile_dict(/g; s/\bbuild_sheet_html\(/pdfmod.build_sheet_html(/; s/\brender_pdf\(/pdfmod.render_pdf(/' $P
```

Verify the result (a scratch run of this pipeline on the pre-B1 file gave 234 body lines and exactly these hits):

```bash
wc -l $P
grep -n "^@router\|^class \|pdfmod\|profile_dict" $P
```

Expected: about 255 lines; routers for patients (GET, POST), encounters (GET, POST), `/api/v1/encounters/today`, documents (POST), `/api/v1/documents/{document_id}` (GET); classes `PatientCreate`, `EncounterCreate`, `DocumentCreate`; exactly one `pdfmod.build_sheet_html(`, one `pdfmod.render_pdf(`, one `profile_dict(`; no `ProfileBody`, no `@app.`. If B1d changed any name used in the body (for example a different `dbmod` helper), the import header above is where to adapt it; the body stays verbatim.

- [ ] **Step 4: Remove the moved code from `main.py` and include the routers**

In `doctor_dictation/main.py` delete the profile block (`ProfileBody`, `_profile_dict`, both profile routes) and everything from `class PatientCreate` to the line before `# Serve frontend`. Directly after the `app = FastAPI(...)`/CORS lines add:

```python
from doctor_dictation.api import persistence, profile  # noqa: E402

app.include_router(profile.router)
app.include_router(persistence.router)
```

The `# Serve frontend` mount must stay last in the file, after these includes. Remove now-unused imports (`sqlite3`, `screen_unverified`, `preserve_untouched_rx_status`, `build_sheet_html`, `render_pdf`) only if nothing else in `main.py` uses them: `grep -n "sqlite3\|screen_unverified\|render_pdf" doctor_dictation/main.py`.

- [ ] **Step 5: Change the four PDF patch targets** — `tests/test_safety.py`. In each of the four tests (`test_finalize_records_rendered_pdf_path`, `test_finalize_fails_soft_when_renderer_unavailable`, `test_finalize_fails_soft_on_non_runtimeerror_renderer_failure`, `test_finalize_passes_current_profile_to_sheet`) replace only the setup line; assertions, fake functions and the other lines stay byte-identical:

| Old line | New line |
|---|---|
| `monkeypatch.setattr(M, "render_pdf", fake_render)` | `monkeypatch.setattr("doctor_dictation.pdf.render_pdf", fake_render)` |
| `monkeypatch.setattr(M, "render_pdf", boom)` (two tests) | `monkeypatch.setattr("doctor_dictation.pdf.render_pdf", boom)` |
| `monkeypatch.setattr(M, "render_pdf", capture)` | `monkeypatch.setattr("doctor_dictation.pdf.render_pdf", capture)` |

Locate them with `grep -n 'setattr(M, "render_pdf"' tests/test_safety.py` (four hits before, none after).

- [ ] **Step 6: Run the suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all green (N0 plus the Task 1 tests that already pass). If a renderer test fails with a real Chromium attempt, the patch target did not take effect: check that `persistence.py` calls `pdfmod.render_pdf(` and not a name imported with `from ... import`.

- [ ] **Step 7: Leave uncommitted.**

---

### Task 3: `health`, `stt` and `format` routers

**Files:**
- Create: `doctor_dictation/api/health.py`, `doctor_dictation/api/stt.py`, `doctor_dictation/api/format.py`
- Modify: `doctor_dictation/main.py`, `tests/test_event_loop.py` (1 setup line)

**Interfaces:**
- Consumes: whatever B1c/B1d left in `main.py` for these routes. Contract names: `make_stt(settings)`, `make_llm(settings)`, `get_settings()`, `secret_presence`, `core.determinism.{validate_structured, ground_rx, ...}`, `core.fallback.fallback_format`, `core.correction.{extract_correction, merge_form, preserve_untouched_rx_status, strip_grounding_markers}`.
- Produces: `health.router`, `stt.router`, `format.router`, and `format._validate` / `format._ground` (module-level functions that look up `validate_structured` / `ground_rx` in the module's own globals at call time).

- [ ] **Step 1: `health.py`** — header and decorator, body verbatim:

```python
"""Health endpoints. Settings are read per request, never at import."""
from fastapi import APIRouter

router = APIRouter()
```

Then copy the whole `health()` function (find it with `grep -n "def health" doctor_dictation/main.py`), keeping both decorators but renaming them to `@router.get("/api/health")` and `@router.get("/health")`. Copy the imports that function uses (`get_settings`, `secret_presence`, `lexicon_version`, `lexicon_size`, the STT helpers B1c left) into the header under the module docstring. The function must read settings as `settings = get_settings()` on its first line; replace any remaining main-level global with the matching `settings.<field>` (`OPENAI_API_KEY` is `settings.openai_api_key`, `STT_ENGINE` is `settings.stt_engine`, `WHISPER_MODEL` is `settings.whisper_model`). The response keys and values are unchanged.

- [ ] **Step 2: `stt.py`** — same recipe for `POST /api/transcribe`:

```python
"""Speech-to-text endpoint. Providers come from the factory at request time."""
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

router = APIRouter()
```

Copy `transcribe` (and any helper only it uses, such as the 413 cap check from B0b) with `@app.post("/api/transcribe")` renamed `@router.post("/api/transcribe")`. Add the imports it needs. It must call `get_settings()` inside the function (the cap is `get_settings().max_audio_bytes`), not read a module constant. Every `JSONResponse` status and body stays as is.

- [ ] **Step 3: `format.py`** — `FormatRequest`, `CorrectRequest`, `SYSTEM_PROMPT` (if it is still in `main.py`; otherwise import it from where B1d put it), `_validate`, `_ground`, `format_transcript`, `correct`:

```python
"""Structuring endpoints: /api/format (extract, ground, repair) and /api/v1/correct."""
import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doctor_dictation.config import get_settings
from doctor_dictation.core.determinism import ground_rx, validate_structured

router = APIRouter()
```

Add to that header the remaining names the two routes use (`FORMAT_LLM_CAP`, `build_repair_message`, `cache_get`, `cache_put`, `lexicon_version`, `loop_should_continue`, `normalize_transcript`, `open_issues`, `transcript_sha` from `core.determinism`; `fallback_format` from `core.fallback`; `extract_correction`, `merge_form`, `preserve_untouched_rx_status`, `strip_grounding_markers` from `core.correction`; `make_llm` from `doctor_dictation.providers.llm.factory`). Rename the decorators to `@router.post("/api/format")` and `@router.post("/api/v1/correct")`. `_validate` and `_ground` keep the B0b bodies (`await asyncio.to_thread(validate_structured, ...)` / `ground_rx`), so a test can patch `doctor_dictation.api.format.validate_structured`.

- [ ] **Step 4: Include the routers and drop the moved code from `main.py`**

Extend the include block from Task 2:

```python
from doctor_dictation.api import format as format_api  # noqa: E402
from doctor_dictation.api import health, persistence, profile, stt  # noqa: E402

app.include_router(health.router)
app.include_router(stt.router)
app.include_router(format_api.router)
app.include_router(profile.router)
app.include_router(persistence.router)
```

Delete the moved functions and models from `main.py`. Order matters only for the static mount, which stays last.

- [ ] **Step 5: Change the one validation patch target** — `tests/test_event_loop.py`, in `test_validation_does_not_block_the_event_loop`:

| Old line | New line |
|---|---|
| `monkeypatch.setattr(M, "validate_structured", slow)` | `monkeypatch.setattr("doctor_dictation.api.format.validate_structured", slow)` |

`real = M.validate_structured` two lines above becomes `real = validate_structured` with `from doctor_dictation.core.determinism import validate_structured` added to the imports (its only role is to name the real function; the `slow` wrapper and every assertion are untouched). Also convert any `setattr(M, "<settings global>", ...)` lines still left in this file by the Task 1 table.

- [ ] **Step 6: Run the suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass, including `test_health_reads_settings_on_every_request`, `test_event_loop.py`, `test_upload_cap.py`, `test_correction.py`, `test_determinism.py`. `grep -n "^@app" doctor_dictation/main.py` now prints nothing.

- [ ] **Step 7: Leave uncommitted.**

---

### Task 4: `create_app()`, thin `main.py`, size guard

**Files:**
- Create: `doctor_dictation/api/app.py`, `tests/test_file_sizes.py`
- Modify: `doctor_dictation/main.py` (replace entirely)

**Interfaces:**
- Consumes: the five routers; `doctor_dictation.db.init_db`.
- Produces: `create_app() -> FastAPI`; `doctor_dictation.main.app`.

- [ ] **Step 1: Write the failing size test** — create `tests/test_file_sizes.py`:

```python
"""User rule: no source file over 500 lines. Also: the uvicorn entry point is a FastAPI app.

Run:  .venv/bin/python -m pytest tests/test_file_sizes.py -q
"""
from pathlib import Path

from fastapi import FastAPI

import doctor_dictation
import doctor_dictation.main as main

LIMIT = 500


def test_no_python_file_over_500_lines():
    root = Path(doctor_dictation.__file__).parent
    sizes = {
        str(p.relative_to(root)): len(p.read_text().splitlines())
        for p in root.rglob("*.py")
    }
    too_big = {name: n for name, n in sizes.items() if n > LIMIT}
    assert too_big == {}, f"files over {LIMIT} lines: {too_big}"


def test_main_app_is_a_fastapi_app():
    assert isinstance(main.app, FastAPI)
```

Run: `.venv/bin/python -m pytest tests/test_file_sizes.py -q`
Expected now: `test_main_app_is_a_fastapi_app` passes; the size test passes only if no other file is over 500 lines. Before this task `main.py` is still large if Task 3 left helpers behind; if the size test names a file other than `main.py`, report it (it is outside this plan's scope) rather than editing it.

- [ ] **Step 2: Create `doctor_dictation/api/app.py`**

```python
"""Application factory: middleware, lifespan, routers, then the static frontend."""
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from doctor_dictation import db as dbmod
from doctor_dictation.api import format as format_api
from doctor_dictation.api import health, persistence, profile, stt

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Create the DB directory and apply pending migrations; idempotent.
    dbmod.init_db()
    yield


def create_app() -> FastAPI:
    # .env must be loaded before the first get_settings() call (settings are cached).
    load_dotenv()
    app = FastAPI(title="Doctor Dictation Demo", lifespan=lifespan)
    # Exactly today's CORS. D0a replaces this with an allow-list.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, stt, format_api, profile, persistence):
        app.include_router(module.router)
    # Serve the frontend from the same process; mounted last so it never shadows /api.
    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    return app
```

`FRONTEND_DIR` is a path constant, not a setting. It resolves to `<repo>/frontend` because `app.py` sits two levels below the repo root (`doctor_dictation/api/app.py`).

- [ ] **Step 3: Replace `doctor_dictation/main.py`** with exactly:

```python
"""uvicorn entry point: `uvicorn doctor_dictation.main:app`."""
from doctor_dictation.api.app import create_app

app = create_app()
```

- [ ] **Step 4: Run the guards**

Run: `.venv/bin/python -m pytest tests/test_api_app.py tests/test_file_sizes.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Run the whole suite and the leftover-reference greps**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N0 + 6` passed.

Run: `grep -rn "doctor_dictation.main import\|setattr(M, " tests/ doctor_dictation/ | grep -v "setattr(M, \"__"`
Expected: no output (tests use `M.app` only; no test patches a `main` attribute any more).

Run: `wc -l doctor_dictation/main.py doctor_dictation/api/*.py`
Expected: `main.py` 4 lines; every file under 500 (`persistence.py` about 255, `format.py` about 230 with the prompt).

- [ ] **Step 6: Leave uncommitted.**

---

### Task 5: Final verification against the running app

**Files:** none changed.

- [ ] **Step 1: Full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `N0 + 6 passed` (N0 recorded in Task 1).

- [ ] **Step 2: Run the app and exercise each router once**

```bash
DB_PATH=$(mktemp -d)/check.db .venv/bin/python -m uvicorn doctor_dictation.main:app --port 8001 &
sleep 3
curl -s localhost:8001/api/health | head -c 200; echo
curl -s -X PUT localhost:8001/api/v1/profile -H 'content-type: application/json' -d '{"doctor_name":"A. Rao"}'; echo
curl -s -X POST localhost:8001/api/format -H 'content-type: application/json' -d '{"transcript":""}'; echo
curl -s -X POST localhost:8001/api/v1/documents -H 'content-type: application/json' -d '{"structured":{"patientName":"Test","opNo":"OP-1","rx":[]},"confirmed_rows":[]}'; echo
curl -s localhost:8001/api/v1/encounters/today | head -c 200; echo
curl -s -o /dev/null -w "%{http_code} %{content_type}\n" localhost:8001/
kill %1
```

Expected: health JSON with `"ok":true`; the profile PUT returns the six fields with `doctor_name` `A. Rao`; the empty format returns `{"error":"Empty transcript"}`; the document POST returns `patient_id`, `encounter_id`, `document_id` (200 even without Chromium, the PDF step is fail-soft); today lists that document; `/` returns `200 text/html` (static mount works and does not shadow `/api`).

- [ ] **Step 3: Report.** Run `git status --short` and list the changed files (no commit): 7 new `doctor_dictation/api/*.py`, `main.py` rewritten, two new test files, `tests/test_safety.py` (4 setup lines), `tests/test_event_loop.py` (patch target plus one import), and any setup lines converted in Task 1 step 2. State N0 and the final count, anything sent back to B1c/B1d, and that the browser flow (record, format, save, today) was not exercised beyond the curl calls.
