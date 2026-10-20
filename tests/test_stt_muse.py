import asyncio
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from doctor_dictation.audio import wav as W
from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt import muse as M
from doctor_dictation.providers.stt.base import SttError, SttUnavailable
from doctor_dictation.providers.stt.factory import CLOUD, derive_chain, make_stt
from doctor_dictation.providers.stt.muse import MuseStt

_run = asyncio.run
FAKE_WAV = b"RIFF\x00\x00\x00\x00WAVEfmt "


def _httpx(mp, status=200, body=None, text=""):
    seen = []

    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, headers=None, **kw):
            seen.append({"url": url, "headers": headers, **kw})
            return SimpleNamespace(status_code=status, text=text or str(body), json=lambda: body or {})

    mp.setattr("httpx.AsyncClient", Client)
    return seen


def _stt(mp, convert=lambda audio, exe: FAKE_WAV, **kw):
    mp.setattr(M, "ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    mp.setattr(M, "to_wav16k", convert)
    return MuseStt(override_settings(mp, **{"meta_api_key": "mk", "openai_api_key": "sk-x", **kw}))


def test_request_keywords_language_bias_and_wav_upload(monkeypatch):
    seen = _httpx(monkeypatch, body={"transcript": "Tab Dolo 650", "turns": []})
    p = _stt(monkeypatch, muse_language_bias=("English", "Hindi"))
    t = _run(p.transcribe(b"webm-bytes", "d.webm", ["Dolo 650", "Pantoprazole"]))
    assert (t.text, t.engine) == ("Tab Dolo 650", "muse:muse-voice-transcribe-1.0")
    assert seen[0]["url"] == "https://api.meta.ai/v1/asr/transcribe"
    assert seen[0]["headers"] == {"Authorization": "Bearer mk"}  # never the OpenAI key
    name, req, ctype = seen[0]["files"]["request"]
    assert (name, ctype) == (None, "application/json")
    assert json.loads(req) == {"mode": "PUSH_TO_TALK", "model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV",
                               "languageBias": ["English", "Hindi"], "keywords": ["Dolo 650", "Pantoprazole"]}
    assert seen[0]["files"]["audio"] == ("dictation.wav", FAKE_WAV, "audio/wav")  # converted, not the webm


def test_no_keywords_without_hints(monkeypatch):
    seen = _httpx(monkeypatch, body={"transcript": "fever"})
    _run(_stt(monkeypatch).transcribe(b"x", "d.webm"))
    assert "keywords" not in json.loads(seen[0]["files"]["request"][1])


def test_failures_and_unavailability(monkeypatch):
    _httpx(monkeypatch, status=429, text="rate limit for mk")
    with pytest.raises(SttError) as e:
        _run(_stt(monkeypatch).transcribe(b"x", "d.webm"))
    assert str(e.value).startswith("Muse STT 429") and "mk" not in str(e.value)

    def broken(audio, exe):
        raise W.WavConvertError("ffmpeg exit 1: invalid data")
    seen = _httpx(monkeypatch, body={"transcript": "x"})
    with pytest.raises(SttError, match="audio conversion failed"):
        _run(_stt(monkeypatch, convert=broken).transcribe(b"x", "d.webm"))
    assert seen == []  # nothing is sent when conversion fails

    p = _stt(monkeypatch)
    monkeypatch.setattr(M, "ffmpeg_path", lambda: None)
    assert p.available() is False
    with pytest.raises(SttUnavailable, match="ffmpeg"):
        _run(p.transcribe(b"x", "d.webm"))
    with pytest.raises(SttUnavailable, match="META_API_KEY"):
        _run(_stt(monkeypatch, meta_api_key="").transcribe(b"x", "d.webm"))


def test_factory_wiring(monkeypatch):
    monkeypatch.setattr(M, "ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    s = override_settings(monkeypatch, stt_engine="muse", stt_chain=(), meta_api_key="mk")
    assert derive_chain(s) == ("muse", "faster-whisper") and "muse" in CLOUD
    assert make_stt(s).active_name() == "muse-api"


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_real_ffmpeg_turns_webm_into_16k_mono_wav():
    exe = shutil.which("ffmpeg")
    webm = subprocess.run([exe, "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=440:d=1:r=48000",
                           "-ac", "2", "-c:a", "libopus", "-f", "webm", "pipe:1"], capture_output=True).stdout
    out = W.to_wav16k(webm, exe)
    assert W.is_wav(out)
    channels, rate, bits = int.from_bytes(out[22:24], "little"), int.from_bytes(out[24:28], "little"), out[34]
    assert (channels, rate, bits) == (1, 16000, 16)
    with pytest.raises(W.WavConvertError):
        W.to_wav16k(b"not audio", exe)
