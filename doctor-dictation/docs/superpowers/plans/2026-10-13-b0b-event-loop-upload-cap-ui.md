# B0b: Event Loop, Upload Cap and UI Warnings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep validation off the event loop, cap audio uploads, show correction warnings in the UI, and verify all of B0 against the running app.

**Architecture:** Two thread-offload helpers (`_validate`, `_ground`) in `backend/main.py` replace direct CPU-bound calls inside async routes; one size check in `/api/transcribe` backed by a new setting; one line of JS shows the `warnings` field added by B0a.

**Tech Stack:** Python 3.12 (venv at `.venv`), FastAPI, pytest, httpx, vanilla JS. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` (§2 problems 3 and 5 in part, §4 rows "Validation off the loop" and "Upload cap"). Plan 2 of 6. **Prerequisite: plan B0a is applied** (`docs/superpowers/plans/2026-10-13-b0a-correction-fixes.md`, 135 tests passing). Task numbers continue from B0a (Tasks 4-7) because Task 4 edits text that B0a Task 3 produced and Task 6 reads the `warnings` field it added. **After this plan:** 140 tests.

## Global Constraints

- "Every fix: write the failing test, watch it fail, then fix. No bundled refactoring."
- "No file over 500 lines." `backend/main.py` is already 1,058 lines (B1 splits it): add only what each task shows.
- `backend/correction.py` is "pure and deterministic: no network, no time, no randomness, stdlib only".
- Run tests with `.venv/bin/python -m pytest tests/ -q`.
- **Do not run `git commit` or `git push`** (user rule; the repo also has no commits yet). Leave every change in the working tree and list changed files at the end. This overrides the usual "commit" step.
- Tests must never call OpenAI. Endpoint tests clear the keys or stub `httpx.AsyncClient` using the existing helpers `_client` and `_stub_llm` in `tests/test_correction.py` (a developer's real `.env` key is loaded by `load_dotenv()`).

## Review Focus

1. Concurrent requests must not be delayed by one request's validation. Task 4 test.
2. Audio of exactly the cap passes; one byte over returns 413; a garbage `MAX_AUDIO_BYTES` falls back to the default. Task 5 tests.
3. The page must still work when the server's response has no `warnings` field. Task 6 (the code guards it; the browser check covers the field being present and empty).

---

### Task 4: Validation and grounding off the event loop

**Files:**
- Modify: `backend/main.py` (top imports line 2; helpers before `llm_config` at line 428; call sites at lines 657, 689, 708, 721, 767)
- Create: `tests/test_event_loop.py`

**Interfaces:**
- Consumes: the `correct()` text produced by Task 3 (the `validate_structured(` call at the end of `correct`).
- Produces: `async _validate(data, transcript)` and `async _ground(rows, transcript)` in `main.py`; both look up `validate_structured` / `ground_rx` at call time so tests can monkeypatch them.

- [ ] **Step 1: Write the failing test** — create `tests/test_event_loop.py`:

```python
"""Validation runs in a worker thread, so a slow call cannot stall other requests.

Run:  .venv/bin/python -m pytest tests/test_event_loop.py -q
"""
import asyncio
import time
import uuid

import httpx

import backend.main as M


def test_validation_does_not_block_the_event_loop(monkeypatch):
    monkeypatch.setattr(M, "DEEPSEEK_API_KEY", "")  # rules path: no LLM, no network
    monkeypatch.setattr(M, "OPENAI_API_KEY", "")
    real = M.validate_structured

    def slow(data, transcript):
        time.sleep(0.4)  # stands in for heavy CPU; a blocked loop stalls for this long
        return real(data, transcript)

    monkeypatch.setattr(M, "validate_structured", slow)

    async def run():
        gaps, flag = [], {"stop": False}

        async def ticker():
            last = time.perf_counter()
            while not flag["stop"]:
                await asyncio.sleep(0.01)
                now = time.perf_counter()
                gaps.append(now - last)
                last = now

        task = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)  # let the ticker start ticking first
        transport = httpx.ASGITransport(app=M.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r1 = await c.post("/api/v1/correct",
                              json={"transcript": "", "current_form": {"rx": []}})
            r2 = await c.post("/api/format",
                              json={"transcript": "loop check " + uuid.uuid4().hex[:8]})
        await asyncio.sleep(0.05)  # let the ticker record the gap after the requests
        flag["stop"] = True
        await task
        return r1.status_code, r2.status_code, max(gaps)

    s1, s2, worst = asyncio.run(run())
    assert (s1, s2) == (200, 200)
    assert worst < 0.2, f"event loop stalled for {worst:.2f}s while validating"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_event_loop.py -q`
Expected: FAIL (`event loop stalled for 0.8s` or similar; measured about 0.64s with a 0.3s sleep before this change).

- [ ] **Step 3: Implement**

In `backend/main.py`, replace the first imports

```python
import json
import os
import sqlite3
```

with

```python
import asyncio
import json
import os
import sqlite3
```

Insert these helpers immediately before `def llm_config():`:

```python
async def _validate(data, transcript):
    """validate_structured in a worker thread: ~10 ms of CPU must not stall the loop."""
    return await asyncio.to_thread(validate_structured, data, transcript)


async def _ground(rows, transcript):
    """ground_rx in a worker thread, for the same reason."""
    return await asyncio.to_thread(ground_rx, rows, transcript)


```

Then change the five call sites (the multi-line context makes each match unique):

1. In `format_transcript`, the rules-only branch:
   - old: `        structured, warnings = validate_structured(fallback_format(normalized), normalized)\n        engine = (f"fallback-rules+lexicon`
   - new: `        structured, warnings = await _validate(fallback_format(normalized), normalized)\n        engine = (f"fallback-rules+lexicon`
2. The loop: `_, issues = ground_rx(draft.get("rx") or [], normalized)` becomes `_, issues = await _ground(draft.get("rx") or [], normalized)`.
3. `structured, warnings = validate_structured(best[1], normalized)` becomes `structured, warnings = await _validate(best[1], normalized)`.
4. The error fallback:
   - old: `    structured, warnings = validate_structured(fallback_format(normalized), normalized)\n    engine = f"fallback-after-error`
   - new: `    structured, warnings = await _validate(fallback_format(normalized), normalized)\n    engine = f"fallback-after-error`
5. In `correct()`:
   - old: `    structured, _warnings = validate_structured(\n        strip_grounding_markers(merge_form(current, patch)), normalized)`
   - new: `    structured, _warnings = await _validate(\n        strip_grounding_markers(merge_form(current, patch)), normalized)`

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (136).

- [ ] **Step 5: Leave uncommitted.**

---

### Task 5: Audio upload cap

**Files:**
- Modify: `backend/config.py` (add field after line 33; kwarg in `build_settings`), `backend/main.py` (constant after `STT_ENGINE = _settings.stt_engine`; `/api/transcribe` lines 549-551), `.env.example`
- Create: `tests/test_upload_cap.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings.max_audio_bytes: int` (env `MAX_AUDIO_BYTES`, default 10 MiB) and module global `MAX_AUDIO_BYTES` in `main.py`, read at call time.

- [ ] **Step 1: Write the failing tests** — create `tests/test_upload_cap.py`:

```python
"""POST /api/transcribe rejects audio over the configured size with HTTP 413.

Run:  .venv/bin/python -m pytest tests/test_upload_cap.py -q
"""
from fastapi.testclient import TestClient

import backend.main as M
from backend.config import build_settings


def _post(size):
    return TestClient(M.app).post(
        "/api/transcribe", files={"audio": ("t.webm", b"\x00" * size, "audio/webm")})


def test_audio_over_the_cap_is_rejected_with_413(monkeypatch):
    monkeypatch.setattr(M, "MAX_AUDIO_BYTES", 1024)
    r = _post(1025)
    assert r.status_code == 413
    assert "larger than" in r.json()["error"]


def test_audio_exactly_at_the_cap_is_not_rejected(monkeypatch):  # Review Focus #5
    monkeypatch.setattr(M, "MAX_AUDIO_BYTES", 1024)
    monkeypatch.setattr(M, "STT_ENGINE", "onnx")  # unconfigured: fails fast, no real STT
    assert _post(1024).status_code != 413


def test_default_cap_is_ten_mebibytes(monkeypatch):
    monkeypatch.delenv("MAX_AUDIO_BYTES", raising=False)
    assert build_settings().max_audio_bytes == 10 * 1024 * 1024


def test_cap_reads_the_env_and_ignores_garbage(monkeypatch):
    monkeypatch.setenv("MAX_AUDIO_BYTES", "2048")
    assert build_settings().max_audio_bytes == 2048
    monkeypatch.setenv("MAX_AUDIO_BYTES", "not-a-number")
    assert build_settings().max_audio_bytes == 10 * 1024 * 1024
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_upload_cap.py -q`
Expected: FAIL (`AttributeError: ... has no attribute 'MAX_AUDIO_BYTES'`).

- [ ] **Step 3: Implement**

`backend/config.py`: in the `Settings` dataclass, after `stt_engine: str` add

```python

    # --- uploads (non-secret) ---
    max_audio_bytes: int
```

and in `build_settings()`, after the `stt_engine=...` line add

```python
        max_audio_bytes=_int_env("MAX_AUDIO_BYTES", 10 * 1024 * 1024),
```

`backend/main.py`: after the line `STT_ENGINE = _settings.stt_engine` add

```python
MAX_AUDIO_BYTES = _settings.max_audio_bytes
```

and in `transcribe()` replace

```python
    raw = await audio.read()
    if not raw:
```

with

```python
    raw = await audio.read(MAX_AUDIO_BYTES + 1)
    if len(raw) > MAX_AUDIO_BYTES:
        return JSONResponse(status_code=413, content={
            "error": f"Audio is larger than the {MAX_AUDIO_BYTES // (1024 * 1024)} MB "
                     "limit. Record a shorter dictation."})
    if not raw:
```

`.env.example`: append these two lines at the end:

```
# Largest audio upload /api/transcribe accepts, in bytes (default 10 MiB). Over this -> HTTP 413.
# MAX_AUDIO_BYTES=10485760
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (140).

- [ ] **Step 5: Leave uncommitted.** Note for plan D0: Starlette buffers a multipart upload before the handler runs, so this check stops oversized audio reaching speech-to-text but does not stop the upload itself. The reverse proxy must also set a request-body limit.

---

### Task 6: Show correction warnings in the UI

**Files:**
- Modify: `frontend/app.js:502-504` (`applyCorrection` status line), `frontend/index.html:141` (script version)

**Interfaces:**
- Consumes: `warnings: string[]` in the `/api/v1/correct` response (Task 3). The code must also work when the field is missing.
- Produces: the status line ends with `⚠ <warning text>` when warnings exist.

- [ ] **Step 1: Implement** — in `frontend/app.js`, replace

```js
    setStatus("Correction merged via " + (j.engine || "engine") + ". " +
      (open ? open + " medicine" + (open > 1 ? "s" : "") + " need" + (open > 1 ? "" : "s") + " a check." : "All medicines verified ✓.") +
      " Review, then Save & Print.");
```

with

```js
    setStatus("Correction merged via " + (j.engine || "engine") + ". " +
      (open ? open + " medicine" + (open > 1 ? "s" : "") + " need" + (open > 1 ? "" : "s") + " a check." : "All medicines verified ✓.") +
      " Review, then Save & Print." +
      (j.warnings && j.warnings.length ? " ⚠ " + j.warnings.join(" ") : ""));
```

In `frontend/index.html` change `<script src="app.js?v=8"></script>` to `<script src="app.js?v=9"></script>` so browsers do not serve the old script.

- [ ] **Step 2: Verify in the browser** (with the dev server running on port 8001). With the Playwright browser tools, open `http://127.0.0.1:8001`, run this in the page, and take a screenshot of the status line:

```js
async () => {
  state.structured = {patientName:"", ageSex:"", opNo:"", diagnosis:[], complaints:[], investigations:[], rx:[], advice:[], review:""};
  window.fetch = async () => ({ ok: true, status: 200, json: async () => ({
    structured: state.structured, engine: "stub",
    warnings: ["Could not tell which medicine this correction was for, so it was not applied (duration: 7 days). Name the medicine and try again."] }) });
  await applyCorrection("duration is 7 days");
  return statusEl.textContent;
}
```

Expected: the returned text ends with `⚠ Could not tell which medicine ...`, and the screenshot shows it readable on the page (not clipped). Run it again with `warnings: []` and confirm no `⚠` appears.

- [ ] **Step 3: Leave uncommitted.**

---

### Task 7: Final verification against the running app

**Files:** none changed.

- [ ] **Step 1: Full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: `140 passed`.

- [ ] **Step 2: Live reproduction** (dev server on 8001 reloads on `.py` changes; this makes one real OpenAI call). Run:

```bash
curl -s -m 90 -X POST http://127.0.0.1:8001/api/v1/correct -H 'Content-Type: application/json' -d '{
 "transcript":"Strength is 5 ml for the Ascoril and the duration is 7 days. Patient name Rahul Sharma.",
 "current_form":{"patientName":"","ageSex":"","opNo":"","diagnosis":[],"complaints":[],"investigations":[],"rx":[{"form":"Syr.","name":"Ascoril","strength":"","dose":"1-0-1","timing":"","duration":"","instructions":"","status":"unknown-medicine","lexicon_match":""}],"advice":[],"review":""}}' \
 | .venv/bin/python -m json.tool | head -40
```

Expected: exactly **one** `rx` row, named `Ascoril`, with `strength` `5 ml` and `duration` `7 days`, `patientName` `Rahul Sharma`, and a `"warnings"` key. (Before this plan the same request returned a second row with an empty name.)

- [ ] **Step 3: Check the age/sex format** (LLM-dependent, report only). Repeat the call with the transcript `Patient is Priya Nair, 32 year old female.` and an empty form. Expected: `ageSex` like `32 / F`. If it still returns `32/Female`, record that in the report. Do not change code in this plan; it becomes a follow-up.

- [ ] **Step 4: Report** the list of changed files (`backend/correction.py`, `backend/main.py`, `backend/config.py`, `.env.example`, `frontend/app.js`, `frontend/index.html`, `tests/test_correction.py`, `tests/test_event_loop.py`, `tests/test_upload_cap.py`), the test count, and the live results. Do not commit.
