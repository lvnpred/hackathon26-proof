import asyncio
import os
from types import SimpleNamespace

import pytest

from doctor_dictation.config import get_settings, override_settings
from doctor_dictation.providers.stt.base import SttError, SttModelLoadError, SttNotImplemented, SttUnavailable
from doctor_dictation.providers.stt import local as L
from doctor_dictation.providers.stt import onnx as O
from doctor_dictation.providers.stt.local import LocalWhisperStt
from doctor_dictation.providers.stt.onnx import OnnxStt
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
    assert seen[1]["data"]["prompt"] == "Telmisartan. Metformin."
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
    assert calls[1][2]["initial_prompt"].endswith(". Telmisartan. Metformin.")
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


def test_onnx_unavailable_then_not_implemented(monkeypatch):
    monkeypatch.setattr(O, "status", lambda: (False, "model dir missing"))
    with pytest.raises(SttUnavailable, match="model dir missing"):
        _run(OnnxStt().transcribe(b"a", "d.webm"))
    monkeypatch.setattr(O, "status", lambda: (True, "ready"))
    with pytest.raises(SttNotImplemented, match="decode loop not implemented"):
        _run(OnnxStt().transcribe(b"a", "d.webm"))


# ---- B1 review fixes ----

def _client_returning(mp, reply):
    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, **kw): return reply

    mp.setattr("httpx.AsyncClient", Client)


def _not_json():
    raise ValueError("Expecting value")


def test_openai_200_with_a_non_json_body_is_a_provider_failure(monkeypatch):
    # Review #1: a captive portal answering 200 with HTML must fall through the chain, not crash.
    _client_returning(monkeypatch, SimpleNamespace(
        status_code=200, text="<html>captive portal</html>", json=_not_json))
    p = OpenAiStt(override_settings(monkeypatch, openai_api_key="sk-x"))
    with pytest.raises(SttError, match="non-JSON"):
        _run(p.transcribe(b"\x00", "d.webm"))


def test_openai_error_body_never_leaks_the_key(monkeypatch):
    # Review #2: a proxy that echoes the Authorization header must not put the key in our response.
    _client_returning(monkeypatch, SimpleNamespace(
        status_code=401, text="bad auth: Bearer sk-secret-key-123", json=_not_json))
    p = OpenAiStt(override_settings(monkeypatch, openai_api_key="sk-secret-key-123"))
    with pytest.raises(SttError) as e:
        _run(p.transcribe(b"\x00", "d.webm"))
    assert "sk-secret-key-123" not in str(e.value) and "[redacted]" in str(e.value)


def test_groq_uses_its_own_url_key_and_model(monkeypatch):
    from doctor_dictation.providers.stt.groq import GroqStt
    seen = _httpx(monkeypatch, body={"text": "fever"})
    p = GroqStt(override_settings(monkeypatch, groq_api_key="gsk-x", openai_api_key="sk-x"))
    t = _run(p.transcribe(b"\x00", "d.webm", ["Metformin"]))
    assert (t.text, t.engine) == ("fever", "groq-whisper-api")
    assert seen[0]["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert seen[0]["headers"] == {"Authorization": "Bearer gsk-x"}  # never the OpenAI key
    assert seen[0]["data"] == {"model": "whisper-large-v3", "language": "en", "prompt": "Metformin."}
    _httpx(monkeypatch, status=500)
    with pytest.raises(SttError) as bad:
        _run(p.transcribe(b"\x00", "d.webm"))
    assert str(bad.value).startswith("Groq STT 500: down") and "gsk-x" not in str(bad.value)
    p = GroqStt(override_settings(monkeypatch, groq_api_key="", groq_stt_model="whisper-large-v3-turbo"))
    with pytest.raises(SttUnavailable, match="GROQ_API_KEY"):
        _run(p.transcribe(b"\x00", "d.webm"))
    assert p._model == "whisper-large-v3-turbo"
