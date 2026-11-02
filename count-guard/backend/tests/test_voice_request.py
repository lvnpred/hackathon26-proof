"""Muse Voice request shape: a JSON `request` part plus an `audio` part. Never a live call."""

from __future__ import annotations

import json
import logging
from dataclasses import replace

import httpx
import pytest

from app.adapters import voice as voice_mod
from app.adapters.voice import VoiceAdapter
from app.config import Settings
from app.journey import live


def _keyed(tmp_path):
    return Settings(
        data_dir=tmp_path, meta_api_key="test-key", meta_base="https://api.meta.ai/v1",
        sam_model="sam-3.1", voice_model="muse-voice-transcribe-1.0", spark_model="muse-spark-1.3",
        baseten_api_key="", spark_open_base="https://inference.baseten.co/v1",
        spark_open_model="meta-models/muse-spark-open-1026", low_confidence=0.45,
        unannounced_window_ms=30_000, lost_after_frames=4, sam_fps=2, dd_base="http://127.0.0.1:9",
    )


def _fake_client(monkeypatch, handler):
    real = httpx.Client
    monkeypatch.setattr(voice_mod.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))


def _parts(request: httpx.Request) -> dict[str, bytes]:
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    parts = {}
    for chunk in request.content.split(b"--" + boundary):
        if b'name="' not in chunk:
            continue
        head, _, body = chunk.partition(b"\r\n\r\n")
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        parts[name] = body.rstrip(b"\r\n")
    return parts


def test_request_has_json_request_part_and_audio_part(tmp_path, monkeypatch):
    seen = {}

    def handler(request):
        seen.update(_parts(request))
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"transcript": "Paracetamol 1 g every 6 hours", "turns": []})

    _fake_client(monkeypatch, handler)
    wav = tmp_path / "heard.wav"
    wav.write_bytes(b"RIFF....WAVE")
    turns = VoiceAdapter(_keyed(tmp_path)).transcribe(wav)
    assert seen["url"] == "https://api.meta.ai/v1/asr/transcribe"
    assert json.loads(seen["request"]) == {
        "mode": "PUSH_TO_TALK", "model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV", "languageBias": ["English"],
    }
    assert seen["audio"] == b"RIFF....WAVE"
    assert "file" not in seen and "model" not in seen
    assert turns == [{"text": "Paracetamol 1 g every 6 hours", "t0_ms": 0, "t1_ms": 0}]


def test_a_rejected_call_is_logged_with_its_reason(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(live, "to_wav", lambda raw, content_type: raw)
    _fake_client(monkeypatch, lambda request: httpx.Response(400, json={"error": {"message": "Malformed request"}}))
    with caplog.at_level(logging.WARNING, logger="app.journey.live"):
        out = live.transcribe(_keyed(tmp_path), b"x", "a.webm", "audio/webm")
    assert out["source"] == "unavailable"
    assert "Malformed request" in caplog.text
    assert "test-key" not in caplog.text


def test_no_key_never_calls_the_api(tmp_path):
    with pytest.raises(RuntimeError):
        VoiceAdapter(replace(_keyed(tmp_path), meta_api_key="")).transcribe(tmp_path / "x.wav")
