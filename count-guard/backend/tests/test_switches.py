"""Live switches (spec §6.7): each AI step says live, prepared or unavailable; a live failure never picks a fixture by file name."""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from app.adapters import spark as spark_mod
from app.adapters.sam import SamAdapter
from app.adapters.voice import VoiceAdapter
from app.config import get_settings
from app.journey import live, switches
from tests.test_flow_states import _new
from tests.test_p2_live import _keyed, _no_key


def _voice_down(monkeypatch):
    monkeypatch.setattr(live, "to_wav", lambda raw, content_type: raw)

    def boom(self, path, offset_ms=0, content_type="audio/wav"):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(VoiceAdapter, "transcribe", boom)


def test_unavailable_shape():
    assert switches.unavailable("no answer") == {"source": "unavailable", "why": "no answer"}


def test_switches_follow_the_key_by_default(tmp_path):
    for name in switches.NAMES:
        assert switches.is_live(_no_key(tmp_path), name) is False
        assert switches.is_live(_keyed(tmp_path), name) is True


def test_a_switch_turned_off_wins_over_the_key(tmp_path):
    keyed = replace(_keyed(tmp_path), voice_live=False, proof_live=False, spark_live=False)
    assert [switches.is_live(keyed, n) for n in ("voice", "proof", "spark")] == [False, False, False]
    # Turned on without a key, nothing can be called, so it stays off.
    no_key = replace(_no_key(tmp_path), voice_live=True)
    assert switches.is_live(no_key, "voice") is False


def test_cut_switches_are_read_from_switches(tmp_path, monkeypatch):
    monkeypatch.setattr(switches, "TRAY_LIVE", False)
    assert switches.is_live(_keyed(tmp_path), "tray") is False
    assert switches.is_live(_keyed(tmp_path), "setup") is True


@pytest.mark.parametrize("value, want", [("1", True), ("0", False), ("", None)])
def test_settings_read_the_switches_from_the_environment(tmp_path, monkeypatch, value, want):
    monkeypatch.setenv("COUNT_GUARD_DATA", str(tmp_path))
    for name in ("VOICE_LIVE", "PROOF_LIVE", "SPARK_LIVE"):
        monkeypatch.setenv(name, value)
    got = get_settings()
    assert (got.voice_live, got.proof_live, got.spark_live) == (want, want, want)


def test_live_transcribe_failure_never_uses_filename_fixture(tmp_path, monkeypatch):
    _voice_down(monkeypatch)
    out = live.transcribe(_keyed(tmp_path), b"x", "kumar-orders.wav", "audio/wav")
    assert out["source"] == "unavailable" and out["text"] is None and out["why"]
    assert [(c["model"], c["source"]) for c in out["calls"]] == [("voice", "unavailable")]


def test_switch_off_uses_prepared_and_labels_it(tmp_path, monkeypatch):
    def called(*a, **k):
        raise AssertionError("the live model was called")

    monkeypatch.setattr(VoiceAdapter, "transcribe", called)
    monkeypatch.setattr(spark_mod.SparkAdapter, "read_monitor", called)
    off = replace(_keyed(tmp_path), voice_live=False, proof_live=False)
    heard = live.transcribe(off, b"x", "kumar-orders.wav", "audio/wav")
    assert heard["source"] == "prepared" and heard["text"].startswith("Admit for open hernia")
    read = live.read_photo(off, "monitor", b"x", "monitor-88-54.png", "image/png")
    assert read["source"] == "prepared" and read["text"]
    # No key at all: the same prepared results, labelled the same way.
    assert live.transcribe(_no_key(tmp_path), b"x", "kumar-orders.wav", "audio/wav")["source"] == "prepared"


def test_read_photo_failure_live_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: [])

    def boom(self, url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(spark_mod.SparkAdapter, "read_monitor", boom)
    out = live.read_photo(_keyed(tmp_path), "monitor", b"x", "monitor-88-54.png", "image/png")
    assert out["source"] == "unavailable" and out["text"] is None and out["why"] == switches.NOT_CHECKED
    assert [(c["model"], c["source"]) for c in out["calls"]] == [("sam", "sam-3.1"), ("spark", "unavailable")]
    assert live.mode_of("unavailable") == "failed"


def test_dictation_upload_with_voice_down_is_an_error_to_retry(tmp_path, monkeypatch):
    from app.journey.media_api import _heard

    class Upload:
        content_type = "audio/wav"
        filename = "kumar-orders.wav"

        class file:
            @staticmethod
            def read(n):
                return b"RIFF"

    _voice_down(monkeypatch)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as err:
        _heard(_keyed(tmp_path), Upload(), None)
    assert err.value.status_code == 502


def test_all_switches_listed_in_models_route(tmp_path):
    client, _ = _new(tmp_path)
    got = client.get("/journey/models").json()
    assert got["live"] is False and got["voice"] is False
    assert got["switches"] == {name: False for name in switches.NAMES}
    assert set(switches.NAMES) == {"voice", "proof", "spark", "tray", "setup", "swabs", "medicines"}


def test_every_live_source_word_maps_to_live():
    for word in ("muse-voice-transcribe", "muse-spark-1.3", "sam-3.1"):
        assert live.mode_of(word) == "live", word
    assert (live.mode_of("prepared"), live.mode_of(switches.UNAVAILABLE)) == ("prepared", "failed")


@pytest.mark.parametrize("check, upload", [("tray", "swabs-closing.mp4"), ("setup", "tray-hernia.mp4"), ("swabs", "saline-setup.mp4")])
def test_sam_failure_live_uses_the_fixture_of_the_check_kind_not_the_file_name(tmp_path, monkeypatch, check, upload):
    monkeypatch.setattr(live, "clip_seconds", lambda p: 6)
    monkeypatch.setattr(live, "to_sam_clip", lambda s, o, f: None)

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(SamAdapter, "segment_video", boom)
    monkeypatch.setattr(SamAdapter, "segment_images", boom)
    want = live.prepared(switches.PREPARED_BY_CHECK[check])
    got = live.segment_clip(_keyed(tmp_path), tmp_path / "c.mp4", upload, ["x"], check=check)
    assert got["source"] == "prepared" and got["detections"] == want["detections"] and got["frames"] == want["frames"]
    assert [(c["model"], c["source"]) for c in got["calls"]] == [("sam", "prepared")]
    still = tmp_path / "p.png"
    still.write_bytes(b"x")
    got = live.segment_photos(_keyed(tmp_path), [still], ["x"], upload.replace(".mp4", ".png"), check=check)
    assert got["source"] == "prepared" and got["detections"] == want["detections"] and got["frames"] == want["stills"]


def test_sam_failure_live_without_a_check_kind_is_failed_not_a_file_name_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "clip_seconds", lambda p: 6)
    monkeypatch.setattr(live, "to_sam_clip", lambda s, o, f: None)

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(SamAdapter, "segment_video", boom)
    got = live.segment_clip(_keyed(tmp_path), tmp_path / "c.mp4", "tray-hernia.mp4", ["x"])
    assert got["source"] == "failed" and got["detections"] is None
