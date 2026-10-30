"""The fixture recorder (D2, R13): pure functions and main with faked model calls. Never a live call."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests.test_p3_video import _keyed, no_network  # noqa: F401  (fixture)

SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "record_fixtures.py"
spec = importlib.util.spec_from_file_location("record_fixtures", SCRIPT)
rec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rec)

LIVE = [{"model": "sam", "model_id": "sam-3.1", "source": "sam-3.1", "ms": 900}]


def test_same_counts_overwrite_and_drop_handmade():
    old = {"detections": {"scissors": {"count": 3, "at_s": 2.0}}, "frames": [], "handmade": True}
    live_result = {"detections": {"scissors": {"count": 3, "at_s": 1.5}}, "frames": [{"t": 1.5, "index": 3, "objects": []}], "raw": {"sam": []}, "calls": [{"ms": 900}, {"ms": 100}]}
    assert rec.differences(old, live_result, "clip") == []
    new = rec.candidate(old, live_result, "clip")
    assert "handmade" not in new and new["ms"] == 1000 and new["detections"] == old["detections"]
    assert new["frames"] == live_result["frames"] and new["raw"] == {"sam": []}


def test_different_counts_are_reported_not_written():
    old = {"detections": {"needle holder": {"count": 2, "at_s": 1.5}}}
    live_result = {"detections": {"needle holder": {"count": 3, "at_s": 1.5}}}
    assert rec.differences(old, live_result, "clip") == ["needle holder: fixture 2, live 3"]
    assert rec.candidate(old, live_result, "clip")["detections"] == live_result["detections"]


def test_a_missing_concept_counts_as_zero_and_a_failed_call_blocks():
    old = {"detections": {"scissors": {"count": 3, "at_s": 2.0}}}
    assert rec.differences(old, {"detections": {}}, "clip") == ["scissors: fixture 3, live 0"]
    failed = {"detections": {"scissors": {"count": 3, "at_s": 2.0}}, "calls": [{"model": "sam", "source": "failed", "ms": 5}]}
    assert rec.differences(old, failed, "clip") == ["sam call did not run live (failed)"]
    assert rec.differences(old, {"detections": None, "calls": []}, "clip") == ["no live result"]


def test_still_fills_stills_and_keeps_the_clip_evidence():
    old = {"detections": {"scissors": {"count": 3, "at_s": 2.0}}, "handmade": True}
    clip = rec.candidate(old, {"detections": old["detections"], "frames": ["c"], "raw": {"sam": ["c"]}, "calls": [{"ms": 10, "model_id": "sam-3.1"}]}, "clip")
    both = rec.candidate(clip, {"detections": old["detections"], "frames": ["s"], "raw": {"sam": ["s"]}, "calls": [{"ms": 99}]}, "still")
    assert both["frames"] == ["c"] and both["stills"] == ["s"] and both["raw"] == {"sam": ["c"]}
    assert both["ms"] == 10 and both["model_id"] == "sam-3.1"


MONITOR_OLD = {"text": '{"sbp": 88, "dbp": 54, "hr": 112}', "handmade": True,
               "regions": [{"bbox": [0, 0, 1, 1], "label": "SBP", "value": "88", "row": 0}, {"bbox": [0, 0, 1, 1], "label": "DBP", "value": "54", "row": 1}, {"bbox": [0, 0, 1, 1], "label": "HR", "value": "112", "row": 2}]}


def _monitor_live(sbp="88"):
    regions = [{"bbox": [0.1, 0.1, 0.2, 0.1], "label": "SBP", "value": sbp, "row": 0}, {"bbox": [0.1, 0.3, 0.2, 0.1], "label": "DBP", "value": "54", "row": 1}, {"bbox": None, "label": "HR", "value": "112", "row": 2}]
    return {"text": f'{{"sbp": {sbp}, "dbp": 54, "hr": 112}}', "regions": regions, "raw": {"sam": [], "spark": "x"}, "calls": [{"ms": 700, "model_id": "sam-3.1"}, {"ms": 300, "model_id": "muse-spark-1.3"}]}


def test_photo_values_compare_by_label_and_the_candidate_takes_live_regions():
    assert rec.differences(MONITOR_OLD, _monitor_live(), "monitor") == []
    assert rec.differences(MONITOR_OLD, _monitor_live("90"), "monitor") == ["SBP: fixture 88, live 90"]
    new = rec.candidate(MONITOR_OLD, _monitor_live(), "monitor")
    assert new["regions"][0]["bbox"] == [0.1, 0.1, 0.2, 0.1] and new["text"] == MONITOR_OLD["text"]
    assert new["ms"] == 1000 and "handmade" not in new


def test_strip_values_are_counted_by_value():
    old = {"text": "t", "regions": [{"bbox": None, "label": "Paracetamol 500 mg", "value": "Paracetamol 500 mg", "row": 0}]}
    live_result = {"text": "t2", "regions": [{"bbox": [0, 0, 1, 1], "label": "Cetirizine 10 mg", "value": "Cetirizine 10 mg", "row": 0}]}
    assert rec.differences(old, live_result, "strip") == [
        "Paracetamol 500 mg: fixture 1, live 0", "Cetirizine 10 mg: fixture 0, live 1"]


def test_no_fixture_is_a_difference():
    assert rec.differences({}, {"detections": {"gauze swab": {"count": 1}}}, "clip") == ["no fixture to compare with"]


def test_refuses_without_key_or_spend(monkeypatch, capsys):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert rec.main(["--spend"]) == 1
    monkeypatch.setenv("MODEL_API_KEY", "k")
    monkeypatch.setattr(rec, "clip_seconds", lambda p: 6.0)
    assert rec.main([]) == 1
    assert "--spend" in capsys.readouterr().out


def test_the_asset_table_and_request_count():
    stems = [a[0] for a in rec.ASSETS]
    assert stems == ["tray-hernia", "tray-hernia", "tray-hernia-full", "tray-hernia-full", "saline-setup", "swabs-closing",
                     "monitor-88-54", "strip-paracetamol", "meds-kumar", "meds-iyer"]
    assert [a[2] for a in rec.ASSETS] == ["clip", "still", "clip", "still", "clip", "clip", "monitor", "strip", "strip", "strip"]
    concepts = {s: list(range(n)) for s, n in {"tray-hernia": 7, "tray-hernia-full": 7, "saline-setup": 4, "swabs-closing": 1}.items()}
    assert rec.request_count(rec.ASSETS, concepts) == 41


@pytest.fixture
def run(tmp_path, monkeypatch):
    """main() against a temp prepared dir and faked seams; returns (exit code, dir, calls made)."""
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    media = tmp_path / "media"
    media.mkdir()
    for name in ("a.mp4", "a.png", "m.png"):
        (media / name).write_bytes(b"x")
    assets = (("a", media / "a.mp4", "clip"), ("a", media / "a.png", "still"), ("m", media / "m.png", "monitor"), ("gone", media / "gone.mp4", "clip"))
    (prepared / "a.json").write_text(json.dumps({"detections": {"scissors": {"count": 3, "at_s": 2.0}}, "handmade": True}))
    (prepared / "m.json").write_text(json.dumps(MONITOR_OLD))
    calls = []

    def go(live_count, sbp="88", capsys=None):
        det = {"scissors": {"count": live_count, "at_s": 1.0}}
        monkeypatch.setenv("MODEL_API_KEY", "k")
        monkeypatch.setattr(rec, "ASSETS", assets)
        monkeypatch.setattr(rec, "PREPARED", prepared)
        monkeypatch.setattr(rec, "clip_seconds", lambda p: 6.0)
        monkeypatch.setattr(rec, "get_settings", lambda: _keyed(tmp_path))
        monkeypatch.setattr(rec.live, "segment_clip", lambda s, p, f, c, live_ok=True: calls.append(("clip", f, c, live_ok)) or {"detections": det, "frames": ["c"], "raw": {}, "calls": LIVE})
        monkeypatch.setattr(rec.live, "segment_photos", lambda s, ps, c, f, live_ok=True: calls.append(("still", f, c, live_ok)) or {"detections": det, "frames": ["s"], "raw": {}, "calls": LIVE})
        monkeypatch.setattr(rec.live, "read_photo", lambda s, r, raw, f, ct, live_ok=True: calls.append((r, f, live_ok)) or _monitor_live(sbp))
        return rec.main(["--spend"])

    return go, prepared, calls


def test_main_overwrites_when_counts_match(run, capsys):
    go, prepared, calls = run
    assert go(3) == 0
    new = json.loads((prepared / "a.json").read_text())
    assert "handmade" not in new and new["frames"] == ["c"] and new["stills"] == ["s"]
    assert json.loads((prepared / "m.json").read_text())["regions"][0]["bbox"] == [0.1, 0.1, 0.2, 0.1]
    assert not list(prepared.glob("*.live.json"))
    assert ("clip", "a.mp4", ["scissors"], True) in calls and ("still", "a.png", ["scissors"], True) in calls and ("monitor", "m.png", True) in calls
    out = capsys.readouterr().out
    assert "skipped" in out and "gone.mp4" in out and "digital display" in out


def test_main_leaves_a_fixture_alone_when_counts_differ(run, capsys):
    go, prepared, _ = run
    before = (prepared / "a.json").read_text()
    assert go(4, sbp="90") == 2
    assert (prepared / "a.json").read_text() == before
    live_a = json.loads((prepared / "a.live.json").read_text())
    assert live_a["detections"]["scissors"]["count"] == 4
    assert (prepared / "m.live.json").exists() and json.loads((prepared / "m.json").read_text())["handmade"] is True
    out = capsys.readouterr().out
    assert "scissors: fixture 3, live 4" in out and "SBP: fixture 88, live 90" in out
