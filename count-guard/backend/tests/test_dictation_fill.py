"""Dictation fills real fields (clarity §4.5, K7): grounding per order item, words not understood are shown and never
signed, a discharge sentence with no section is not placed, a theatre line with no drug name says what was heard."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.journey import dictation as d, live
from app.journey.dictation_cover import unplaced_sentences
from app.main import create_app
from tests.test_flow_states import _new, _to_theatre, _to_ward
from tests.test_flow_tasks import NURSE, OBS, _ack, _sign, _url
from tests.test_p2_live import ORDERS_TEXT, _keyed

DOC = "Dr. A. Rao (synthetic)"
SAID = "Paracetamol 1 g every 6 hours. Insert urinary catheter."
PARA = {"kind": "dose", "text": "Paracetamol 1 g every 6 hours", "name": "paracetamol", "amount": "1 g", "every_h": 6}
INVENTED = {"kind": "other", "text": "Urinary catheter with bladder scan"}  # "bladder scan" was never said


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a test made a real network call")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse)


def _typed(client, eid, tail, text, by=DOC):
    return client.post(_url(eid, tail), data={"by": by, "at_ms": 0, "text": text})


def test_one_unknown_item_keeps_the_others_fields():
    out = d.items_from_reply(json.dumps({"reason": "", "items": [PARA, INVENTED]}), SAID)
    assert out["items"] == [{"kind": "dose", "text": "Paracetamol 1 g every 6 hours", "mode": "tick", "proof": "none",
                             "every_h": 6, "name": "paracetamol", "amount": "1 g"}]
    assert out["unclear"] == [{"kind": "unclear", "heard": "Insert urinary catheter"}]


def test_an_invented_extra_item_is_dropped_and_nothing_said_is_lost():
    out = d.items_from_reply(json.dumps({"reason": "", "items": [PARA, INVENTED]}), "Paracetamol 1 g every 6 hours.")
    assert [i["name"] for i in out["items"]] == ["paracetamol"] and out["unclear"] == []


def test_a_reply_with_no_grounded_item_falls_back_to_rules():
    assert d.items_from_reply(json.dumps({"reason": "", "items": [INVENTED]}), SAID) is None


def test_rules_mark_an_unmatched_clause_unclear_not_other():
    out = d.parse_order_text(SAID)
    assert [i["kind"] for i in out["items"]] == ["dose"]
    assert out["unclear"] == [{"kind": "unclear", "heard": "Insert urinary catheter"}]
    assert d.parse_order_text(ORDERS_TEXT)["unclear"] == []


def test_model_draft_keeps_grounded_items_and_shows_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "spark_text", lambda s, prompt: json.dumps({"reason": "", "items": [PARA, INVENTED]}))
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/journey/episodes", json={"label": "x"}).json()["id"]
    draft = _typed(client, eid, "dictate/orders", SAID).json()["drafts"]["order"]
    assert draft["source"] == "muse-spark-1.3"
    assert draft["items"][0]["name"] == "paracetamol" and len(draft["items"]) == 1
    assert draft["unclear"] == [{"kind": "unclear", "heard": "Insert urinary catheter"}]


def test_only_words_not_understood_still_make_a_draft(tmp_path):
    client, eid = _new(tmp_path)
    draft = _typed(client, eid, "dictate/orders", "Insert urinary catheter.").json()["drafts"]["order"]
    assert draft["items"] == [] and draft["unclear"] == [{"kind": "unclear", "heard": "Insert urinary catheter"}]


def test_signing_never_takes_an_unclear_item(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    bad = _sign(client, eid, [{"kind": "unclear", "heard": "Insert urinary catheter", "text": "Insert urinary catheter"}])
    assert bad.status_code == 422


def test_discharge_sentence_with_no_section_is_not_placed():
    out = d.discharge_draft("Diagnosis: right inguinal hernia. The family visited this morning.")
    assert out["sections"] == [{"heading": "Diagnosis", "text": "Right inguinal hernia."}]
    assert out["unplaced"] == ["The family visited this morning."]
    assert all(s["heading"] != "Course on the ward" for s in out["sections"])
    assert d.discharge_sections("Recovered well on the ward, wound clean and dry.")[0]["heading"] == "Course on the ward"


def test_dictated_discharge_carries_unplaced(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    draft = _typed(client, eid, "dictate/discharge", "Diagnosis: hernia. The family visited this morning.").json()["drafts"]["discharge"]
    assert draft["unplaced"] == ["The family visited this morning."]
    assert [s["heading"] for s in draft["sections"]] == ["Diagnosis"]


def test_theatre_drug_with_no_name_says_what_was_heard(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    out = client.post(f"/journey/episodes/{eid}/theatre/drug", data={"text": "five ml", "by": DOC})
    assert out.status_code == 422
    assert out.json()["detail"] == "Heard: 'five ml' — no drug name"


def test_task_voice_values_in_words(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    order = _sign(client, eid, [OBS]).json()["order_list"][0]
    _ack(client, eid, order["id"])
    body = _typed(client, eid, "dictate/task", "BP one hundred twenty over eighty, pulse seventy two", by=NURSE).json()
    assert body["values"] == {"sbp": 120, "dbp": 80, "hr": 72}


# Fix round 1: coverage is per clause, never pooled across items.
TWO = "Paracetamol 1 g every 6 hours. Ceftriaxone 1 g every 8 hours."
CEF_MISREAD = {"kind": "dose", "text": "Ceftriaxone 2 g every 8 hours", "name": "ceftriaxone", "amount": "2 g", "every_h": 8}


def test_a_misread_second_dose_is_shown_not_dropped():
    out = d.items_from_reply(json.dumps({"reason": "", "items": [PARA, CEF_MISREAD]}), TWO)
    assert [i["name"] for i in out["items"]] == ["paracetamol"]
    assert out["unclear"] == [{"kind": "unclear", "heard": "Ceftriaxone 1 g every 8 hours"}]


def test_a_clause_the_model_left_out_is_shown():
    out = d.items_from_reply(json.dumps({"reason": "", "items": [PARA]}), TWO)
    assert out["unclear"] == [{"kind": "unclear", "heard": "Ceftriaxone 1 g every 8 hours"}]


def test_a_discharge_sentence_the_model_left_out_is_unplaced(tmp_path, monkeypatch):
    reply = json.dumps({"sections": [{"heading": "Diagnosis", "text": "Right inguinal hernia."}]})
    monkeypatch.setattr(live, "spark_text", lambda s, prompt: reply)
    client = TestClient(create_app(_keyed(tmp_path)))
    eid = client.post("/journey/episodes", json={"label": "x"}).json()["id"]
    _to_ward(client, eid)
    said = "Diagnosis right inguinal hernia. Review in clinic on day 7."
    draft = _typed(client, eid, "dictate/discharge", said).json()["drafts"]["discharge"]
    assert draft["source"] == "muse-spark-1.3"
    assert draft["unplaced"] == ["Review in clinic on day 7."]


def test_left_out_sentences_are_kept_on_the_signed_discharge(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    draft = _typed(client, eid, "dictate/discharge", "Diagnosis: hernia. The family visited this morning.").json()["drafts"]["discharge"]
    body = {"summary": "Diagnosis: Hernia.", "by": DOC, "at_ms": 0, "draft_id": draft["id"], "left_out": ["The family visited this morning."]}
    assert client.post(_url(eid, "discharge/sign"), json=body).status_code == 200
    [signed] = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "discharge.signed"]
    assert signed["payload"]["left_out"] == ["The family visited this morning."]


# Fix round 2 (ruling P14): the kept items at home in a clause must account for every drug, number and obs or
# procedure word in it; each kept item is grounded in ONE clause. The reviewer's probe, case by case.
def _dose(text, name, amount, h=None):
    return {"kind": "dose", "text": text, "name": name, "amount": amount, **({"every_h": h} if h else {})}


CEF = "Ceftriaxone 1 g every 8 hours"
T3 = "Paracetamol 1 g every 6 hours. Ceftriaxone 1 g every 8 hours. Ondansetron 4 mg every 8 hours."
T4 = "Paracetamol 1 g every 6 hours. Paracetamol 500 mg every 4 hours."
T5 = "Paracetamol 1 g every 6 hours. Paracetamol 1 g at night."
NOPUNCT = "paracetamol 1 g every 6 hours ceftriaxone 1 g every 8 hours"
PROBE = [
    ("A", "Paracetamol 1 g every 6 hours. Ceftriaxone 1 g every 8 hours.", [PARA, _dose("Ceftriaxone 2 g every 8 hours", "ceftriaxone", "2 g", 8)], 1, [CEF]),
    ("B1", T3, [PARA, _dose("Ondansetron 4 mg every 8 hours", "ondansetron", "4 mg", 8)], 2, [CEF]),
    ("B2", T3, [PARA, _dose("Ondansetron 4 mg", "ondansetron", "4 mg")], 2, [CEF, "Ondansetron 4 mg every 8 hours"]),
    ("C1 cross-clause dose", T4, [PARA, _dose("Paracetamol 1 g every 4 hours", "paracetamol", "1 g", 4)], 1, ["Paracetamol 500 mg every 4 hours"]),
    ("C2", T4, [PARA], 1, ["Paracetamol 500 mg every 4 hours"]),
    ("C3", T4, [_dose("Paracetamol", "paracetamol", "")], 1, ["Paracetamol 1 g every 6 hours", "Paracetamol 500 mg every 4 hours"]),
    ("C4", T5, [PARA], 1, ["Paracetamol 1 g at night"]),
    ("C5", T5, [_dose("Paracetamol 1 g", "paracetamol", "1 g")], 1, ["Paracetamol 1 g every 6 hours", "Paracetamol 1 g at night"]),
    ("D1", "Paracetamol 1 g every 6 hours. Obs every hour.", [PARA], 1, ["Obs every hour"]),
    ("D2", "Paracetamol 1 g every 6 hours. Obs every 4 hours.", [PARA], 1, ["Obs every 4 hours"]),
    ("D3", "Paracetamol 1 g every 6 hours. Check BP every 6 hours.", [PARA], 1, ["Check BP every 6 hours"]),
    ("E1", NOPUNCT, [PARA], 1, [NOPUNCT]),
    ("E2", NOPUNCT, [PARA, _dose("Ceftriaxone 2 g every 8 hours", "ceftriaxone", "2 g", 8)], 1, [NOPUNCT]),
    ("E3", "paracetamol one gram every six hours and obs every hour", [PARA], 1, ["paracetamol 1 gram every 6 hours and obs every hour"]),
    ("E4", "Paracetamol 1 g every 6 hours and ceftriaxone 1 g every 8 hours.", [PARA], 1, ["Paracetamol 1 g every 6 hours and ceftriaxone 1 g every 8 hours"]),
    ("E5", "Paracetamol 1 g every 6 hours, ceftriaxone 1 g every 8 hours", [PARA], 1, ["Paracetamol 1 g every 6 hours, ceftriaxone 1 g every 8 hours"]),
    ("F1", "Obs every hour. Obs every 4 hours, call if systolic below 90.", [{"kind": "obs", "text": "Obs every hour", "every_h": 1}], 1, ["Obs every 4 hours, call if systolic below 90"]),
    ("F2", "Paracetamol 1 g every 6 hours. Give 1 g of paracetamol if pain.", [PARA], 1, ["Give 1 g of paracetamol if pain"]),
]


@pytest.mark.parametrize("label, said, items, kept, unclear", PROBE, ids=[p[0] for p in PROBE])
def test_every_said_order_is_kept_or_shown(label, said, items, kept, unclear):
    out = d.items_from_reply(json.dumps({"reason": "", "items": items}), said)
    assert len(out["items"]) == kept
    assert [u["heard"] for u in out["unclear"]] == unclear


def test_a_cross_clause_dose_is_not_kept():
    out = d.items_from_reply(json.dumps({"reason": "", "items": [PARA, _dose("Paracetamol 1 g every 4 hours", "paracetamol", "1 g", 4)]}), T4)
    assert [i["text"] for i in out["items"]] == ["Paracetamol 1 g every 6 hours"]  # 1 g every 4 hours was never said


def test_rules_show_a_clause_with_two_orders():
    out = d.parse_order_text("Paracetamol 1 g every 6 hours and ceftriaxone 1 g every 8 hours.")
    assert out["unclear"] == [{"kind": "unclear", "heard": "Paracetamol 1 g every 6 hours and ceftriaxone 1 g every 8 hours"}]


def test_discharge_sentence_with_a_name_the_section_lost_is_unplaced():
    assert unplaced_sentences("Paracetamol and codeine for pain.", ["Medicines: Paracetamol for pain."]) == ["Paracetamol and codeine for pain."]
    assert unplaced_sentences("Paracetamol and codeine for pain.", ["Medicines: Paracetamol and codeine for pain."]) == []


def test_discharge_sentence_with_a_number_the_section_lost_is_unplaced():
    said = "Diagnosis appendicitis. Paracetamol 1 g every 6 hours for 5 days."
    assert unplaced_sentences(said, ["Diagnosis: appendicitis", "Medicines: Paracetamol 1 g"]) == ["Paracetamol 1 g every 6 hours for 5 days."]
    assert unplaced_sentences("Review in clinic on day 7. Stitches out day 10.", ["Follow-up: Review in clinic on day 7."]) == ["Stitches out day 10."]


# Fix round 3 (ruling P15): every key word is accounted for, and a clause that turns an order around is never a give
# order. The reviewer's probe7b, case by case.
P500 = _dose("Paracetamol 500 mg every 6 hours", "paracetamol", "500 mg", 6)
PROBE_B = [
    ("N2b", "Paracetamol 500 mg every 6 hours, also cefuroxim", [P500], ["Paracetamol 500 mg every 6 hours, also cefuroxim"]),
    ("N2c", "Paracetamol 500 mg every 6 hours with codeine", [P500], ["Paracetamol 500 mg every 6 hours with codeine"]),
]
# X3 ("... and nil by mouth") moved to test_dictation_negation.py: under ruling P16 "nil" negates the whole clause,
# so nothing is kept and the clause is shown, instead of keeping the paracetamol item.


@pytest.mark.parametrize("label, said, items, unclear", PROBE_B, ids=[p[0] for p in PROBE_B])
def test_a_key_word_no_item_says_shows_the_clause(label, said, items, unclear):
    out = d.items_from_reply(json.dumps({"reason": "", "items": items}), said)
    assert [u["heard"] for u in out["unclear"]] == unclear


@pytest.mark.parametrize("said", ["Stop paracetamol 500 mg every 6 hours.", "Do not give paracetamol 500 mg every 6 hours.",
                                  "Hold paracetamol 500 mg every 6 hours."])
def test_stop_or_not_is_never_a_give_order(said):
    assert d.items_from_reply(json.dumps({"reason": "", "items": [P500]}), said) is None  # nothing kept from the model
    out = d.parse_order_text(said)  # and the rules do not make one either
    assert out["items"] == [] and out["unclear"] == [{"kind": "unclear", "heard": said.rstrip(".")}]


def test_stop_in_one_clause_keeps_the_other_clauses_orders():
    said = "Ondansetron 4 mg every 8 hours. Stop paracetamol 500 mg every 6 hours."
    out = d.items_from_reply(json.dumps({"reason": "", "items": [_dose("Ondansetron 4 mg every 8 hours", "ondansetron", "4 mg", 8), P500]}), said)
    assert [i["name"] for i in out["items"]] == ["ondansetron"]
    assert [u["heard"] for u in out["unclear"]] == ["Stop paracetamol 500 mg every 6 hours"]


# Ruling P16 revoked the "item carries the stop word" exception this test asserted: an item echoing stop or not is
# never kept now (test_dictation_negation.py SD/SO cover kind dose and kind other with the same text).


def test_the_same_order_said_twice_is_two_items():
    said = "Paracetamol 500 mg every 6 hours. Paracetamol 500 mg every 6 hours."
    out = d.items_from_reply(json.dumps({"reason": "", "items": [P500, P500]}), said)
    assert len(out["items"]) == 2 and out["unclear"] == []


def test_spoken_units_are_their_short_forms():
    said = "Paracetamol five hundred milligrams every six hours for pain."
    assert unplaced_sentences(said, ["Medicines: Paracetamol 500 mg every 6 hours for pain."]) == []
    out = d.items_from_reply(json.dumps({"reason": "", "items": [P500]}), "Paracetamol five hundred milligrams every six hours.")
    assert out["unclear"] == []
    rules = d.parse_order_text("Paracetamol five hundred milligrams every six hours.")
    assert rules["items"][0]["amount"] == "500 mg"
    assert d.parse_order_text("Ondansetron 4 micrograms every 8 hours.")["items"][0]["amount"] == "4 mcg"
