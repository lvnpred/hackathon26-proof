"""Every prepared fixture uses known keys, and its frames agree with its counts (C6)."""

from __future__ import annotations

import json

from app.journey import video
from app.journey.live import PREPARED_DIR

ALLOWED = {"transcript", "text", "detections", "frames", "stills", "regions", "raw", "ms", "model_id", "handmade"}


def test_every_fixture_uses_known_keys_and_counts_match_frames():
    for path in sorted(PREPARED_DIR.glob("*.json")):
        if path.name.endswith(".live.json"):
            continue
        data = json.loads(path.read_text())
        assert set(data) <= ALLOWED, path.name
        for key, photos in (("frames", False), ("stills", True)):
            if data.get(key) is None:
                continue
            concepts = list(data["detections"])
            counts = video.summarize(video.records_of(data[key]), 1 if photos else 2, 0.45, concepts)
            assert {c: v["count"] for c, v in counts.items()} == {c: v["count"] for c, v in data["detections"].items()}, path.name
            for frame in data[key]:
                for o in frame["objects"]:
                    assert all(0 <= v <= 1 for v in o["bbox"]) and isinstance(o["kept"], bool)


def test_the_three_clip_fixtures_are_handmade_with_frames_and_stills():
    for stem in ("tray-hernia", "tray-hernia-full", "saline-setup", "swabs-closing"):
        data = json.loads((PREPARED_DIR / f"{stem}.json").read_text())
        assert data["handmade"] is True and len(data["frames"]) == 12
        assert [f["t"] for f in data["frames"]] == [n / 2 for n in range(12)]
        assert len(data["stills"]) == 1 and data["stills"][0]["t"] is None


def test_the_hernia_clip_has_two_ignored_needle_holder_boxes():
    data = json.loads((PREPARED_DIR / "tray-hernia.json").read_text())
    ignored = [(f["t"], o) for f in data["frames"] for o in f["objects"] if not o["kept"]]
    assert [(t, o["id"], o["score"], o["label"]) for t, o in ignored] == [(2.0, "9", 0.32, "needle holder"), (2.5, "9", 0.32, "needle holder")]
