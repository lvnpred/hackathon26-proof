# ACC1: STT Benchmark Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A command that runs each STT provider over a manifest of clips and prints word error rate (WER), drug-name recall and estimated cost, so ACC2 and ACC3 are kept or dropped on evidence.

**Architecture:** New package `doctor_dictation/bench/`: `metrics.py` (pure scoring), `manifest.py` (load, validate), `run.py` (CLI; builds one provider at a time through the STT factory). The app never imports it.

**Tech Stack:** Python 3.12 stdlib only (`unicodedata`, `wave`, `argparse`, `asyncio`, `json`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 5.4; contracts file sections 4.2, 4.7 (`docs/superpowers/plans/2026-10-13-00-index-and-contracts.md`). Plan 8 of 15.

**Adds 26 tests.** First run `.venv/bin/python -m pytest tests/ -q` and note the count `C`; expect `C + 26` at the end.

## Assumptions about earlier plans

- `doctor_dictation.core.determinism.load_lexicon()` returns entries with `canonical` and `brands` (checked in `backend/lexicon/drugs.json`).
- `doctor_dictation.config`: frozen `Settings` (`stt_chain`, `allow_stub_providers`) and `get_settings()` (4.1).
- `doctor_dictation.providers.stt.factory.make_stt(settings)` returns a provider with `available()` and `async transcribe(audio, filename, hints)` giving `.text`; the stub honours `STUB_TRANSCRIPT` and raises `ValueError` unless `allow_stub_providers` (4.2). Confirm with `grep -n` before Task 3.
- With a one-name chain a failed transcription raises; Task 3 treats any exception as a failed clip.

## Global Constraints

- Spec 5.4: "Synthetic (text-to-speech) audio is not acceptable as the main test set." Generated audio only tests the harness. **Never add real or synthetic audio to the repo.**
- Tests are offline (stub or fakes). `.env` holds a real key, so `run.py` calls `load_dotenv()` only under `__main__`.
- No `git commit` or `git push`; leave changes uncommitted. Usage docs live in the `run.py` docstring only.

## Review Focus

1. `wer` with an empty reference is defined, not a crash (Task 1).
2. `drug_recall` never matches partial words; multi-word names must be contiguous and ordered (Task 1).
3. A failing clip or unavailable provider is a table row (exit stays 0); unknown audio length gives `n/a`, never a silent 0 (Task 3).

---

### Task 1: Metrics

**Files:** Create `doctor_dictation/bench/__init__.py` (empty), `doctor_dictation/bench/metrics.py`; test `tests/test_bench_metrics.py`.
**Interfaces:** Produces `normalise(text) -> str`, `wer(reference, hypothesis) -> float`, `drug_recall(reference, hypothesis, drug_names) -> tuple[int, int]` (found, expected).
- [ ] **Step 1: Write the failing tests.** Run `touch doctor_dictation/bench/__init__.py && .venv/bin/python -m pytest tests/test_bench_metrics.py -q`: expect `ModuleNotFoundError ... bench.metrics`.
```python
import pytest

from doctor_dictation.bench.metrics import drug_recall, wer


@pytest.mark.parametrize("ref,hyp,expected", [
    ("Tab Dolo 650", "tab dolo 650", 0.0),               # identical
    ("one two three four", "one two three five", 0.25),  # substitution
    ("one two", "one two three", 0.5),                   # insertion
    ("one two three four", "one two four", 0.25),        # deletion
    ("one", "one two three", 2.0),                       # not capped
    ("", "", 0.0), ("  ...  ", "", 0.0), ("", "something", 1.0),  # empty reference
    ("five hundred mg", "500 mg", 2 / 3),                # number words kept as-is
    ("Tab. Dolo-650, Don't 1-0-1!", "tab dolo 650 dont 1 0 1", 0.0),  # punctuation, case
])
def test_wer(ref, hyp, expected):
    assert wer(ref, hyp) == pytest.approx(expected)


def test_drug_recall_multiword_needs_same_words_in_order():
    names = ["Calcium Carbonate"]
    assert drug_recall("give calcium carbonate", "give Calcium-Carbonate", names) == (1, 1)
    assert drug_recall("give calcium carbonate", "give calcium and carbonate", names) == (0, 1)
    assert drug_recall("give calcium carbonate", "give carbonate calcium", names) == (0, 1)


def test_drug_recall_whole_word_case_insensitive_and_distinct():
    assert drug_recall("Add DOLO", "add dolo", ["Dolo"]) == (1, 1)
    assert drug_recall("add dolo", "add dolor", ["Dolo"]) == (0, 1)
    assert drug_recall("add dolo", "add adolo", ["Dolo"]) == (0, 1)
    assert drug_recall("only paracetamol", "paracetamol zinc", ["Paracetamol", "paracetamol", "Zinc", " "]) == (1, 1)
```

- [ ] **Step 2: Implement** `doctor_dictation/bench/metrics.py` (names are padded with single spaces after normalising, so `" dolo "` is a whole-word test and multi-word names are contiguous substrings)
```python
"""Scoring for the STT benchmark. Pure: stdlib only.

Normalisation, both sides: lowercase; apostrophes dropped; other punctuation and
symbols become spaces ("1-0-1" -> "1 0 1"); whitespace collapsed. Number words are
left as-is ("five hundred" != "500").
"""
from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence


def normalise(text: str) -> str:
    lowered = text.lower().replace("'", "").replace("’", "")
    return " ".join("".join(" " if unicodedata.category(c)[0] in "PS" else c for c in lowered).split())


def _edit_distance(ref: Sequence[str], hyp: Sequence[str]) -> int:
    """Word-level Levenshtein: insert, delete, substitute each cost 1."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float:
    """Edit distance / reference words (may exceed 1.0). Empty reference: 0.0 if the
    hypothesis is empty too, else 1.0 (defined, not a division by zero)."""
    ref, hyp = normalise(reference).split(), normalise(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return _edit_distance(ref, hyp) / len(ref)


def drug_recall(reference: str, hypothesis: str, drug_names: Iterable[str]) -> tuple[int, int]:
    """(found, expected) over distinct names: expected = in the reference, found =
    also in the hypothesis. Whole-word, case-insensitive; a multi-word name needs
    the same words in order ("dolo" != "dolor"; "calcium carbonate" != "calcium and carbonate")."""
    ref, hyp = f" {normalise(reference)} ", f" {normalise(hypothesis)} "
    expected = [n for n in {normalise(n) for n in drug_names} - {""} if f" {n} " in ref]
    return sum(f" {n} " in hyp for n in expected), len(expected)
```
- [ ] **Step 3: Run to verify pass.** Same pytest command; expected `12 passed`.

### Task 2: Manifest loader and example

**Files:** Create `doctor_dictation/bench/manifest.py`, `tests/stt_bench/manifest.example.json`; test `tests/test_bench_manifest.py`.
**Interfaces:** Produces `Clip(audio: Path, reference: str, seconds: float | None)`, `ManifestError(ValueError)`, `load_manifest(path) -> list[Clip]` (audio files must exist).
- [ ] **Step 1: Write the example** `tests/stt_bench/manifest.example.json` (its audio paths must not be created; the real manifest is the git-ignored `manifest.json`)
```json
[
  {"audio": "audio/clip-001.wav", "reference": "Tab Azithromycin 500 mg once daily for 3 days after food", "seconds": 6.5},
  {"audio": "audio/clip-002.webm", "reference": "Syp Ascoril 5 ml thrice daily for 5 days and Tab Cetirizine 10 mg at night"}
]
```
- [ ] **Step 2: Write the failing tests.** Run `.venv/bin/python -m pytest tests/test_bench_manifest.py -q`: expect `ModuleNotFoundError ... bench.manifest`.
```python
import json
from pathlib import Path

import pytest

from doctor_dictation.bench.manifest import ManifestError, load_manifest


def _write(tmp_path: Path, data) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def test_relative_audio_resolves_against_manifest_folder(tmp_path):
    (tmp_path / "clips").mkdir()
    (tmp_path / "clips" / "a.wav").write_bytes(b"x")
    clip, = load_manifest(_write(tmp_path, [{"audio": "clips/a.wav", "reference": " tab dolo ", "seconds": 4}]))
    assert clip.audio == tmp_path.resolve() / "clips" / "a.wav"
    assert (clip.reference, clip.seconds) == ("tab dolo", 4.0)


@pytest.mark.parametrize("data,message", [
    ("{not json", "not readable JSON"),
    ([], "non-empty JSON list"),
    (["a.wav"], "entry 0: expected an object"),
    ([{"reference": "x"}], "entry 0: 'audio' must be"),
    ([{"audio": "gone.wav", "reference": "x"}], r"entry 0 \(gone\.wav\): audio file not found"),
    ([{"audio": "a.wav", "reference": "  "}], r"entry 0 \(a\.wav\): 'reference' must be non-empty"),
    ([{"audio": "a.wav", "reference": "x", "seconds": 0}], "'seconds' must be a positive number"),
])
def test_invalid_manifests_raise_clear_errors(tmp_path, data, message):
    (tmp_path / "a.wav").write_bytes(b"x")
    with pytest.raises(ManifestError, match=message):
        load_manifest(_write(tmp_path, data))


def test_missing_manifest(tmp_path):
    with pytest.raises(ManifestError, match="manifest not found"):
        load_manifest(tmp_path / "nope.json")
```

- [ ] **Step 3: Implement** `doctor_dictation/bench/manifest.py`
```python
"""Load and validate the benchmark manifest (a JSON list of clips)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ManifestError(ValueError):
    """str(e) names the offending entry."""


@dataclass(frozen=True)
class Clip:
    audio: Path
    reference: str
    seconds: float | None = None


def _clip(i: int, raw: object, base: Path) -> Clip:
    if not isinstance(raw, dict):
        raise ManifestError(f"entry {i}: expected an object, got {type(raw).__name__}")
    audio, ref, secs = raw.get("audio"), raw.get("reference"), raw.get("seconds")
    if not isinstance(audio, str) or not audio.strip():
        raise ManifestError(f"entry {i}: 'audio' must be a non-empty string path")
    where = f"entry {i} ({audio})"
    if not isinstance(ref, str) or not ref.strip():
        raise ManifestError(f"{where}: 'reference' must be non-empty text")
    path = Path(audio) if Path(audio).is_absolute() else base / audio
    if not path.is_file():
        raise ManifestError(f"{where}: audio file not found: {path}")
    if secs is not None and (isinstance(secs, bool) or not isinstance(secs, (int, float)) or secs <= 0):
        raise ManifestError(f"{where}: 'seconds' must be a positive number")
    return Clip(path, ref.strip(), None if secs is None else float(secs))


def load_manifest(path: str | Path) -> list[Clip]:
    """Relative audio paths resolve against the manifest's own folder."""
    manifest = Path(path)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ManifestError(f"manifest not found: {manifest}") from None
    except (OSError, ValueError) as exc:
        raise ManifestError(f"manifest is not readable JSON: {manifest} ({exc})") from None
    if not isinstance(data, list) or not data:
        raise ManifestError("manifest must be a non-empty JSON list of clips")
    base = manifest.resolve().parent
    return [_clip(i, raw, base) for i, raw in enumerate(data)]
```
- [ ] **Step 4: Run to verify pass.** Same command; expected `9 passed`.

### Task 3: CLI runner, price table, report

**Decisions.** *Audio length:* manifest `seconds`, else the WAV header (stdlib `wave`), else unknown. No `ffprobe`: it is an external dependency and browser `webm` carries no duration header, so it often answers "N/A" for exactly the clips that matter; set `seconds` for those. *Mean WER* is per-clip. *Isolation:* `replace(get_settings(), stt_chain=(name,))` gives one provider, not a chain.

**Files:** Create `doctor_dictation/bench/run.py`; modify `.gitignore`; test `tests/test_bench_run.py`.
**Interfaces:** Consumes Tasks 1-2. Produces `PRICE_PER_MINUTE`, `audio_seconds(clip)`, `async score_provider(name, clips, hints) -> dict`, `render_table(rows) -> str`, `main(argv) -> int`.
- [ ] **Step 1: Write the failing tests.** Run `.venv/bin/python -m pytest tests/test_bench_run.py -q`: expect `ModuleNotFoundError ... bench.run`. (The `.wav` clips are silent, synthetic, and live only in `tmp_path`)
```python
import json
import wave
from pathlib import Path

import pytest

from doctor_dictation.bench import run
from doctor_dictation.bench.manifest import Clip


def make_wav(path: Path, seconds: float) -> Path:
    """Silent synthetic clip: tests the harness only, never real audio."""
    with wave.open(str(path), "wb") as w:
        w.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return path


def _manifest(tmp_path: Path, seconds=None) -> Path:
    refs = ["Tab Azithromycin 500 mg once daily", "Tab Cetirizine 10 mg at night"]
    entries = [{"audio": make_wav(tmp_path / f"{i}.wav", 2 + i).name, "reference": r} for i, r in enumerate(refs)]
    entries[0]["seconds"] = seconds
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def _report(tmp_path: Path, *argv: str) -> dict:
    assert run.main([*argv, "--report", str(tmp_path / "r.json")]) == 0
    return json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["providers"][0]


def test_audio_seconds_manifest_then_wav_header(tmp_path):
    wav = make_wav(tmp_path / "a.wav", 2.5)
    assert run.audio_seconds(Clip(wav, "x", seconds=9.0)) == 9.0
    assert run.audio_seconds(Clip(wav, "x")) == pytest.approx(2.5)


def test_cli_end_to_end_with_stub_provider(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("STUB_TRANSCRIPT", "Tab Azithromycin 500 mg once daily")
    row = _report(tmp_path, "--manifest", str(_manifest(tmp_path)), "--providers", "stub,no-such-engine")
    assert (row["failed"], row["drug_found"], row["drug_expected"]) == (0, 1, 2)
    assert row["results"][0]["wer"] == 0.0 and row["results"][1]["wer"] == pytest.approx(4 / 6)
    assert row["mean_wer"] == pytest.approx(1 / 3) and row["seconds"] == pytest.approx(5.0)
    out = capsys.readouterr().out  # an unknown provider is a row, not a crash
    assert "0.333" in out and "no-such-engine | unavailable" in out


def test_cost_uses_price_table_and_unknown_length_gives_na(tmp_path, monkeypatch):
    monkeypatch.setenv("STUB_TRANSCRIPT", "x")
    monkeypatch.setitem(run.PRICE_PER_MINUTE, "stub", 0.6)
    manifest = _manifest(tmp_path, seconds=60)
    row = _report(tmp_path, "--manifest", str(manifest), "--providers", "stub")
    assert row["seconds"] == pytest.approx(63.0) and row["cost_usd"] == pytest.approx(0.63)
    (tmp_path / "1.wav").write_bytes(b"not a wav")  # length now unknown
    row = _report(tmp_path, "--manifest", str(manifest), "--providers", "stub")
    assert row["seconds"] is None and row["cost_usd"] is None


def test_failed_clip_is_counted_and_hints_follow_the_flag(tmp_path, monkeypatch, capsys):
    seen = []

    class Flaky:
        def available(self):
            return True

        async def transcribe(self, audio, filename, hints=()):
            seen.append(list(hints))
            if len(seen) % 2:
                raise RuntimeError("boom")
            return type("T", (), {"text": "Tab Cetirizine 10 mg at night"})()

    monkeypatch.setattr(run, "make_stt", lambda settings: Flaky())
    manifest = str(_manifest(tmp_path))
    assert run.main(["--manifest", manifest, "--providers", "flaky"]) == 0
    assert "1/2" in capsys.readouterr().out
    run.main(["--manifest", manifest, "--providers", "flaky", "--hints"])
    assert seen[:2] == [[], []] and len(seen[2]) > 0


def test_bad_manifest_exits_2_and_repo_holds_no_audio(tmp_path, capsys):
    assert run.main(["--manifest", str(tmp_path / "missing.json"), "--providers", "stub"]) == 2
    assert "manifest error" in capsys.readouterr().err
    bench = Path(__file__).parent / "stt_bench"
    assert [p for p in bench.rglob("*") if p.suffix in {".wav", ".webm", ".mp3", ".m4a", ".ogg"}] == []
```

- [ ] **Step 2: Implement** `doctor_dictation/bench/run.py`
```python
"""STT benchmark: word error rate, drug-name recall and cost, per provider.

    python -m doctor_dictation.bench.run --manifest tests/stt_bench/manifest.json
        --providers openai,faster-whisper [--hints] [--report out.json]

Manifest: JSON list of {"audio": "clips/a.webm", "reference": "exact text"}, optional
"seconds"; relative paths resolve against the manifest's folder (see
tests/stt_bench/manifest.example.json). Drug names scored: lexicon canonical names
and brands found in each reference.

REAL DATA ONLY: numbers mean something only for 50-100 real, consented,
de-identified dictations. Synthetic or text-to-speech audio is for testing this
harness, never for choosing a provider. Clips, manifest.json and reports/ are
git-ignored; keep them out of git.

Each provider is built alone (stt_chain=(name,)), never as a chain; "stub" is
allowed because you named it (STUB_TRANSCRIPT sets its text). --hints sends the
first 70 lexicon names. Mean WER is per-clip. Clip length: manifest "seconds",
else the WAV header, else unknown (browser webm has none: set "seconds"); unknown
makes seconds and cost "n/a". Exit 0 when the run completes, 2 for a bad manifest.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import wave
from dataclasses import replace
from pathlib import Path

from doctor_dictation.bench.manifest import Clip, ManifestError, load_manifest
from doctor_dictation.bench.metrics import drug_recall, wer
from doctor_dictation.config import get_settings
from doctor_dictation.core.determinism import load_lexicon
from doctor_dictation.providers.stt.factory import make_stt

# USD per audio minute. THIRD-PARTY FIGURES, NOT CHECKED AGAINST A BILL: confirm
# before quoting (openai = whisper-1 list price). Missing provider shows "n/a".
PRICE_PER_MINUTE: dict[str, float] = {"openai": 0.006, "faster-whisper": 0.0, "onnx": 0.0, "stub": 0.0}


def audio_seconds(clip: Clip) -> float | None:
    if clip.seconds is not None:
        return clip.seconds
    try:
        with wave.open(str(clip.audio), "rb") as w:
            return w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, OSError):
        return None


async def score_provider(name: str, clips: list[Clip], hints: list[str]) -> dict:
    row = {"provider": name, "clips": len(clips), "failed": 0, "status": "ok", "mean_wer": None,
           "drug_found": 0, "drug_expected": 0, "seconds": None, "cost_usd": None, "results": []}
    try:
        base = get_settings()  # a one-name chain: this provider alone, never a fallback
        provider = make_stt(replace(base, stt_chain=(name,),
                                    allow_stub_providers=base.allow_stub_providers or name == "stub"))
        if not provider.available():
            raise RuntimeError("not available (not installed or no key)")
    except Exception as exc:  # unknown name, stub not allowed, missing key
        row["status"] = f"unavailable: {str(exc)[:120]}"
        return row
    names = [n for e in load_lexicon() for n in [e.get("canonical", ""), *e.get("brands", [])] if n]
    wers, secs = [], []
    for clip in clips:
        item = {"audio": str(clip.audio)}
        row["results"].append(item)
        try:
            text = (await provider.transcribe(clip.audio.read_bytes(), clip.audio.name, hints)).text
        except Exception as exc:  # one bad clip must not end the run
            row["failed"] += 1
            item["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            continue
        found, expected = drug_recall(clip.reference, text, names)
        item.update(wer=wer(clip.reference, text), drug_found=found, drug_expected=expected, transcript=text)
        wers.append(item["wer"])
        row["drug_found"] += found
        row["drug_expected"] += expected
        secs.append(audio_seconds(clip))
    if wers:
        row["mean_wer"] = sum(wers) / len(wers)
    if secs and None not in secs:
        row["seconds"] = sum(secs)
        if name in PRICE_PER_MINUTE:
            row["cost_usd"] = row["seconds"] / 60 * PRICE_PER_MINUTE[name]
    return row


def render_table(rows: list[dict]) -> str:
    na = lambda v, f: "n/a" if v is None else format(v, f)
    lines = ["provider | clips ok | mean WER | drug recall | audio sec | est. cost USD"]
    for r in rows:
        if r["status"] != "ok":
            lines.append(f"{r['provider']} | {r['status']} | - | - | - | -")
            continue
        lines.append(f"{r['provider']} | {r['clips'] - r['failed']}/{r['clips']} | {na(r['mean_wer'], '.3f')} | "
                     f"{r['drug_found']}/{r['drug_expected']} | {na(r['seconds'], '.1f')} | {na(r['cost_usd'], '.4f')}")
    lines.append("prices: PRICE_PER_MINUTE in doctor_dictation/bench/run.py (third-party, confirm)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m doctor_dictation.bench.run")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--providers", required=True, help="comma list, e.g. openai,stub")
    parser.add_argument("--hints", action="store_true", help="send the vocabulary hint list")
    parser.add_argument("--report", help="also write full results as JSON to this path")
    args = parser.parse_args(argv)
    names = [p.strip() for p in args.providers.split(",") if p.strip()]
    try:
        clips = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"manifest error: {exc}", file=sys.stderr)
        return 2
    hints = [e["canonical"] for e in load_lexicon()[:70] if e.get("canonical")] if args.hints else []

    async def _all() -> list[dict]:
        return [await score_provider(n, clips, hints) for n in names]

    rows = asyncio.run(_all())
    print(render_table(rows))
    if args.report:
        Path(args.report).write_text(json.dumps({"manifest": args.manifest, "hints": args.hints,
                                                 "price_per_minute": PRICE_PER_MINUTE,
                                                 "providers": rows}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    from dotenv import load_dotenv  # a real key is only loaded when run as a CLI

    load_dotenv()
    sys.exit(main())
```
- [ ] **Step 3: Keep real data out of git.**
```bash
cat >> .gitignore <<'EOF'

# STT benchmark: real clips, the real manifest and reports stay local
tests/stt_bench/audio/
tests/stt_bench/manifest.json
tests/stt_bench/reports/
EOF
```
- [ ] **Step 4: Run to verify pass.** Same pytest command; expected `5 passed`.

### Task 4: Final verification
- [ ] **Step 1:** `.venv/bin/python -m pytest tests/ -q`. Expected `C + 26` passed.
- [ ] **Step 2: Run the CLI by hand** with one generated silent clip and the stub only (`openai` is not named, so no network call is made despite the key in `.env`):
```bash
D=$(mktemp -d); .venv/bin/python -c "import wave,sys;w=wave.open(sys.argv[1]+'/a.wav','wb');w.setparams((1,2,8000,0,'NONE','x'));w.writeframes(b'\0\0'*16000)" $D
echo '[{"audio":"a.wav","reference":"Tab Azithromycin 500 mg once daily"}]' > $D/m.json
STUB_TRANSCRIPT="tab azithromycin 500 mg" .venv/bin/python -m doctor_dictation.bench.run --manifest $D/m.json --providers stub,no-such-engine --report $D/r.json; echo exit=$?
```

Expected (2 of 6 reference words missing, drug found, 2.0 s, exit 0; the unavailable text comes from the factory's `ValueError`):
```
provider | clips ok | mean WER | drug recall | audio sec | est. cost USD
stub | 1/1 | 0.333 | 1/1 | 2.0 | 0.0000
no-such-engine | unavailable: unknown STT provider 'no-such-engine' | - | - | - | -
prices: PRICE_PER_MINUTE in doctor_dictation/bench/run.py (third-party, confirm)
exit=0
```
- [ ] **Step 3:** `git status --short` lists only the files below and `find tests/stt_bench -type f` shows only `manifest.example.json`. Changed files (uncommitted): `doctor_dictation/bench/{__init__,metrics,manifest,run}.py`, `tests/test_bench_{metrics,manifest,run}.py`, `tests/stt_bench/manifest.example.json`, `.gitignore`.

**Not done:** the real benchmark (50-100 consented, de-identified clips with verified references, supplied by you); confirming `PRICE_PER_MINUTE` against current price lists; switching `--hints` to ACC2's `core.hints.build_hints` (ACC2 may replace the 70-name lexicon list in `run.py`). **Decision needed:** the reference-writing convention (digits or number words), because `wer` leaves number words as-is, before the first real run.
