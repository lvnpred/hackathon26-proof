"""P3 sample data: cited hernia tray and saline set-up templates, the loader, and procedure validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from app import config
from app.journey import procedures, states
from tests.test_flow_states import ADMIT_CHECKS, _move, _new, _to_ward, _view

ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
CLIPS = Path(__file__).resolve().parents[2] / "eval" / "p3" / "clips.json"
CLIP_KEYS = {"name", "url", "licence", "licence_url", "allows_demo", "downloaded", "note"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _rows(template: dict) -> list[dict]:
    return template.get("instruments", []) + template.get("swabs", []) + template.get("items", [])


def _strings(value, skip_url=True):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, inner in value.items():
            if skip_url and key == "url":
                continue
            yield from _strings(inner, skip_url)
    elif isinstance(value, list):
        for inner in value:
            yield from _strings(inner, skip_url)


def test_templates_load_and_cite():
    for template in [*procedures.PROCEDURE_TEMPLATES.values(), *procedures.SETUP_TEMPLATES.values()]:
        ids = {source["id"] for source in template["sources"]}
        assert ids and len(ids) == len(template["sources"])
        for row in _rows(template):
            assert row["source"] in ids, row
        for source in template["sources"]:
            assert source["url"].startswith("https://")
            assert source["took"].strip()


def test_concepts_are_known():
    tray = {i["concept"] for i in procedures.PROCEDURE_TEMPLATES["hernia-repair"]["instruments"]} - {None}
    assert tray <= set(config.TRAY_CONCEPTS)
    assert "needle holder" in tray
    assert next(i for i in procedures.PROCEDURE_TEMPLATES["hernia-repair"]["instruments"] if i["concept"] == "needle holder")["qty"] >= 1
    setup = {i["concept"] for i in procedures.SETUP_TEMPLATES["saline"]["items"]}
    assert setup <= set(config.SETUP_CONCEPTS)
    assert config.TRAY_CONCEPTS[: len(config.SAM_CONCEPTS)] == config.SAM_CONCEPTS


def test_tray_plan_shape():
    plan = procedures.tray_plan("hernia-repair")
    template = procedures.PROCEDURE_TEMPLATES["hernia-repair"]
    assert plan["template"] == "hernia-repair"
    assert plan["title"] == "Open inguinal hernia repair"
    assert plan["swab_total"] == sum(s["packs"] * s["pack_size"] for s in plan["swabs"]) > 0
    assert plan["expected_minutes"] == template["expected_minutes"]
    assert plan["note"] == template["note"] and "open incisional" in plan["note"]
    assert {set(i) == {"name", "qty", "concept"} for i in plan["instruments"]} == {True}
    assert plan["sources"] == [{"id": s["id"], "title": s["title"], "url": s["url"]} for s in template["sources"]]
    with pytest.raises(KeyError):
        procedures.tray_plan("knee")


def test_setup_for():
    assert procedures.setup_for({"title": "Saline 1 litre over 2 hours, video check of the set-up"}) == "saline"
    assert procedures.setup_for({"title": "Paracetamol 1 g"}) is None


def test_no_advice_in_sample_data():
    templates = [*procedures.PROCEDURE_TEMPLATES.values(), *procedures.SETUP_TEMPLATES.values()]
    for template in templates:
        for text in _strings(template):
            assert not ADVICE.search(text), text
    for source in ("hernia-repair.json", "saline-setup.json"):
        raw = json.loads((Path(procedures.__file__).parent / "sample_data" / source).read_text())
        assert all(not ADVICE.search(t) for t in _strings(raw))


def test_clips_record():
    record = json.loads(CLIPS.read_text())
    assert record["searched"] and all(isinstance(s, str) and s for s in record["searched"])
    for clip in record["clips"]:
        assert set(clip) == CLIP_KEYS
        assert not clip["downloaded"] or clip["allows_demo"]
        assert clip["url"].startswith("https://")


def test_procedure_validation_rejects_bad_template():
    with pytest.raises(ValueError):
        procedures.Template.model_validate({"key": "x", "title": "X", "expected_minutes": 5, "instruments": [], "swabs": [],
                                            "count_points": [], "sources": [{"id": 1, "url": "http://x", "title": "t", "took": "t"}], "note": "n"})


def test_unknown_procedure_is_422(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    response = _move(client, eid, "theatre", procedure="knee")
    assert response.status_code == 422
    assert _view(client, eid)["state"] == "ward"


def test_procedures_view_unchanged(tmp_path):
    client, eid = _new(tmp_path)
    assert _view(client, eid)["procedures"] == {"hernia-repair": "Open inguinal hernia repair"}
    assert states.PROCEDURES == {k: t["title"] for k, t in procedures.PROCEDURE_TEMPLATES.items()}
