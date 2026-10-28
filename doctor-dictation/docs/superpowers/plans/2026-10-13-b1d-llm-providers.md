# B1d: LLM Providers and Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `llm_config()` / `_llm_complete()` in `main.py` with an `LlmProvider` interface (JSON mode, tool calls, image parts), one OpenAI-compatible provider for OpenAI and DeepSeek, a stub provider, and `make_llm(settings, vision=False)` called per request.

**Architecture:** `doctor_dictation/providers/llm/{base,openai_compat,stub,factory}.py`. The retry loop of `_llm_complete` moves unchanged into `OpenAICompatLlm._post`. The three routes call `make_llm(get_settings())`; tests move to `override_settings(...)`.

**Tech Stack:** Python 3.12 (`.venv`), FastAPI, httpx, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` (sections 3, 3.1, 7A.4); contracts `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` 4.1 (`llm_vision_model`) and 4.3. Plan 6 of 15.

**Adds 7 tests.** Run `.venv/bin/python -m pytest tests/ -q` first and note the count N. Expect N + 7 at the end. The three `llm_config` tests are rewritten in place, not added.

## Assumptions about earlier plans

- B1a/B1b: package `doctor_dictation`; tests use `import doctor_dictation.main as M`.
- B1c (contracts 4.1, 4.2): `Settings.allow_stub_providers` and `override_settings(monkeypatch, **fields)` exist in `doctor_dictation/config.py`; `providers/__init__.py` exists.
- Line numbers are from the pre-B1 tree: **locate each spot with `grep -n`** and match the quoted snippet.

## Global Constraints

- "No file over 500 lines." No `git commit` / `git push` (user rule): leave changes uncommitted, list changed files at the end.
- Tests are offline (`load_dotenv()` loads a real key): stub `httpx.AsyncClient` or clear keys via `override_settings`. Route status codes and JSON shapes do not change; a moved patch target changes only a test's setup line, never an assertion.

## Review Focus

1. A 400 naming `temperature`, then `top_p`, then `seed` is retried in that order, ending `(None, "openai 400: ...")` (Task 1 test).
2. `LLM_PROVIDER=stub` without `ALLOW_STUB_PROVIDERS` raises `ValueError`, so a misconfigured server answers 500 instead of silently running a fake (Task 1 test, Task 4 step 3).
3. An unknown `LLM_PROVIDER` acts as `openai`; a blank `LLM_VISION_MODEL` falls back to the text model (Task 1 test).

### Task 1: Setting, provider package, unit tests

**Files:**
- Modify: `doctor_dictation/config.py`, `.env.example`
- Create: `doctor_dictation/providers/llm/{__init__,base,openai_compat,stub,factory}.py`, `tests/test_llm_providers.py`

**Interfaces:**
- Produces (consumes the existing `Settings` LLM and key fields plus `allow_stub_providers`): `make_llm(settings, *, vision=False) -> LlmProvider | None`; `p.name`, `p.model`, `await p.complete_json(messages) -> (dict|None, str)`, `await p.complete(messages, tools=None) -> Completion` (raises `LlmError`); `OpenAICompatLlm.base_url`; `StubLlm.from_env()`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_llm_providers.py`:

```python
"""LLM providers, offline (httpx.AsyncClient is replaced). Run: pytest tests/test_llm_providers.py -q"""
import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from doctor_dictation.config import build_settings
from doctor_dictation.providers.llm.base import LlmError
from doctor_dictation.providers.llm.factory import make_llm
from doctor_dictation.providers.llm.stub import StubLlm

MSG = [{"role": "user", "content": "x"}]
run = asyncio.run


def _settings(**kw):
    base = dict(llm_provider="openai", openai_api_key="k", deepseek_api_key="",
                llm_model="gpt-6-luna", llm_vision_model="",
                openai_base_url="https://api.openai.com/v1", allow_stub_providers=False)
    return replace(build_settings(), **{**base, **kw})


def _resp(status, body):
    return SimpleNamespace(status_code=status, text=str(body), json=lambda: body)


def _chat(content=None, tool_calls=None, finish="stop"):
    msg = {"content": content, **({"tool_calls": tool_calls} if tool_calls else {})}
    return _resp(200, {"choices": [{"finish_reason": finish, "message": msg}]})


def _serve(monkeypatch, replies):
    """Replace httpx.AsyncClient; serve `replies` in order (the last repeats)."""
    seen = []

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, headers=None, **kw):
            seen.append({"url": url, "headers": headers, "json": dict(kw["json"])})
            return replies[min(len(seen) - 1, len(replies) - 1)]

    monkeypatch.setattr("httpx.AsyncClient", Client)
    return seen


def test_complete_json_payload_retry_order_and_error_strings(monkeypatch):
    llm = make_llm(_settings(llm_seed=11))
    seen = _serve(monkeypatch, [
        _resp(400, "Unsupported value: 'temperature' does not support 0.0"),
        _resp(400, "Unsupported parameter: 'top_p'"),
        _resp(400, "Unsupported parameter: 'seed'"), _chat('{"ok": true}')])
    assert run(llm.complete_json(MSG)) == ({"ok": True}, "")
    assert (seen[0]["url"], seen[0]["headers"]["Authorization"]) == (
        "https://api.openai.com/v1/chat/completions", "Bearer k")
    assert seen[0]["json"] == {
        "model": "gpt-6-luna", "response_format": {"type": "json_object"},
        "temperature": 0.0, "top_p": 1.0, "seed": 11, "messages": MSG}
    assert [tuple(k in c["json"] for k in ("temperature", "top_p", "seed")) for c in seen] == [
        (True, True, True), (False, True, True), (False, False, True), (False, False, False)]
    for reply, want in [(_resp(500, "down"), (None, "openai 500: down")),
                        (_resp(400, "bad model"), (None, "openai 400: bad model"))]:
        _serve(monkeypatch, [reply])
        assert run(llm.complete_json(MSG)) == want
    _serve(monkeypatch, [_chat("not json at all")])
    data, err = run(llm.complete_json(MSG))
    assert data is None and err.startswith("JSON parse:")


def test_complete_parses_tool_calls_text_and_failures(monkeypatch):
    llm = make_llm(_settings())
    calls = [{"id": "c1", "function": {"name": "layout", "arguments": '{"top": 0.1}'}}]
    tools = [{"type": "function", "function": {"name": "layout", "parameters": {}}}]
    seen = _serve(monkeypatch, [_chat(None, calls, "tool_calls")])
    out = run(llm.complete(MSG, tools))
    assert (out.text, out.json, out.finish) == ("", None, "tool_calls")
    assert [(c.id, c.name, c.arguments) for c in out.tool_calls] == [("c1", "layout", {"top": 0.1})]
    assert seen[0]["json"]["tools"] == tools and "response_format" not in seen[0]["json"]
    _serve(monkeypatch, [_chat('{"a": 1}')])
    out = run(llm.complete(MSG))
    assert (out.text, out.json, out.tool_calls) == ('{"a": 1}', {"a": 1}, ())
    bad = [{"id": "c", "function": {"name": "f", "arguments": "{oops"}}]
    for reply, match in [(_resp(500, "down"), "openai 500"), (_chat(None, bad), "response parse")]:
        _serve(monkeypatch, [reply])
        with pytest.raises(LlmError, match=match):
            run(llm.complete(MSG))


def test_image_parts_reach_the_http_payload_unchanged(monkeypatch):
    seen = _serve(monkeypatch, [_chat('{"ok": 1}')])
    msgs = [{"role": "user", "content": [
        {"type": "text", "text": "read this letterhead"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,AAAA"}}]}]
    expected = json.loads(json.dumps(msgs))
    llm = make_llm(_settings(), vision=True)
    run(llm.complete_json(msgs))
    run(llm.complete(msgs))
    assert [c["json"]["messages"] for c in seen] == [expected, expected]


def test_factory_vision_model_fallback_and_provider_fields(monkeypatch):
    assert make_llm(_settings(llm_vision_model="gpt-vis")).model == "gpt-6-luna"
    assert make_llm(_settings(llm_vision_model="gpt-vis"), vision=True).model == "gpt-vis"
    for blank in ("", "   "):
        assert make_llm(_settings(llm_vision_model=blank), vision=True).model == "gpt-6-luna"
    ds = _settings(llm_provider="deepseek", deepseek_api_key="d")
    assert make_llm(ds, vision=True).model == ds.deepseek_model
    assert make_llm(_settings(openai_api_key="")) is None
    assert make_llm(replace(ds, deepseek_api_key="")) is None
    assert make_llm(_settings(llm_provider="weird")).name == "openai"  # typo acts like openai
    monkeypatch.setenv("LLM_VISION_MODEL", "  gpt-vis  ")
    assert build_settings().llm_vision_model == "gpt-vis"
    monkeypatch.delenv("LLM_VISION_MODEL")
    assert build_settings().llm_vision_model == ""


def test_stub_gating_and_behaviour(monkeypatch):
    want = {"rx": [{"name": "Paracetamol"}]}
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(want))
    with pytest.raises(ValueError, match="ALLOW_STUB_PROVIDERS"):
        make_llm(_settings(llm_provider="stub", openai_api_key=""))
    llm = make_llm(_settings(llm_provider="stub", allow_stub_providers=True))
    assert isinstance(llm, StubLlm) and run(llm.complete_json([])) == (want, "")
    assert run(llm.complete([])).json == want
```

- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_llm_providers.py -q` fails with `ModuleNotFoundError ... providers.llm`.
- [ ] **Step 3: Add the setting.** In `Settings` add `llm_vision_model: str` after `llm_model: str`; in `build_settings()` add `llm_vision_model=os.getenv("LLM_VISION_MODEL", "").strip(),` after the `llm_model=` line. In `.env.example`, after `LLM_MODEL=gpt-6-luna`, add `LLM_VISION_MODEL=` (comment: blank reuses `LLM_MODEL`).

- [ ] **Step 4: Create the package.**

`doctor_dictation/providers/llm/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class Completion:
    text: str
    json: dict | None
    tool_calls: tuple[ToolCall, ...] = ()
    finish: str = ""


class LlmError(Exception):
    """`complete` failed; str(e) is safe to show (<= 300 chars)."""


class LlmProvider(Protocol):
    name: str  # "openai" | "deepseek" | "stub"
    model: str

    async def complete_json(self, messages: list[dict]) -> tuple[dict | None, str]: ...
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> Completion: ...
```

`doctor_dictation/providers/llm/openai_compat.py`:

```python
from __future__ import annotations

import json

import httpx

from .base import Completion, LlmError, ToolCall


class OpenAICompatLlm:
    def __init__(self, *, name, base_url, model, api_key, seed):
        self.name, self.model = name, model
        self.base_url = base_url.rstrip("/")
        self._key, self._seed = api_key, seed

    async def _post(self, payload: dict):
        # Full payload + up to 3 param drops; httpx.AsyncClient is looked up at call time.
        async with httpx.AsyncClient(timeout=60.0) as client:
            for _ in range(4):
                r = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._key}",
                             "Content-Type": "application/json"},
                    json=payload)
                if r.status_code == 400:
                    err = r.text[:500].lower()
                    dropped = next((p for p in ("temperature", "top_p", "seed")
                                    if p in payload and p in err), None)
                    if dropped:
                        print(f"LLM {self.model}: dropping unsupported param "
                              f"'{dropped}'", flush=True)
                        payload = {k: v for k, v in payload.items() if k != dropped}
                        continue
                if r.status_code != 200:
                    return None, f"{self.name} {r.status_code}: {r.text[:200]}"
                return r, ""
        return None, f"{self.name} 400: params rejected"

    def _payload(self, messages, **extra) -> dict:
        return {"model": self.model, **extra, "temperature": 0.0, "top_p": 1.0,
                "seed": self._seed, "messages": messages}

    async def complete_json(self, messages):
        r, err = await self._post(
            self._payload(messages, response_format={"type": "json_object"}))
        if r is None:
            return None, err
        try:
            return json.loads(r.json()["choices"][0]["message"]["content"]), ""
        except Exception as e:
            return None, f"JSON parse: {e}"

    async def complete(self, messages, tools=None):
        r, err = await self._post(self._payload(messages, **({"tools": tools} if tools else {})))
        if r is None:
            raise LlmError(err[:300])
        try:
            choice = r.json()["choices"][0]
            text = choice["message"].get("content") or ""
            calls = tuple(
                ToolCall(c.get("id", ""), c["function"]["name"],
                         json.loads(c["function"].get("arguments") or "{}"))
                for c in choice["message"].get("tool_calls") or [])
            try:
                value = json.loads(text) if text else None
            except ValueError:
                value = None
            return Completion(text, value if isinstance(value, dict) else None,
                              calls, choice.get("finish_reason") or "")
        except Exception as e:
            raise LlmError(f"{self.name} response parse: {e}"[:300]) from e
```

`doctor_dictation/providers/llm/stub.py`:

```python
from __future__ import annotations

import asyncio
import json
import os

from .base import Completion


class StubLlm:
    name = model = "stub"

    def __init__(self, text: str = "{}", delay: float = 0.0):
        self._text, self._delay = text, delay

    @classmethod
    def from_env(cls) -> "StubLlm":
        ms = os.getenv("STUB_DELAY_MS", "0")
        return cls(os.getenv("STUB_LLM_JSON", "{}"), int(ms) / 1000 if ms.isdigit() else 0.0)

    async def complete_json(self, messages):
        await asyncio.sleep(self._delay)
        try:
            value = json.loads(self._text)
        except ValueError as e:
            return None, f"stub STUB_LLM_JSON invalid: {e}"
        return (value, "") if isinstance(value, dict) else (None, "stub: not an object")

    async def complete(self, messages, tools=None):
        value, err = await self.complete_json(messages)
        return Completion(self._text if value is not None else err, value, (), "stop")
```

`doctor_dictation/providers/llm/factory.py`:

```python
"""make_llm: turns Settings into a provider, or None when no key is configured."""
from __future__ import annotations

from ...config import Settings
from .base import LlmProvider
from .openai_compat import OpenAICompatLlm
from .stub import StubLlm


def make_llm(s: Settings, *, vision: bool = False) -> LlmProvider | None:
    """An unknown LLM_PROVIDER acts like "openai" (today's default branch).

    `vision=True` prefers `llm_vision_model`; blank falls back to the text model.
    """
    if s.llm_provider == "stub":
        if not s.allow_stub_providers:
            raise ValueError("LLM_PROVIDER=stub requires ALLOW_STUB_PROVIDERS=1")
        return StubLlm.from_env()
    if s.llm_provider == "deepseek":
        name, base, model = "deepseek", s.deepseek_base_url, s.deepseek_model
        key, seed = s.deepseek_api_key, s.deepseek_seed
    else:
        name, base, model = "openai", s.openai_base_url, s.llm_model
        key, seed = s.openai_api_key, s.llm_seed
    if not key:
        return None
    if vision:
        model = (s.llm_vision_model or "").strip() or model
    return OpenAICompatLlm(name=name, base_url=base, model=model, api_key=key, seed=seed)
```

`doctor_dictation/providers/llm/__init__.py`: create it empty (imports use the submodules).

- [ ] **Step 5: Run.** `.venv/bin/python -m pytest tests/test_llm_providers.py -q` expects `5 passed`; `.venv/bin/python -m pytest tests/ -q` expects N + 5 passed (`main.py` is untouched). Leave uncommitted.

### Task 2: Rewire the routes, delete the old code

- **Files:** Modify `doctor_dictation/main.py`.
- **Interfaces:** Consumes `make_llm`, `get_settings`. Produces `main.py` without `llm_config`, `_llm_complete`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_SEED`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_SEED`.

**Until Task 3 ends, run every test command with the keys emptied** (`OPENAI_API_KEY= DEEPSEEK_API_KEY= .venv/bin/python -m pytest ...`): old tests patch globals that no longer control the LLM, so a real `.env` key could reach the network. An empty environment variable wins over `.env` because `load_dotenv()` does not override variables already set (verified).

- [ ] **Step 1: Import** `from doctor_dictation.providers.llm.factory import make_llm` beside the other provider imports.
- [ ] **Step 2: `/api/health`.** `cfg = llm_config()` becomes `llm = make_llm(get_settings())`; the values of `llm_provider`, `llm_model`, `llm_configured` become `llm.name if llm else get_settings().llm_provider`, `llm.model if llm else ""`, `llm is not None`.

- [ ] **Step 3: `/api/v1/correct`.** The bound `complete_json` has the old closure's shape, so the `import httpx` and `complete` closure go; the `except Exception as e:` branch stays:

```python
    llm = make_llm(get_settings())
    ...
    if llm is not None and normalized:
        try:
            patch = await extract_correction(normalized, current, llm.complete_json)
            llm_calls = 1
            engine = f"{llm.name}:{llm.model}+lexicon v{lexicon_version()}"
```

- [ ] **Step 4: `/api/format`**, four edits: (1) `cfg = llm_config()` / `if cfg is None:` become `llm = make_llm(get_settings())` / `if llm is None:`; (2) delete `import httpx` before `base_messages`; (3) drop the `async with httpx.AsyncClient(timeout=60) as client:` wrapper, dedent its body, call the provider:

```python
    try:
        while True:
            draft, err = await llm.complete_json(messages)
            ...  # rest of the loop body unchanged (grounding, best draft, caps, repair)
    except Exception as e:
        last_err = str(e)
```

(4) the success engine string uses `{llm.name}:{llm.model}` instead of `{cfg['name']}:{cfg['model']}`. Same requests, order and payloads; only one HTTP client per call instead of per request.

- [ ] **Step 5: Delete** `llm_config`, `_llm_complete`, the six globals under Produces and their comment. `grep -n "OPENAI_API_KEY\|OPENAI_BASE_URL\|DEEPSEEK_API_KEY" doctor_dictation/main.py`: keep one only if a remaining line (STT, health presence) reads it.
  Gate: `grep -rn "llm_config\|_llm_complete\|LLM_PROVIDER\b\|LLM_MODEL\b\|LLM_SEED\|DEEPSEEK_SEED\|DEEPSEEK_MODEL\|DEEPSEEK_BASE_URL" doctor_dictation/ | grep -v "config.py\|providers/llm"` must print nothing.

### Task 3: Migrate LLM test setup lines

**Files:** Modify `tests/test_correction.py`, `tests/test_determinism.py`, `tests/test_event_loop.py`.

Add `from doctor_dictation.config import override_settings` to all three; `test_determinism.py` also needs `get_settings` from the same module and `from doctor_dictation.providers.llm.factory import make_llm`.

- [ ] **Step 1: Replace these setup lines** (pre-B1 line numbers; every assertion stays). `K` below means `openai_api_key="", deepseek_api_key=""`.

| File, spot | Old lines | New line |
|---|---|---|
| `test_correction.py` `_client` (85-86) | `M, "DEEPSEEK_API_KEY", ""` and `M, "OPENAI_API_KEY", ""` | `override_settings(monkeypatch, K)` |
| `test_correction.py` `_stub_llm` (117-118) | `M, "OPENAI_API_KEY", "k"` and `M, "LLM_PROVIDER", "openai"` | `override_settings(monkeypatch, openai_api_key="k", llm_provider="openai")` |
| `test_event_loop.py` (B0b, 57-58); `test_determinism.py` `_client` (112-113) | the same two key-clearing lines | `override_settings(monkeypatch, K)` |
| `test_determinism.py` `test_complete_drops_unsupported_param` (193-195) | `LLM_PROVIDER`, `OPENAI_API_KEY`, `LLM_MODEL` | `override_settings(monkeypatch, llm_provider="openai", openai_api_key="k", llm_model="gpt-6-luna")` |
| `test_determinism.py` `_stub_llm` (409-410) | `OPENAI_API_KEY "dummy-key"`, `LLM_PROVIDER` | `override_settings(monkeypatch, openai_api_key="dummy-key", llm_provider="openai")` |

- [ ] **Step 2: Rewrite the three `llm_config` tests** (`test_determinism.py` 165-187). They call a deleted function, so the call and accessor change (`cfg["base"]` becomes `llm.base_url`; `M.DEEPSEEK_MODEL` becomes `get_settings().deepseek_model`); the asserted values are the same; the first test also pins `openai_base_url`.

```python
def test_llm_config_default_openai(monkeypatch):
    override_settings(monkeypatch, llm_provider="openai", openai_api_key="k",
                      llm_model="gpt-6-luna", openai_base_url="https://api.openai.com/v1")
    llm = make_llm(get_settings())
    assert (llm.name, llm.model, llm.base_url) == ("openai", "gpt-6-luna", "https://api.openai.com/v1")


def test_llm_config_deepseek_and_missing_key(monkeypatch):
    override_settings(monkeypatch, llm_provider="deepseek", deepseek_api_key="")
    assert make_llm(get_settings()) is None
    override_settings(monkeypatch, deepseek_api_key="d")
    llm = make_llm(get_settings())
    assert (llm.name, llm.model) == ("deepseek", get_settings().deepseek_model)


def test_llm_config_openai_missing_key(monkeypatch):
    override_settings(monkeypatch, llm_provider="openai", openai_api_key="")
    assert make_llm(get_settings()) is None
```

- [ ] **Step 3: Gate.** `grep -rn "M, \"LLM_\|M, \"DEEPSEEK_\|llm_config" tests/` prints only the three `test_llm_config_*` names. `grep -rn "M, \"OPENAI_API_KEY\"\|M, \"DEEPSEEK_API_KEY\"" tests/` may print only STT tests (`test_transcribe_*`) and the presence test in `test_secrets.py` (B1c's path, never the LLM); migrate any other hit the same way.
- [ ] **Step 4: Run.** `.venv/bin/python -m pytest tests/ -q` expects N + 5 passed (`AttributeError: ... 'LLM_...'` means a missed setup line).

### Task 4: Route tests through the stub, final verification

**Files:**
- Modify: `tests/test_llm_providers.py` (append two tests)

- [ ] **Step 1: Append the tests**

```python
def _client(monkeypatch, **fields):
    from fastapi.testclient import TestClient

    import doctor_dictation.main as M
    from doctor_dictation.config import override_settings
    override_settings(monkeypatch, **fields)
    return TestClient(M.app)


def test_format_route_uses_the_stub_provider(monkeypatch):
    client = _client(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    monkeypatch.setenv("STUB_LLM_JSON", '{"rx": []}')
    r = client.post("/api/format", json={"transcript": "b1d stub route 7731 fever two days"})
    assert r.status_code == 200, r.text
    assert r.json()["engine"].startswith("stub:stub+lexicon")
    assert r.json()["grounding"]["llm_calls"] == 1


def test_health_reports_the_stub_provider(monkeypatch):
    client = _client(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    h = client.get("/api/health").json()
    assert (h["llm_provider"], h["llm_model"], h["llm_configured"]) == ("stub", "stub", True)
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_llm_providers.py -q` expects `7 passed`. `.venv/bin/python -m pytest tests/ -q` expects N + 7 passed. `wc -l doctor_dictation/main.py doctor_dictation/providers/llm/*.py` shows each file under 500.
- [ ] **Step 3: Run the app on the stub.**

```
ALLOW_STUB_PROVIDERS=1 LLM_PROVIDER=stub STUB_LLM_JSON='{"rx": []}' .venv/bin/uvicorn doctor_dictation.main:app --port 8001 &
sleep 3; curl -s localhost:8001/api/health | grep -o '"llm_[a-z]*":[^,]*'
curl -s -X POST localhost:8001/api/format -H 'content-type: application/json' -d '{"transcript":"fever two days"}' | grep -o '"engine":"stub:stub+lexicon'
curl -s -X POST localhost:8001/api/v1/correct -H 'content-type: application/json' -d '{"transcript":"change the dose","current_form":{"patientName":"Anita"}}' | grep -o '"engine":"stub[^"]*'
kill %1
```

Expected: the three `llm_*` fields (`stub`, `stub`, `true`), then `"engine":"stub:stub+lexicon` twice. Restart with `LLM_PROVIDER=stub` only (no `ALLOW_STUB_PROVIDERS`): `curl -s -o /dev/null -w "%{http_code}\n" localhost:8001/api/health` prints `500`.

- [ ] **Step 4: Changed files (nothing committed).** `git status --short` lists: `doctor_dictation/config.py`, `.env.example`, `doctor_dictation/main.py`, `doctor_dictation/providers/llm/{__init__,base,openai_compat,stub,factory}.py`, `tests/test_llm_providers.py`, `tests/test_correction.py`, `tests/test_determinism.py`, `tests/test_event_loop.py`. Not verified: behaviour against the live OpenAI/DeepSeek APIs, and whether the configured `LLM_MODEL` accepts image parts (spec 7A.4; set `LLM_VISION_MODEL` before B2b).
