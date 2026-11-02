"""Theatre panels (spec §6.4, §6.5): drug given by voice, the simulated vitals strip, the context card.

Hard stop: nothing heard writes `count.pack_opened` or `count.closing`. A heard pack is a draft until a person confirms it.
"""

from __future__ import annotations

from app.journey import states
from app.morning.brownbag import read_strip
from tests.test_flow_states import _count, _new, _surgery, _to_theatre, _to_ward

DOCTOR = "Dr. A. Rao (synthetic)"
NURSE = "Nurse Asha (synthetic)"
BANNER = "Research demo — not for clinical use"


def _theatre(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    return client, eid


def _url(eid, path=""):
    return f"/journey/episodes/{eid}/theatre{path}"


def _say(client, eid, text, by=DOCTOR):
    return client.post(_url(eid, "/drug"), data={"text": text, "by": by})


def _events(client, eid):
    return client.app.state.morning.events(eid)


def _of(client, eid, kind):
    return [e for e in _events(client, eid) if e["event_type"] == kind]


def test_drug_phrase_becomes_grounded_row(tmp_path):
    client, eid = _theatre(tmp_path)
    assert _say(client, eid, "lignocaine two percent, five ml, local infiltration").status_code == 200
    [draft] = _of(client, eid, "druglog.parsed")
    row = draft["payload"]
    assert (row["generic"], row["strength"], row["amount"], row["unit"]) == ("lignocaine", "2%", 5, "ml")
    assert row["grounded"] is True and row["route"] == "local infiltration"
    panel = client.get(_url(eid)).json()
    [shown] = panel["drugs"]
    assert shown["id"] == draft["id"] and shown["given"] is None


def test_drug_needs_confirm_before_given(tmp_path):
    client, eid = _theatre(tmp_path)
    _say(client, eid, "lignocaine two percent, five ml, local infiltration")
    assert _of(client, eid, "drug.given") == []  # heard is a draft only
    [draft] = _of(client, eid, "druglog.parsed")
    done = client.post(_url(eid, f"/drug/{draft['id']}/confirm"), json={"by": DOCTOR})
    assert done.status_code == 200
    [given] = _of(client, eid, "drug.given")
    assert given["payload"]["by"] == DOCTOR and given["payload"]["draft_id"] == draft["id"]
    assert client.get(_url(eid)).json()["drugs"][0]["given"]["by"] == DOCTOR
    again = client.post(_url(eid, f"/drug/{draft['id']}/confirm"), json={"by": DOCTOR})
    assert again.status_code == 409
    assert client.post(_url(eid, "/drug/nope/confirm"), json={"by": DOCTOR}).status_code == 404


def test_heard_drug_from_prepared_audio_is_labelled(tmp_path):
    client, eid = _theatre(tmp_path)
    # Voice is off in tests: the prepared transcript of the sample file stands in, labelled (spec §6.7).
    audio = ("drug-lignocaine.wav", b"RIFF0000WAVE", "audio/wav")
    done = client.post(_url(eid, "/drug"), data={"by": DOCTOR}, files={"file": audio})
    assert done.status_code == 200
    [draft] = _of(client, eid, "druglog.parsed")
    assert draft["payload"]["source"] == "prepared" and draft["payload"]["generic"] == "lignocaine"
    assert _of(client, eid, "drug.given") == []


def test_spoken_pack_phrase_is_heard(tmp_path):
    client, eid = _theatre(tmp_path)
    assert _say(client, eid, "opening twenty swabs", by=NURSE).status_code == 200
    [heard] = _of(client, eid, "count.pack_heard")
    assert heard["payload"]["n"] == 20 and heard["payload"]["item_type"] == "swab"
    assert _of(client, eid, "count.pack_opened") == [] and _of(client, eid, "druglog.parsed") == []


def test_heard_pack_never_counts_until_confirmed(tmp_path):
    client, eid = _theatre(tmp_path)
    assert _surgery(client, eid, "began").status_code == 200
    before = states.stay_opened(_events(client, eid))
    _say(client, eid, "opening twenty swabs", by=NURSE)
    events = _events(client, eid)
    assert states.stay_opened(events) == before is None
    assert states.count_gate(events) == "none"
    assert not any(e["event_type"] in ("count.pack_opened", "count.closing") for e in events)
    [heard] = _of(client, eid, "count.pack_heard")
    assert client.post(_url(eid, f"/pack/{heard['id']}/confirm"), json={"by": "  "}).status_code == 422
    done = client.post(_url(eid, f"/pack/{heard['id']}/confirm"), json={"by": NURSE})
    assert done.status_code == 200
    [opened] = _of(client, eid, "count.pack_opened")
    assert opened["payload"]["by"] == NURSE and opened["payload"]["quantity"] == 20
    assert states.stay_opened(_events(client, eid)) == 20
    assert _of(client, eid, "count.closing") == []
    assert client.post(_url(eid, f"/pack/{heard['id']}/confirm"), json={"by": NURSE}).status_code == 409


def _drop_with_context(client, eid):
    client.app.state.morning.append(eid, "brownbag.med_found", read_strip("metoprolol", "25 mg"), ts_ms=0)
    assert _count(client, eid, "opened", quantity=20).status_code == 200
    _say(client, eid, "lignocaine two percent, five ml, local infiltration")
    [draft] = _of(client, eid, "druglog.parsed")
    client.post(_url(eid, f"/drug/{draft['id']}/confirm"), json={"by": DOCTOR})
    for _ in range(4):
        assert client.post(_url(eid, "/vitals/step"), json={}).status_code == 200


def test_vitals_drop_raises_card_with_three_sources(tmp_path):
    client, eid = _theatre(tmp_path)
    assert client.post(_url(eid, "/tier"), json={"on": True}).status_code == 200
    _drop_with_context(client, eid)
    readings = _of(client, eid, "vitals.reading")
    assert [r["payload"]["systolic"] for r in readings] == [120, 118, 110, 86]
    assert all(r["payload"]["source"] == "simulated" for r in readings)
    assert client.post(_url(eid, "/vitals/step"), json={}).status_code == 409  # the strip has ended
    got = client.get(_url(eid, "/card"))
    assert got.status_code == 200
    body = got.json()
    assert body["banner"] == BANNER
    card = body["card"]
    text = card["text"]
    assert text.startswith("BP 86/50, down 28% in 4 min.")
    assert "lignocaine" in text and "metoprolol" in text and "20 swabs" in text
    assert card["wording"] == "template" and card["source"] == "prepared"  # SPARK_LIVE off: the template, labelled
    assert not any(word in text.lower() for word in ("give", "consider", "should", "recommend"))


def test_card_written_when_tier_turned_on_after_the_drop(tmp_path):
    client, eid = _theatre(tmp_path)
    _drop_with_context(client, eid)
    assert client.get(_url(eid, "/card")).status_code == 404
    assert client.post(_url(eid, "/tier"), json={"on": True}).json()["decision_tier"] is True
    assert client.get(_url(eid, "/card")).json()["card"]["text"].startswith("BP 86/50")
    client.post(_url(eid, "/tier"), json={"on": True})
    assert len(_of(client, eid, "vitals.card")) == 1


def test_card_404_when_tier_off(tmp_path):
    client, eid = _theatre(tmp_path)
    client.post(_url(eid, "/tier"), json={"on": True})
    _drop_with_context(client, eid)
    assert client.get(_url(eid, "/card")).status_code == 200
    assert client.post(_url(eid, "/tier"), json={"on": False}).status_code == 200
    assert client.get(_url(eid, "/card")).status_code == 404
    assert client.get(_url(eid)).json()["tier"] is False


def test_theatre_routes_refuse_outside_theatre(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    calls = [
        client.get(_url(eid)),
        _say(client, eid, "lignocaine two percent, five ml"),
        client.post(_url(eid, "/drug/x/confirm"), json={"by": DOCTOR}),
        client.post(_url(eid, "/pack/x/confirm"), json={"by": NURSE}),
        client.post(_url(eid, "/vitals/step"), json={}),
        client.post(_url(eid, "/tier"), json={"on": True}),
        client.get(_url(eid, "/card")),
    ]
    for response in calls:
        assert response.status_code == 409, response.text
        assert response.json()["error"] == "not in theatre"
    assert client.get("/journey/episodes/missing/theatre").status_code == 404


def test_theatre_lines_read_as_plain_words(tmp_path):
    import re

    client, eid = _theatre(tmp_path)
    client.post(_url(eid, "/tier"), json={"on": True})
    _drop_with_context(client, eid)
    _say(client, eid, "opening twenty swabs", by=NURSE)
    timeline = client.get(f"/journey/episodes/{eid}").json()["timeline"]
    ours = [t for t in timeline if t["type"] in ("drug.given", "count.pack_heard", "vitals.reading", "druglog.parsed")]
    assert len(ours) == 7
    for item in ours:
        assert not re.search(r"\b[a-z]{3,}\.[a-z]{3,}\b|_", item["plain"]), item["plain"]
    assert any("(simulated)" in t["plain"] for t in ours)
    assert all(t["patient"] == "" for t in ours if t["type"] in ("druglog.parsed", "count.pack_heard"))


AI_BYS = ("Count Guard AI", "AI (on behalf of Ward 4)", "count-guard ai.")


def test_ai_by_cannot_confirm_a_heard_pack(tmp_path):
    """Final fix I1: the pack confirm refuses an AI or camera `by`, as /count and /correct do (U10)."""
    client, eid = _theatre(tmp_path)
    _say(client, eid, "opening twenty swabs", by=NURSE)
    [heard] = _of(client, eid, "count.pack_heard")
    for by in AI_BYS:
        r = client.post(_url(eid, f"/pack/{heard['id']}/confirm"), json={"by": by})
        assert r.status_code == 422, (by, r.text)
    assert _of(client, eid, "count.pack_opened") == []
    assert client.post(_url(eid, f"/pack/{heard['id']}/confirm"), json={"by": NURSE}).status_code == 200


def test_ai_by_cannot_confirm_a_heard_drug(tmp_path):
    client, eid = _theatre(tmp_path)
    _say(client, eid, "lignocaine two percent, five ml, local infiltration")
    [draft] = _of(client, eid, "druglog.parsed")
    for by in AI_BYS:
        r = client.post(_url(eid, f"/drug/{draft['id']}/confirm"), json={"by": by})
        assert r.status_code == 422, (by, r.text)
    assert _of(client, eid, "drug.given") == []
    assert client.post(_url(eid, f"/drug/{draft['id']}/confirm"), json={"by": DOCTOR}).status_code == 200
