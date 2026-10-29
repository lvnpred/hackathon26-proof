"""SAM 3.1 cost preview and the Muse Spark-alone baseline parser."""

from __future__ import annotations

import pytest

from app.baseline import baseline_prompt, parse_baseline
from app.spend import sam_video_cost


def test_short_clip_bills_the_50_frame_minimum_per_concept():
    cost = sam_video_cost(10, fps=2, concepts=5)
    assert cost["frames"] == 20
    assert cost["billed_frames"] == 250
    assert cost["usd"] == 0.05


def test_long_clip_bills_every_frame():
    cost = sam_video_cost(300, fps=10, concepts=2)
    assert cost["billed_frames"] == 6000
    assert cost["usd"] == 1.2


def test_cost_rejects_empty_input():
    with pytest.raises(ValueError):
        sam_video_cost(0, fps=2, concepts=1)


def test_baseline_prompt_names_items_and_forbids_advice():
    prompt = baseline_prompt(["lap sponge", "gauze swab"])
    assert "lap sponge, gauze swab" in prompt
    assert "Do not give medical advice" in prompt


def test_parse_baseline_reads_fenced_json():
    text = '```json\n{"Lap Sponge": {"opened": 10, "bucket": 9, "tray": 0, "unaccounted": 1}}\n```'
    assert parse_baseline(text) == {"lap sponge": {"opened": 10, "bucket": 9, "tray": 0, "unaccounted": 1}}


def test_parse_baseline_drops_non_numbers_instead_of_guessing():
    text = '{"lap sponge": {"opened": "ten", "bucket": 9, "tray": true}}'
    assert parse_baseline(text) == {"lap sponge": {"bucket": 9}}


def test_parse_baseline_unreadable_is_empty():
    assert parse_baseline("I could not see the tray.") == {}
    assert parse_baseline("{not json}") == {}
