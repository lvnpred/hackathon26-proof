"""The guide tells the screen the next plain-language step."""

import re
from pathlib import Path

from app.morning.guide import build_guide, explain_event
from app.site import catalog
from tests.test_care_demo import _client

CG = Path(__file__).resolve().parents[2]


def test_product_map_links_every_feature_to_a_care_page(tmp_path):
    """Task 16: the older screens are archived, so every link is a care route and every API a mounted one."""
    product = catalog()
    app_jsx = (CG / "frontend" / "src" / "App.jsx").read_text(encoding="utf8")
    routes = set(re.findall(r'path="(/[a-z-]*)"', app_jsx))
    assert {f["href"] for f in product["features"]} | {a["start"] for a in product["audiences"]} <= routes
    assert product["banner"].startswith("Research demo")
    paths = _client(tmp_path).app.openapi()["paths"]
    for feature in product["features"]:
        assert (CG / feature["code"]).is_file(), feature["code"]
        method, path = feature["api"].split()
        path = path.replace("{id}", "{episode_id}")
        assert method.lower() in paths.get(path, {}), feature["api"]


def test_empty_morning_starts_at_the_strips():
    guide = build_guide([])
    assert guide["done"] == 0
    assert guide["steps"][0]["current"] is True
    assert guide["steps"][0]["href"] == "/opd"
    assert guide["next_href"] == "/opd"
    assert "this patient only" in guide["rule"].lower()
    assert guide["summary"].startswith("For This patient:")


def test_a_closing_count_is_said_in_words():
    line = explain_event(
        {
            "event_type": "count.closing",
            "payload": {"opened": 20, "returned": 19, "unaccounted": 1},
        }
    )
    assert line == "Closing count: opened 20, back 19, unaccounted 1."


def test_finished_steps_move_the_current_marker():
    events = [
        {"event_type": "brownbag.med_found", "payload": {"generic": "metoprolol", "strength": "25 mg", "grounded": True, "drug_class": "beta-blocker"}},
        {"event_type": "count.pack_opened", "payload": {"quantity": 20, "item_type": "swab"}},
    ]
    guide = build_guide(events)
    assert guide["done"] == 2
    assert guide["steps"][2]["id"] == "count"
    assert guide["steps"][2]["current"] is True
    assert "bucket" in guide["summary"]
