"""P2 model seam: prepared results without a key, faked adapters with one. Never a live call."""

from __future__ import annotations

import re

import httpx
import pytest

from app.adapters.sam import SamAdapter
from app.adapters import spark as spark_mod
from app.adapters.spark import MONITOR_PROMPT, STRIP_PROMPT
from app.adapters.voice import VoiceAdapter
from app.journey import live

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
ORDERS_TEXT = (
    "Admit for open hernia repair. Paracetamol 1 g every 6 hours, strip photo as proof. "
    "BP and pulse every 1 hour, lower systolic limit 90."
)


def bare(result: dict) -> dict:
    """A model result without its `calls` list (covered in test_ai_calls.py)."""
    return {k: v for k, v in result.items() if k not in ("calls", "regions", "raw", "handmade")}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _no_key(tmp_path):
    from app.config import Settings

    return Settings(
        data_dir=tmp_path, meta_api_key="", meta_base="https://api.meta.ai/v1",
        sam_model="sam-3.1", voice_model="muse-voice-transcribe-1.0", spark_model="muse-spark-1.3",
        baseten_api_key="", spark_open_base="https://inference.baseten.co/v1",
        spark_open_model="meta-models/muse-spark-open-1026", low_confidence=0.45,
        unannounced_window_ms=30_000, lost_after_frames=4, sam_fps=2, dd_base="http://127.0.0.1:9",
    )


def _keyed(tmp_path):
    from dataclasses import replace

    return replace(_no_key(tmp_path), meta_api_key="test-key")


def test_safe_stem_rejects_paths_and_odd_names():
    assert live.safe_stem("../../etc/passwd.wav") is None
    assert live.safe_stem("Kumar Orders.WAV") is None
    assert live.safe_stem("a" * 200 + ".wav") is None
    assert live.safe_stem("..\\x.wav") is None
    assert live.safe_stem(None) is None
    assert live.safe_stem("kumar-orders.wav") == "kumar-orders"
    assert live.safe_stem("KUMAR-ORDERS.WAV") == "kumar-orders"


def test_no_key_uses_prepared_transcript(tmp_path):
    out = live.transcribe(_no_key(tmp_path), b"x", "kumar-orders.wav", "audio/wav")
    assert bare(out) == {"text": ORDERS_TEXT, "source": "prepared"}


def test_no_key_unknown_audio_is_409_with_type_hint(tmp_path):
    with pytest.raises(live.NotHeard) as err:
        live.transcribe(_no_key(tmp_path), b"x", "recording.webm", "audio/webm")
    assert err.value.status == 409
    assert "Type what was said" in err.value.detail


def test_key_calls_faked_voice_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "to_wav", lambda raw, content_type: raw)
    monkeypatch.setattr(
        VoiceAdapter, "transcribe",
        lambda self, path, offset_ms=0, content_type="audio/wav": [
            {"text": "Paracetamol one gram", "t0_ms": 0, "t1_ms": 1},
            {"text": "given to bed 4", "t0_ms": 2, "t1_ms": 3},
        ],
    )
    out = live.transcribe(_keyed(tmp_path), b"x", "recording.webm", "audio/webm")
    assert bare(out) == {"text": "Paracetamol one gram given to bed 4", "source": "muse-voice-transcribe"}


def test_key_adapter_error_is_502(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "to_wav", lambda raw, content_type: raw)

    def boom(self, path, offset_ms=0, content_type="audio/wav"):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(VoiceAdapter, "transcribe", boom)
    out = live.transcribe(_keyed(tmp_path), b"x", "a.webm", "audio/webm")
    assert out["source"] == "unavailable" and out["why"] == live.UNREACHABLE  # the route turns this into a 502


def test_read_photo_prepared_and_unknown(tmp_path):
    s = _no_key(tmp_path)
    out = live.read_photo(s, "strip", b"x", "strip-paracetamol.png", "image/png")
    assert out["source"] == "prepared"
    assert out["text"] == '{"strips": [{"name": "Paracetamol", "strength": "500 mg"}]}'
    out = live.read_photo(s, "monitor", b"x", "monitor-88-54.png", "image/png")
    assert out["text"] == '{"sbp": 88, "dbp": 54, "hr": 112}'
    assert bare(live.read_photo(s, "strip", b"x", "IMG_0001.jpg", "image/jpeg")) == {
        "text": None, "source": "none",
    }


def test_read_photo_key_uses_faked_spark(tmp_path, monkeypatch):
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: [])
    monkeypatch.setattr(spark_mod.SparkAdapter, "read_monitor", lambda self, url: "seen:" + url[:15])
    out = live.read_photo(_keyed(tmp_path), "monitor", b"x", "m.png", "image/png")
    assert bare(out) == {"text": "seen:data:image/png;", "source": "muse-spark-1.3"}

    def boom(self, url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(spark_mod.SparkAdapter, "read_strips", boom)
    out = live.read_photo(_keyed(tmp_path), "strip", b"x", "s.png", "image/png")
    assert bare(out) == {"text": None, "source": "unavailable", "why": "Not checked — model unavailable"}


def test_spark_text(tmp_path, monkeypatch):
    assert live.spark_text(_no_key(tmp_path), "p") is None
    monkeypatch.setattr(spark_mod.SparkAdapter, "write", lambda self, p: "ok " + p)
    assert live.spark_text(_keyed(tmp_path), "p") == "ok p"
    monkeypatch.setattr(
        spark_mod.SparkAdapter, "write", lambda self, p: (_ for _ in ()).throw(RuntimeError("x"))
    )
    assert live.spark_text(_keyed(tmp_path), "p") is None


def test_to_wav_passes_wav_through():
    assert live.to_wav(b"RIFFx", "audio/wav") == b"RIFFx"


def test_prompts_forbid_advice():
    assert "Do not give medical advice." in MONITOR_PROMPT
    assert "Do not give medical advice." in STRIP_PROMPT


def test_detail_strings_have_no_advice_words(tmp_path):
    details = []
    for name in ("recording.webm",):
        with pytest.raises(live.NotHeard) as err:
            live.transcribe(_no_key(tmp_path), b"x", name, "audio/webm")
        details.append(err.value.detail)
    import app.journey.live as mod

    details.append(mod.UNREACHABLE)
    assert len(details) == 2
    assert not any(ADVICE.search(d) for d in details)
