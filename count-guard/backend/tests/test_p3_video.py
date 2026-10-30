"""P3 video seam: planned vs seen, prepared results, faked SAM. Never a live call."""

from __future__ import annotations

import re
import shutil
import subprocess

import httpx
import pytest

from app.adapters.sam import SamAdapter
from app.journey import live, video
from app.journey.procedures import SETUP_TEMPLATES, tray_plan
from app.media_pipeline import cut_frames

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)


def bare(result: dict) -> dict:
    """A model result without its `calls` (test_ai_calls.py) and its evidence (test_evidence.py)."""
    return {k: v for k, v in result.items() if k not in ("calls", "frames", "raw", "handmade", "regions")}


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


def _rec(frame, oid, label="needle holder", score=0.9):
    return {"frame_index": frame, "object_id": oid, "label": label, "bbox": [0.1, 0.2, 0.3, 0.4], "score": score}


def test_expected_for_tray_groups_by_concept():
    plan = tray_plan("hernia-repair")
    rows = video.expected_for_tray(plan)
    by = {r["concept"]: r for r in rows}
    assert by["needle holder"]["planned"] == sum(
        i["qty"] for i in plan["instruments"] if i["concept"] == "needle holder"
    )
    assert by["retractor"]["planned"] == 4 and len(by["retractor"]["names"]) == 4
    assert [r["concept"] for r in rows][0] == "scalpel handle"
    assert "Mosquito forceps" in video.unchecked_for_tray(plan)
    assert "Knife handle" not in video.unchecked_for_tray(plan)


def test_expected_for_setup_has_four_rows():
    rows = video.expected_for_setup("saline")
    assert [r["concept"] for r in rows] == [i["concept"] for i in SETUP_TEMPLATES["saline"]["items"]]
    assert all(r["planned"] == 1 for r in rows)


def test_summarize_max_per_frame_with_id_switch():
    records = [_rec(f, oid) for f in range(4) for oid in ((1, 2) if f < 2 else (3, 4))]
    records.append(_rec(0, 9, score=0.2))
    records.append(_rec(0, 5, label="scissors"))
    out = video.summarize(records, 2, 0.45, ["needle holder"])
    assert out == {"needle holder": {"count": 2, "at_s": 0.0}}


def test_summarize_unseen_and_no_score_and_later_max():
    records = [_rec(2, 1, score=None), _rec(3, 1), _rec(3, 2)]
    out = video.summarize(records, 2, 0.45, ["needle holder", "towel clip"])
    assert out["needle holder"] == {"count": 2, "at_s": 1.5}
    assert out["towel clip"] == {"count": 0, "at_s": None}


def test_compare_ok_mismatch_none():
    expected = [
        {"concept": "needle holder", "names": ["Needle holder"], "planned": 3},
        {"concept": "scissors", "names": ["Scissors"], "planned": 2},
    ]
    ok = video.compare(expected, {"needle holder": {"count": 3, "at_s": 1.0}, "scissors": {"count": 2, "at_s": 0.5}})
    assert ok["match"] == "ok" and ok["missing"] == [] and ok["why"] == "Every planned item was seen in the clip."
    bad = video.compare(expected, {"needle holder": {"count": 2, "at_s": 1.0}})
    assert bad["match"] == "mismatch" and bad["missing"] == ["needle holder", "scissors"]
    assert bad["why"] == "Not seen in the clip: needle holder (planned 3, seen 2); scissors (planned 2, seen 0)."
    assert bad["rows"][1]["seen"] == 0
    none = video.compare(expected, None)
    assert none["match"] == "none" and none["why"] == video.NOT_CHECKED
    assert none["why"] == "The clip was not checked: no model key and no prepared result for this clip."
    assert all(r["seen"] is None for r in none["rows"])
    failed = video.compare(expected, None, "failed")
    assert failed["why"] == video.NO_ANSWER == "The clip was not checked: the model did not answer."


def test_prepared_tray_flags_only_the_needle_holder():
    expected = video.expected_for_tray(tray_plan("hernia-repair"))
    flagged = video.compare(expected, live.prepared("tray-hernia.mp4")["detections"])
    assert flagged["missing"] == ["needle holder"]
    full = video.compare(expected, live.prepared("tray-hernia-full.mp4")["detections"])
    assert full["missing"] == [] and full["match"] == "ok"
    setup = video.compare(video.expected_for_setup("saline"), live.prepared("saline-setup.mp4")["detections"])
    assert setup["match"] == "ok"


def test_prepared_at_s_within_clip():
    for stem in ("tray-hernia", "tray-hernia-full", "saline-setup"):
        for cell in live.prepared(f"{stem}.mp4")["detections"].values():
            assert 0 <= cell["at_s"] < 6


def test_segment_clip_no_key(tmp_path):
    settings = _no_key(tmp_path)
    got = live.segment_clip(settings, tmp_path / "x.mp4", "tray-hernia.mp4", ["needle holder"])
    assert got["source"] == "prepared" and got["detections"]["needle holder"]["count"] == 2
    for name in ("IMG_0001.mov", "../../x.mp4"):
        assert bare(live.segment_clip(settings, tmp_path / "x.mp4", name, ["needle holder"])) == {
            "detections": None, "source": "none"}


def _fake_media(monkeypatch, seconds=6):
    monkeypatch.setattr(live, "clip_seconds", lambda p: seconds)
    monkeypatch.setattr(live, "to_sam_clip", lambda s, o, f: None)


def test_segment_clip_live_faked(tmp_path, monkeypatch):
    _fake_media(monkeypatch)
    calls = []

    def fake(self, path, concepts):
        calls.append(concepts)
        return [_rec(0, 1), _rec(0, 2)]

    monkeypatch.setattr(SamAdapter, "segment_video", fake)
    got = live.segment_clip(_keyed(tmp_path), tmp_path / "c.mp4", "tray-hernia.mp4", ["needle holder"])
    assert bare(got) == {"detections": {"needle holder": {"count": 2, "at_s": 0.0}}, "source": "sam-3.1"}
    # live_ok False skips the adapter (P3-R6)
    calls.clear()
    got = live.segment_clip(_keyed(tmp_path), tmp_path / "c.mp4", "tray-hernia.mp4", ["needle holder"], live_ok=False)
    assert calls == [] and got["source"] == "prepared"


@pytest.mark.parametrize("exc", [RuntimeError("x"), httpx.ConnectError("x"), KeyError("id"), TypeError("x"), ValueError("x"), OSError("x")])
def test_segment_clip_keyed_failure_falls_back(tmp_path, monkeypatch, exc):
    _fake_media(monkeypatch)

    def boom(self, path, concepts):
        raise exc

    monkeypatch.setattr(SamAdapter, "segment_video", boom)
    keyed = _keyed(tmp_path)
    got = live.segment_clip(keyed, tmp_path / "c.mp4", "tray-hernia.mp4", ["needle holder"])
    assert got["source"] == live.FALLBACK and got["detections"]["needle holder"]["count"] == 2
    assert bare(live.segment_clip(keyed, tmp_path / "c.mp4", "IMG_0001.mov", ["needle holder"])) == {
        "detections": None, "source": "failed"}


def test_segment_clip_unreadable_clip_and_too_long(tmp_path, monkeypatch):
    def unreadable(p):
        raise SystemExit("ffprobe could not read")

    monkeypatch.setattr(live, "clip_seconds", unreadable)
    got = live.segment_clip(_keyed(tmp_path), tmp_path / "c.mp4", "IMG_1.mov", ["scissors"])
    assert bare(got) == {"detections": None, "source": "unreadable"}
    _fake_media(monkeypatch, seconds=300)
    with pytest.raises(live.NotHeard) as err:
        live.segment_clip(_keyed(tmp_path), tmp_path / "c.mp4", "tray-hernia.mp4", ["scissors"])
    assert err.value.status == 400 and err.value.detail == live.LONG_CLIP


def test_frame_times():
    rows = [{"seen": 2, "at_s": 1.5}, {"seen": 1, "at_s": 0.5}, {"seen": 3, "at_s": 1.5}, {"seen": 0, "at_s": None}]
    assert video.frame_times(rows) == [0.5, 1.5]
    assert video.frame_times([{"seen": 0, "at_s": None}]) == [0.0]
    assert video.frame_times([{"seen": None, "at_s": None}]) == []
    many = [{"seen": 1, "at_s": float(i)} for i in range(9)]
    assert video.frame_times(many) == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_cut_frames_with_real_ffmpeg(tmp_path):
    clip = tmp_path / "t.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    out = tmp_path / "frames"
    out.mkdir()
    files = cut_frames(clip, [0.0, 1.0], out)
    assert len(files) == 2 and all(f.read_bytes()[:3] == b"\xff\xd8\xff" for f in files)


def test_cut_frames_missing_clip_raises(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    with pytest.raises(RuntimeError):
        cut_frames(tmp_path / "nope.mp4", [0.0], tmp_path)


def test_why_strings_have_no_advice_words():
    expected = video.expected_for_tray(tray_plan("hernia-repair"))
    det = live.prepared("tray-hernia.mp4")["detections"]
    texts = [
        video.compare(expected, det)["why"],
        video.compare(expected, live.prepared("tray-hernia-full.mp4")["detections"])["why"],
        video.compare(expected, None)["why"],
        video.compare(expected, None, "failed")["why"],
        video.compare(expected, None, "unreadable")["why"],
        video.NO_FRAMES, live.LONG_CLIP,
    ]
    for text in texts:
        assert not ADVICE.search(text), text


@pytest.mark.parametrize("exc", [SystemExit("x"), FileNotFoundError("ffprobe"), ValueError("N/A")])
def test_unreadable_clip_is_not_prepared_and_not_a_model_failure(tmp_path, monkeypatch, exc):
    def probe(p):
        raise exc

    monkeypatch.setattr(live, "clip_seconds", probe)
    got = live.segment_clip(_keyed(tmp_path), tmp_path / "c.mp4", "tray-hernia.mp4", ["scissors"])
    assert bare(got) == {"detections": None, "source": "unreadable"}
    why = video.compare([{"concept": "scissors", "names": ["S"], "planned": 1}], None, got["source"])["why"]
    assert why == "The clip could not be read."


def test_subprocess_timeouts(tmp_path, monkeypatch):
    from app import media_pipeline, spend

    def slow(cmd, **kw):
        assert kw["timeout"] == 60
        raise subprocess.TimeoutExpired(cmd, 60)

    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(RuntimeError, match="timed out"):
        cut_frames(tmp_path / "c.mp4", [0.0], tmp_path)
    with pytest.raises(SystemExit):
        spend.clip_seconds(tmp_path / "c.mp4")


def test_cut_frames_past_the_end_raises(tmp_path, monkeypatch):
    done = subprocess.CompletedProcess([], 0, "", "")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: done)
    with pytest.raises(RuntimeError, match="No frame"):
        cut_frames(tmp_path / "c.mp4", [99.0], tmp_path)
