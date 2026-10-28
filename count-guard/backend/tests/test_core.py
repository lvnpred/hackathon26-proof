"""Rules, parser, zones, and the five scripted clips."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.core.parser import parse_utterance
from app.core.zones import zone_for_bbox
from app.engine import Engine, id_switch_count
from app.scenarios import ZONES, eval_clips, get_scenario
from app.store import Store


def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        meta_api_key="",
        meta_base="https://api.meta.ai/v1",
        sam_model="sam-3.1",
        voice_model="muse-voice-transcribe-1.0",
        spark_model="muse-spark-1.3",
        baseten_api_key="",
        spark_open_base="https://inference.baseten.co/v1",
        spark_open_model="meta-models/muse-spark-open-1026",
        low_confidence=0.45,
        unannounced_window_ms=30_000,
        lost_after_frames=4,
        sam_fps=2,
    )


def engine(tmp_path: Path) -> Engine:
    return Engine(Store(tmp_path / "countguard.db"), settings(tmp_path))


def test_parser_add_and_closing_count():
    parsed = parse_utterance("Adding 10 lap sponges")
    assert parsed["adds"] == [
        {"item_type": "lap sponge", "quantity": 10, "action": "add", "zone": "tray"}
    ]
    assert parsed["needs_model"] is False

    closing = parse_utterance("Closing count, ten.")
    assert closing["phase"] == "closing"
    assert closing["counts"][0]["quantity"] == 10
    assert closing["counts"][0]["zone"] == "bucket"
    assert closing["counts"][0]["item_type"] is None

    tray = parse_utterance("Closing count, two on the tray.")
    assert tray["counts"][0]["zone"] == "tray"
    assert tray["counts"][0]["quantity"] == 2

    gauze = parse_utterance("opening twenty swabs")
    assert gauze["adds"][0]["item_type"] == "gauze swab"
    assert gauze["adds"][0]["quantity"] == 20

    assert parse_utterance("the light is bright")["needs_model"] is False


def test_zone_centers_stay_in_their_zone():
    assert zone_for_bbox([0.05, 0.22, 0.04, 0.04], ZONES) == "tray"
    assert zone_for_bbox([0.44 + 4 * 0.045, 0.22, 0.04, 0.04], ZONES) == "field"
    assert zone_for_bbox([0.74 + 4 * 0.045, 0.44, 0.04, 0.04], ZONES) == "bucket"


def _open_rules(result: dict) -> set[tuple[str, str | None]]:
    return {
        (row["rule_id"], row["item_type"])
        for row in result["discrepancies"]
        if row["status"] == "open"
    }


def _ledger_map(result: dict) -> dict[str, dict]:
    return {row["item_type"]: row for row in result["ledger"]}


@pytest.mark.parametrize("name", ["clip1", "clip2", "clip3", "clip4", "clip5", "worked", "demo"])
def test_scenario(tmp_path, name):
    scenario = get_scenario(name)
    app = engine(tmp_path)
    case = app.create_case(name, scenario["item_types"])
    result = app.replay(case["id"], scenario)
    expect = scenario["expect"]
    assert _open_rules(result) == set(expect["rules"])
    got = _ledger_map(result)
    for item_type, counts in expect["ledger"].items():
        row = got[item_type]
        for key, value in counts.items():
            assert row[key] == value, f"{name} {item_type} {key}: {row[key]} != {value}"
    assert id_switch_count(app.store.events(case["id"])) == expect["id_switches"]
    assert result["gate"]["status"] == expect["gate"]
