"""The theatre panel says, before a click, whether that click will write the context card and whether Spark is asked
(care-app clarity §4.1, ruling P10: a step line never claims a model call that does not happen). Never a live call."""

from __future__ import annotations

from tests.test_evidence_payload import _keyed, _of, no_network  # noqa: F401  (fixture)
from tests.test_flow_states import _count, _new, _to_theatre
from tests.test_flow_tasks import _url


def _panel(client, eid):
    return client.get(_url(eid, "theatre")).json()


def _step(client, eid):
    assert client.post(_url(eid, "theatre/vitals/step"), json={}).status_code == 200


def _theatre(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    assert _count(client, eid, "opened", quantity=20).status_code == 200
    return client, eid


def test_card_due_only_on_the_reading_that_writes_the_card(tmp_path):
    client, eid = _theatre(tmp_path)
    client.post(_url(eid, "theatre/tier"), json={"on": True})
    seen = []
    while not _panel(client, eid)["strip_done"]:
        due = _panel(client, eid)["card_due"]
        before = len(_of(client, eid, "vitals.card"))
        _step(client, eid)
        wrote = len(_of(client, eid, "vitals.card")) > before
        seen.append(due)
        assert (due is not None) == wrote, (len(seen), due, wrote)
    assert seen.count("rules") == 1 and "spark" not in seen  # SPARK_LIVE off: the template, no model asked


def test_card_due_names_spark_when_spark_is_live(tmp_path, monkeypatch):
    from app.journey import live
    client, eid = _theatre(tmp_path)
    _keyed(client)
    monkeypatch.setattr(live, "spark_text", lambda settings, prompt: "Please give fluids now.")
    client.post(_url(eid, "theatre/tier"), json={"on": True})
    dues = []
    while not _panel(client, eid)["strip_done"]:
        dues.append(_panel(client, eid)["card_due"])
        _step(client, eid)
    assert dues.count("spark") == 1 and "rules" not in dues


def test_no_card_due_with_the_tier_off_then_turning_it_on_is(tmp_path):
    client, eid = _theatre(tmp_path)
    while not _panel(client, eid)["strip_done"]:
        assert _panel(client, eid)["card_due"] is None  # the tier is off: no reading writes a card
        _step(client, eid)
    assert _panel(client, eid)["card_on_tier"] == "rules"  # the drop happened: turning the tier on writes it now
    client.post(_url(eid, "theatre/tier"), json={"on": True})
    assert len(_of(client, eid, "vitals.card")) == 1
    assert _panel(client, eid)["card_on_tier"] is None  # written once per stay
