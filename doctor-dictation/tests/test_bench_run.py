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


# ---- ACC review fixes ----

def _recorder(monkeypatch):
    seen = []

    class Rec:
        def available(self):
            return True

        async def transcribe(self, audio, filename, hints=()):
            seen.append({"audio": audio, "filename": filename, "hints": list(hints)})
            return type("T", (), {"text": "x"})()

    monkeypatch.setattr(run, "make_stt", lambda settings: Rec())
    return seen


def test_hints_flag_sends_the_same_list_the_app_would(tmp_path, monkeypatch):
    # Review #1: the benchmark must measure the hint list the app really sends, not the alphabet.
    from doctor_dictation.core.hints import build_hints
    seen = _recorder(monkeypatch)
    assert run.main(["--manifest", str(_manifest(tmp_path)), "--providers", "rec", "--hints"]) == 0
    assert seen[0]["hints"] == build_hints() and seen[0]["hints"][0] != "Abacavir"


def test_trim_flag_trims_like_the_route(tmp_path, monkeypatch):
    seen = _recorder(monkeypatch)
    monkeypatch.setattr(run, "trim_silence", lambda audio, name: b"TRIMMED")
    manifest = str(_manifest(tmp_path))
    run.main(["--manifest", manifest, "--providers", "rec"])
    assert seen[0]["audio"] != b"TRIMMED" and seen[0]["filename"].endswith(".wav")
    run.main(["--manifest", manifest, "--providers", "rec", "--trim"])
    assert seen[2]["audio"] == b"TRIMMED" and seen[2]["filename"].endswith(".ogg")


def test_corrupt_wav_header_does_not_abort_the_run(tmp_path, monkeypatch, capsys):
    # Review #5: a WAV claiming a 0 Hz sample rate must give unknown length, not a crash.
    manifest = _manifest(tmp_path)
    raw = bytearray((tmp_path / "1.wav").read_bytes())
    raw[24:28] = (0).to_bytes(4, "little")          # sample rate field
    (tmp_path / "1.wav").write_bytes(bytes(raw))
    assert run.audio_seconds(Clip(tmp_path / "1.wav", "x")) is None
    monkeypatch.setenv("STUB_TRANSCRIPT", "x")
    assert run.main(["--manifest", str(manifest), "--providers", "stub"]) == 0
    assert "n/a" in capsys.readouterr().out
