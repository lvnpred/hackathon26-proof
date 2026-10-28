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
