import json

from doctor_dictation.core import investigations as I
from doctor_dictation.core.investigations import TEXT_CHARS, activate, coerce_items, flatten, key, lookup, print_text

CAT = [{"canonical": "Renal Function Test", "aliases": ["rft", "kft"], "category": "Blood", "print": "RFT"},
       {"canonical": "Ultrasound Kidneys Ureters and Bladder", "aliases": ["usg kub"], "category": "Imaging", "print": "USG KUB"}]


def test_lookup_is_exact_on_any_name_with_punctuation_and_a_qualifier_ignored():
    activate(CAT)
    assert lookup("R.F.T")["canonical"] == "Renal Function Test" and lookup("kft")["print"] == "RFT"
    assert lookup("USG-KUB")["print"] == "USG KUB" and lookup("Repeat USG KUB")["print"] == "USG KUB"
    assert lookup("Follow-up RFT")["print"] == "RFT"
    assert lookup("RFTs") is None and lookup("") is None and lookup(None) is None


def test_each_list_object_gets_its_own_index():
    other = [{"canonical": "Other", "aliases": ["rft"], "category": "Blood", "print": "O"}]
    activate(CAT)
    assert lookup("rft")["canonical"] == "Renal Function Test"
    activate(other)
    assert lookup("rft")["canonical"] == "Other"
    activate([])
    assert lookup("rft") is None


def test_without_an_active_clinic_list_the_shipped_catalogue_is_used(monkeypatch, tmp_path):
    p = tmp_path / "ix.json"; p.write_text(json.dumps({"version": "t", "entries": CAT}))
    monkeypatch.setattr(I, "CATALOGUE_PATH", p); monkeypatch.setattr(I, "_shipped_cache", None)
    monkeypatch.setattr(I, "_active", I.ContextVar("t", default=None))
    assert I.entries() == CAT


def test_missing_or_bad_shipped_file_gives_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(I, "_shipped_cache", None)
    monkeypatch.setattr(I, "CATALOGUE_PATH", tmp_path / "none.json")
    assert I.shipped() == []
    bad = tmp_path / "bad.json"; bad.write_text("{nope")
    monkeypatch.setattr(I, "CATALOGUE_PATH", bad)
    assert I.shipped() == []


def test_legacy_strings_and_bad_items_coerce_safely():
    got = coerce_items(["CBC", " ", 5, {"text": "  RFT ", "status": "bogus", "source": "x", "canonical": 3},
                       {"text": "", "status": "verified"}, {"text": "x" * 300}])
    assert got[0] == {"text": "CBC", "canonical": "", "status": "", "source": "dictated"}
    assert got[1] == {"text": "RFT", "canonical": "", "status": "", "source": "dictated"}
    assert len(got) == 3 and len(got[2]["text"]) == TEXT_CHARS
    assert coerce_items(None) == [] and coerce_items("CBC") == []


def test_flatten_gives_texts_without_mutating():
    form = {"investigations": ["CBC", {"text": "RFT", "canonical": "Renal Function Test"}], "x": 1}
    assert flatten(form) == {"investigations": ["CBC", "RFT"], "x": 1}
    assert isinstance(form["investigations"][1], dict)


def test_print_text_follows_decision_4():
    assert print_text({"text": "RFT", "canonical": "Renal Function Test"}) == "RFT (Renal Function Test)"
    assert print_text({"text": "renal function test", "canonical": "Renal Function Test"}) == "renal function test"
    assert print_text({"text": "Uroflow at home", "canonical": ""}) == "Uroflow at home"
    assert print_text("CBC") == "CBC" and print_text(None) == ""


def test_key_agrees_with_the_builder():
    from doctor_dictation.core.lexicon import build_investigations as B
    for s in ("Urine C&S", "S. Creatinine", "TLC/DC", "  X-ray  KUB "):
        assert key(s) == B.key(s)


def test_spaceless_fallback_is_only_for_spelled_letters_and_never_ambiguous():
    cat = [{"canonical": "T34 Panel", "aliases": [], "category": "Blood", "print": "T34"}]
    activate(cat)
    assert lookup("t34")["canonical"] == "T34 Panel" and lookup("t 34") is None
    activate(CAT)
    assert lookup("R.F.T") is not None and lookup("u s g k u b")["print"] == "USG KUB"
    clash = [{"canonical": "A", "aliases": ["r f t"], "category": "Blood", "print": "A"},
             {"canonical": "B", "aliases": ["rft"], "category": "Blood", "print": "B"}]
    activate(clash)
    assert lookup("rft")["canonical"] == "B" and lookup("r f t")["canonical"] == "A"   # spaced keys win
    assert lookup("R.F.T")["canonical"] == "A"
    clash2 = [{"canonical": "A", "aliases": ["r.f.t"], "category": "Blood", "print": "A"},
              {"canonical": "B", "aliases": ["rf t"], "category": "Blood", "print": "B"}]
    activate(clash2)
    assert lookup("r f t")["canonical"] == "A"
    clash3 = [{"canonical": "A", "aliases": ["rf t"], "category": "Blood", "print": "A"},
              {"canonical": "B", "aliases": ["r ft"], "category": "Blood", "print": "B"}]
    activate(clash3)
    assert lookup("r f t") is None            # "rft" belongs to two different entries


# --- Task 3: was it dictated? -------------------------------------------------------------------------------------
from doctor_dictation.core.investigations import check_items, heard  # noqa: E402


def test_a_dictated_short_code_written_in_full_is_verified():                 # Review Focus 1
    activate(CAT)
    [i] = check_items(["Renal Function Test"], "advise rft and review")
    assert (i["status"], i["canonical"], i["source"]) == ("verified", "Renal Function Test", "dictated")


def test_letters_spelled_by_speech_count_as_heard():                          # Review Focus 2
    activate(CAT)
    assert [i["status"] for i in check_items(["RFT", "USG KUB"], "get r f t and usg k u b done")] == ["verified", "verified"]


def test_an_invented_test_is_red_and_a_heard_unknown_one_is_amber():
    activate(CAT)
    got = check_items(["Brain impulses", "ECG", "Uroflow at home"], "do uroflow at home, rft")
    assert [i["status"] for i in got] == ["not-dictated", "not-dictated", "new"]   # "ECG" was never said


def test_a_doctor_item_is_never_red():
    activate(CAT)
    got = check_items([{"text": "ECG", "source": "doctor"}, {"text": "kft", "source": "doctor"}], "nothing said")
    assert [(i["status"], i["canonical"]) for i in got] == [("new", ""), ("verified", "Renal Function Test")]


def test_check_items_never_mutates_its_input():
    items = [{"text": "RFT", "canonical": "", "status": "", "source": "dictated"}]
    check_items(items, "rft"); assert items[0]["status"] == ""


def _statuses(values, *transcripts):
    return [i["status"] for i in check_items(values, *transcripts)]


def test_a_test_said_inside_a_longer_phrase_is_heard():
    activate(CAT)
    assert _statuses(["RFT", "Renal function test"], "advise renal function test tomorrow") == ["verified", "verified"]
    assert _statuses(["ECG"], "please get an ecg done today") == ["new"]


def test_fully_spelled_letters_and_dotted_codes_are_heard_on_both_sides():
    activate(CAT)
    assert _statuses(["USG KUB", "R.F.T."], "u s g k u b and R.F.T.") == ["verified", "verified"]
    assert _statuses(["U.S.G. K.U.B", "usg-kub", "rft"], "USG KUB, Rft") == ["verified", "verified", "verified"]
    assert _statuses(["e c g"], "ECG") == ["new"] and _statuses(["ECG"], "e. c. g.") == ["new"]


def test_a_qualifier_is_heard_either_way():
    activate(CAT)
    got = check_items(["Repeat USG KUB"], "repeat usg kub after two weeks")
    assert (got[0]["status"], got[0]["canonical"]) == ("verified", "Ultrasound Kidneys Ureters and Bladder")
    assert _statuses(["Repeat USG KUB"], "usg kub") == ["verified"]
    assert _statuses(["Repeat ECG"], "repeat ecg") == ["new"] and _statuses(["Repeat ECG"], "repeat rft") == ["not-dictated"]


def test_a_negated_mention_is_not_heard():
    activate(CAT)
    assert _statuses(["ECG", "RFT"], "no need for ECG, do rft") == ["not-dictated", "verified"]
    assert _statuses(["RFT", "USG KUB"], "rft and no need of usg kub") == ["verified", "not-dictated"]
    assert _statuses(["USG KUB", "RFT"], "usg kub not needed. rft") == ["not-dictated", "verified"]
    assert _statuses(["ECG", "USG KUB"], "no ecg; avoid usg kub") == ["not-dictated", "not-dictated"]
    assert _statuses(["RFT"], "don't do rft") == ["not-dictated"]


def test_a_negation_does_not_spread_to_a_later_test():
    activate(CAT)
    assert _statuses(["ECG"], "no fever, get ecg") == ["new"]
    assert _statuses(["ECG"], "no fever get ecg") == ["new"]                       # bare "no" covers only the next word
    assert _statuses(["ECG", "RFT"], "no need for ecg but do rft") == ["not-dictated", "verified"]
    assert _statuses(["ECG"], "no need for ecg. later: get ecg") == ["new"]          # also said plainly


def test_close_but_different_tests_are_not_heard():
    activate(CAT)
    assert _statuses(["LFT", "Serum creatinine", "CBC"], "rft only") == ["not-dictated"] * 3
    assert _statuses(["EEG"], "ecg") == ["not-dictated"]
    assert _statuses(["T3 T4"], "t3 t5") == ["not-dictated"]
    assert _statuses(["MRI brain"], "mr sharma has brain fog") == ["not-dictated"]   # short codes are matched exactly
    assert _statuses(["Lipid profile"], "lipid profle") == ["new"]                   # a longer word may be a speech spelling


def test_heard_takes_the_entry_or_none():
    activate(CAT)
    rft = lookup("rft")
    assert heard("Renal Function Test", rft, "kft please") and not heard("Renal Function Test", None, "kft please")
    assert not heard("RFT", rft) and not heard("", None, "anything")


def test_words_from_separate_remarks_do_not_add_up_to_a_test():
    activate(CAT)
    assert _statuses(["Kidney function test"], "kidney pain since 2 days, function normal") == ["not-dictated"]
    assert _statuses(["Liver function test"], "liver is enlarged, function tests to be done later") == ["not-dictated"]
    assert _statuses(["Liver function test"], "liver is enlarged and renal function test") == ["not-dictated"]
    assert _statuses(["CT abdomen"], "previous CT was normal. abdomen soft") == ["not-dictated"]
    assert _statuses(["Urine culture"], "urine is cloudy. blood culture sent") == ["not-dictated"]
    assert _statuses(["X-ray chest"], "chest pain, x ray of knee") == ["not-dictated"]
    assert _statuses(["Vitamin D"], "get vitamin b12 level") == ["not-dictated"]
    assert _statuses(["X-ray wrist"], "no x ray wrist") == ["not-dictated"]


def test_content_words_in_one_clause_in_order_are_heard():
    activate(CAT)
    assert _statuses(["X-ray chest PA view"], "x-ray chest PA view") == ["new"]
    assert _statuses(["CT abdomen", "Vitamin D"], "ct of the abdomen and vitamin d level") == ["new", "new"]
    assert _statuses(["Urine culture"], "send urine for culture") == ["new"]


def test_reconcile_uses_each_previous_item_once():
    activate(CAT)
    prev = [{"text": "RFT", "canonical": "Renal Function Test", "status": "verified", "source": "dictated"}]
    got = I.reconcile(prev, ["RFT", "RFT"], "advise rft")
    assert got[0] == prev[0] and got[1]["text"] == "RFT" and got[1] is not prev[0]


def test_reconcile_marks_an_item_the_correction_added_but_did_not_say_not_dictated():
    activate(CAT)
    got = I.reconcile(["CBC"], ["CBC", "Brain impulses"], "make the dose twice daily")
    assert (got[0]["text"], got[0]["status"]) == ("CBC", "")
    assert (got[1]["text"], got[1]["status"], got[1]["source"]) == ("Brain impulses", "not-dictated", "dictated")


def test_reconcile_never_trusts_a_source_status_or_canonical_on_a_new_item():
    """Final review I1: a correction's patch cannot smuggle an AI-invented test in as the doctor's (forged dict)."""
    activate(CAT)
    prev = [{"text": "RFT", "canonical": "Renal Function Test", "status": "verified", "source": "doctor"}]
    forged = [{"text": t, "source": "doctor", "status": "verified", "canonical": "Forged"} for t in ("USG KUB", "ECG")]
    got = I.reconcile(prev, [{**prev[0], "source": "dictated"}] + forged, "change dolo to twice daily")
    assert got[0] == prev[0]                                                  # a kept item keeps the page's source
    assert [(i["text"], i["status"], i["source"], i["canonical"]) for i in got[1:]] == [
        ("USG KUB", "not-dictated", "dictated", "Ultrasound Kidneys Ureters and Bladder"),   # catalogue test: red
        ("ECG", "not-dictated", "dictated", "")]                                             # unknown test: red
    assert [b["text"] for b in I.screen({"investigations": got})] == ["USG KUB", "ECG"]      # both block Save
    said = I.reconcile(prev, forged, "also advise usg kub and ecg")
    assert [(i["status"], i["source"]) for i in said] == [("verified", "dictated"), ("new", "dictated")]


def test_regrade_never_keeps_a_page_canonical_on_an_unchecked_item():
    activate(CAT)
    got = I.regrade([{"text": "Brain impulses", "canonical": "<b>x</b>", "status": "", "source": "dictated"},
                     {"text": "RFT", "canonical": "Forged", "status": "not-dictated", "source": "dictated"}])
    assert [(i["status"], i["canonical"]) for i in got] == [("", ""), ("not-dictated", "Renal Function Test")]
