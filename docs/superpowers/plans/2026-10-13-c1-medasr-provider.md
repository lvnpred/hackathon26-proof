# C1: MedASR Provider Implementation Plan (optional, benchmark-first)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Google's open medical dictation model, MedASR, as a local speech-to-text provider (`medasr`) so the ACC1 benchmark can score it against whisper-1 on the clinic's real dictations. It is **not** made a default; it is chosen only if the benchmark shows a gain.

**Architecture:** One new provider file `doctor_dictation/providers/stt/medasr.py` (lazy `transformers` pipeline run in a worker thread), one registry line, one failure-message branch, one optional install extra, one setting (model id). The heavy dependencies are never installed into the default environment.

**Tech Stack:** Python 3.12, `transformers` (>= 5.0.0 per the model card) and `torch` in a separate optional environment, pytest with a fake pipeline.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` sections 5.4 and 10 (MedASR "added as a benchmark candidate"). Contracts: `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 4.1, 4.2. Sits between the B plans and the D plans; nothing after it depends on it.

**Adds 8 tests.** Run `.venv/bin/python -m pytest tests/ -q` first and note the count `N`; expect `N + 8` at the end.

## Prerequisites and a decision gate

- **Task 0 is a decision, not code.** The model is released under Google's *Health AI Developer Foundations* terms (the Hugging Face card lists the license as "other"), not a standard open-source license. Nobody has read those terms for this project. **If they do not allow your use (commercial use, clinical use, hosting for others, patient data), stop: this plan ends there and no code is written.**
- **Evidence is thin.** Published numbers are Google's own, on US dictation (radiology-heavy). No independent result on Indian or other non-US accents was found. The ACC1 benchmark on your real clips is the only judge. **Without 50 to 100 real, consented, de-identified clips (written with digits), do not execute Tasks 1 to 5**: there would be nothing to decide with.
- Assumptions about earlier plans: ACC1 is applied (`doctor_dictation/bench/run.py` with `PRICE_PER_MINUTE`), B1c is applied (`providers/stt/{base,factory}.py`, `override_settings`, `STT_CHAIN`).
- What was **not** verified when this plan was written: the exact `transformers` version or commit the model card requires today, whether the model is gated on Hugging Face (accepting the terms and logging in with a token is likely required), the download size, and CPU speed. Task 5 records these.

## Global Constraints

- No `git commit` or `git push` (user rule): leave everything uncommitted. No source file over 500 lines.
- Tests are offline and never download a model: the pipeline is replaced by a fake. A real OpenAI key sits in `.env`, so tests use `override_settings` and never call the network.
- `torch` and `transformers` go in an **optional extra** and a **separate virtual environment** (`.venv-medasr`), never into `.venv` or the production image by default.
- MedASR is a CTC model with no prompt input, so **hints are ignored** by this provider (stated in its docstring and tested).
- Existing HTTP status codes and JSON shapes do not change.

## Review Focus

1. A missing `transformers` install is "unavailable" (the chain moves on), not a crash (Task 2).
2. A model that fails to load answers 500 without the `fallback` key, exactly like the local Whisper provider; a decode failure answers 500 with it (Task 3).
3. A chain of only `medasr` that is not installed gets a message that names MedASR, not faster-whisper (Task 3).

---

### Task 0: Read the terms (decision gate)

- [ ] **Step 1:** Open the Health AI Developer Foundations terms linked from <https://huggingface.co/google/medasr> and from <https://developers.google.com/health-ai-developer-foundations/medasr/model-card>.
- [ ] **Step 2:** Write the answer to each question in the ledger (`.superpowers/sdd/2026-10-13-c1-medasr-provider/progress.md`): may it be used commercially? in a clinical or patient-facing product? hosted for other clinics? with patient data? is redistribution or fine-tuning restricted? is attribution required?
- [ ] **Step 3:** If any answer blocks your use, stop and report. Otherwise continue.

---

### Task 1: Setting, extra and requirements file

**Files:** Modify `doctor_dictation/config.py`, `pyproject.toml`, `.env.example`; Create `doctor_dictation/requirements-medasr.txt`, `tests/test_medasr_settings.py`.

- [ ] **Step 1: Write the failing test**

```python
from doctor_dictation.config import build_settings


def test_medasr_model_defaults_and_overrides(monkeypatch):
    monkeypatch.delenv("MEDASR_MODEL", raising=False)
    assert build_settings().medasr_model == "google/medasr"
    monkeypatch.setenv("MEDASR_MODEL", "  my-org/medasr-finetuned  ")
    assert build_settings().medasr_model == "my-org/medasr-finetuned"
    monkeypatch.setenv("MEDASR_MODEL", "   ")
    assert build_settings().medasr_model == "google/medasr"
```

- [ ] **Step 2: Run, expect failure.** `.venv/bin/python -m pytest tests/test_medasr_settings.py -q` fails with `AttributeError: 'Settings' object has no attribute 'medasr_model'`.
- [ ] **Step 3: Implement.** In `config.py` add the defaulted field after the last field of `Settings` (defaulted fields must come last) and the kwarg in `build_settings()`:

```python
    medasr_model: str = "google/medasr"
```

```python
        medasr_model=os.getenv("MEDASR_MODEL", "").strip() or "google/medasr",
```

Create `doctor_dictation/requirements-medasr.txt`:

```
# Optional: MedASR local speech-to-text (providers/stt/medasr.py). Install into a SEPARATE venv:
#   python3.12 -m venv .venv-medasr && .venv-medasr/bin/pip install -e ".[medasr]"
# The model card asks for transformers >= 5.0.0 and may pin a GitHub commit: confirm it first.
# The first run downloads the model; it is likely gated (accept the terms on Hugging Face, then log in).
transformers>=5.0.0
torch
```

In `pyproject.toml`, add one line under `[tool.setuptools.dynamic.optional-dependencies]`:

```toml
medasr = { file = ["doctor_dictation/requirements-medasr.txt"] }
```

Append to `.env.example`:

```
# MedASR (optional local model, benchmark candidate). Use STT_CHAIN=medasr,openai to try it.
# MEDASR_MODEL=google/medasr
```

- [ ] **Step 4: Run, expect `1 passed`.** Then `.venv/bin/python -m pytest tests/ -q` is `N + 1`. Leave uncommitted.

---

### Task 2: The provider

**Files:** Create `doctor_dictation/providers/stt/medasr.py`, `tests/test_stt_medasr.py`.

**Interfaces:** Produces `MedAsrStt` (name `medasr`), `transformers_available()`, `get_pipeline(model_id)`. Consumes `SttError`, `SttModelLoadError`, `SttUnavailable`, `Transcript` from `providers/stt/base.py`.

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
import threading
from types import SimpleNamespace

import pytest

from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt import medasr as MA
from doctor_dictation.providers.stt.base import SttError, SttModelLoadError, SttUnavailable

_run = asyncio.run


def _ready(monkeypatch, pipe):
    monkeypatch.setattr(MA, "transformers_available", lambda: True)
    monkeypatch.setattr(MA, "_pipe", None)
    monkeypatch.setattr(MA, "_load_pipeline", lambda model_id: pipe)
    return MA.MedAsrStt(override_settings(monkeypatch, medasr_model="google/medasr"))


def test_transcribes_off_the_event_loop_and_ignores_hints(monkeypatch):
    seen = {}

    def pipe(audio, **kw):
        seen.update(audio=audio, kw=kw, thread=threading.current_thread())
        return {"text": "  tab azithromycin 500 mg  "}

    t = _run(_ready(monkeypatch, pipe).transcribe(b"BYTES", "a.webm", ["Hint1", "Hint2"]))
    assert (t.text, t.engine) == ("tab azithromycin 500 mg", "medasr:google/medasr")
    assert seen["audio"] == b"BYTES" and seen["kw"] == {"chunk_length_s": 20, "stride_length_s": 2}
    assert seen["thread"] is not threading.main_thread()      # blocking model call runs in a worker thread


def test_not_installed_is_unavailable_not_a_crash(monkeypatch):
    monkeypatch.setattr(MA.importlib.util, "find_spec", lambda name: None)
    provider = MA.MedAsrStt(override_settings(monkeypatch))
    assert provider.available() is False
    with pytest.raises(SttUnavailable, match="not installed"):
        _run(provider.transcribe(b"x", "a.webm"))


def test_load_failure_is_a_model_load_error(monkeypatch):
    def boom(model_id):
        raise OSError("gated repo: accept the terms")

    monkeypatch.setattr(MA, "transformers_available", lambda: True)
    monkeypatch.setattr(MA, "_pipe", None)
    monkeypatch.setattr(MA, "_load_pipeline", boom)
    with pytest.raises(SttModelLoadError, match=r"failed to load \(google/medasr\): gated repo"):
        _run(MA.MedAsrStt(override_settings(monkeypatch)).transcribe(b"x", "a.webm"))


def test_decode_failure_is_a_plain_stt_error(monkeypatch):
    def pipe(audio, **kw):
        raise ValueError("cannot decode audio")

    with pytest.raises(SttError, match="MedASR failed: cannot decode audio") as e:
        _run(_ready(monkeypatch, pipe).transcribe(b"x", "a.webm"))
    assert not isinstance(e.value, (SttModelLoadError, SttUnavailable))
```

- [ ] **Step 2: Run, expect failure.** `.venv/bin/python -m pytest tests/test_stt_medasr.py -q` fails with `ModuleNotFoundError: ... providers.stt.medasr`.
- [ ] **Step 3: Implement** `doctor_dictation/providers/stt/medasr.py`:

```python
"""MedASR provider: Google's open medical dictation model, run locally with transformers.

MedASR is a CTC model: it has no prompt input, so `hints` are accepted and ignored.
The pipeline decodes the audio bytes itself (it needs the ffmpeg binary) and is loaded
lazily on first use; the blocking calls run in worker threads.
"""
import asyncio
import importlib.util
import threading

from doctor_dictation.config import get_settings
from doctor_dictation.providers.stt.base import (
    SttError, SttModelLoadError, SttUnavailable, Transcript)

CHUNK_S, STRIDE_S = 20, 2  # the model card's example chunking
_pipe = None
_pipe_name = None
_lock = threading.Lock()


def transformers_available() -> bool:
    return importlib.util.find_spec("transformers") is not None


def _load_pipeline(model_id: str):
    from transformers import pipeline  # heavy import: only on first use

    return pipeline("automatic-speech-recognition", model=model_id)


def get_pipeline(model_id: str):
    global _pipe, _pipe_name
    with _lock:
        if _pipe is None or _pipe_name != model_id:
            _pipe, _pipe_name = _load_pipeline(model_id), model_id
    return _pipe


class MedAsrStt:
    name = "medasr"

    def __init__(self, settings=None):
        self._model = (settings or get_settings()).medasr_model

    def available(self) -> bool:
        return transformers_available()

    async def transcribe(self, audio, filename, hints=()):
        if not transformers_available():
            raise SttUnavailable("transformers is not installed (pip install -e '.[medasr]' in .venv-medasr)")
        try:
            pipe = await asyncio.to_thread(get_pipeline, self._model)
        except Exception as e:
            raise SttModelLoadError(f"MedASR model failed to load ({self._model}): {e}".strip()[:500]) from e
        try:
            out = await asyncio.to_thread(pipe, audio, chunk_length_s=CHUNK_S, stride_length_s=STRIDE_S)
        except Exception as e:
            raise SttError(f"MedASR failed: {e}".strip()[:300]) from e
        return Transcript(text=str(out.get("text", "")).strip(), engine=f"medasr:{self._model}")
```

- [ ] **Step 4: Run, expect `4 passed`.** Leave uncommitted.

---

### Task 3: Registry and failure message

**Files:** Modify `doctor_dictation/providers/stt/factory.py`; Append to `tests/test_stt_factory.py`.

- [ ] **Step 1: Write the failing tests** (append; `override_settings`, `make_stt`, `failure_response`, `SttChainError`, `SttUnavailable` are already imported in that file):

```python
def test_medasr_is_registered_and_orders_in_a_chain(monkeypatch):
    s = override_settings(monkeypatch, stt_chain=("medasr", "openai"), stt_engine="auto",
                          allow_stub_providers=False)
    assert make_stt(s).chain_names == ("medasr", "openai")


def test_medasr_only_chain_not_installed_names_medasr_in_the_503():
    status, body = failure_response(
        SttChainError([("medasr", SttUnavailable("transformers is not installed"))]), ("medasr",))
    assert status == 503 and body["fallback"] == "browser"
    assert "medasr" in body["error"].lower() and "faster-whisper" not in body["error"].lower()
    assert "requirements-medasr" in body["hint"] or ".[medasr]" in body["hint"]
```

- [ ] **Step 2: Run, expect failure.** `.venv/bin/python -m pytest tests/test_stt_factory.py -q`: `ValueError: unknown STT provider 'medasr'` and a wrong 503 text.
- [ ] **Step 3: Implement** in `factory.py`: import `from doctor_dictation.providers.stt.medasr import MedAsrStt`; add `"medasr": MedAsrStt` to `STT_REGISTRY` and `"medasr": "medasr"` to `DISPLAY`; and in `failure_response`, before the final generic 503 (`return 503, {...}` with "No server STT installed"), add:

```python
    if tuple(chain) == ("medasr",):
        return 503, {"error": "STT_CHAIN=medasr but MedASR is not installed here (transformers missing).",
                     "fallback": "browser",
                     "hint": "Install it in a separate venv: pip install -e \".[medasr]\" (see doctor_dictation/requirements-medasr.txt)."}
```

- [ ] **Step 4: Run, expect all pass.** `.venv/bin/python -m pytest tests/ -q` is `N + 7`. Leave uncommitted.

---

### Task 4: Benchmark price entry

**Files:** Modify `doctor_dictation/bench/run.py`; Append to `tests/test_bench_run.py`.

- [ ] **Step 1: Write the failing test**

```python
def test_medasr_runs_locally_so_it_has_a_zero_price_row():
    assert run.PRICE_PER_MINUTE["medasr"] == 0.0   # self-hosted: compute is not priced here
```

- [ ] **Step 2: Run, expect `KeyError: 'medasr'`.** Then in `run.py` change the dict to include `"medasr": 0.0`:

```python
PRICE_PER_MINUTE: dict[str, float] = {"openai": 0.006, "faster-whisper": 0.0, "onnx": 0.0, "medasr": 0.0, "stub": 0.0}
```

- [ ] **Step 3: Run the whole suite.** Expected `N + 8` passed. Leave uncommitted.

---

### Task 5: Verification and the real run

- [ ] **Step 1: Offline checks.** `.venv/bin/python -m pytest tests/ -q` gives `N + 8` passed. `grep -rn "torch\|transformers" doctor_dictation --include='*.py' | grep -v providers/stt/medasr.py` prints nothing (no other module imports the heavy packages), and `.venv/bin/python -c "import torch"` still fails, proving the default environment stayed light.
- [ ] **Step 2: Unavailable path in the real app.** `STT_CHAIN=medasr .venv/bin/uvicorn doctor_dictation.main:app --port 8001`, then `curl -s -F audio=@<any file> localhost:8001/api/transcribe` returns 503 with the MedASR message and `"fallback":"browser"`. Stop the server.
- [ ] **Step 3: The real benchmark (only with real clips and an accepted licence).** Build the separate environment and run both engines on the same manifest:

```bash
python3.12 -m venv .venv-medasr && .venv-medasr/bin/pip install -e ".[medasr,dev]"
# accept the model terms on Hugging Face and log in (huggingface-cli login) if the repo is gated
.venv-medasr/bin/python -m doctor_dictation.bench.run --manifest tests/stt_bench/manifest.json \
  --providers openai,medasr --report tests/stt_bench/reports/medasr.json
```

Record in the ledger: the exact `transformers` version that worked, the model download size, seconds per minute of audio on this machine, and the table (WER and drug-name recall for `openai` versus `medasr`). A provider is worth adopting only if it beats whisper-1 on **drug-name recall** for your doctors' accents, not on overall WER alone.
- [ ] **Step 4: Report.** Changed files (uncommitted): `doctor_dictation/{config.py,providers/stt/{medasr.py,factory.py},bench/run.py,requirements-medasr.txt}`, `pyproject.toml`, `.env.example`, `tests/{test_medasr_settings.py,test_stt_medasr.py,test_stt_factory.py,test_bench_run.py}`. State what was not verified (Task 5 step 3 if it was skipped).

**Not done on purpose:** making MedASR a default or fallback; shipping `torch` in the default environment or the container image; fine-tuning (the accent study suggests it helps, but it needs its own plan and data); hosting MedASR as a separate service.
