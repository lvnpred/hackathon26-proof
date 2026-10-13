# B1c: STT Providers and Factory Implementation Plan (part 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `doctor_dictation/providers/stt/` (interface, five providers, factory, stub) plus the `stt_chain` / `allow_stub_providers` settings and the `override_settings` test helper, as a purely additive change.

**Scope note:** the full B1c scope did not fit in 500 lines with real code, so it is split. This file is part 1: the package and the contract 4.2 surface (`make_stt`, `FallbackStt`), purely additive, `main.py` untouched, suite green after every task. Part 2, `2026-10-13-b1c2-stt-route-rewire.md` (run it right after this, before B1d), adds `failure_response`/`success_body`, rewires `/api/transcribe` and `/api/health`, deletes the moved code, migrates the existing STT tests and adds the route tests.

**Architecture:** One provider per file. `FallbackStt` tries the chain in order and (after part 2) answers both `/api/transcribe` and `/api/health`, so they cannot disagree.

**Tech Stack:** Python 3.12 (`.venv`), httpx, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 3. Contracts: `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 4.1, 4.2, 5.

**Adds 6 tests.** Run the suite first (`.venv/bin/python -m pytest tests/ -q`), note the count N, expect N + 6 at the end.

## Assumptions about earlier plans

- B1a: package `doctor_dictation/` at the repo root; tests import `doctor_dictation.main as M`; `stt_onnx.py` is at `doctor_dictation/stt_onnx.py`. B1b: `doctor_dictation.core.determinism` has `normalize_transcript` and `transcript_sha`. B0b: `Settings.max_audio_bytes` exists. Find code with `grep -n`, never by number (old `backend/main.py`: STT block 95-185, `get_model` 226-252, `transcribe_via_openai` 524-542).

## Global Constraints and Decisions

- **No `git commit`/`git push`**; leave changes uncommitted. Tests never touch the network; keys never appear in logs or responses. No file over 500 lines. Factories call `get_settings()` at call time so `override_settings` works.
- `browser.py` is a marker provider (never available): the browser fallback is a response (`"fallback": "browser"`), not a server call.
- Cloud-failure side effect: after an earlier provider *really failed* (not merely unavailable), `FallbackStt` calls the next provider's `after_earlier_failure()`; only the local provider has one (pin `small.en`, drop the cached model).
- Copies, not moves: `STT_DECODE`, `faster_whisper_available` and `stt_onnx.py` are deleted from their old homes in part 2.
- **Review Focus:** (1) hints reach OpenAI as `prompt` and local as `initial_prompt` without mutating `STT_DECODE`; (2) the stub cannot be built without `ALLOW_STUB_PROVIDERS`; (3) the after-failure hook fires only after a *real* failure.

---

### Task 1: Settings fields and `override_settings`

**Files:** Modify `doctor_dictation/config.py`; Create `tests/test_stt_factory.py` (grows in Task 4)

- [ ] **Step 1: Failing test.** Create `tests/test_stt_factory.py`:
```python
from doctor_dictation.config import build_settings, get_settings, override_settings

def test_stt_settings_and_override_helper(monkeypatch):
    monkeypatch.delenv("STT_CHAIN", raising=False)
    monkeypatch.delenv("ALLOW_STUB_PROVIDERS", raising=False)
    s = build_settings()
    assert (s.stt_chain, s.allow_stub_providers) == ((), False)
    monkeypatch.setenv("STT_CHAIN", " OpenAI, faster-whisper ,,")
    monkeypatch.setenv("ALLOW_STUB_PROVIDERS", "Yes")
    s = build_settings()
    assert (s.stt_chain, s.allow_stub_providers) == (("openai", "faster-whisper"), True)
    before = get_settings()
    with monkeypatch.context() as m:
        new = override_settings(m, stt_engine="onnx")
        assert get_settings() is new and new.stt_engine == "onnx"
    assert get_settings() is before  # undone with the monkeypatch
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_stt_factory.py -q`. Expect `ImportError: cannot import name 'override_settings'`.
- [ ] **Step 3: Implement** in `config.py`. Imports: `import dataclasses`, `import os`, `import sys`, `from dataclasses import dataclass`. In `Settings`, after `max_audio_bytes: int`, add `stt_chain: tuple[str, ...]  # () = derive from stt_engine` and `allow_stub_providers: bool`. In `build_settings()`'s `Settings(...)` add `stt_chain=_csv_env("STT_CHAIN"),` and `allow_stub_providers=_bool_env("ALLOW_STUB_PROVIDERS"),`. Add the helpers before `build_settings`; append `override_settings` at the end of the file:
```python
def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None or not raw.strip() else raw.strip().lower() in ("1", "true", "yes", "on")

def _csv_env(name: str) -> tuple[str, ...]:
    return tuple(p.strip().lower() for p in os.getenv(name, "").split(",") if p.strip())

def override_settings(monkeypatch, **fields) -> Settings:
    new = dataclasses.replace(get_settings(), **fields)
    monkeypatch.setattr(sys.modules[__name__], "_settings", new)
    return new
```

- [ ] **Step 4: Run** the same command. Expect `1 passed`.

---

### Task 2: Interface, OpenAI, browser and stub providers

**Files:** Create `providers/__init__.py` and `providers/stt/__init__.py` (both empty) under `doctor_dictation/`, then `base.py`, `openai.py`, `browser.py`, `stub.py` in `providers/stt/`; Create `tests/test_stt_providers.py`

- [ ] **Step 1: Failing tests.** Create `tests/test_stt_providers.py` (Task 3 appends to it):
```python
import asyncio
import os
from types import SimpleNamespace

import pytest

from doctor_dictation.config import get_settings, override_settings
from doctor_dictation.providers.stt.base import SttError, SttModelLoadError, SttUnavailable
from doctor_dictation.providers.stt.openai import OpenAiStt

_run = asyncio.run

def _httpx(mp, status=200, body=None):
    seen = []

    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, headers=None, **kw):
            seen.append({"url": url, "headers": headers, **kw})
            return SimpleNamespace(status_code=status, text="down " * 99, json=lambda: body or {})

    mp.setattr("httpx.AsyncClient", Client)
    return seen

def test_openai_request_hints_errors_and_no_key(monkeypatch):
    seen = _httpx(monkeypatch, body={"text": "fever"})
    p = OpenAiStt(override_settings(monkeypatch, openai_api_key="sk-x"))
    t = _run(p.transcribe(b"\x00", "d.webm"))
    assert (t.text, t.engine) == ("fever", "openai-whisper-api")
    assert seen[0]["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert seen[0]["headers"] == {"Authorization": "Bearer sk-x"}
    assert seen[0]["data"] == {"model": "whisper-1", "language": "en"}  # no prompt without hints
    assert seen[0]["files"]["file"] == ("d.webm", b"\x00", "audio/webm")
    _run(p.transcribe(b"\x00", "d.webm", ["Telmisartan", "Metformin"]))
    assert seen[1]["data"]["prompt"] == "Telmisartan, Metformin"
    _httpx(monkeypatch, status=500)
    with pytest.raises(SttError) as bad:
        _run(p.transcribe(b"\x00", "d.webm"))
    assert str(bad.value).startswith("OpenAI STT 500: down") and len(str(bad.value)) <= 300
    assert "sk-x" not in str(bad.value)  # the key never leaks
    seen = _httpx(monkeypatch)
    p = OpenAiStt(override_settings(monkeypatch, openai_api_key=""))
    with pytest.raises(SttUnavailable):
        _run(p.transcribe(b"\x00", "d.webm"))
    assert p.available() is False and seen == []  # no key, no network call
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_stt_providers.py -q`. Expect `ModuleNotFoundError: No module named 'doctor_dictation.providers'`.
- [ ] **Step 3: Create `base.py`:** `Transcript`, `SttError`, `SttUnavailable` and `SttProvider` verbatim from contract 4.2 (with the `dataclass`, `field`, `Protocol`, `Sequence` imports and `from __future__ import annotations`), plus:
```python
class SttNotImplemented(SttError): "Configured but no decode loop yet (ONNX): the route answers 501."
class SttModelLoadError(SttError): "Local model failed to load: the route answers 500, no fallback key."

class SttChainError(SttError):
    def __init__(self, failures):  # [(provider name, SttError)] in chain order
        self.failures = failures
        super().__init__("; ".join(f"{n}: {e}" for n, e in failures)[:300])
```

- [ ] **Step 4: Create `openai.py`** (from `transcribe_via_openai`; the URL stays hard-coded as before):
```python
import httpx

from doctor_dictation.providers.stt.base import SttError, SttUnavailable, Transcript

URL = "https://api.openai.com/v1/audio/transcriptions"

class OpenAiStt:
    name = "openai"

    def __init__(self, settings):
        self._key = settings.openai_api_key

    def available(self) -> bool:
        return bool(self._key)

    async def transcribe(self, audio, filename, hints=()):
        if not self._key:
            raise SttUnavailable("OPENAI_API_KEY is not set")
        data = {"model": "whisper-1", "language": "en"}
        if hints:
            data["prompt"] = ", ".join(hints)
        files = {"file": (filename or "dictation.webm", audio, "audio/webm")}
        try:  # httpx.AsyncClient is looked up at call time so tests can patch it
            async with httpx.AsyncClient(timeout=90) as client:
                r = await client.post(URL, headers={"Authorization": f"Bearer {self._key}"},
                                      files=files, data=data)
        except Exception as e:  # network, timeout, TLS: all mean "cloud failed"
            raise SttError(str(e)[:300]) from e
        if r.status_code != 200:
            raise SttError(f"OpenAI STT {r.status_code}: {r.text[:300]}"[:300])
        return Transcript(text=r.json().get("text", ""), engine="openai-whisper-api")
```

- [ ] **Step 5: Create `browser.py` and `stub.py`.** `BrowserStt`: `name = "browser"`, `__init__(self, settings=None)`, `available()` returns False, `async transcribe(self, audio, filename, hints=())` raises `SttUnavailable("speech recognition runs in the browser")`. `stub.py`:
```python
import asyncio
import os

from doctor_dictation.providers.stt.base import Transcript

class StubStt:  # load tests and demos; the factory refuses it unless ALLOW_STUB_PROVIDERS
    name = "stub"
    def __init__(self, settings=None): ...
    def available(self) -> bool: return True

    async def transcribe(self, audio, filename, hints=()):
        delay = int(os.getenv("STUB_DELAY_MS") or 0)  # env read at call time
        if delay > 0:
            await asyncio.sleep(delay / 1000)
        return Transcript(text=os.getenv("STUB_TRANSCRIPT") or "stub transcript", engine="stub")
```

- [ ] **Step 6: Run** the same command. Expect `1 passed`.

---

### Task 3: Local faster-whisper and ONNX providers

**Files:** Create `providers/stt/local.py` and `providers/stt/onnx.py`; Append to `tests/test_stt_providers.py`

- [ ] **Step 1: Failing tests.** Add `from doctor_dictation.providers.stt import local as L` and `from doctor_dictation.providers.stt.local import LocalWhisperStt` to the imports, then append:
```python
def _local(mp, whisper_model="small.en"):
    override_settings(mp, whisper_model=whisper_model)
    mp.setattr(L, "_pinned_name", None)
    mp.setattr(L, "_model", None)
    mp.setattr(L, "faster_whisper_available", lambda: True)
    calls = []

    def transcribe(path, **kw):
        calls.append((os.path.exists(path), path, kw))
        return ([SimpleNamespace(text=" hello "), SimpleNamespace(text="world")],
                SimpleNamespace(language="en", duration=1.5))

    mp.setattr(L, "get_model", lambda: SimpleNamespace(transcribe=transcribe))
    return LocalWhisperStt(), calls

def test_local_decode_hints_and_temp_file_cleanup(monkeypatch):
    p, calls = _local(monkeypatch)
    t = _run(p.transcribe(b"\x00", "d.webm"))
    assert (t.text, t.engine, t.language, t.duration) == ("hello world", "local:small.en", "en", 1.5)
    assert t.extra["decode"] == {"temperature": 0.0, "beam_size": 5, "patience": 1.0,
                                 "condition_on_previous_text": False}
    existed, path, kw = calls[0]
    assert existed and path.endswith(".webm") and not os.path.exists(path) and kw == L.STT_DECODE
    _run(p.transcribe(b"\x00", "d.webm", ["Telmisartan", "Metformin"]))
    assert calls[1][2]["initial_prompt"].endswith(", Telmisartan, Metformin")
    assert "Telmisartan" not in L.STT_DECODE["initial_prompt"]  # constant untouched

def test_local_errors_and_the_small_model_pin(monkeypatch):
    p, _ = _local(monkeypatch, "large-v3-turbo")

    def boom(*a, **k):
        raise OSError("no weights")

    monkeypatch.setattr(L, "get_model", boom)
    with pytest.raises(SttModelLoadError, match=r"failed to load \(large-v3-turbo\): no weights"):
        _run(p.transcribe(b"\x00", "d.webm"))
    monkeypatch.setattr(L, "get_model", lambda: SimpleNamespace(transcribe=boom))
    with pytest.raises(SttError, match="Server STT failed: no weights") as e:
        _run(p.transcribe(b"\x00", "d.webm"))
    assert not isinstance(e.value, SttModelLoadError)
    monkeypatch.setattr(L, "_model", object())
    p.after_earlier_failure()  # what FallbackStt calls after a cloud failure
    assert L.whisper_model_name() == "small.en" and L._model is None
    assert get_settings().whisper_model == "large-v3-turbo"  # settings untouched
    monkeypatch.setattr(L, "faster_whisper_available", lambda: False)
    with pytest.raises(SttUnavailable):
        _run(p.transcribe(b"\x00", "d.webm"))
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_stt_providers.py -q`. Expect `ImportError: cannot import name 'local'`.
- [ ] **Step 3: Create `local.py`.** Copy `STT_DECODE` and `faster_whisper_available` from `main.py` unchanged where marked (part 2 deletes the originals):
```python
import asyncio
import os
import tempfile
import threading
from pathlib import Path

from doctor_dictation.config import get_settings
from doctor_dictation.providers.stt.base import (
    SttError, SttModelLoadError, SttUnavailable, Transcript)

# ... STT_DECODE and faster_whisper_available copied here from main.py, unchanged ...
_pinned_name = None  # set by pin_small_model(); wins over settings
_model = None
_lock = threading.Lock()

def whisper_model_name() -> str:
    return _pinned_name or get_settings().whisper_model

def pin_small_model() -> None:  # small.en: fast, no turbo; drop the cached model
    global _pinned_name, _model
    if whisper_model_name() != "small.en":
        print(f"STT: pinning local fallback to small.en (was {whisper_model_name()})", flush=True)
        _pinned_name, _model = "small.en", None

def get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            s = get_settings()
            _model = WhisperModel(whisper_model_name(), device=s.whisper_device,
                                  compute_type=s.whisper_compute_type)
    return _model

class LocalWhisperStt:
    name = "faster-whisper"
    def __init__(self, settings=None): ...
    def available(self) -> bool: return faster_whisper_available()
    def after_earlier_failure(self) -> None: pin_small_model()  # a cloud provider really failed

    async def transcribe(self, audio, filename, hints=()):
        if not faster_whisper_available():
            raise SttUnavailable("faster-whisper is not installed")
        try:
            model = await asyncio.to_thread(get_model)
        except Exception as e:
            raise SttModelLoadError(
                f"STT model failed to load ({whisper_model_name()}): {e}".strip()[:500]) from e
        decode = dict(STT_DECODE)
        if hints:
            decode["initial_prompt"] += ", " + ", ".join(hints)
        suffix = Path(filename or "audio.webm").suffix or ".webm"

        def _run():
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(audio)
            try:
                segments, info = model.transcribe(tmp.name, **decode)
                return " ".join(s.text.strip() for s in segments).strip(), info.language, info.duration
            finally:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass

        try:
            text, lang, dur = await asyncio.to_thread(_run)
        except Exception as e:
            raise SttError(f"Server STT failed: {e}".strip()[:500]) from e
        used = {"temperature": 0.0, "beam_size": 5, "patience": 1.0, "condition_on_previous_text": False}
        return Transcript(text=text, engine=f"local:{whisper_model_name()}", language=lang,
                          duration=dur, extra={"decode": used})
```

- [ ] **Step 4: Create `onnx.py`.** `cp doctor_dictation/stt_onnx.py doctor_dictation/providers/stt/onnx.py` (part 2 deletes the original). Set `MODEL_DIR = Path(__file__).resolve().parents[2] / "stt_models"` (same folder as before), delete `available()` and `transcribe_pcm` (`grep -rn transcribe_pcm doctor_dictation tests` should find no caller), add `from doctor_dictation.providers.stt.base import SttNotImplemented, SttUnavailable`, and append:
```python
class OnnxStt:
    name = "onnx"
    def __init__(self, settings=None): ...
    def available(self) -> bool: return status()[0]

    async def transcribe(self, audio, filename, hints=()):
        ok, detail = status()
        if not ok:
            raise SttUnavailable(detail)
        raise SttNotImplemented("ONNX decode loop not implemented yet (Step 1 work item).")
```

- [ ] **Step 5: Run** the same command. Expect `3 passed`.

---

### Task 4: Factory and fallback chain

**Files:** Create `providers/stt/factory.py`; Append to `tests/test_stt_factory.py`

- [ ] **Step 1: Failing tests.** Add these imports at the top of `tests/test_stt_factory.py` and append the rest:
```python
import asyncio

import pytest

from doctor_dictation.providers.stt.base import SttChainError, SttError, SttUnavailable, Transcript
from doctor_dictation.providers.stt.factory import FallbackStt, derive_chain, make_stt

def _cfg(mp, **kw):
    base = dict(stt_engine="auto", stt_chain=(), openai_api_key="", allow_stub_providers=False)
    return override_settings(mp, **{**base, **kw})

class _Fake:
    def __init__(self, name, outcome):
        self.name, self._outcome, self.calls, self.pinned = name, outcome, [], 0
    def available(self): return True
    def after_earlier_failure(self): self.pinned += 1

    async def transcribe(self, audio, filename, hints=()):
        self.calls.append(tuple(hints))
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return Transcript(text=self._outcome, engine=self.name)

def _go(chain, hints=()):
    return asyncio.run(FallbackStt(chain).transcribe(b"a", "d.webm", hints))

def test_chain_derivation_and_stub_gating(monkeypatch):
    both = ("openai", "faster-whisper")
    expect = {"auto": both, "nonsense": both, "onnx": ("onnx",), "faster-whisper": ("faster-whisper",),
              "stub": ("stub",)}
    for engine, chain in expect.items():
        assert derive_chain(_cfg(monkeypatch, stt_engine=engine)) == chain, engine
    s = _cfg(monkeypatch, stt_engine="onnx", stt_chain=("faster-whisper", "openai", "browser"))
    assert make_stt(s).chain_names == ("faster-whisper", "openai", "browser")  # STT_CHAIN wins
    for kw in (dict(stt_chain=("whisperx",)), dict(stt_chain=("stub",)), dict(stt_engine="stub")):
        with pytest.raises(ValueError, match="unknown STT provider|ALLOW_STUB_PROVIDERS"):
            make_stt(_cfg(monkeypatch, **kw))
    stub = make_stt(_cfg(monkeypatch, stt_chain=("stub", "browser"), allow_stub_providers=True))
    assert stub.chain_names == ("stub", "browser") and stub.active_name() == "stub"
    monkeypatch.setenv("STUB_TRANSCRIPT", "tablet Paracetamol 650 mg")
    monkeypatch.setenv("STUB_DELAY_MS", "5")
    t = asyncio.run(stub.transcribe(b"a", "d.webm"))
    assert (t.text, t.engine) == ("tablet Paracetamol 650 mg", "stub")
    with pytest.raises(SttUnavailable):  # the browser marker never answers
        asyncio.run(stub.providers[1].transcribe(b"a", "d.webm"))

def test_chain_order_hints_and_the_after_failure_hook():
    a, b = _Fake("openai", "from cloud"), _Fake("faster-whisper", "from local")
    assert _go([a, b], ["Metformin"]).text == "from cloud"
    assert a.calls == [("Metformin",)] and b.calls == [] and b.pinned == 0
    b = _Fake("faster-whisper", "from local")
    assert _go([_Fake("openai", SttError("down")), b], ["Metformin"]).text == "from local"
    assert b.calls == [("Metformin",)] and b.pinned == 1  # a real failure pins small.en
    b = _Fake("faster-whisper", "from local")
    _go([_Fake("openai", SttUnavailable("no key")), b])
    assert b.pinned == 0  # an unconfigured cloud is not a failure
    with pytest.raises(SttChainError) as e:
        _go([_Fake("openai", SttError("down")), _Fake("faster-whisper", SttUnavailable("no pkg"))])
    assert [n for n, _ in e.value.failures] == ["openai", "faster-whisper"]
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_stt_factory.py -q`. Expect `ModuleNotFoundError: ... providers.stt.factory`.
- [ ] **Step 3: Create `factory.py`.**

```python
from typing import Sequence

from doctor_dictation.providers.stt.base import SttChainError, SttError, SttUnavailable, Transcript
from doctor_dictation.providers.stt.browser import BrowserStt
from doctor_dictation.providers.stt.local import LocalWhisperStt
from doctor_dictation.providers.stt.onnx import OnnxStt
from doctor_dictation.providers.stt.openai import OpenAiStt
from doctor_dictation.providers.stt.stub import StubStt

STT_REGISTRY = {"openai": OpenAiStt, "faster-whisper": LocalWhisperStt, "onnx": OnnxStt,
                "browser": BrowserStt, "stub": StubStt}
DISPLAY = {"openai": "openai-whisper-api", "faster-whisper": "faster-whisper",
           "onnx": "onnx", "stub": "stub"}

def derive_chain(s) -> tuple[str, ...]:
    # STT_CHAIN when set, else implied by STT_ENGINE (unknown values act as auto)
    return s.stt_chain or {"faster-whisper": ("faster-whisper",), "onnx": ("onnx",),
                           "stub": ("stub",)}.get(s.stt_engine, ("openai", "faster-whisper"))

class FallbackStt:
    name = "chain"  # tries providers in order; route and /api/health share it

    def __init__(self, providers):
        self.providers = tuple(providers)

    @property
    def chain_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.providers)

    def active_name(self) -> str:
        for p in self.providers:
            if p.available():
                return DISPLAY[p.name]
        if len(self.providers) == 1 and self.providers[0].name != "browser":
            return f"unavailable:{self.providers[0].name}"
        return "browser-webspeech"

    async def transcribe(self, audio: bytes, filename: str, hints: Sequence[str] = ()) -> Transcript:
        failures, really_failed = [], False
        for p in self.providers:
            if really_failed and hasattr(p, "after_earlier_failure"):
                p.after_earlier_failure()  # local pins small.en after a cloud failure
            try:
                return await p.transcribe(audio, filename, hints)
            except SttError as e:
                failures.append((p.name, e))
                if not isinstance(e, SttUnavailable):
                    really_failed = True
                    print(f"STT provider {p.name} failed: {e}", flush=True)
        raise SttChainError(failures)

def make_stt(settings) -> FallbackStt:
    providers = []
    for name in derive_chain(settings):
        if name not in STT_REGISTRY:
            raise ValueError(f"unknown STT provider '{name}' (known: {', '.join(STT_REGISTRY)})")
        if name == "stub" and not settings.allow_stub_providers:
            raise ValueError("the stub STT provider needs ALLOW_STUB_PROVIDERS=1")
        providers.append(STT_REGISTRY[name](settings))
    return FallbackStt(providers)
```

- [ ] **Step 4: Run** the same command. Expect `2 passed`.

---

### Task 5: Verification of part 1

- [ ] **Step 1: Suite.** `.venv/bin/python -m pytest tests/ -q` gives N + 6 passed (`main.py` is untouched, so no existing test changed).
- [ ] **Step 2: Smoke the chain without the app** (stub provider, no network):
```bash
ALLOW_STUB_PROVIDERS=1 STT_CHAIN=stub STUB_TRANSCRIPT="fever and cough" .venv/bin/python -c "import asyncio; from doctor_dictation.config import build_settings as b; from doctor_dictation.providers.stt.factory import make_stt; s = make_stt(b()); print(s.chain_names, s.active_name(), asyncio.run(s.transcribe(b'x', 'a.webm')).text)"
```

Expect `('stub',) stub fever and cough`. Without `ALLOW_STUB_PROVIDERS`, expect `ValueError: the stub STT provider needs ALLOW_STUB_PROVIDERS=1`.
- [ ] **Step 3: Files, uncommitted.** `git status --short` shows only: modified `config.py`; new `providers/` tree (`stt/{base,openai,local,onnx,browser,stub,factory}.py`, two `__init__.py`), `tests/test_stt_factory.py`, `tests/test_stt_providers.py`. **Not done here:** the route does not use the factory yet (part 2); real OpenAI and faster-whisper calls are never exercised (no key in tests, package absent from the venv).
