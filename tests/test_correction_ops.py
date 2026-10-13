"""Spoken remove / replace in corrections: apply_ops (pure) + POST /api/v1/correct."""
import copy
import json

import pytest

import doctor_dictation.main as M
from doctor_dictation.config import override_settings
from doctor_dictation.core.correction import merge_form
from doctor_dictation.core.ops import apply_ops


def _row(name, **kw):
    base = {"form": "Tab.", "name": name, "strength": "40 mg", "dose": "1-0-0",
            "timing": "After food", "duration": "5 days", "instructions": ""}
    base.update(kw)
    return base


def _names(form):
    return [r["name"] for r in form["rx"]]


# ---- core: rx remove ----

def test_remove_rx_by_exact_name():
    cur = {"rx": [_row("Pantoprazole"), _row("Paracetamol")]}
    new, rest, notes, _t = apply_ops(cur, {"remove": {"rx": ["pantoprazole"]}})
    assert _names(new) == ["Paracetamol"]
    assert notes == ["Removed Pantoprazole."]
    assert "remove" not in rest


def test_remove_rx_by_unique_word_boundary_prefix():
    cur = {"rx": [_row("Dolo 650"), _row("Paracetamol")]}
    new, _rest, notes, _t = apply_ops(cur, {"remove": {"rx": ["dolo"]}})
    assert _names(new) == ["Paracetamol"]
    assert notes == ["Removed Dolo 650."]


def test_remove_rx_single_word_prefix_is_intentional():
    # "pan" is a whole leading word of "Pan D": allowed because it is unique.
    cur = {"rx": [_row("Pan D"), _row("Metformin")]}
    new, _r, notes, _t = apply_ops(cur, {"remove": {"rx": ["Pan"]}})
    assert _names(new) == ["Metformin"] and notes == ["Removed Pan D."]


def test_remove_rx_mid_word_prefix_does_not_match():
    cur = {"rx": [_row("Pantoprazole"), _row("Metformin")]}
    for ref in ("pan", "panto"):
        new, _r, notes, _t = apply_ops(cur, {"remove": {"rx": [ref]}})
        assert new == cur
        assert notes == [f"Could not find {ref} on the prescription; nothing was changed. "
                         "Use the x button."]


def test_remove_rx_longer_ref_never_matches_shorter_row():
    cur = {"rx": [_row("Pan"), _row("Metformin")]}
    new, _r, notes, _t = apply_ops(cur, {"remove": {"rx": ["Pantoprazole"]}})
    assert new == cur and "Could not find" in notes[0]


@pytest.mark.parametrize("ref", ["P", "ß", " a ", "  "])
def test_too_short_ref_matches_nothing(ref):
    cur = {"rx": [_row("Pantoprazole"), _row("Metformin")], "advice": ["a b", "c"]}
    new, _r, notes, _t = apply_ops(cur, {"remove": {"rx": [ref], "advice": [ref]}})
    assert new == cur
    if ref.strip():
        assert notes == ["That name is too short to match safely; nothing was changed. "
                         "Use the x button."] * 2


def test_list_too_short_and_replace_too_short():
    cur = {"complaints": ["c", "cough"]}
    new, _r, notes, _t = apply_ops(cur, {"remove": {"complaints": ["c"]},
                                      "replace": {"complaints": [{"from": "c", "to": "x"}]}})
    assert new == cur and len(notes) == 2 and all("too short" in n for n in notes)


def test_remove_rx_ambiguous_changes_nothing():
    cur = {"rx": [_row("Dolo 650"), _row("Dolo 500")]}
    new, _rest, notes, _t = apply_ops(cur, {"remove": {"rx": ["Dolo"]}})
    assert new == cur
    assert notes == ["Several rows match Dolo; nothing was changed. "
                     "Use the x button on the right row."]


def test_remove_rx_not_found_changes_nothing():
    cur = {"rx": [_row("Paracetamol")]}
    new, _rest, notes, _t = apply_ops(cur, {"remove": {"rx": ["Zinc"]}})
    assert new == cur
    assert notes == ["Could not find Zinc on the prescription; nothing was changed. "
                     "Use the x button."]


# ---- core: rx replace ----

def test_replace_rx_renames_keeps_fields_drops_grounding():
    marker = "[unverified: confirm with doctor]"
    cur = {"rx": [_row("Cephixime", strength="200 mg", dose="1-0-1", status="unknown-medicine",
                       lexicon_match="x", instructions=f"shake well {marker}"),
                  _row("Paracetamol", status="verified")]}
    new, _rest, notes, _t = apply_ops(
        cur, {"replace": {"rx": [{"from": "Cephixime", "to": " Cefixime "}]}})
    row = new["rx"][0]
    assert row["name"] == "Cefixime"
    assert (row["strength"], row["dose"], row["timing"], row["duration"], row["form"]) == \
        ("200 mg", "1-0-1", "After food", "5 days", "Tab.")
    assert "status" not in row and "lexicon_match" not in row
    assert row["instructions"] == "shake well"
    assert new["rx"][1]["status"] == "verified"
    assert notes == ["Renamed Cephixime to Cefixime."]


def test_replace_rx_empty_to_is_ignored_with_note():
    cur = {"rx": [_row("Cephixime")]}
    new, _rest, notes, _t = apply_ops(cur, {"replace": {"rx": [{"from": "Cephixime", "to": "  "}]}})
    assert new == cur
    assert len(notes) == 1 and notes[0]


def test_replace_and_overlay_in_same_patch():
    cur = {"rx": [_row("Cephixime", dose="1-0-0")]}
    patch = {"replace": {"rx": [{"from": "Cephixime", "to": "Cefixime"}]},
             "rx": [{"name": "Cefixime", "dose": "1-0-1"}]}
    new, rest, _notes, _t = apply_ops(cur, patch)
    merged = merge_form(new, rest)
    assert _names(merged) == ["Cefixime"]
    assert merged["rx"][0]["dose"] == "1-0-1"
    assert merged["rx"][0]["strength"] == "40 mg"
    assert "remove" not in merged and "replace" not in merged


def test_remove_replace_never_leak_into_merged_form():
    cur = {"rx": [_row("Pantoprazole")], "diagnosis": ["aaa"]}
    patch = {"remove": {"rx": ["Pantoprazole"]}, "replace": {"diagnosis": [{"from": "aaa", "to": "b"}]}}
    new, rest, _n, _t = apply_ops(cur, patch)
    merged = merge_form(new, rest)
    assert "remove" not in merged and "replace" not in merged
    assert merged["rx"] == [] and merged["diagnosis"] == ["b"]


# ---- core: list fields ----

def test_list_remove_exact_and_substring():
    cur = {"complaints": ["fever", "cough with fever", "headache"],
           "diagnosis": ["viral fever", "gastritis"]}
    new, _r, notes, _t = apply_ops(cur, {"remove": {"complaints": ["fever"], "diagnosis": ["viral"]}})
    assert new["complaints"] == ["cough with fever", "headache"]  # exact beats substring
    assert new["diagnosis"] == ["gastritis"]
    assert len(notes) == 2


def test_list_remove_ambiguous_and_missing():
    cur = {"advice": ["drink water", "drink warm water"]}
    new, _r, notes, _t = apply_ops(cur, {"remove": {"advice": ["drink", "walk"]}})
    assert new == cur
    assert notes == ["Several items match drink; nothing was changed. "
                     "Use the x button on the right item.",
                     "Could not find walk in advice; nothing was changed. Use the x button."]


def test_list_replace_keeps_position():
    cur = {"diagnosis": ["gastritis", "viral fever", "anaemia"]}
    new, _r, notes, _t = apply_ops(
        cur, {"replace": {"diagnosis": [{"from": "Viral Fever", "to": "dengue fever"}]}})
    assert new["diagnosis"] == ["gastritis", "dengue fever", "anaemia"]
    assert notes == ["Changed viral fever to dengue fever."]


def test_list_match_needs_whole_words():
    cur = {"diagnosis": ["fevers", "gastritis"]}
    new, _r, notes, _t = apply_ops(cur, {"remove": {"diagnosis": ["fever"]}})
    assert new == cur and "Could not find fever" in notes[0]


# ---- rename collision / no-op / touched ----

def test_rename_to_name_of_another_row_is_refused():
    cur = {"rx": [_row("Cefixime", status="verified", lexicon_match="Cefixime"),
                  _row("Cephixime")]}
    new, _r, notes, touched = apply_ops(
        cur, {"replace": {"rx": [{"from": "Cephixime", "to": "cefixime"}]}})
    assert new == cur and touched == set()
    assert notes == ["Another row is already named cefixime; nothing was changed. "
                     "Use the x button to remove the wrong one."]


def test_rename_to_same_normalised_name_is_noop():
    cur = {"rx": [_row("Cefixime", status="verified")]}
    new, _r, notes, touched = apply_ops(
        cur, {"replace": {"rx": [{"from": "Cefixime", "to": " CEFIXIME"}]}})
    assert new == cur and touched == set()
    assert notes == ["Cefixime already has that name; nothing was changed."]


def test_touched_holds_normalised_new_names():
    cur = {"rx": [_row("Cephixime")]}
    _n, _r, _notes, touched = apply_ops(
        cur, {"replace": {"rx": [{"from": "Cephixime", "to": "Cefixime"}]}})
    assert touched == {"cefixime"}


def test_preserve_untouched_respects_extra_named():
    from doctor_dictation.core.correction import preserve_untouched_rx_status
    cur = {"rx": [_row("Cefixime", status="old")]}
    out = {"rx": [_row("Cefixime", status="verified")]}
    preserve_untouched_rx_status(cur, {}, copy.deepcopy(out))
    assert preserve_untouched_rx_status(cur, {}, copy.deepcopy(out))["rx"][0]["status"] == "old"
    assert preserve_untouched_rx_status(
        cur, {}, copy.deepcopy(out), extra_named={"cefixime"})["rx"][0]["status"] == "verified"


# ---- wipe cap ----

def _many(n):
    return [_row(f"Drug{i}x") for i in range(n)]


def test_rx_remove_more_than_three_is_refused():
    cur = {"rx": _many(6)}
    new, _r, notes, _t = apply_ops(cur, {"remove": {"rx": [f"Drug{i}x" for i in range(4)]}})
    assert new == cur
    assert notes == ["That would remove 4 medicines at once; nothing was changed. "
                     "Use the x button on the rows you mean."]


def test_rx_remove_three_of_six_allowed():
    cur = {"rx": _many(6)}
    new, _r, _n, _t = apply_ops(cur, {"remove": {"rx": [f"Drug{i}x" for i in range(3)]}})
    assert len(new["rx"]) == 3


def test_rx_remove_every_row_of_two_is_refused():
    cur = {"rx": _many(2)}
    new, _r, notes, _t = apply_ops(cur, {"remove": {"rx": ["Drug0x", "Drug1x"]}})
    assert new == cur and notes[0].startswith("That would remove 2 medicines at once")


def test_rx_remove_only_row_allowed():
    cur = {"rx": _many(1)}
    new, _r, _n, _t = apply_ops(cur, {"remove": {"rx": ["Drug0x"]}})
    assert new["rx"] == []


def test_list_wipe_caps():
    cur = {"advice": ["alpha one", "beta two", "gamma three", "delta four", "epsilon five"],
           "complaints": ["cough", "cold"], "diagnosis": ["only one"]}
    new, _r, notes, _t = apply_ops(cur, {"remove": {
        "advice": ["alpha", "beta", "gamma", "delta"],
        "complaints": ["cough", "cold"], "diagnosis": ["only one"]}})
    assert new["advice"] == cur["advice"] and new["complaints"] == cur["complaints"]
    assert new["diagnosis"] == []
    assert notes[0] == "Removed only one."
    assert notes[1].startswith("That would remove 2 items at once")
    assert notes[2] == ("That would remove 4 items at once; nothing was changed. "
                        "Use the x button on the items you mean.")


# ---- core: robustness ----

@pytest.mark.parametrize("patch", [
    {"remove": "x"}, {"replace": 5}, {"remove": {"rx": [None, 5, {}]}},
    {"remove": {"rx": "Pantoprazole", "diagnosis": {"a": 1}}},
    {"replace": {"rx": [None, "x", {"from": 1, "to": 2}, {"from": "a"}], "advice": [[]]}},
    {"remove": {"bogus": ["x"]}, "replace": {"bogus": [{"from": "a", "to": "b"}]}},
])
def test_garbage_ops_never_raise_and_change_nothing(patch):
    cur = {"rx": [_row("Pantoprazole")], "advice": ["a"]}
    new, rest, _notes, _t = apply_ops(cur, patch)
    assert new == cur
    assert "remove" not in rest and "replace" not in rest


def test_garbage_current_and_patch_tolerated():
    assert apply_ops(None, None)[0] == {}
    assert apply_ops({"rx": "x", "advice": 3}, {"remove": {"rx": ["a"], "advice": ["a"]}})[0] \
        == {"rx": "x", "advice": 3}


def test_apply_ops_never_mutates_inputs():
    cur = {"rx": [_row("Cephixime", status="verified"), _row("Pantoprazole")],
           "diagnosis": ["viral fever"]}
    patch = {"remove": {"rx": ["Pantoprazole"]},
             "replace": {"rx": [{"from": "Cephixime", "to": "Cefixime"}],
                         "diagnosis": [{"from": "viral fever", "to": "dengue"}]},
             "advice": ["rest"]}
    c0, p0 = copy.deepcopy(cur), copy.deepcopy(patch)
    apply_ops(cur, patch)
    assert cur == c0 and patch == p0


# ---- route (offline, stub provider via STUB_LLM_JSON) ----

def _post(monkeypatch, patch, current, transcript="spoken correction"):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("ALLOW_STUB_PROVIDERS", "1")
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(patch))
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True)
    r = TestClient(M.app).post("/api/v1/correct",
                               json={"transcript": transcript, "current_form": current})
    assert r.status_code == 200, r.text
    return r.json()


_CUR = {"rx": [_row("Paracetamol", strength="650 mg", status="verified", lexicon_match="Paracetamol"),
               _row("Pantoprazole", status="verified", lexicon_match="Pantoprazole"),
               _row("Cephixime", strength="200 mg", status="unknown-medicine", lexicon_match="",
                    instructions="[unverified: confirm with doctor]")]}


def test_route_spoken_remove_removes_row_and_warns(monkeypatch):
    j = _post(monkeypatch, {"remove": {"rx": ["Pantoprazole"]}}, copy.deepcopy(_CUR))
    assert _names(j["structured"]) == ["Paracetamol", "Cephixime"]
    assert j["warnings"][0] == "Removed Pantoprazole."
    assert "remove" not in j["structured"]


def test_route_rename_replaces_row_and_keeps_other_status(monkeypatch):
    j = _post(monkeypatch, {"replace": {"rx": [{"from": "Cephixime", "to": "Cefixime"}]}},
              copy.deepcopy(_CUR))
    names = _names(j["structured"])
    assert "Cephixime" not in names and names.count("Cefixime") == 1
    by = {r["name"]: r for r in j["structured"]["rx"]}
    assert by["Paracetamol"]["status"] == "verified"
    assert by["Pantoprazole"]["status"] == "verified"
    assert j["warnings"][0] == "Renamed Cephixime to Cefixime."


def test_route_rename_status_is_recomputed_not_carried(monkeypatch):
    cur = copy.deepcopy(_CUR)
    cur["rx"][2].update(status="STALE-OLD-STATUS", lexicon_match="STALE-OLD-MATCH")
    j = _post(monkeypatch, {"replace": {"rx": [{"from": "Cephixime", "to": "Cefixime"}]}},
              cur, transcript="the drug is Cefixime not Cephixime")
    row = next(r for r in j["structured"]["rx"] if r["name"] == "Cefixime")
    assert row["status"] not in ("STALE-OLD-STATUS", "unknown-medicine")
    assert row["lexicon_match"] != "STALE-OLD-MATCH"
    assert row["status"] == "verified"  # old row was unknown-medicine; Cefixime is in the lexicon
    assert "[unverified" not in row["instructions"]
    assert row["strength"] == "200 mg"


def test_route_ambiguous_remove_leaves_form_and_warns(monkeypatch):
    cur = {"rx": [_row("Dolo 650", status="verified"), _row("Dolo 500", status="verified")]}
    j = _post(monkeypatch, {"remove": {"rx": ["Dolo"]}}, copy.deepcopy(cur))
    assert _names(j["structured"]) == ["Dolo 650", "Dolo 500"]
    assert j["warnings"] and j["warnings"][0].startswith("Several rows match Dolo")


def test_instruction_documents_remove_and_replace():
    from doctor_dictation.core.correction import CORRECTION_INSTRUCTION as I
    assert '"remove"' in I and '"replace"' in I and '"from"' in I and "byte-identical" in I


def test_route_rename_collision_refused_with_warning(monkeypatch):
    cur = {"rx": [_row("Cefixime", strength="200 mg", status="verified", lexicon_match="Cefixime"),
                  _row("Cephixime", strength="200 mg", status="unknown-medicine")]}
    j = _post(monkeypatch, {"replace": {"rx": [{"from": "Cephixime", "to": "Cefixime"}]}},
              copy.deepcopy(cur), transcript="it is Cefixime")
    assert _names(j["structured"]) == ["Cefixime", "Cephixime"]
    assert j["warnings"][0].startswith("Another row is already named Cefixime")


def test_route_wipe_cap_refuses_and_warns(monkeypatch):
    cur = {"rx": [_row("Alpha1"), _row("Beta22")]}
    j = _post(monkeypatch, {"remove": {"rx": ["Alpha1", "Beta22"]}}, copy.deepcopy(cur))
    assert _names(j["structured"]) == ["Alpha1", "Beta22"]
    assert j["warnings"][0].startswith("That would remove 2 medicines at once")


def test_instruction_forbids_remove_for_value_changes():
    from doctor_dictation.core.correction import CORRECTION_INSTRUCTION as I
    assert 'never use "remove" to change a dose' in I.lower()
