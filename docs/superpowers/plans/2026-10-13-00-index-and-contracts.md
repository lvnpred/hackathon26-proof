# Implementation Plans: Index and Shared Contracts

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md`. Every plan below implements part of it. When a plan and the spec disagree, the spec's section 12 and this file win; report the disagreement, do not silently pick.

This file is the single source of truth for **names, paths and interfaces that cross plan boundaries**. Plans are written in parallel, so each plan relies on this file, not on another plan's text.

## 1. Order and prerequisites

Plans run strictly in this order. Each assumes every earlier plan is applied and the full suite is green.

| # | File (under `docs/superpowers/plans/`) | Delivers | Needs |
|---|---|---|---|
| 1 | `2026-10-13-b0a-correction-fixes.md` | Blank-name correction fix, correction prompt rules (written) | baseline 122 tests |
| 2 | `2026-10-13-b0b-event-loop-upload-cap-ui.md` | Event-loop offload, upload cap, UI warnings (written) | B0a; ends at 140 tests |
| 3 | `2026-10-13-b1a-package-rename.md` | `backend/` becomes the installable package `doctor_dictation` | B0b |
| 4 | `2026-10-13-b1b-core-split.md` | `core/` subpackage, `fallback_format` extracted | B1a |
| 5a | `2026-10-13-b1c-stt-providers.md` | STT interface, providers, factory, stub, settings override helper (additive; main.py untouched) | B1b |
| 5b | `2026-10-13-b1c2-stt-route-rewire.md` | `/api/transcribe` and `/api/health` use the factory; moved code deleted; STT tests migrated | B1c |
| 6 | `2026-10-13-b1d-llm-providers.md` | LLM interface (tools, images), providers, factory, stub | B1c |
| 7 | `2026-10-13-b1e-api-routers.md` | Routers, `create_app()`, thin `main.py`, size-limit test | B1d |
| 8 | `2026-10-13-acc1-benchmark-harness.md` | WER, drug-name recall, cost harness | B1e |
| 9 | `2026-10-13-acc2-hints-and-silence-trim.md` | Vocabulary hints, silence trimming (flag-gated) | ACC1 |
| 10 | `2026-10-13-acc3-phonetic-candidates.md` | Sound-alike candidates in the repair message | ACC2 |
| 11 | `2026-10-13-b2a-pdf-renderer-and-layout.md` | `pdf/` package: layout vocabulary, sheet builder, pooled renderer | B1e |
| 12a | `2026-10-13-b2b1-settings-and-storage.md` | Template settings, migration 004, db helpers | B2a |
| 12b | `2026-10-13-b2b2-images-and-builder.md` | Image cleaning, vision prompt and layout builder | B2b1, B1d |
| 12c | `2026-10-13-b2b3-service-rules.md` | Rate limit, draft expiry, edit, accept, discard | B2b2 |
| 12d | `2026-10-13-b2b4-routes-and-save.md` | Template routes, save path uses the active layout | B2b3 |
| 13 | `2026-10-13-b2c-template-ui.md` | Letterhead panel in the page | B2b |
| 13a | `2026-10-13-b2d-template-deactivate.md` | Stop using an accepted letterhead (route and button) | B2c |
| C1 | `2026-10-13-c1-medasr-provider.md` | **Optional.** MedASR local STT provider, benchmark candidate only; starts with a licence-reading gate and needs real clips | ACC1, B1c |
| E | `2026-10-13-e-elevenlabs-scribe-provider.md` | **Optional, awaiting user approval.** ElevenLabs Scribe v2 Medical as an opt-in cloud STT provider; fixes cloud-failure fallback | B1c; benchmark before any default change |
| 14 | `2026-10-13-d0a-auth-and-hardening.md` | Basic login, CORS lock, demo banner | B2d (C1 not required) |
| 15 | `2026-10-13-d0b-container-and-deploy.md` | Docker image, proxy, load test, runbook | D0a |

Plans 8-10 and 11-13 may be executed in either order relative to each other, but each group stays internally ordered.

## 2. Conventions every plan follows

1. **Header** exactly as the writing-plans skill requires (Goal, Architecture, Tech Stack, Spec, Global Constraints, Review Focus), then tasks with checkbox steps.
2. **Size:** the plan file must stay **under 500 lines** (user rule). Aim for 300-450 lines and 4-8 tasks. If the scope will not fit, report that instead of cramming.
3. **No commits.** The user's rule: never run `git commit` or `git push` unless asked. Replace "commit" steps with "leave uncommitted" and finish with the changed-file list.
4. **Test-first with real code:** every code step shows the actual code; every test step shows the actual test; every run step shows the exact command and the expected result. No "TBD", "similar to Task N", or "add appropriate handling".
5. **Tests are offline.** `main.py` calls `load_dotenv()`, so a developer's real `.env` key is present during tests. Tests must stub or clear providers and must never call OpenAI or any network.
6. **Test command:** `.venv/bin/python -m pytest tests/ -q`. Each plan states "Adds N tests" and the baseline rule "run the suite first, note the count, expect count + N at the end".
7. **Verify, do not assume.** Quote line numbers and snippets only after reading the current file. For code that does not exist yet, cite the symbol name from this file's contracts, and tell the executor to locate it with `grep -n`. Check library behaviour (Pillow, Playwright, httpx, ffmpeg) with a small script in the scratchpad before writing steps that depend on it. Never modify the real repo while writing a plan; copying the repo into the scratchpad to try something is fine.
8. **Assumptions block:** a plan that depends on something from a not-yet-written plan lists it under "Assumptions about earlier plans" at the top, naming the contract item.
9. **Behaviour preservation:** HTTP status codes and JSON shapes of existing endpoints do not change unless the plan says so. The existing tests are the guard; when a test must change because a patch target moved, change only its setup line, never its assertion.
10. **File rule:** no source file over 500 lines after the plan is applied.

## 3. Layout after each stage

**After B1a** (rename only): `backend/` is now `doctor_dictation/` at the repo root, flat layout; modules keep their names (`main.py`, `determinism.py`, `correction.py`, `safety.py`, `pdf.py`, `config.py`, `secret_loader.py`, `stt_onnx.py`, `db/`, `lexicon/`, `data/`). `frontend/`, `tests/`, `docs/` stay. `pyproject.toml` exists. The run command is `uvicorn doctor_dictation.main:app`. No dual `try/except` imports remain.

**After B1b:** `doctor_dictation/core/{__init__,determinism,correction,safety,fallback}.py` and `doctor_dictation/core/lexicon/{drugs.json,seed_extra.json,build.py}`. `core` imports nothing from `providers`, `db`, `api`, `pdf`, nor `fastapi`, `httpx`, `sqlite3` (enforced by `tests/test_core_purity.py`).

**After B1e (target):**

```
doctor_dictation/
  __init__.py
  main.py                  # app = create_app()   (uvicorn entry point)
  config.py  secret_loader.py
  core/                    # pure: determinism, correction, safety, fallback, lexicon/
  providers/
    stt/   base.py openai.py local.py onnx.py browser.py stub.py factory.py
    llm/   base.py openai_compat.py stub.py factory.py
  db/                      # sqlite store + migrations/
  pdf.py                   # replaced by the pdf/ package in B2a
  api/   app.py health.py stt.py format.py persistence.py profile.py
  data/                    # runtime, gitignored
```

Later plans add `doctor_dictation/{bench,audio,templates,pdf}/`, `api/{templates,security}.py`, `core/{hints,candidates}.py`.

## 4. Contracts

### 4.1 Settings (`doctor_dictation/config.py`)

`Settings` stays a frozen dataclass built by `build_settings()` and cached by `get_settings()`. New or changed fields (env name in brackets):

| Field | Env | Default | Plan |
|---|---|---|---|
| `max_audio_bytes: int` | `MAX_AUDIO_BYTES` | 10 MiB | B0b (exists) |
| `llm_vision_model: str` | `LLM_VISION_MODEL` | `""` (blank = reuse `llm_model`) | B1d |
| `stt_chain: tuple[str, ...]` | `STT_CHAIN` (comma list) | derived from `stt_engine` (see 4.2) | B1c |
| `allow_stub_providers: bool` | `ALLOW_STUB_PROVIDERS` | `False` | B1c |
| `stt_use_hints: bool` | `STT_USE_HINTS` | `False` | ACC2 |
| `stt_hint_limit: int` | `STT_HINT_LIMIT` | 70 | ACC2 |
| `stt_trim_silence: bool` | `STT_TRIM_SILENCE` | `False` | ACC2 |
| `template_uploads_per_day: int` | `TEMPLATE_UPLOADS_PER_DAY` | 10 | B2b |
| `template_draft_ttl_hours: int` | `TEMPLATE_DRAFT_TTL_HOURS` | 24 | B2b |
| `template_max_image_bytes: int` | `TEMPLATE_MAX_IMAGE_BYTES` | 8 MiB | B2b |
| `template_max_pixels: int` | `TEMPLATE_MAX_PIXELS` | 40,000,000 | B2b |
| `medasr_model: str` | `MEDASR_MODEL` | `google/medasr` | C1 |
| `demo_mode: bool` | `DEMO_MODE` | `False` | D0a |
| `demo_username: str`, `demo_password: str` | `DEMO_USERNAME`, `DEMO_PASSWORD` | `""` | D0a |
| `allowed_origins: tuple[str, ...]` | `ALLOWED_ORIGINS` (comma list) | `()` = same-origin only | D0a |

Test helper (created in B1c, `doctor_dictation/config.py`):

```python
def override_settings(monkeypatch, **fields) -> Settings:
    """Replace the cached settings with dataclasses.replace(get_settings(), **fields)."""
```

Routes and factories read `get_settings()` at **call time**, never at import time, so the helper takes effect. Keys never appear in logs or responses.

### 4.2 STT (`doctor_dictation/providers/stt/`)

```python
@dataclass(frozen=True)
class Transcript:
    text: str
    engine: str                      # e.g. "openai-whisper-api", "local:small.en"
    language: str = ""
    duration: float | None = None
    extra: dict = field(default_factory=dict)   # e.g. {"decode": {...}} for local

class SttError(Exception): ...        # provider failed; str(e) is safe to show (<= 300 chars)
class SttUnavailable(SttError): ...   # not installed / not configured; the chain moves on

class SttProvider(Protocol):
    name: str                                        # "openai" | "faster-whisper" | "onnx" | "browser" | "stub" | "medasr" (C1, optional)
    def available(self) -> bool: ...
    async def transcribe(self, audio: bytes, filename: str, hints: Sequence[str] = ()) -> Transcript: ...

def make_stt(settings: Settings) -> SttProvider      # a FallbackStt over the chain
```

- **Chain derivation** when `STT_CHAIN` is empty: `stt_engine` `auto` or `openai` gives `("openai", "faster-whisper")`; `faster-whisper` gives `("faster-whisper",)`; `onnx` gives `("onnx",)`. `browser` is never in the chain; "no provider answered" is what makes the route return the browser-fallback errors.
- **`/api/transcribe` responses are unchanged** (status codes 400, 413, 501, 502, 503, 500 and every JSON shape, including `fallback: "browser"` and `hint`). The B1c plan must read the current route and reproduce each branch; the existing tests are the guard. The cloud-failure side effect (pin the local model to `small.en` and reset the cached model) is preserved inside `local.py`.
- `FallbackStt.active_name() -> str` replaces `active_stt_engine()` and returns the same strings (`"openai-whisper-api"`, `"faster-whisper"`, `"onnx"`, `"browser-webspeech"`). `/api/health` output is byte-for-byte compatible.
- **Hints:** `hints` reaches every provider. OpenAI sends `prompt` (comma-joined). Local appends to `initial_prompt`. The route passes `()` until ACC2.
- **Stub provider** (`stub.py`, name `"stub"`): returns `Transcript(text=<STUB_TRANSCRIPT env or "stub transcript">, engine="stub")` after an optional `STUB_DELAY_MS` sleep. Usable only when `allow_stub_providers` is true; otherwise the factory raises `ValueError`.

### 4.3 LLM (`doctor_dictation/providers/llm/`)

```python
@dataclass(frozen=True)
class ToolCall:
    id: str; name: str; arguments: dict

@dataclass(frozen=True)
class Completion:
    text: str
    json: dict | None
    tool_calls: tuple[ToolCall, ...] = ()
    finish: str = ""

class LlmProvider(Protocol):
    name: str                       # "openai" | "deepseek" | "stub"
    model: str
    async def complete_json(self, messages: list[dict]) -> tuple[dict | None, str]: ...
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> Completion: ...

def make_llm(settings: Settings, *, vision: bool = False) -> LlmProvider | None
```

- `complete_json` keeps today's contract exactly: `(parsed_dict_or_None, error_string)`, the full deterministic payload, and the parameter-drop retries (`temperature`, `top_p`, `seed`) up to four attempts. `core.correction.extract_correction`'s `complete(messages)` closure keeps working unchanged.
- `make_llm` returns `None` when no key is configured (today's `llm_config() is None`). `vision=True` uses `llm_vision_model`, falling back to `llm_model` when blank.
- `messages` may contain OpenAI-style content parts, e.g. `{"role":"user","content":[{"type":"text","text":"..."},{"type":"image_url","image_url":{"url":"data:image/jpeg;base64,..."}}]}`. Providers pass them through untouched.
- HTTP goes through `httpx.AsyncClient` looked up at call time (`import httpx` then `httpx.AsyncClient(...)`), because existing tests monkeypatch `httpx.AsyncClient`.
- **Stub provider** (name `"stub"`): `complete_json` returns the dict parsed from the `STUB_LLM_JSON` env var (default `{}`), after the same optional delay; selected with `LLM_PROVIDER=stub`; same `allow_stub_providers` rule.

### 4.4 Storage (`doctor_dictation/db/`)

The sqlite module stays the store. New migrations are numbered after the current `003_clinic_profile.sql`. B2b adds `004_templates.sql`:

```sql
CREATE TABLE IF NOT EXISTS templates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic      TEXT NOT NULL DEFAULT 'default',
    layout_json TEXT NOT NULL,
    logo_path   TEXT,
    status      TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','archived')),
    created_at  TEXT NOT NULL,
    accepted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_templates_status ON templates(clinic, status);
```

The default DB path moves with the package to `doctor_dictation/data/app.db`; `DB_PATH` overrides it.

### 4.5 PDF (`doctor_dictation/pdf/`, built in B2a)

```python
class PdfUnavailable(RuntimeError): ...

class PdfRenderer(Protocol):
    def render(self, html: str, out_path: Path) -> Path: ...     # raises PdfUnavailable

def render_prescription(structured: dict, meta: dict, out_path: Path,
                        layout: "Layout | None" = None) -> Path
```

- `meta` keeps today's keys (`date`, `opNo`, `profile`) and gains `patientName` for the continuation line and `logo`: a `data:image/jpeg;base64,...` (or png) URI for the header `logo` block. B2b builds it from the stored logo crop with `service.logo_data_uri(path)`.
- The default renderer is a **pooled** headless Chromium: one browser owned by one worker thread, requests queued, started lazily, closed at app shutdown. `render` on a missing browser raises `PdfUnavailable` and the save path stays fail-soft (`pdf_path = None`, browser print fallback).
- Layout vocabulary module `pdf/layout.py`: `Layout`, `LayoutError`, `validate_layout(raw: dict) -> Layout`, `DEFAULT_LAYOUT`. The JSON shape is the one in spec section 7A.2: `header`/`footer` lists of `text` (`field` or `text`, `role` in `title|subtitle|normal|small`, `align`, optional hex `color`), `logo` (`crop` as four fractions, `align`), `rule` (`color`, `thickness` in `thin|medium`), and `body` (`top`, `bottom` fractions with `0 <= top < bottom <= 1`), plus `profile` with the six clinic fields. Unknown block types, out-of-range numbers, non-hex colours and text over 200 characters raise `LayoutError`.
- Page 1 prints header, body and footer. **Pages 2 onward** print one small identifier line (patient name, OP number, date, page number) and continue the body with standard margins.
- `pdf.py` from B1a is replaced; `render_pdf(html, out_path)` and `build_sheet_html(structured, meta)` remain importable from `doctor_dictation.pdf` as thin wrappers until B2b switches the save path to `render_prescription`.

### 4.6 Templates (B2b), routes under `/api/v1/templates`

| Method and path | Behaviour |
|---|---|
| `POST /api/v1/templates` (multipart field `image`) | Clean the image, call the vision LLM, validate the layout, store a `draft`. 201 with `{id, status, layout, profile}`. 400 bad image, 413 too large, 429 daily limit, 502 LLM failed or invalid layout (nothing stored), 503 no vision-capable LLM configured. |
| `GET /api/v1/templates/{id}/preview.pdf` | Page 1 of the draft or active layout filled with a sample prescription. |
| `PUT /api/v1/templates/{id}` (JSON `{profile: {six fields}, lines: [{section: "header"|"footer", index: int, text: str}]}`) | Edit profile fields and literal text lines of a draft. `index` is the block's position inside `layout[section]`; only literal `text` blocks can be edited. Re-validated; returns the same shape as POST. |
| `POST /api/v1/templates/{id}/accept` | Make it the clinic's `active` template (previous active becomes `archived`), save the profile through the existing profile store, delete the original upload. |
| `DELETE /api/v1/templates/{id}` | Discard a draft. |
| `GET /api/v1/templates/active` | The active layout and profile, or 404 when none. |
| `POST /api/v1/templates/deactivate` (plan B2d) | Archive the active template so saves use the built-in layout again. 200 `{"deactivated": true}`, or `{"deactivated": false}` when none was active. Audit row `template_deactivate`. |

Drafts older than `template_draft_ttl_hours` are deleted lazily (on any templates request and at startup). Every upload, accept and discard writes an `audit_log` row. With no active template, saves use the built-in layout and the clinic profile (today's behaviour).

### 4.7 Accuracy modules

- `core/hints.py`: `build_hints(doctor_top: Sequence[str] = (), limit: int = 70) -> list[str]` (doctor's most-used medicines first, then common lexicon names, no duplicates, capped).
- `db`: `top_medicines(conn, limit: int = 30) -> list[str]` (names from finalized documents' `structured_json`, most frequent first).
- `audio/trim.py`: `trim_silence(audio: bytes, filename: str) -> bytes` using `ffmpeg` `silenceremove` with about 300 ms padding; **fail-soft**: if `ffmpeg` is missing or fails, return the input unchanged.
- `core/candidates.py`: `phonetic_key(word: str) -> str` and `suggest_candidates(name: str, k: int = 3) -> list[str]` over the lexicon names, pure and deterministic.
- `bench/metrics.py`: `wer(reference: str, hypothesis: str) -> float`, `drug_recall(reference: str, hypothesis: str, drug_names: Iterable[str]) -> tuple[int, int]` (found, expected). `bench/run.py` is a CLI: `python -m doctor_dictation.bench.run --manifest PATH --providers openai,stub`. The manifest is JSON: `[{"audio": "path.webm", "reference": "text"}]`.

### 4.8 Security and deployment (D0a, D0b)

- `api/security.py`: `BasicAuthMiddleware`, active only when both `demo_username` and `demo_password` are set; constant-time comparison; `/health` and `/api/health` stay open for the container healthcheck; failures return 401 with `WWW-Authenticate: Basic realm="Doctor Dictation"`. The authenticated username becomes the `actor` of `audit_log` rows written by the template and document routes.
- CORS: no CORS middleware unless `allowed_origins` is non-empty, then exactly those origins.
- `/api/health` gains `demo: bool` (from `demo_mode`); the page shows a persistent "Demo, fake patients only" banner when true.
- Deployment: Python 3.12 slim image, non-root user, Chromium and fonts installed (include Indian-language coverage), `WEB_CONCURRENCY` workers, volume mounted at `/data` with `DB_PATH=/data/app.db`, a reverse proxy providing HTTPS and a request-body limit, a container healthcheck on `/health`, and stub providers enabled only for the load test.
- Load test: `tests/load/run_load.py` (not collected by pytest), concurrent simulated dictations including saves that render a PDF on a custom template; exit gate is zero 5xx, a stated p95 latency, stable memory.

## 5. What each plan must leave behind

Every plan ends with a verification task that runs the full suite, states the expected count, runs the app (`uvicorn doctor_dictation.main:app --port 8001` from B1a onward) and exercises the changed behaviour once by hand, and lists the changed files. Anything the plan could not verify is stated in its final report, not hidden.

## 6. Known follow-ups (not blocking)

- ~~ACC1's `--hints` stopgap~~ Done (ACC review fix): `--hints` now sends `core.hints.build_hints()` and `--trim` applies the app's silence trim, so the benchmark measures what the app does.
- ACC2 trims to Ogg/Opus while the OpenAI provider labels uploads `audio/webm`. **Checked live on 2026-10-13:** whisper-1 accepts the trimmed `.ogg` (and the `prompt` hint) and transcribes it correctly (a spoken test clip shrank from 332 KB to 21 KB). That is format acceptance only, not accuracy; the ACC1 benchmark on real dictations still decides whether to turn `STT_TRIM_SILENCE` / `STT_USE_HINTS` on.
- D0a defers a Content-Security-Policy; try it in report-only mode after D0b.
- B1a installs the package in editable mode only (the frontend is found beside the package); D0b's image must keep the repo layout.
