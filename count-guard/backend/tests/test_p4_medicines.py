"""P4 Task 3: the medicine photo. Strips matched to the prescription by exact name, each named with its schedule."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from app.adapters import spark as spark_mod
from app.journey import ask_api, proof
from app.journey.ask_api import NO_MEDICINES
from app.journey.ask import ask_view
from app.journey.stories import plain
from app.journey.medicines import dose_rows, match_medicines, record_holds
from app.journey.rx import document_for, from_document
from app.main import create_app
from app.morning.strips import parse_strip_text
from tests.test_care_demo import _client
from tests.test_flow_states import DISCHARGE_CHECKS, _move
from tests.test_flow_tasks import DOC, _ack, _sign, _url
from tests.test_p2_live import _keyed
from tests.test_p4_ask import _home, _patients

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
ADVICE = re.compile(r"\b(give|take|stop|increase|reduce|start|administer|consider)\b", re.I)
KUMAR_STRIPS = [
    {"name": "Metoprolol", "strength": "25 mg"}, {"name": "Amlodipine", "strength": "5 mg"},
    {"name": "Pantoprazole", "strength": "40 mg"}, {"name": "Cetirizine", "strength": "10 mg"},
]
WHY_KUMAR = "3 of 4 medicines in the photo are on your prescription. Flagged: Cetirizine 10 mg."
NO_HOME = "A medicines photo is checked once the visit is closed or you are home."
NONE_HELD = " Your record holds no orders yet."
DOSE = [{"by": "Dr. A. Rao (synthetic)", "items": [
    {"kind": "dose", "name": "Paracetamol", "amount": "1 g", "every_h": 6, "text": "Paracetamol 1 g every 6 h"}]}]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _rx(label="R. Kumar, 58 M (synthetic)"):
    return from_document(document_for(label), source="demo")


def _strips(*pairs):
    return parse_strip_text(json.dumps({"strips": [{"name": n, "strength": s} for n, s in pairs]}))


def _post(client, eid, name="meds-kumar.png", content=PNG, kind="image/png"):
    return client.post(_url(eid, "ask/medicines"), files={"file": (name, content, kind)}, data={"at_ms": "3000"})


def _iyer_home(client, eid):
    body = {"summary": "Recovering well.", "by": DOC, "at_ms": 0}
    assert client.post(_url(eid, "discharge/sign"), json=body).status_code == 200
    assert _move(client, eid, "home", checklist=DISCHARGE_CHECKS).status_code == 200


def test_match_names_each_with_its_schedule():
    out = match_medicines(_strips(*[(s["name"], s["strength"]) for s in KUMAR_STRIPS]), _rx())
    rows = out["rows"]
    assert [r["prescribed"] for r in rows] == [True, True, True, False]
    amlodipine = rows[1]
    assert amlodipine["schedule"] == "1 in the morning; After food; for 30 days"
    assert amlodipine["why"] == "On your prescription: Tab. Amlodipine 5 mg, 1 in the morning; After food; for 30 days."
    assert rows[3]["flag"] == "not_prescribed" and rows[3]["medicine"] is None
    assert rows[3]["why"] == "Cetirizine 10 mg is not on your prescription from Dr. A. Rao (synthetic). Ask Dr. Rao about it."
    assert out["match"] == "mismatch" and out["why"] == WHY_KUMAR


def test_short_names_never_match():
    out = match_medicines(_strips(("Amlo", "5 mg"), ("Pan", "40 mg"), ("Para", "500 mg")), _rx())
    assert [r["flag"] for r in out["rows"]] == ["not_prescribed"] * 3
    assert not any(r["prescribed"] for r in out["rows"])


def test_strength_differs_is_flagged():
    out = match_medicines(_strips(("Amlodipine", "10 mg")), _rx())
    row = out["rows"][0]
    assert row["prescribed"] is True and row["flag"] == "strength_differs"
    assert row["why"] == "The strip reads Amlodipine 10 mg. The prescription says Tab. Amlodipine 5 mg."
    assert out["match"] == "mismatch" and out["why"].endswith("Flagged: Amlodipine 10 mg.")


def test_no_strips_is_none():
    out = match_medicines([], _rx())
    assert out == {"rows": [], "match": "none", "why": proof.NO_STRIP}


def test_all_prescribed_is_ok():
    out = match_medicines(_strips(("Metoprolol", "25 mg")), _rx())
    assert out["match"] == "ok" and out["why"] == "1 of 1 medicines in the photo are on your prescription."


def test_route_offline_kumar_and_iyer(tmp_path):
    client = _client(tmp_path)
    ids = _patients(client)
    kumar, iyer = ids["4"], ids["7"]
    _home(client, kumar)
    view = _post(client, kumar).json()
    got = view["ask"]["medicines"][-1]
    assert got["source"] == "prepared" and len(got["rows"]) == 4 and got["match"] == "mismatch"
    assert got["why"] == WHY_KUMAR
    assert got["photo"]["url"].startswith(f"/journey/episodes/{kumar}/photos/")
    assert client.get(got["photo"]["url"]).status_code == 200
    _iyer_home(client, iyer)
    got = _post(client, iyer, "meds-iyer.png").json()["ask"]["medicines"][-1]
    flags = {r["read"]: r["flag"] for r in got["rows"]}
    assert flags["Ibuprofen 400 mg"] == "not_prescribed"
    assert [r["flag"] for r in got["rows"]].count(None) == 3
    assert all(r["schedule"] for r in got["rows"] if r["prescribed"])
    event = client.app.state.morning.events(iyer)[-1]
    assert event["event_type"] == "medicines.read" and event["payload"]["by"] == "S. Iyer, 64 F (synthetic)"
    assert plain(event).startswith("Medicines photo: ") and event["payload"]["why"] in plain(event)


def test_route_refusals(tmp_path):
    client = _client(tmp_path)
    ids = _patients(client)
    kumar, das = ids["4"], ids["9"]
    assert client.post(_url(kumar, "rx/demo"), json={"at_ms": 0}).status_code == 200
    refused = _post(client, kumar)
    assert refused.status_code == 409 and refused.json()["detail"] == NO_HOME
    assert _move(client, das, "clinic_done").status_code == 200
    refused = _post(client, das)
    assert refused.status_code == 409 and refused.json()["detail"] == NO_MEDICINES + NONE_HELD
    _home(client, kumar)
    got = _post(client, kumar, "IMG_0001.png").json()["ask"]["medicines"][-1]
    assert got["match"] == "none" and got["source"] == "none" and got["rows"] == []
    assert client.get(got["photo"]["url"]).status_code == 200
    assert _post(client, kumar, content=b"not an image").status_code == 400


def test_live_read_and_cut_switch(tmp_path, monkeypatch):
    keyed = _keyed_client(tmp_path)
    kumar2 = _patients(keyed)["4"]
    _home(keyed, kumar2)
    calls = []
    reply = json.dumps({"strips": [{"name": "Metoprolol", "strength": "25 mg"}]})

    def fake(self, url):
        calls.append(url)
        return reply

    monkeypatch.setattr(spark_mod.SparkAdapter, "read_strips", fake)
    got = _post(keyed, kumar2).json()["ask"]["medicines"][-1]
    assert got["source"] == "muse-spark-1.3" and got["match"] == "ok" and len(calls) == 1

    def boom(self, url):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(spark_mod.SparkAdapter, "read_strips", boom)
    got = _post(keyed, kumar2).json()["ask"]["medicines"][-1]
    assert got["source"] == "prepared (live call failed)" and len(got["rows"]) == 4

    monkeypatch.setattr(spark_mod.SparkAdapter, "read_strips", fake)
    monkeypatch.setattr(ask_api, "MEDICINES_LIVE", False)
    del calls[:]
    got = _post(keyed, kumar2).json()["ask"]["medicines"][-1]
    assert got["source"] == "prepared" and calls == [] and len(got["rows"]) == 4
    assert ask_api.MEDICINES_LIVE is False


def _keyed_client(tmp_path):
    from fastapi.testclient import TestClient

    return TestClient(create_app(_keyed(tmp_path / "keyed")))


def test_ask_view_medicines_oldest_first():
    events = [
        {"id": "p1", "episode_id": "e", "event_type": "medicines.read", "ts_ms": 5, "payload": {
            "photo_id": "ph1", "rows": [], "match": "none", "why": proof.NO_STRIP, "source": "none", "by": "x"}},
        {"id": "p2", "episode_id": "e", "event_type": "medicines.read", "ts_ms": 9, "payload": {
            "photo_id": "ph2", "rows": [], "match": "none", "why": proof.NO_STRIP, "source": "none", "by": "x"}},
    ]
    meds = ask_view(events)["medicines"]
    assert [m["id"] for m in meds] == ["p1", "p2"]
    assert meds[0]["photo"] == {"id": "ph1", "url": "/journey/episodes/e/photos/ph1"} and meds[0]["at_ms"] == 5


def test_medicine_strings_have_no_advice(tmp_path):
    out = match_medicines(_strips(*[(s["name"], s["strength"]) for s in KUMAR_STRIPS], ("Amlodipine", "10 mg")), _rx())
    strings = [out["why"], NO_HOME, NO_MEDICINES, record_holds([]), record_holds(DOSE)]
    strings.append(record_holds([{"by": "D", "items": []}])) + [r["why"] for r in out["rows"]]
    strings += [r["schedule"] for r in out["rows"] if r["schedule"]]
    doses = dose_rows(DOSE)
    out = match_medicines(_strips(("Paracetamol", "1 g"), ("Paracetamol", "500 mg"), ("Cetirizine", "10 mg")), None, doses)
    strings += [out["why"]] + [r["why"] for r in out["rows"]] + [r["schedule"] for r in out["rows"] if r["schedule"]]
    strings.append(match_medicines(_strips(("Cetirizine", "10 mg")), _rx(), doses)["rows"][0]["why"])
    for text in strings:
        assert not ADVICE.search(text), text


def test_dose_order_matches_without_a_prescription():
    got = match_medicines(_strips(("Paracetamol", "1 g")), None, dose_rows(DOSE))
    row = got["rows"][0]
    assert row["prescribed"] and row["medicine"] == "Paracetamol 1 g" and row["schedule"] == "every 6 h"
    assert row["why"] == "On your signed orders from Dr. A. Rao (synthetic): Paracetamol 1 g, every 6 h."
    assert got["why"] == "1 of 1 medicines in the photo are on your signed orders."


def test_dose_order_without_interval_reads_as_ordered():
    items = [{"kind": "dose", "name": "Ondansetron", "amount": "4 mg", "every_h": None, "text": "Ondansetron 4 mg"}]
    assert dose_rows([{"by": "D", "items": items}])[0]["schedule"] == "as ordered"


def test_dose_rows_skip_items_without_a_dose_name():
    items = [{"kind": "obs", "text": "BP every 1 h", "every_h": 1}, {"kind": "dose", "name": "", "text": "Rest"}]
    assert dose_rows([{"by": "D", "items": items}]) == []


def test_prescription_wins_over_a_dose_order():
    got = match_medicines(_strips(("Paracetamol", "650 mg")), _rx(), dose_rows(DOSE))
    assert got["rows"][0]["schedule"] == "as needed; As needed for pain; Max 3 times daily"


def test_dose_order_strength_differs_is_flagged():
    got = match_medicines(_strips(("Paracetamol", "500 mg")), None, dose_rows(DOSE))
    row = got["rows"][0]
    assert row["flag"] == "strength_differs" and row["why"] == "The strip reads Paracetamol 500 mg. Your signed orders say Paracetamol 1 g."
    assert got["match"] == "mismatch" and got["why"].endswith("Flagged: Paracetamol 500 mg.")


def test_not_matched_names_where_it_looked():
    strips = _strips(("Cetirizine", "10 mg"))
    only_doses = match_medicines(strips, None, dose_rows(DOSE))
    assert only_doses["rows"][0]["why"] == "Cetirizine 10 mg is not on your signed orders. Ask Dr. Rao about it."
    both = match_medicines(strips, _rx(), dose_rows(DOSE))
    assert both["rows"][0]["why"] == (
        "Cetirizine 10 mg is not on your prescription from Dr. A. Rao (synthetic) or your signed orders. Ask Dr. Rao about it.")
    assert both["why"] == "0 of 1 medicines in the photo are on your prescription or signed orders. Flagged: Cetirizine 10 mg."


def test_record_holds_uses_fixed_sentences_never_free_text():
    items = [{"kind": "obs", "name": "", "text": "secret free text", "every_h": 1}]
    got = record_holds([{"by": "D", "items": items}])
    assert got == "Your record holds signed orders, but none is a medicine."
    assert "obs" not in got and "secret" not in got
    assert record_holds([]) == "Your record holds no orders yet."


def test_409_says_signed_orders_hold_no_medicine(tmp_path):
    client = _client(tmp_path)
    das = _patients(client)["9"]
    item = {"kind": "procedure", "name": "Wound dressing", "text": "Wound dressing, call family first"}
    assert _sign(client, das, [item]).status_code == 200
    assert _move(client, das, "clinic_done").status_code == 200
    refused = _post(client, das)
    assert refused.status_code == 409
    assert refused.json()["detail"] == f"{NO_MEDICINES} Your record holds signed orders, but none is a medicine."
    assert "Wound" not in refused.json()["detail"] and "obs" not in refused.json()["detail"]


def test_route_signed_dose_orders_match_without_a_prescription(tmp_path):
    client = _client(tmp_path)
    das = _patients(client)["9"]
    assert _move(client, das, "admitting", reason="Hernia repair").status_code == 200
    checks = {"band": True, "allergies": True, "baseline_obs": True, "consent": True}
    assert _move(client, das, "ward", checklist=checks).status_code == 200
    doses = [{"kind": "dose", "name": s["name"], "amount": s["strength"], "every_h": 8, "text": f"{s['name']} {s['strength']}"} for s in KUMAR_STRIPS]
    order = _sign(client, das, doses).json()["order_list"][0]
    assert _ack(client, das, order["id"]).status_code == 200
    _iyer_home(client, das)
    got = _post(client, das).json()["ask"]["medicines"][-1]
    assert got["match"] == "ok" and len(got["rows"]) == 4
    assert got["rows"][0]["why"] == "On your signed orders from Dr. A. Rao (synthetic): Metoprolol 25 mg, every 8 h."
    assert got["why"] == "4 of 4 medicines in the photo are on your signed orders."
