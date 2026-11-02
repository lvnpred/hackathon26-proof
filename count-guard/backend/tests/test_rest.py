"""Dwell count and spoken pack (the route tests are archived with the morning routes)."""

from __future__ import annotations

from app.morning.count_rules import demo_frames, fresh_state, observe, replay
from app.morning.intents import parse_pack


def test_wave_shorter_than_dwell_does_not_count():
    state = fresh_state()
    frames = [
        {"t_ms": 0, "track_id": "wave", "zone": "bucket", "frame_id": "a"},
        {"t_ms": 1, "track_id": "wave", "zone": "bucket", "frame_id": "b"},
        {"t_ms": 2, "track_id": "wave", "zone": "field", "frame_id": "c"},
    ]
    emitted = []
    for frame in frames:
        emitted.extend(observe(state, frame))
    assert emitted == []


def test_replay_counts_nineteen_and_names_the_missing_swab():
    events = replay(demo_frames(), opened=20)
    outs = [event for event in events if event["event_type"] == "count.item_out"]
    closing = events[-1]["payload"]
    assert len(outs) == 19
    assert closing["opened"] == 20
    assert closing["returned"] == 19
    assert closing["unaccounted"] == 1
    assert closing["track_id"] == "swab-20"
    assert closing["frame_id"] == "field-swab-20"


def test_opening_twenty_swabs_is_a_pack():
    parsed = parse_pack("opening twenty swabs")
    assert parsed["quantity"] == 20
    assert parsed["item_type"] == "swab"
    assert parse_pack("lignocaine 5 ml iv") is None
