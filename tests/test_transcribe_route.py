from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.providers.stt import local as L

AUDIO = {"audio": ("t.webm", b"\x00\x01", "audio/webm")}


def _cfg(mp, **kw):
    base = dict(stt_engine="auto", stt_chain=(), openai_api_key="", allow_stub_providers=False)
    return override_settings(mp, **{**base, **kw})


def test_stub_chain_answers_and_is_refused_without_the_flag(monkeypatch):
    _cfg(monkeypatch, stt_chain=("stub",), allow_stub_providers=True)
    monkeypatch.setenv("STUB_TRANSCRIPT", "fever and cough")
    r = TestClient(M.app).post("/api/transcribe", files=AUDIO)
    assert r.status_code == 200, r.text
    assert (r.json()["transcript"], r.json()["engine"]) == ("fever and cough", "stub")
    assert len(r.json()["transcript_sha256"]) == 64
    _cfg(monkeypatch, stt_chain=("stub",))
    r = TestClient(M.app).post("/api/transcribe", files=AUDIO)
    assert r.status_code == 500 and r.json()["fallback"] == "browser"
    assert r.json()["error"].startswith("STT misconfigured: ") and "ALLOW_STUB_PROVIDERS" in r.json()["error"]


def test_health_stt_fields_keep_their_shape(monkeypatch):
    _cfg(monkeypatch, stt_engine="faster-whisper")
    monkeypatch.setattr(L, "faster_whisper_available", lambda: False)
    h = TestClient(M.app).get("/api/health").json()
    assert h["stt_engine_requested"] == "faster-whisper"
    assert h["stt_engine_active"] == h["stt_engine"] == "unavailable:faster-whisper"
    assert h["stt_decode"] == {k: v for k, v in L.STT_DECODE.items() if k != "initial_prompt"}
    assert h["stt_decode"]["beam_size"] == 5 and h["stt_decode"]["vad_filter"] is True
    monkeypatch.setattr(L, "faster_whisper_available", lambda: True)
    h = TestClient(M.app).get("/api/health").json()
    assert h["stt_engine"] == f"local:{h['whisper_model']}"


def test_cloud_200_with_html_body_answers_502_with_the_browser_fallback(monkeypatch):
    # Review #1 end to end: the page must still get {"fallback": "browser"} so it retries with Web Speech.
    from types import SimpleNamespace

    def not_json():
        raise ValueError("Expecting value")

    class Client:
        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

        async def post(self, url, headers=None, **kw):
            return SimpleNamespace(status_code=200, text="<html>portal</html>", json=not_json)

    monkeypatch.setattr("httpx.AsyncClient", Client)
    monkeypatch.setattr(L, "faster_whisper_available", lambda: False)
    _cfg(monkeypatch, openai_api_key="sk-x")
    r = TestClient(M.app).post("/api/transcribe", files=AUDIO)
    assert r.status_code == 502, r.text
    assert r.json()["fallback"] == "browser" and "non-JSON" in r.json()["error"]
