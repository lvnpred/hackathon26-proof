import asyncio

import pytest

from doctor_dictation.config import build_settings, get_settings, override_settings
from doctor_dictation.providers.stt.base import (
    SttChainError, SttError, SttModelLoadError, SttNotImplemented, SttUnavailable, Transcript)
from doctor_dictation.providers.stt.factory import (
    FallbackStt, derive_chain, failure_response, make_stt, success_body)

def test_stt_settings_and_override_helper(monkeypatch):
    monkeypatch.delenv("STT_CHAIN", raising=False)
    monkeypatch.delenv("ALLOW_STUB_PROVIDERS", raising=False)
    s = build_settings()
    assert (s.stt_chain, s.allow_stub_providers) == ((), False)
    monkeypatch.setenv("STT_CHAIN", " OpenAI, faster-whisper ,,")
    monkeypatch.setenv("ALLOW_STUB_PROVIDERS", "Yes")
    s = build_settings()
    assert (s.stt_chain, s.allow_stub_providers) == (("openai", "faster-whisper"), True)
    before = get_settings()
    with monkeypatch.context() as m:
        new = override_settings(m, stt_engine="onnx")
        assert get_settings() is new and new.stt_engine == "onnx"
    assert get_settings() is before  # undone with the monkeypatch


def _cfg(mp, **kw):
    base = dict(stt_engine="auto", stt_chain=(), openai_api_key="", allow_stub_providers=False)
    return override_settings(mp, **{**base, **kw})

class _Fake:
    def __init__(self, name, outcome):
        self.name, self._outcome, self.calls, self.pinned = name, outcome, [], 0
    def available(self): return True
    def after_earlier_failure(self): self.pinned += 1

    async def transcribe(self, audio, filename, hints=()):
        self.calls.append(tuple(hints))
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return Transcript(text=self._outcome, engine=self.name)

def _go(chain, hints=()):
    return asyncio.run(FallbackStt(chain).transcribe(b"a", "d.webm", hints))

def test_chain_derivation_and_stub_gating(monkeypatch):
    both = ("openai", "faster-whisper")
    expect = {"auto": both, "nonsense": both, "onnx": ("onnx",), "faster-whisper": ("faster-whisper",),
              "stub": ("stub",)}
    for engine, chain in expect.items():
        assert derive_chain(_cfg(monkeypatch, stt_engine=engine)) == chain, engine
    s = _cfg(monkeypatch, stt_engine="onnx", stt_chain=("faster-whisper", "openai", "browser"))
    assert make_stt(s).chain_names == ("faster-whisper", "openai", "browser")  # STT_CHAIN wins
    for kw in (dict(stt_chain=("whisperx",)), dict(stt_chain=("stub",)), dict(stt_engine="stub")):
        with pytest.raises(ValueError, match="unknown STT provider|ALLOW_STUB_PROVIDERS"):
            make_stt(_cfg(monkeypatch, **kw))
    stub = make_stt(_cfg(monkeypatch, stt_chain=("stub", "browser"), allow_stub_providers=True))
    assert stub.chain_names == ("stub", "browser") and stub.active_name() == "stub"
    monkeypatch.setenv("STUB_TRANSCRIPT", "tablet Paracetamol 650 mg")
    monkeypatch.setenv("STUB_DELAY_MS", "5")
    t = asyncio.run(stub.transcribe(b"a", "d.webm"))
    assert (t.text, t.engine) == ("tablet Paracetamol 650 mg", "stub")
    with pytest.raises(SttUnavailable):  # the browser marker never answers
        asyncio.run(stub.providers[1].transcribe(b"a", "d.webm"))

def test_chain_order_hints_and_the_after_failure_hook():
    a, b = _Fake("openai", "from cloud"), _Fake("faster-whisper", "from local")
    assert _go([a, b], ["Metformin"]).text == "from cloud"
    assert a.calls == [("Metformin",)] and b.calls == [] and b.pinned == 0
    b = _Fake("faster-whisper", "from local")
    assert _go([_Fake("openai", SttError("down")), b], ["Metformin"]).text == "from local"
    assert b.calls == [("Metformin",)] and b.pinned == 1  # a real failure pins small.en
    b = _Fake("faster-whisper", "from local")
    _go([_Fake("openai", SttUnavailable("no key")), b])
    assert b.pinned == 0  # an unconfigured cloud is not a failure
    with pytest.raises(SttChainError) as e:
        _go([_Fake("openai", SttError("down")), _Fake("faster-whisper", SttUnavailable("no pkg"))])
    assert [n for n, _ in e.value.failures] == ["openai", "faster-whisper"]


def test_failure_bodies_match_the_old_route():
    def fail(chain, *pairs):
        return failure_response(SttChainError(list(pairs)), chain)

    auto = ("openai", "faster-whisper")
    s, b = fail(auto, ("openai", SttError("down")), ("faster-whisper", SttUnavailable("x")))
    assert (s, b) == (502, {"error": "Cloud STT failed and no local STT available: down",
                            "fallback": "browser"})
    s, b = fail(auto, ("openai", SttError("down")), ("faster-whisper", SttModelLoadError("load boom")))
    assert (s, b) == (500, {"error": "load boom"})  # no fallback key, as before
    s, b = fail(auto, ("openai", SttError("down")), ("faster-whisper", SttError("Server STT failed: x")))
    assert (s, b) == (500, {"error": "Server STT failed: x", "fallback": "browser"})
    s, b = fail(("onnx",), ("onnx", SttNotImplemented("ONNX decode loop not implemented yet")))
    assert (s, b["fallback"]) == (501, "browser") and "decode loop" in b["error"]
    s, b = fail(("onnx",), ("onnx", SttUnavailable("model dir missing")))
    assert (s, b["error"]) == (503, "ONNX STT not configured: model dir missing")
    assert b["hint"].startswith("See doctor_dictation/requirements-onnx.txt")
    s, b = fail(("faster-whisper",), ("faster-whisper", SttUnavailable("x")))
    assert s == 503 and b["error"].startswith("STT_ENGINE=faster-whisper but") and "hint" in b
    s, b = fail(auto, ("openai", SttUnavailable("k")), ("faster-whisper", SttUnavailable("x")))
    assert s == 503 and b["error"].startswith("No server STT installed") and b["fallback"] == "browser"
    cloud = success_body(Transcript(text="fever", engine="openai-whisper-api"))
    assert list(cloud) == ["transcript", "engine", "transcript_sha256"]
    loc = success_body(Transcript(text="fever", engine="local:small.en", language="en",
                                  duration=1.0, extra={"decode": {"beam_size": 5}}))
    assert list(loc) == ["transcript", "language", "duration", "engine", "transcript_sha256", "decode"]


def test_chain_reports_availability_like_a_single_provider():
    class Off(_Fake):
        def available(self): return False

    assert FallbackStt([Off("openai", "x"), _Fake("faster-whisper", "y")]).available() is True
    assert FallbackStt([Off("openai", "x")]).available() is False
    assert FallbackStt([]).available() is False


def test_groq_engine_falls_back_locally_and_counts_as_cloud(monkeypatch):
    assert derive_chain(_cfg(monkeypatch, stt_engine="groq")) == ("groq", "faster-whisper")
    chain = make_stt(_cfg(monkeypatch, stt_engine="groq", groq_api_key="gsk-x"))
    assert chain.chain_names == ("groq", "faster-whisper") and chain.active_name() == "groq-whisper-api"
    err = SttChainError([("groq", SttError("down")), ("faster-whisper", SttUnavailable("no pkg"))])
    status, body = failure_response(err, ("groq", "faster-whisper"))
    assert status == 502 and body["error"].startswith("Cloud STT failed")  # cloud, not a local 500
