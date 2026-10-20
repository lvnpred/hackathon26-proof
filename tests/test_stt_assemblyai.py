import asyncio
from types import SimpleNamespace

import pytest

from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt import assemblyai as A
from doctor_dictation.providers.stt.assemblyai import AssemblyAiStt
from doctor_dictation.providers.stt.base import SttError, SttUnavailable
from doctor_dictation.providers.stt.factory import CLOUD, derive_chain, make_stt

_run = asyncio.run
BASE = "https://api.assemblyai.com/v2"


def _reply(status=200, body=None, text=""):
    return SimpleNamespace(status_code=status, text=text or str(body), json=lambda: body or {})


def _httpx(mp, polls, upload=None, submit=None):
    """Upload and submit answer once; each GET takes the next poll reply."""
    seen, polls = [], list(polls)

    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, headers=None, **kw):
            seen.append({"method": "POST", "url": url, "headers": headers, **kw})
            if url.endswith("/upload"):
                return upload or _reply(body={"upload_url": "https://cdn/u1"})
            return submit or _reply(body={"id": "t1", "status": "queued"})

        async def get(self, url, headers=None, **kw):
            seen.append({"method": "GET", "url": url, "headers": headers})
            return polls.pop(0)

    mp.setattr("httpx.AsyncClient", Client)
    mp.setattr(A, "POLL_SECONDS", 0)
    return seen


def _stt(mp, **kw):
    return AssemblyAiStt(override_settings(mp, **{"assemblyai_api_key": "aai-x", **kw}))


def test_upload_submit_poll_with_keyterms(monkeypatch):
    seen = _httpx(monkeypatch, [_reply(body={"status": "processing"}),
                                _reply(body={"status": "completed", "text": "Tab Metformin 500 mg"})])
    long_hint = "one two three four five six seven"  # 7 words: AssemblyAI would reject it
    t = _run(_stt(monkeypatch).transcribe(b"\x00", "d.webm", ["Metformin", "Dolo 650", long_hint]))
    assert (t.text, t.engine) == ("Tab Metformin 500 mg", "assemblyai:universal-3-5-pro")
    assert [(s["method"], s["url"]) for s in seen] == [
        ("POST", f"{BASE}/upload"), ("POST", f"{BASE}/transcript"),
        ("GET", f"{BASE}/transcript/t1"), ("GET", f"{BASE}/transcript/t1")]
    assert all(s["headers"] == {"authorization": "aai-x"} for s in seen)  # raw key, no Bearer
    assert seen[0]["content"] == b"\x00"
    assert seen[1]["json"] == {"audio_url": "https://cdn/u1", "speech_models": ["universal-3-5-pro"],
                               "language_code": "en", "keyterms_prompt": ["Metformin", "Dolo 650"]}


def test_medical_mode_and_model_and_no_hints(monkeypatch):
    seen = _httpx(monkeypatch, [_reply(body={"status": "completed", "text": "fever"})])
    _run(_stt(monkeypatch, assemblyai_model="universal-2", assemblyai_medical=True).transcribe(b"\x00", "d.webm"))
    assert seen[1]["json"] == {"audio_url": "https://cdn/u1", "speech_models": ["universal-2"],
                               "language_code": "en", "domain": "medical-v1"}  # no keyterms without hints


def test_failures_are_provider_errors_and_never_leak_the_key(monkeypatch):
    _httpx(monkeypatch, [], upload=_reply(401, text="bad key aai-x"))
    with pytest.raises(SttError) as e:
        _run(_stt(monkeypatch).transcribe(b"\x00", "d.webm"))
    assert str(e.value).startswith("AssemblyAI STT upload 401") and "aai-x" not in str(e.value)
    _httpx(monkeypatch, [_reply(body={"status": "error", "error": "audio too short"})])
    with pytest.raises(SttError, match="job failed: audio too short"):
        _run(_stt(monkeypatch).transcribe(b"\x00", "d.webm"))
    _httpx(monkeypatch, [_reply(body={"status": "processing"})] * 3)
    monkeypatch.setattr(A, "DEADLINE_SECONDS", -1)  # already past the deadline after the first poll
    with pytest.raises(SttError, match="timed out"):
        _run(_stt(monkeypatch).transcribe(b"\x00", "d.webm"))
    p = _stt(monkeypatch, assemblyai_api_key="")
    with pytest.raises(SttUnavailable, match="ASSEMBLYAI_API_KEY"):
        _run(p.transcribe(b"\x00", "d.webm"))
    assert p.available() is False


def test_factory_wiring(monkeypatch):
    s = override_settings(monkeypatch, stt_engine="assemblyai", stt_chain=(), assemblyai_api_key="aai-x")
    assert derive_chain(s) == ("assemblyai", "faster-whisper") and "assemblyai" in CLOUD
    assert make_stt(s).active_name() == "assemblyai-api"
