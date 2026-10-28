# ACC2: Vocabulary Hints and Silence Trimming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `/api/transcribe` optionally (a) send the doctor's most-used medicines plus common lexicon names to the speech-to-text provider as a vocabulary hint, and (b) cut long silences from the audio before upload. Both are **off by default** behind flags; the spec ships them enabled only if the ACC1 benchmark shows a net gain.

**Architecture:** Three independent units: `core/hints.py` (pure), `db.top_medicines` (SQL plus tolerant JSON parsing), `audio/trim.py` (one `ffmpeg` subprocess over pipes, fail-soft). The route reads three new settings at call time. With both flags off it behaves exactly as before: `hints=()` and the original bytes.

**Tech Stack:** Python 3.12 (`.venv`), FastAPI, pytest, system `ffmpeg` (optional). No new Python dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` sections 5.1, 5.3 (acceptance 5.4). Contracts: `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` sections 2, 4.1, 4.2, 4.7.

**Adds 15 tests** (pytest items: 1 + 3 + 2 + 5 + 4). Run `.venv/bin/python -m pytest tests/ -q` first and note the count N; expect **N + 15** at the end (1 of them skips if `ffmpeg` is absent). Task 6 adds none.

## Assumptions about earlier plans

- B1a-B1e applied: package `doctor_dictation`; route in `doctor_dictation/api/stt.py` (`grep -n "transcribe" doctor_dictation/api/stt.py`); `create_app()` in `doctor_dictation/api/app.py`; blocking route work already uses `asyncio.to_thread` (B0b).
- B1b: `doctor_dictation/core/determinism.py` exposes `load_lexicon()` returning the `drugs.json` `entries` (keys `canonical`, `brands`, `strengths`, `aliases`, `forms`).
- B1c (contract 4.2): `make_stt(settings)` provider has `async transcribe(audio, filename, hints=())` and the route already passes `hints=()`; `Transcript` is in `doctor_dictation.providers.stt.base`; `override_settings(monkeypatch, **fields)` and `_int_env(name, default)` are in `doctor_dictation/config.py`.
- The route module imports `make_stt` by name; tests patch `make_stt` and `trim_silence` on that module. `doctor_dictation/db/__init__.py` keeps today's repository functions (`get_conn`, `migrate`, `create_patient`, `create_encounter`, `save_document`).

## Global Constraints

- Existing HTTP status codes and JSON shapes do not change; no new response fields (trim outcome is logged only).
- **No `git commit` / `git push`** (user rule): every task ends "leave uncommitted". No source file over 500 lines.
- Tests are offline (a real `OPENAI_API_KEY` is loaded from `.env`): route tests replace `make_stt` with a recording fake. Settings are read at call time.

## Design decisions

1. **"Common" lexicon names.** `drugs.json` (444 entries) has no frequency column and is alphabetical. Deterministic proxy: market breadth, meaning more brands first, then more strengths, then lowercase canonical. This ranks Co-Amoxiclav, Ceftriaxone, Paracetamol, Potassium Magnesium Citrate, Carvedilol first; 280 entries have one brand, so beyond the top ~170 the stable alphabetical tie-break decides. Hints are **canonical names only** (brands are spoken inconsistently; 70 names fill Whisper's ~224-token prompt).
2. **`top_medicines` parses JSON in Python**, not SQLite `json_each`: one malformed row would fail the whole SQL query. It scans the newest 500 finalized documents.
3. **Trim output is Ogg/Opus mono 16 kHz 32 kbps**, not WAV: a pipe cannot seek back to write a WAV length. The route renames the file `<stem>.ogg` when `trim_silence` returned new bytes.
4. **Filter measured** (scratchpad, 7.0 s file: 0.5 s silence, 1 s tone, 3 s silence, 1 s tone, 1.5 s silence): `stop_duration=0.6` left 0.9 s gaps (4.05 s); `stop_duration=0.3` leaves 0.6 s gaps, **3.45 s, 51% shorter**, both tones intact (peak -5.8 dB). Each cut keeps 0.3 s either side; pauses under 0.3 s are untouched. All-silent input gives a 137-byte header-only Ogg (caught by `MIN_OUTPUT_BYTES`); non-audio exits 183. Both return the original.

## Review Focus

1. Flags off: provider gets `hints == ()` and the original bytes (Task 5, test 1).
2. Missing, failing, hanging or empty `ffmpeg` never fails a request (Task 4); a malformed `structured_json` row never breaks `top_medicines` (Task 3).

### Task 1: Settings and `.env.example`

**Files:** Modify `doctor_dictation/config.py`, `.env.example`; test `tests/test_acc2_settings.py` (create). **Produces** `Settings.stt_use_hints=False`, `stt_hint_limit=70`, `stt_trim_silence=False` (contract 4.1).

- [ ] **Step 1: Write the failing test**

```python
from doctor_dictation.config import build_settings

def test_acc2_flags_default_off_and_parse(monkeypatch):
    for name in ("STT_USE_HINTS", "STT_HINT_LIMIT", "STT_TRIM_SILENCE"):
        monkeypatch.delenv(name, raising=False)
    s = build_settings()
    assert (s.stt_use_hints, s.stt_hint_limit, s.stt_trim_silence) == (False, 70, False)
    monkeypatch.setenv("STT_USE_HINTS", "1")
    monkeypatch.setenv("STT_TRIM_SILENCE", "true")
    monkeypatch.setenv("STT_HINT_LIMIT", "40")
    s = build_settings()
    assert (s.stt_use_hints, s.stt_hint_limit, s.stt_trim_silence) == (True, 40, True)
    monkeypatch.setenv("STT_HINT_LIMIT", "banana")
    assert build_settings().stt_hint_limit == 70
```

- [ ] **Step 2: Run, expect failure.** `.venv/bin/python -m pytest tests/test_acc2_settings.py -q` gives `1 failed` (`AttributeError ... stt_use_hints`).
- [ ] **Step 3: Implement.** Append these fields **after** the last field of `Settings` (defaulted fields must come last):

```python
    # --- ACC2 accuracy flags (off by default; enable only if the benchmark gains) ---
    stt_use_hints: bool = False
    stt_hint_limit: int = 70
    stt_trim_silence: bool = False
```

Add to the `Settings(...)` call in `build_settings()`:

```python
        stt_use_hints=os.getenv("STT_USE_HINTS", "").strip().lower() in ("1", "true", "yes", "on"),
        stt_hint_limit=_int_env("STT_HINT_LIMIT", 70),
        stt_trim_silence=os.getenv("STT_TRIM_SILENCE", "").strip().lower() in ("1", "true", "yes", "on"),
```

Append to `.env.example`:

```
# --- ACC2 accuracy flags (both OFF by default; enable only if the benchmark shows a net gain) ---
# STT_USE_HINTS=1      send the doctor's most-used medicines + common lexicon names as a Whisper vocabulary prompt
# STT_HINT_LIMIT=70    max names in that prompt (~70 fit Whisper's 224-token window)
# STT_TRIM_SILENCE=1   cut long pauses (keeps ~300 ms padding) with ffmpeg before upload; skipped if ffmpeg is missing
# FFMPEG_BIN=ffmpeg    optional path to the ffmpeg binary
```

- [ ] **Step 4: Run, expect `1 passed`. Step 5: leave uncommitted.**

### Task 2: `core/hints.py`

**Files:** Create `doctor_dictation/core/hints.py`; test `tests/test_hints.py` (create). **Produces** `common_lexicon_names()` and `build_hints(doctor_top=(), limit=70) -> list[str]`; imports only `core.determinism` (keeps `tests/test_core_purity.py` green).

- [ ] **Step 1: Write the failing tests**

```python
from doctor_dictation.core.hints import build_hints, common_lexicon_names

def test_doctor_names_first_then_lexicon_with_case_insensitive_dedup():
    out = build_hints(["Tamsulosin", "paracetamol", "PARACETAMOL"], limit=10)
    assert out[:2] == ["Tamsulosin", "paracetamol"] and len(out) == 10
    assert [n.lower() for n in out].count("paracetamol") == 1


def test_cap_blank_names_and_zero_limit():
    many = [f"Drug{i}" for i in range(100)]
    assert build_hints(many, limit=70) == many[:70]
    assert build_hints(["  ", "", "Tamsulosin"], limit=3)[0] == "Tamsulosin"
    assert "" not in build_hints(["  ", ""], limit=3)
    assert build_hints(["Tamsulosin"], limit=0) == []

def test_common_names_deterministic_unique_and_breadth_ranked():
    names = common_lexicon_names()
    assert names == common_lexicon_names()
    assert len({n.lower() for n in names}) == len(names)
    assert "Paracetamol" in names[:10]                           # 3 brands
    assert names.index("Paracetamol") < names.index("Acarbose")  # 1 brand
```

- [ ] **Step 2: Run, expect failure** (`ModuleNotFoundError`). `.venv/bin/python -m pytest tests/test_hints.py -q`
- [ ] **Step 3: Implement**

```python
"""Vocabulary hints (ACC2). Pure. "Common" = widely marketed: brands, strengths, then alphabetical."""
from collections.abc import Sequence

from .determinism import load_lexicon

def common_lexicon_names() -> list[str]:
    ranked = sorted(
        (e for e in load_lexicon() if str(e.get("canonical") or "").strip()),
        key=lambda e: (-len(e.get("brands") or []), -len(e.get("strengths") or []),
                       e["canonical"].lower()),
    )
    return [e["canonical"].strip() for e in ranked]

def build_hints(doctor_top: Sequence[str] = (), limit: int = 70) -> list[str]:
    """Doctor's most-used medicines first, then common lexicon names; unique, capped."""
    out: list[str] = []
    seen: set[str] = set()
    for name in [*doctor_top, *common_lexicon_names()]:
        if len(out) >= max(limit, 0):
            break
        clean = " ".join(str(name).split())
        if clean and clean.casefold() not in seen:
            seen.add(clean.casefold())
            out.append(clean)
    return out
```

- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_hints.py tests/test_core_purity.py -q`; all pass (3 new). **Step 5: leave uncommitted.**

### Task 3: `db.top_medicines`

**Files:** Modify `doctor_dictation/db/__init__.py` (after `get_document`); test `tests/test_top_medicines.py` (create). **Produces** `top_medicines(conn, limit=30) -> list[str]`: finalized documents' names, most used first, ties to the more recent, case-insensitive.

- [ ] **Step 1: Write the failing tests** (isolated temp DB, as in `tests/test_today.py`)

```python
import json

import pytest

from doctor_dictation import db as dbmod

@pytest.fixture()
def conn(tmp_path):
    c = dbmod.get_conn(tmp_path / "top.db")
    dbmod.migrate(c)
    yield c
    c.close()

def _doc(conn, names=(), finalized="2026-10-13T00:00:00Z", raw=None):
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    body = raw if raw is not None else json.dumps({"rx": [{"name": n} for n in names]})
    conn.execute("INSERT INTO documents(encounter_id, transcript_sha, structured_json,"
                 " finalized_at, created_at) VALUES (?, 'sha', ?, ?, '2026-10-13T00:00:00Z')",
                 (eid, body, finalized))
    conn.commit()

def test_most_frequent_first_case_insensitive_newest_spelling(conn):
    assert dbmod.top_medicines(conn) == []                       # empty DB
    _doc(conn, ["Paracetamol", "Tamsulosin"])
    _doc(conn, ["paracetamol"])
    _doc(conn, ["PARACETAMOL", "Zincovit"])
    assert dbmod.top_medicines(conn) == ["PARACETAMOL", "Zincovit", "Tamsulosin"]   # ties: most recent first
    assert dbmod.top_medicines(conn, limit=1) == ["PARACETAMOL"]
    assert dbmod.top_medicines(conn, limit=0) == []

def test_unfinalized_and_malformed_rows_are_ignored(conn):
    _doc(conn, ["Draftmed"], finalized=None)
    for raw in ("not json", "[]", "null", "", '{"rx": "x"}',
                '{"rx": [1, "s", null, {"name": 5}, {"name": "  "}, {}]}'):
        _doc(conn, raw=raw)
    _doc(conn, ["Goodmed"])
    assert dbmod.top_medicines(conn) == ["Goodmed"]
```

- [ ] **Step 2: Run, expect failure** (`AttributeError: ... top_medicines`). `.venv/bin/python -m pytest tests/test_top_medicines.py -q`
- [ ] **Step 3: Implement** (`json` is already imported in that module)

```python
TOP_MEDICINES_WINDOW = 500  # newest finalized documents scanned

def top_medicines(conn, limit: int = 30) -> list[str]:
    """Finalized documents' medicine names, most used first; malformed rows are skipped."""
    if limit <= 0:
        return []
    rows = conn.execute(
        "SELECT structured_json FROM documents"
        " WHERE finalized_at IS NOT NULL AND structured_json IS NOT NULL"
        " ORDER BY id DESC LIMIT ?", (TOP_MEDICINES_WINDOW,)).fetchall()
    counts: dict[str, int] = {}
    display: dict[str, str] = {}
    for (raw,) in rows:                      # newest first: dict order is recency order
        try:
            rx = json.loads(raw).get("rx")
        except (TypeError, ValueError, AttributeError):
            continue
        for row in rx if isinstance(rx, list) else ():
            name = row.get("name") if isinstance(row, dict) else None
            if not isinstance(name, str) or not name.strip():
                continue
            clean = " ".join(name.split())
            counts[clean.casefold()] = counts.get(clean.casefold(), 0) + 1
            display.setdefault(clean.casefold(), clean)
    ranked = sorted(counts, key=lambda k: -counts[k])   # stable: recency breaks ties
    return [display[k] for k in ranked[:limit]]
```

- [ ] **Step 4: Run, expect `2 passed`** (the same cases passed in scratch against today's `backend.db`). **Step 5: leave uncommitted.**

### Task 4: `audio/trim.py`

**Files:** Create `doctor_dictation/audio/__init__.py` (empty) and `audio/trim.py`; test `tests/test_trim_silence.py` (create). **Produces** `trim_silence(audio, filename) -> bytes`: **new** Ogg/Opus bytes on success, the **same object** on any problem (the route checks `is`). `FFMPEG_BIN` selects the binary.

- [ ] **Step 1: Write the failing tests**

```python
import io, logging, math, shutil, struct, subprocess, time, wave  # noqa: E401

import pytest

from doctor_dictation.audio import trim as trim_mod

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 16000
RAW = b"\x00" * 100

def _wav(parts):
    """parts: (seconds, amplitude) pairs; amplitude 0 is silence, else a 440 Hz tone."""
    s = [int(a * math.sin(2 * math.pi * 440 * i / SR)) for secs, a in parts for i in range(int(SR * secs))]
    buf = io.BytesIO()
    w = wave.open(buf, "wb")
    w.setnchannels(1), w.setsampwidth(2), w.setframerate(SR)
    w.writeframes(struct.pack(f"<{len(s)}h", *s))
    w.close()
    return buf.getvalue()

def _decode(data):
    p = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", "pipe:0", "-f", "s16le",
                        "-ac", "1", "-ar", str(SR), "pipe:1"], input=data, capture_output=True, check=True)
    return struct.unpack(f"<{len(p.stdout) // 2}h", p.stdout)

def _fake(tmp_path, monkeypatch, body):
    script = tmp_path / "fake-ffmpeg"
    script.write_text("#!/bin/sh\n" + body + "\n")
    script.chmod(0o755)
    monkeypatch.setenv("FFMPEG_BIN", str(script))

@needs_ffmpeg
def test_real_ffmpeg_shortens_and_keeps_both_speech_bursts():
    raw = _wav([(0.5, 0), (1.0, 16000), (3.0, 0), (1.0, 16000), (1.5, 0)])      # 7.0 s
    out = trim_mod.trim_silence(raw, "a.wav")
    assert out is not raw
    pcm = _decode(out)
    assert 3.0 < len(pcm) / SR < 4.0                                          # measured 3.45 s
    loud = sum(1 for i in range(0, len(pcm) - 1600, 1600) if max(abs(x) for x in pcm[i:i + 1600]) > 8000)
    assert loud >= 18                                                         # ~2 s of tone survived

def test_missing_binary_returns_input_and_logs_once(monkeypatch, caplog):
    monkeypatch.setenv("FFMPEG_BIN", "/nonexistent/ffmpeg")
    monkeypatch.setattr(trim_mod, "_warned_missing", False)
    with caplog.at_level(logging.WARNING, logger=trim_mod.log.name):
        assert trim_mod.trim_silence(RAW, "a.webm") is RAW
        assert trim_mod.trim_silence(RAW, "a.webm") is RAW
    assert sum("not found" in r.message for r in caplog.records) == 1

@pytest.mark.parametrize("body, logged", [("exit 1", "exit 1"), ("cat > /dev/null; exit 0", "0 bytes out")])
def test_nonzero_exit_or_empty_output_returns_input(tmp_path, monkeypatch, caplog, body, logged):
    _fake(tmp_path, monkeypatch, body)
    with caplog.at_level(logging.WARNING, logger=trim_mod.log.name):
        assert trim_mod.trim_silence(RAW, "a.webm") is RAW
    assert any(logged in r.message for r in caplog.records)


def test_timeout_returns_input_quickly(tmp_path, monkeypatch):
    _fake(tmp_path, monkeypatch, "exec sleep 5")        # exec: killing the script kills the sleep
    monkeypatch.setattr(trim_mod, "TIMEOUT_S", 0.5)
    t0 = time.monotonic()
    assert trim_mod.trim_silence(RAW, "a.webm") is RAW
    assert time.monotonic() - t0 < 3
```

- [ ] **Step 2: Run, expect failure** (`ModuleNotFoundError: doctor_dictation.audio`). `.venv/bin/python -m pytest tests/test_trim_silence.py -q`
- [ ] **Step 3: Implement** `doctor_dictation/audio/trim.py`

```python
"""Silence trimming before upload (ACC2). Fail-soft: any problem returns the input object."""
import logging
import os
import shutil
import subprocess

log = logging.getLogger(__name__)

TIMEOUT_S = 20.0
MIN_OUTPUT_BYTES = 400   # an all-silent input yields a ~137-byte header-only Ogg
FILTER = ("silenceremove=start_periods=1:start_duration=0.1:start_threshold=-45dB:start_silence=0.3"
          ":stop_periods=-1:stop_duration=0.3:stop_threshold=-45dB:stop_silence=0.3")
_warned_missing = False

def _ffmpeg() -> str | None:
    return shutil.which(os.getenv("FFMPEG_BIN", "ffmpeg"))

def trim_silence(audio: bytes, filename: str) -> bytes:
    """Ogg/Opus bytes with long pauses removed, or `audio` itself on any failure.
    Pipes only, no temp files. Blocking: call with asyncio.to_thread."""
    global _warned_missing
    if not audio:
        return audio
    exe = _ffmpeg()
    if exe is None:
        if not _warned_missing:
            _warned_missing = True
            log.warning("silence trim skipped: ffmpeg not found")
        return audio
    cmd = [exe, "-nostdin", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vn",
           "-af", FILTER, "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "32k",
           "-f", "ogg", "pipe:1"]
    try:
        done = subprocess.run(cmd, input=audio, capture_output=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        log.warning("silence trim skipped: ffmpeg timed out after %.0fs", TIMEOUT_S)
        return audio
    except OSError as exc:
        log.warning("silence trim skipped: cannot run ffmpeg (%s)", exc)
        return audio
    if done.returncode != 0 or len(done.stdout) < MIN_OUTPUT_BYTES:
        log.warning("silence trim skipped: ffmpeg exit %s, %d bytes out", done.returncode, len(done.stdout))
        return audio
    log.info("silence trim: %s %d -> %d bytes", filename, len(audio), len(done.stdout))
    return done.stdout
```

- [ ] **Step 4: Run, expect `5 passed`** (`4 passed, 1 skipped` without ffmpeg); this logic passed in the scratchpad against ffmpeg 8.1.1. **Step 5: leave uncommitted.**

### Task 5: Wire into `/api/transcribe`

**Files:** Modify `doctor_dictation/api/stt.py`; test `tests/test_transcribe_acc2.py` (create). No new response fields.

- [ ] **Step 1: Locate.** `grep -n "make_stt\|transcribe\|hints\|^import\|^from" doctor_dictation/api/stt.py`. Confirm `make_stt` is imported by name and note the upload-bytes and filename variables (today's `backend/main.py:545-570`: `raw`, `audio.filename or "dictation.webm"`). If the route module differs, change the test import.
- [ ] **Step 2: Write the failing tests**

```python
import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as route_mod
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt.base import Transcript

class Recorder:
    name = "recorder"
    available = staticmethod(lambda: True)
    calls = []

    async def transcribe(self, audio, filename, hints=()):
        self.calls.append({"audio": audio, "filename": filename, "hints": hints})
        return Transcript(text="hello", engine="recorder")

@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "acc2.db"))
    rec, trims = Recorder(), []
    rec.calls = []
    monkeypatch.setattr(route_mod, "make_stt", lambda settings: rec)
    monkeypatch.setattr(route_mod, "trim_silence", lambda audio, name: trims.append(name) or b"TRIMMED")
    with TestClient(create_app()) as client:
        yield client, rec, trims, monkeypatch

def _post(client):
    return client.post("/api/transcribe", files={"audio": ("note.webm", b"RAWBYTES", "audio/webm")})

def test_flags_off_means_no_hints_and_untouched_audio(env):
    client, rec, trims, mp = env
    override_settings(mp, stt_use_hints=False, stt_trim_silence=False)
    assert _post(client).status_code == 200
    assert rec.calls == [{"audio": b"RAWBYTES", "filename": "note.webm", "hints": ()}]
    assert trims == []

def test_hints_on_sends_doctors_medicines_first_then_lexicon(env):
    client, rec, _, mp = env
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    dbmod.save_document(conn, eid, "sha", {"rx": [{"name": "Tamsulosin"}, {"name": "Tamsulosin"},
                                                  {"name": "Zincovit"}]}, finalized_at="2026-10-13T00:00:00Z")
    conn.close()
    override_settings(mp, stt_use_hints=True, stt_hint_limit=12)
    assert _post(client).status_code == 200
    hints = list(rec.calls[0]["hints"])
    assert hints[:2] == ["Tamsulosin", "Zincovit"]
    assert len(hints) == 12 and len({h.lower() for h in hints}) == 12
    assert rec.calls[0]["audio"] == b"RAWBYTES"

def test_hints_on_survives_a_database_error(env):
    client, rec, _, mp = env
    override_settings(mp, stt_use_hints=True, stt_hint_limit=5)
    mp.setattr(route_mod.dbmod, "top_medicines", lambda conn, limit=30: 1 / 0)
    assert _post(client).status_code == 200
    assert len(rec.calls[0]["hints"]) == 5            # lexicon names only

def test_trim_on_sends_trimmed_bytes_with_ogg_name_and_failsoft_keeps_original(env):
    client, rec, trims, mp = env
    override_settings(mp, stt_trim_silence=True)
    assert _post(client).status_code == 200
    assert trims == ["note.webm"]
    assert (rec.calls[0]["audio"], rec.calls[0]["filename"], rec.calls[0]["hints"]) == (b"TRIMMED", "note.ogg", ())
    mp.setattr(route_mod, "trim_silence", lambda audio, name: audio)     # fail-soft: same object back
    assert _post(client).status_code == 200
    assert (rec.calls[1]["audio"], rec.calls[1]["filename"]) == (b"RAWBYTES", "note.webm")
```

- [ ] **Step 3: Run, expect failure.** `.venv/bin/python -m pytest tests/test_transcribe_acc2.py -q`: `AttributeError` on `trim_silence` or `dbmod` (monkeypatch refuses absent names).
- [ ] **Step 4: Implement.** Add imports to `doctor_dictation/api/stt.py` (skip any already present):

```python
import asyncio
from contextlib import closing
from pathlib import PurePath

from .. import db as dbmod
from ..audio.trim import trim_silence
from ..core.hints import build_hints
```

Add above the route (if the file would pass 500 lines, put both helpers in `doctor_dictation/api/stt_prep.py` and patch that module's names in the tests):

```python
def _doctor_top(limit: int) -> list[str]:
    """The doctor's most-used medicines; any database problem means no personalisation."""
    try:
        with closing(dbmod.get_conn()) as conn:
            return dbmod.top_medicines(conn, min(30, limit))
    except Exception as exc:  # noqa: BLE001 - hints are optional
        print(f"hints: top_medicines unavailable: {exc}", flush=True)
        return []

async def _prepare_audio(raw: bytes, filename: str, settings) -> tuple[bytes, str, tuple[str, ...]]:
    """Apply the ACC2 flags. Both off returns (raw, filename, ())."""
    hints: tuple[str, ...] = ()
    if settings.stt_trim_silence:
        trimmed = await asyncio.to_thread(trim_silence, raw, filename)
        if trimmed is not raw:                         # new bytes are Ogg/Opus
            raw, filename = trimmed, PurePath(filename).stem + ".ogg"
    if settings.stt_use_hints:
        top = await asyncio.to_thread(_doctor_top, settings.stt_hint_limit)
        hints = tuple(build_hints(top, settings.stt_hint_limit))
    return raw, filename, hints
```

In the route, right after the empty-upload 400 check and before the provider call, using the Step 1 variable names:

```python
    settings = get_settings()          # reuse the route's existing settings variable if any
    raw, filename, hints = await _prepare_audio(raw, filename, settings)
    # existing call becomes: make_stt(settings).transcribe(raw, filename, hints=hints)
```

- [ ] **Step 5: Run, expect `4 passed`;** then the full suite `.venv/bin/python -m pytest tests/ -q`. **Step 6: leave uncommitted.**

### Task 6: Final verification

- [ ] **Step 1: Full suite.** `.venv/bin/python -m pytest tests/ -q`. Expect **N + 15 passed** (1 + 3 + 2 + 5 + 4), or N + 14 passed and 1 skipped without `ffmpeg`.
- [ ] **Step 2: Real app, flags off then on.** `ALLOW_STUB_PROVIDERS=1 STT_CHAIN=stub .venv/bin/uvicorn doctor_dictation.main:app --port 8001 &`, then `curl -s -F audio=@/private/tmp/claude-502/-Users-narenlingala-Documents-workspace-work-Zebra-doctor-dic-doctor-dictation-main/1946fd26-8d6c-4ed9-a861-8a22c5d350ca/scratchpad/acc2/in.wav http://127.0.0.1:8001/api/transcribe`: expect 200 and the same JSON keys as before. Stop it, restart with `STT_TRIM_SILENCE=1 STT_USE_HINTS=1` added, repeat: 200, same keys, no `silence trim skipped` warning (the stub ignores hints; delivery is proven by Task 5). Stop the server.
- [ ] **Step 3: Real trim and missing ffmpeg.** `.venv/bin/python -c "from doctor_dictation.audio.trim import trim_silence as t; d=open('<scratchpad>/acc2/in.wav','rb').read(); o=t(d,'in.wav'); print(len(d), len(o), o is d)"` prints `224044`, a smaller number, `False`. With `FFMPEG_BIN=/nope` prefixed it prints one warning and `True`.
- [ ] **Step 4: List changed files** (`git status --short`): `doctor_dictation/{config.py,core/hints.py,db/__init__.py,audio/__init__.py,audio/trim.py,api/stt.py}` (plus `api/stt_prep.py` only if split), `.env.example`, five new test files. Nothing committed.
- [ ] **Step 5: Not verified here:** (a) whether hints or trimming raise or lower drug-name recall is the ACC1 benchmark's job, so neither flag turns on; (b) OpenAI Whisper accepting the Ogg/Opus upload, and the OpenAI provider's hard-coded `audio/webm` multipart type with an `.ogg` filename, were not exercised against the live API; (c) trim savings are logged as bytes, not seconds.

**Deliberately not done:** enabling either flag by default; brand-name hints; per-doctor hints (documents carry no doctor column, so `top_medicines` covers the whole clinic); a response field reporting trim savings; installing `ffmpeg` in the container image (D0b).
