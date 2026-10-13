"""POST /api/transcribe rejects audio over the configured size with HTTP 413.

Run:  .venv/bin/python -m pytest tests/test_upload_cap.py -q
"""
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import build_settings, override_settings


def _post(size):
    return TestClient(M.app).post(
        "/api/transcribe", files={"audio": ("t.webm", b"\x00" * size, "audio/webm")})


def test_audio_over_the_cap_is_rejected_with_413(monkeypatch):
    override_settings(monkeypatch, max_audio_bytes=1024)
    r = _post(1025)
    assert r.status_code == 413
    assert "larger than" in r.json()["error"]


def test_audio_exactly_at_the_cap_is_not_rejected(monkeypatch):  # Review Focus #5
    override_settings(monkeypatch, max_audio_bytes=1024)
    override_settings(monkeypatch, stt_engine="onnx", stt_chain=())  # unconfigured: fails fast, no real STT
    assert _post(1024).status_code != 413


def test_default_cap_is_ten_mebibytes(monkeypatch):
    monkeypatch.delenv("MAX_AUDIO_BYTES", raising=False)
    assert build_settings().max_audio_bytes == 10 * 1024 * 1024


def test_cap_reads_the_env_and_ignores_garbage(monkeypatch):
    monkeypatch.setenv("MAX_AUDIO_BYTES", "2048")
    assert build_settings().max_audio_bytes == 2048
    monkeypatch.setenv("MAX_AUDIO_BYTES", "not-a-number")
    assert build_settings().max_audio_bytes == 10 * 1024 * 1024
