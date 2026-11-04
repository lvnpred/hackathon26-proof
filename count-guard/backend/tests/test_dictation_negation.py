"""Ruling P16 (fix round 4): a clause with a stop or not word is ALWAYS shown as not understood and keeps NO item, in the
model path and the rules path. The rules path accounts with the rule item's own words, never the whole clause. A limit
accounts only for the words of its own vital. The reviewer's probe7c, case by case, with the safe outcome."""

from __future__ import annotations

import json

import pytest

from app.journey import dictation as d


def _dose(text, name, amount="", h=None):
    return {"kind": "dose", "text": text, "name": name, **({"amount": amount} if amount else {}), **({"every_h": h} if h else {})}


def _model(said, items):
    return d.items_from_reply(json.dumps({"reason": "", "items": items}), said)


P = _dose("Paracetamol 1 g every 6 hours", "paracetamol", "1 g", 6)
H = "Hold metoprolol if pulse below 60."
WORDS = ["Omit", "Cancel", "Suspend", "Withdraw", "Pause", "Avoid", "Discontinue", "Cease", "Withhold", "Never give",
         "Do not restart", "Doesn't need", "Shouldn't have", "Won't need", "Cannot have", "Nil", "Stopped", "Held",
         "Omitted", "Cancelled", "Suspended", "Paused", "Can't have", "Doesn’t need", "Dont give", "Halt"]
NEGATED = [
    ("H1 hold, model plain give", H, [_dose("Metoprolol", "metoprolol")]),
    ("H2 hold, model hold dose item", H, [_dose("Hold metoprolol if pulse below 60", "metoprolol")]),
    ("H3 hold, model obs+dose", H, [{"kind": "obs", "text": "Pulse, hold metoprolol if below 60", "limits": {"sbp_min": 60}},
                                    _dose("Hold metoprolol if pulse below 60", "metoprolol")]),
    ("H4 hold with dose", "Metoprolol 25 mg every 12 hours, hold if pulse below 60.",
     [_dose("Metoprolol 25 mg every 12 hours", "metoprolol", "25 mg", 12)]),
    ("NM1 no more, model give", "No more paracetamol.", [_dose("Paracetamol", "paracetamol")]),
    ("NM2 no more, model echoes", "No more paracetamol.", [_dose("No more paracetamol", "paracetamol")]),
    ("DF1 don't forget", "Don't forget paracetamol 1 g every 6 hours.", [P]),
    ("DF2 dont forget", "Dont forget paracetamol 1 g every 6 hours.", [P]),
    ("DF3 curly apostrophe", "Don’t forget paracetamol 1 g every 6 hours.", [P]),
    ("AL1 allergy history one clause", "Not allergic to penicillin, give amoxicillin 500 mg every 8 hours.",
     [_dose("Amoxicillin 500 mg every 8 hours", "amoxicillin", "500 mg", 8)]),
    *[(f"W {w}", f"{w} paracetamol 1 g every 6 hours.", [P]) for w in WORDS],
    ("WP no longer", "Paracetamol 1 g every 6 hours no longer needed.", [P]),
    ("WP not needed", "Paracetamol 1 g every 6 hours is not needed.", [P]),
    ("WP instead of", "Ibuprofen 400 mg every 8 hours instead of paracetamol.",
     [_dose("Ibuprofen 400 mg every 8 hours", "ibuprofen", "400 mg", 8)]),
    ("SD stop item kind dose", "Stop paracetamol 500 mg every 6 hours.",
     [_dose("Stop paracetamol 500 mg every 6 hours", "paracetamol", "500 mg", 6)]),
    ("SO stop item kind other", "Stop paracetamol 500 mg every 6 hours.",
     [{"kind": "other", "text": "Stop paracetamol 500 mg every 6 hours"}]),
    ("X3 nil by mouth", "Paracetamol 500 mg every 6 hours and nil by mouth",
     [_dose("Paracetamol 500 mg every 6 hours", "paracetamol", "500 mg", 6)]),
]


@pytest.mark.parametrize("label, said, items", NEGATED, ids=[c[0] for c in NEGATED])
def test_a_negated_clause_keeps_no_item_and_is_shown(label, said, items):
    assert _model(said, items) is None  # nothing kept from the model: the rules take over
    out = d.parse_order_text(said)
    assert out["items"] == [] and out["unclear"] == [{"kind": "unclear", "heard": d.digits(said).rstrip(".")}]


def test_hold_in_its_own_sentence_keeps_the_dose_before_it():
    said = "Metoprolol 25 mg every 12 hours. Hold if pulse below 60."
    out = _model(said, [_dose("Metoprolol 25 mg every 12 hours", "metoprolol", "25 mg", 12)])
    assert [i["name"] for i in out["items"]] == ["metoprolol"] and [u["heard"] for u in out["unclear"]] == ["Hold if pulse below 60"]
    rules = d.parse_order_text(said)
    assert [i["name"] for i in rules["items"]] == ["metoprolol"] and [u["heard"] for u in rules["unclear"]] == ["Hold if pulse below 60"]


def test_not_in_one_sentence_keeps_the_other_sentences_order():
    out = _model("Not allergic to penicillin. Give amoxicillin 500 mg every 8 hours.",
                 [_dose("Amoxicillin 500 mg every 8 hours", "amoxicillin", "500 mg", 8)])
    assert [i["name"] for i in out["items"]] == ["amoxicillin"] and [u["heard"] for u in out["unclear"]] == ["Not allergic to penicillin"]


def test_stop_then_start_never_keeps_the_stopped_drug():
    said = "Stop paracetamol. Start ibuprofen 400 mg every 8 hours."
    out = _model(said, [_dose("Paracetamol", "paracetamol"), _dose("Ibuprofen 400 mg every 8 hours", "ibuprofen", "400 mg", 8)])
    assert [i["name"] for i in out["items"]] == ["ibuprofen"] and "Stop paracetamol" in [u["heard"] for u in out["unclear"]]
    rules = d.parse_order_text(said)
    assert all(i.get("name") != "paracetamol" for i in rules["items"]) and "Stop paracetamol" in [u["heard"] for u in rules["unclear"]]


def test_a_model_stop_the_doctor_never_said_is_not_kept():
    assert _model("Paracetamol 1 g every 6 hours.", [_dose("Stop paracetamol 1 g every 6 hours", "paracetamol", "1 g", 6)]) is None
    rules = d.parse_order_text("Paracetamol 1 g every 6 hours.")
    assert [i["name"] for i in rules["items"]] == ["paracetamol"] and rules["unclear"] == []


def test_continue_is_a_give_order_and_a_word_the_item_lacks_is_shown():
    assert _model("Continue paracetamol.", [_dose("Continue paracetamol", "paracetamol")])["unclear"] == []
    said = "Continue paracetamol 1 g every 6 hours."
    out = _model(said, [P])
    assert len(out["items"]) == 1 and [u["heard"] for u in out["unclear"]] == ["Continue paracetamol 1 g every 6 hours"]
    rules = d.parse_order_text(said)
    assert len(rules["items"]) == 1 and [u["heard"] for u in rules["unclear"]] == ["Continue paracetamol 1 g every 6 hours"]


# Finding 3: the rules path accounts with the rule item's own words (name, amount, interval, obs and proof words).
@pytest.mark.parametrize("said", ["Paracetamol 500 mg every 6 hours with codeine", "Paracetamol 500 mg every 6 hours, also cefuroxim",
                                  "Paracetamol 500 mg every 6 hours for pain"])
def test_rules_show_a_key_word_the_rule_item_does_not_say(said):
    assert [u["heard"] for u in d.parse_order_text(said)["unclear"]] == [said]


KUMAR = "Admit for open hernia repair. Paracetamol 1 g every 6 hours, strip photo as proof. BP and pulse every 1 hour, lower systolic limit 90."


def test_kumar_demo_order_is_fully_covered_by_rules_and_model():
    rules = d.parse_order_text(KUMAR)
    assert rules["unclear"] == [] and [i["kind"] for i in rules["items"]] == ["dose", "obs"]
    assert rules["items"][0]["proof"] == "photo" and rules["items"][1]["limits"] == {"sbp_min": 90}
    out = _model(KUMAR, [{**P, "text": "Paracetamol 1 g every 6 hours, strip photo as proof", "proof": "photo"},
                         {"kind": "obs", "text": "BP and pulse every 1 hour", "every_h": 1, "limits": {"sbp_min": 90}}])
    assert len(out["items"]) == 2 and out["unclear"] == []


# Finding 4: a limit accounts only for its own vital, and its value must be said after that vital.
PULSE = "Check BP every 4 hours, call if pulse below 60."


def test_a_pulse_threshold_is_never_a_systolic_limit():
    rules = d.parse_order_text(PULSE)
    assert all(not i.get("limits") for i in rules["items"]) and [u["heard"] for u in rules["unclear"]] == [PULSE.rstrip(".")]
    short = {"kind": "obs", "text": "Check BP every 4 hours", "every_h": 4, "limits": {"sbp_min": 60}}
    whole = {**short, "text": "Check BP every 4 hours, call if pulse below 60"}
    for item in (short, whole):
        out = _model(PULSE, [item])
        assert out is None or (out["items"] == [] or not out["items"][0].get("limits")) and out["unclear"]


def test_a_pulse_limit_accounts_for_pulse_words():
    said = "Pulse every hour, call if heart rate above 120."
    out = _model(said, [{"kind": "obs", "text": "Pulse every hour", "every_h": 1, "limits": {"hr_max": 120}}])
    assert out["unclear"] == []
    out = _model(said, [{"kind": "obs", "text": "Pulse every hour", "every_h": 1, "limits": {"sbp_max": 120}}])
    assert out is None or out["unclear"] == [said.rstrip(".")]
