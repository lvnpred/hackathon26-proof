# B1c2: STT Route Rewire Implementation Plan (part 2 of 2 of B1c)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/api/transcribe` and `/api/health` use `make_stt(get_settings())`, delete the STT code that moved to `doctor_dictation/providers/stt/`, and migrate the existing STT tests, with the same HTTP behaviour as today.

**Architecture:** Two pure helpers in `factory.py` (`failure_response`, `success_body`) turn the chain result into today's JSON; `main.py` shrinks to a few lines per route.

**Tech Stack:** Python 3.12 (`.venv`), FastAPI, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 3. Contracts: `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 4.1, 4.2, 5. **Prerequisite:** `2026-10-13-b1c-stt-providers.md` is applied (N tests green).

**Adds 4 tests.** Run the suite first, note the count N, expect N + 4 at the end.

## Global Constraints and Decisions

- Status codes and JSON of `/api/transcribe` and `/api/health` do not change. **No `git commit`/`git push`.** Tests never touch the network. No file over 500 lines. B0b's 413 check and `Empty audio upload` 400 stay untouched.
- Deliberate differences, unreachable normally: an unknown `STT_ENGINE` acts like `auto` in the route (health already did); health no longer says `"onnx"` under `auto` (the route never used it); a bad `STT_CHAIN` or ungated stub gives 500 `STT misconfigured: ...` and health `"misconfigured"`; model load runs in `asyncio.to_thread`; stack traces are no longer printed (one `STT provider X failed: ...` line is).
- **Review Focus:** (1) every old route branch keeps its status and JSON (the migrated tests plus `test_failure_bodies_match_the_old_route`); (2) the route passes `()` as hints until ACC2; (3) health's `stt_decode` is unchanged.

---

### Task 1: `failure_response`, `success_body`, ONNX provider test

**Files:** Modify `providers/stt/factory.py`; Append to `tests/test_stt_factory.py` and `tests/test_stt_providers.py`

- [ ] **Step 1: Failing tests.** Add `SttModelLoadError, SttNotImplemented` to the `base` import and `failure_response, success_body` to the `factory` import of `tests/test_stt_factory.py`; append:

```python
def test_failure_bodies_match_the_old_route():
    def fail(chain, *pairs):
        return failure_response(SttChainError(list(pairs)), chain)

    auto = ("openai", "faster-whisper")
    s, b = fail(auto, ("openai", SttError("down")), ("faster-whisper", SttUnavailable("x")))
    assert (s, b) == (502, {"error": "Cloud STT failed and no local STT available: down",
                            "fallback": "browser"})
    s, b = fail(auto, ("openai", SttError("down")), ("faster-whisper", SttModelLoadError("load boom")))
    assert (s, b) == (500, {"error": "load boom"})  # no fallback key, as before
    s, b = fail(auto, ("openai", SttError("down")), ("faster-whisper", SttError("Server STT failed: x")))
    assert (s, b) == (500, {"error": "Server STT failed: x", "fallback": "browser"})
    s, b = fail(("onnx",), ("onnx", SttNotImplemented("ONNX decode loop not implemented yet")))
    assert (s, b["fallback"]) == (501, "browser") and "decode loop" in b["error"]
    s, b = fail(("onnx",), ("onnx", SttUnavailable("model dir missing")))
    assert (s, b["error"]) == (503, "ONNX STT not configured: model dir missing")
    assert b["hint"].startswith("See backend/requirements-onnx.txt")
    s, b = fail(("faster-whisper",), ("faster-whisper", SttUnavailable("x")))
    assert s == 503 and b["error"].startswith("STT_ENGINE=faster-whisper but") and "hint" in b
    s, b = fail(auto, ("openai", SttUnavailable("k")), ("faster-whisper", SttUnavailable("x")))
    assert s == 503 and b["error"].startswith("No server STT installed") and b["fallback"] == "browser"
    cloud = success_body(Transcript(text="fever", engine="openai-whisper-api"))
    assert list(cloud) == ["transcript", "engine", "transcript_sha256"]
    loc = success_body(Transcript(text="fever", engine="local:small.en", language="en",
                                  duration=1.0, extra={"decode": {"beam_size": 5}}))
    assert list(loc) == ["transcript", "language", "duration", "engine", "transcript_sha256", "decode"]
```

For `tests/test_stt_providers.py`, add `from doctor_dictation.providers.stt import onnx as O`, `from doctor_dictation.providers.stt.onnx import OnnxStt` and `SttNotImplemented` to the imports and append:

```python
def test_onnx_unavailable_then_not_implemented(monkeypatch):
    monkeypatch.setattr(O, "status", lambda: (False, "model dir missing"))
    with pytest.raises(SttUnavailable, match="model dir missing"):
        _run(OnnxStt().transcribe(b"a", "d.webm"))
    monkeypatch.setattr(O, "status", lambda: (True, "ready"))
    with pytest.raises(SttNotImplemented, match="decode loop not implemented"):
        _run(OnnxStt().transcribe(b"a", "d.webm"))
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_stt_factory.py tests/test_stt_providers.py -q`. Expect `ImportError: cannot import name 'failure_response'`.
- [ ] **Step 3: Implement.** In `factory.py` add `from doctor_dictation.core.determinism import normalize_transcript, transcript_sha` and import `SttModelLoadError, SttNotImplemented` from `base`; append these two functions. The three 503 bodies are the old route's: compare each string with the live text before deleting it in Task 2 (`grep -n "No server STT installed\|Web Speech\|ONNX STT not configured" doctor_dictation/main.py`); the live text wins.

```python
def success_body(t: Transcript) -> dict:
    """The 200 body, with the key set each engine always returned."""
    body: dict = {"transcript": t.text}
    if t.language or t.duration is not None:
        body.update(language=t.language, duration=t.duration)
    body["engine"] = t.engine
    body["transcript_sha256"] = transcript_sha(normalize_transcript(t.text))
    body.update(t.extra)
    return body


def failure_response(err: SttChainError, chain: Sequence[str]) -> tuple[int, dict]:
    """(status, JSON) exactly as the old if-chain in /api/transcribe returned."""
    for _, e in err.failures:
        if isinstance(e, SttNotImplemented):
            return 501, {"error": str(e), "fallback": "browser"}
    real = [(n, e) for n, e in err.failures if not isinstance(e, SttUnavailable)]
    local = [e for n, e in real if n != "openai"]
    if local:  # a local engine really failed: never loop back to the cloud
        body = {"error": str(local[-1])[:500]}
        if not isinstance(local[-1], SttModelLoadError):
            body["fallback"] = "browser"
        return 500, body
    if real:  # only the cloud failed and nothing else could answer
        return 502, {"error": f"Cloud STT failed and no local STT available: {real[0][1]}",
                     "fallback": "browser"}
    if tuple(chain) == ("onnx",):
        return 503, {"error": f"ONNX STT not configured: {err.failures[0][1]}",
                     "fallback": "browser",
                     "hint": "See backend/requirements-onnx.txt (ARM64 py3.11 venv + QNN SDK + model export)."}
    if tuple(chain) == ("faster-whisper",):
        return 503, {"error": "STT_ENGINE=faster-whisper but faster-whisper is not installed here.",
                     "fallback": "browser",
                     "hint": "Run the server from .venv-stt (Python 3.11/3.12 x64) or set STT_ENGINE=auto."}
    return 503, {
        "error": "No server STT installed — run the server from .venv-stt (faster-whisper needs Python 3.11/3.12 x64).",
        "fallback": "browser",
        "hint": "Chrome/Edge: the page will auto-retry with free on-device Web Speech recognition — just allow mic and speak again. Or set OPENAI_API_KEY for cloud Whisper.",
    }
```

- [ ] **Step 4: Run** the same command. Expect all pass (the two new tests included).

---

### Task 2: Rewire `main.py`, migrate the existing tests

**Files:** Modify `doctor_dictation/main.py`, `tests/test_determinism.py`, `tests/test_upload_cap.py`, `.env.example`; delete `doctor_dictation/stt_onnx.py`; Create `tests/test_transcribe_route.py`

- [ ] **Step 1: Failing route tests.** Create `tests/test_transcribe_route.py`:

```python
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt import local as L

AUDIO = {"audio": ("t.webm", b"\x00\x01", "audio/webm")}


def _cfg(mp, **kw):
    base = dict(stt_engine="auto", stt_chain=(), openai_api_key="", allow_stub_providers=False)
    return override_settings(mp, **{**base, **kw})


def test_stub_chain_answers_and_is_refused_without_the_flag(monkeypatch):
    _cfg(monkeypatch, stt_chain=("stub",), allow_stub_providers=True)
    monkeypatch.setenv("STUB_TRANSCRIPT", "fever and cough")
    r = TestClient(M.app).post("/api/transcribe", files=AUDIO)
    assert r.status_code == 200, r.text
    assert (r.json()["transcript"], r.json()["engine"]) == ("fever and cough", "stub")
    assert len(r.json()["transcript_sha256"]) == 64
    _cfg(monkeypatch, stt_chain=("stub",))
    r = TestClient(M.app).post("/api/transcribe", files=AUDIO)
    assert r.status_code == 500 and r.json()["fallback"] == "browser"
    assert r.json()["error"].startswith("STT misconfigured: ") and "ALLOW_STUB_PROVIDERS" in r.json()["error"]


def test_health_stt_fields_keep_their_shape(monkeypatch):
    _cfg(monkeypatch, stt_engine="faster-whisper")
    monkeypatch.setattr(L, "faster_whisper_available", lambda: False)
    h = TestClient(M.app).get("/api/health").json()
    assert h["stt_engine_requested"] == "faster-whisper"
    assert h["stt_engine_active"] == h["stt_engine"] == "unavailable:faster-whisper"
    assert h["stt_decode"] == {k: v for k, v in L.STT_DECODE.items() if k != "initial_prompt"}
    assert h["stt_decode"]["beam_size"] == 5 and h["stt_decode"]["vad_filter"] is True
    monkeypatch.setattr(L, "faster_whisper_available", lambda: True)
    h = TestClient(M.app).get("/api/health").json()
    assert h["stt_engine"] == f"local:{h['whisper_model']}"
```

Run `.venv/bin/python -m pytest tests/test_transcribe_route.py -q`. Expect 2 failures (the old route answers 503 for the stub chain; health has no `unavailable:` name).

- [ ] **Step 2: Delete the moved code** (find each with `grep -n`): in `main.py`, globals `WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `STT_ENGINE`, `_model`, `_model_lock` (keep `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MAX_AUDIO_BYTES`: the LLM code and the size check use them); `STT_DECODE` and its comment; functions `faster_whisper_available`, `onnx_stt_status`, `active_stt_engine`, `_use_small_model`, `_get_lock`, `get_model`, `transcribe_via_openai`. Then `rm doctor_dictation/stt_onnx.py` and `sed -i '' 's#stt_onnx.py#providers/stt/onnx.py#' doctor_dictation/requirements-onnx.txt`. Add these imports and drop any that became unused (`grep -n "tempfile\|sys\.\|Path(" doctor_dictation/main.py`):

```python
from doctor_dictation.providers.stt.base import SttChainError
from doctor_dictation.providers.stt.factory import failure_response, make_stt, success_body
from doctor_dictation.providers.stt.local import STT_DECODE, whisper_model_name
from doctor_dictation.providers.stt.onnx import status as onnx_stt_status
```

- [ ] **Step 3: `/api/health`.** Replace `active = active_stt_engine()` with the block below. Use `whisper_model_name()` where `WHISPER_MODEL` was (the `stt` map and the `whisper_model` key), `get_settings().stt_engine` for `STT_ENGINE`, and `active` for the second `active_stt_engine()` call. `onnx_stt_status()` and `STT_DECODE` keep their names through the new imports.

```python
    try:
        active = make_stt(get_settings()).active_name()
    except ValueError:  # bad STT_CHAIN, or stub without ALLOW_STUB_PROVIDERS
        active = "misconfigured"
```

- [ ] **Step 4: `/api/transcribe`.** Keep everything through the `Empty audio upload` check. Delete from the comment `# 0) Explicit ONNX engine` to the end of the function, plus its now-unused `import asyncio` / `import traceback`. Put this after the empty check:

```python
    try:
        stt = make_stt(get_settings())
    except ValueError as e:
        return JSONResponse(status_code=500, content={
            "error": f"STT misconfigured: {e}", "fallback": "browser"})
    try:
        transcript = await stt.transcribe(raw, audio.filename or "dictation.webm", ())
    except SttChainError as e:
        status, content = failure_response(e, stt.chain_names)
        return JSONResponse(status_code=status, content=content)
    return success_body(transcript)
```

- [ ] **Step 5: Migrate the existing tests, setup lines only.** In `tests/test_determinism.py` import `override_settings` and `get_settings` (`doctor_dictation.config`), `local as L` (`doctor_dictation.providers.stt`), `SttError` and `Transcript` (`...stt.base`), `make_stt` (`...stt.factory`), `OpenAiStt` (`...stt.openai`). Every changed line:

| Test | Old | New |
|---|---|---|
| `test_transcribe_onnx_unconfigured_503`, `..._explicit_faster_whisper_missing_503`, and `tests/test_upload_cap.py::..._exactly_at_the_cap_is_not_rejected` | `setattr(M, "STT_ENGINE", X)` | `override_settings(monkeypatch, stt_engine=X, stt_chain=())` |
| every test that patches it | `setattr(M, "faster_whisper_available", ...)` | `setattr(L, "faster_whisper_available", ...)` |
| `_cloud_ok` / `_cloud_fail` | `async def fake(audio_bytes, filename)` returning the dict / raising `RuntimeError(msg)` | `async def fake(self, audio_bytes, filename, hints=())` that starts with `assert tuple(hints) == ()` (the route passes no hints until ACC2), then returns `Transcript(text=transcript, engine="openai-whisper-api")` / raises `SttError(msg)` |
| `test_transcribe_cloud_default`, `..._no_local_502`, `..._falls_back_to_small`, `test_active_engine_prefers_cloud` | the `STT_ENGINE` and `OPENAI_API_KEY` setattrs | one `override_settings(monkeypatch, stt_engine="auto", stt_chain=(), openai_api_key="k")`; the fall-back test adds `whisper_model="large-v3-turbo"` and drops its `M.WHISPER_MODEL` setattr; the active-engine test later uses `override_settings(monkeypatch, openai_api_key="")` |
| the first three | `setattr(M, "transcribe_via_openai", X)` | `setattr(OpenAiStt, "transcribe", X)` |
| `..._falls_back_to_small` | `setattr(M, "_model", None)`, `setattr(M, "get_model", ...)` | same on `L`, plus a new `setattr(L, "_pinned_name", None)` |
| `test_active_engine_prefers_cloud` | `M.active_stt_engine()` twice | `_active()`, defined above as `def _active(): return make_stt(get_settings()).active_name()` |

**Two assertions cannot stay verbatim, because what they read moved.** `test_transcribe_cloud_default`: `assert j["transcript_sha256"] == "abc"` becomes `== transcript_sha(normalize_transcript("fever and cough"))` (the route now hashes; the old fake injected `"abc"`; import `transcript_sha` from `doctor_dictation.core.determinism`). `..._falls_back_to_small`: `assert M.WHISPER_MODEL == "small.en"` becomes `assert L.whisper_model_name() == "small.en"`. Report both.

- [ ] **Step 6: Document.** Append to `.env.example`:

```
# STT chain, tried in order: openai, faster-whisper, onnx, browser. Blank = derived from STT_ENGINE.
# STT_CHAIN=openai,faster-whisper
# Load tests and demos only: lets STT_CHAIN=stub run the fake provider (STUB_TRANSCRIPT, STUB_DELAY_MS).
# ALLOW_STUB_PROVIDERS=1
```

- [ ] **Step 7: Run** `.venv/bin/python -m pytest tests/ -q`. Expect N + 4 passed. Then `grep -rnE "WHISPER_MODEL|STT_ENGINE|get_model|_use_small_model|active_stt_engine|transcribe_via_openai|stt_onnx" doctor_dictation tests` must hit only `providers/stt/`, `config.py`, the health lines, `tests/test_secrets.py` (env names) and the new tests.

---

### Task 3: Final verification

- [ ] **Step 1: Suite and size.** `.venv/bin/python -m pytest tests/ -q` gives N + 4 passed. `wc -l doctor_dictation/main.py` is at least 120 lines shorter than before Task 2; no file is over 500 lines.
- [ ] **Step 2: Run the app and exercise it.**
```bash
STT_CHAIN=stub ALLOW_STUB_PROVIDERS=1 STUB_TRANSCRIPT="fever and cough" \
  .venv/bin/uvicorn doctor_dictation.main:app --port 8001 &
sleep 3; printf '\x00\x01' > /tmp/a.webm
curl -s -F audio=@/tmp/a.webm localhost:8001/api/transcribe
curl -s localhost:8001/api/health | .venv/bin/python -c "import sys,json; h=json.load(sys.stdin); print(h['stt_engine_active'], h['stt_decode']['beam_size'])"
kill %1
```
Expect `{"transcript":"fever and cough","engine":"stub","transcript_sha256":"<64 hex>"}` then `stub 5`. Restart with `STT_ENGINE=faster-whisper` (the venv has no faster-whisper): the same curl returns 503 `STT_ENGINE=faster-whisper but faster-whisper is not installed here.` Restart with `STT_CHAIN=stub` and no allow flag: 500 `STT misconfigured: the stub STT provider needs ALLOW_STUB_PROVIDERS=1`, while `/api/health` stays 200 with `stt_engine_active` `misconfigured`. Stop each server.
- [ ] **Step 3: Files, uncommitted.** `git status --short` adds to part 1's list: modified `main.py`, `requirements-onnx.txt`, `.env.example`, `tests/test_determinism.py`, `tests/test_upload_cap.py`, `factory.py`; new `tests/test_transcribe_route.py`; removed `doctor_dictation/stt_onnx.py`. **Not done:** the route never passes hints (ACC2); real OpenAI and faster-whisper calls are not exercised (no key in tests, package absent from the venv).
