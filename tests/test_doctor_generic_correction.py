from test_correction import _stub_llm
from fastapi.testclient import TestClient
import doctor_dictation.main as M
from doctor_dictation.core.correction import CORRECTION_INSTRUCTION, build_correction_messages
from doctor_dictation.core.doctor_generic import patch_generics

# The page's real row shape (rxview.js wire): a LISTED row never carries its generic, only a doctor row does.
FORM = {"rx": [{"name": "Zerodol-P", "status": "unknown-medicine", "lexicon_match": "", "dose": "1-0-1"},
               {"name": "Pan", "status": "verified", "lexicon_match": "Pantoprazole", "dose": "1-0-0"}]}
SAID = "generic of zerodol-p is aceclofenac plus paracetamol, pan generic pantoprazole, dolo"


def test_instruction_teaches_the_generic_key_with_the_owner_example():
    assert '"generic of Zerodol-P is aceclofenac plus paracetamol" -> {"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}]}' in CORRECTION_INSTRUCTION
    assert "Never return \"generic_source\"" in CORRECTION_INSTRUCTION
    assert "16. To set or change a medicine's generic" in CORRECTION_INSTRUCTION
    assert CORRECTION_INSTRUCTION.index("15. vitals:") < CORRECTION_INSTRUCTION.index("16. To set")
    assert CORRECTION_INSTRUCTION.rstrip().endswith('{"replace": {"rx": [{"from": "Cephixime", "to": "Cefixime"}]}}')
    assert CORRECTION_INSTRUCTION.index("generic of Zerodol-P") < CORRECTION_INSTRUCTION.index("Cephixime")


def test_patch_whitelist():
    original = {"rx": [{"name": "Zerodol-P", "generic": "aceclofenac plus paracetamol", "generic_source": "lexicon"},
                       {"name": "Pan", "dose": "1-0-1", "generic": "pantoprazole"},
                       {"name": "Dolo", "generic": "<x>"}]}
    p, w = patch_generics(FORM, original, SAID)
    assert p["rx"][0] == {"name": "Zerodol-P", "generic": "aceclofenac + paracetamol", "generic_source": "doctor", "generic_pending": True}
    assert p["rx"][1] == {"name": "Pan", "dose": "1-0-1"}                  # an echo of Pan's LEXICON generic (not sent by the page)
    assert "generic" not in p["rx"][2] and w == ["The generic for Dolo was not changed: " + "Use letters, digits, spaces and . , ' ( ) / - only."]
    assert original["rx"][0]["generic_source"] == "lexicon" and original["rx"][1]["generic"] == "pantoprazole"


def test_model_set_source_and_pending_are_dropped():
    p, _ = patch_generics(FORM, {"rx": [{"name": "Zerodol-P", "dose": "SOS", "generic_source": "doctor", "generic_pending": False,
                                         "generic_suggestion": "X", "generic_suggestion_unknown": ["X"]}]})
    assert p["rx"] == [{"name": "Zerodol-P", "dose": "SOS"}]


def test_the_model_never_sees_suggestion_fields():
    form = {"rx": [{"name": "Zerodol-P", "generic_suggestion": "X", "generic_suggestion_unknown": ["X"], "generic_pending": True}]}
    sent = build_correction_messages("t", form)[1]["content"]
    assert "generic_suggestion" not in sent and "generic_pending" not in sent
    assert "generic_pending" in form["rx"][0]                                  # the caller's form is untouched


def test_spoken_generic_end_to_end(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol", "generic_source": "lexicon"}]})
    res = TestClient(M.app).post("/api/v1/correct", json={"transcript": "generic of zerodol-p is aceclofenac plus paracetamol", "current_form": FORM}).json()
    row = res["structured"]["rx"][0]
    assert (row["generic"], row["generic_source"], row["generic_pending"]) == ("Aceclofenac + Paracetamol", "doctor", True)
    assert "generic_listed" not in row                                       # an unlisted name has no listed generic
    assert res["structured"]["rx"][1]["generic"] == "Pantoprazole"
    assert res["changed_rows"] == [0]


def test_empty_or_null_generic_is_dropped_without_a_warning():
    p, w = patch_generics(FORM, {"rx": [{"name": "Zerodol-P", "dose": "SOS", "generic": ""},
                                        {"name": "Pan", "generic": None}, {"name": "Dolo", "generic": "  "}]})
    assert p["rx"] == [{"name": "Zerodol-P", "dose": "SOS"}, {"name": "Pan"}, {"name": "Dolo"}] and w == []


CROCIN = {"form": "Tab.", "name": "Crocin", "strength": "500 mg", "dose": "SOS", "timing": "", "duration": "", "instructions": "",
          "status": "verified", "lexicon_match": "Paracetamol", "heard": "", "lookalike": ""}
ZERODOL = {"form": "Tab.", "name": "Zerodol-P", "strength": "", "dose": "SOS", "timing": "", "duration": "5 days",
           "instructions": "", "status": "unknown-medicine", "lexicon_match": "", "heard": "", "lookalike": "",
           "generic_suggestion": "Aceclofenac + Paracetamol"}


def _correct(monkeypatch, patch, transcript, rows):
    _stub_llm(monkeypatch, patch)
    return TestClient(M.app).post("/api/v1/correct", json={"transcript": transcript, "current_form": {"patientName": "A", "rx": rows}}).json()


def test_final_review_probe_1_an_echoed_lexicon_generic_on_a_dose_patch_is_no_doctor_generic(monkeypatch):
    res = _correct(monkeypatch, {"rx": [{"name": "Crocin", "dose": "1-0-1", "generic": "Paracetamol"}]}, "make crocin twice daily", [CROCIN])
    row = res["structured"]["rx"][0]
    assert (row["dose"], row["generic"], row["generic_source"], row.get("generic_pending")) == ("1-0-1", "Paracetamol", "lexicon", None)
    assert res["warnings"] == []


def test_final_review_probe_2_an_unsaid_ai_generic_is_dropped_silently(monkeypatch):
    res = _correct(monkeypatch, {"rx": [{"name": "Zerodol-P", "dose": "1-0-1", "generic": "Aceclofenac + Paracetamol"}]},
                   "make zerodol p twice daily", [ZERODOL])
    row = res["structured"]["rx"][0]
    assert (row["dose"], row["generic"], row["generic_source"], row.get("generic_pending")) == ("1-0-1", "", "", None)
    assert row["generic_suggestion"] == "Aceclofenac + Paracetamol" and res["warnings"] == []


def test_a_said_generic_is_kept_with_a_speech_spelling_and_partly_said_is_dropped():
    patch = {"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}]}
    p, _ = patch_generics(FORM, patch, "generic of zerodol p is aceclofenak plus paracetamol")
    assert p["rx"][0]["generic_source"] == "doctor"                          # a close speech spelling counts as said
    p, _ = patch_generics(FORM, patch, "generic of zerodol p is aceclofenac")
    assert p["rx"][0] == {"name": "Zerodol-P"}                               # Paracetamol was never said
    p, _ = patch_generics(FORM, patch)                                       # no dictation at all: nothing was said
    assert p["rx"][0] == {"name": "Zerodol-P"}


def test_an_echo_of_the_current_doctor_generic_is_dropped_even_when_said():
    form = {"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol", "generic_source": "doctor", "generic_pending": True}]}
    p, w = patch_generics(form, {"rx": [{"name": "Zerodol-P", "dose": "SOS", "generic": "aceclofenac plus paracetamol"}]},
                          "zerodol p aceclofenac plus paracetamol sos")
    assert p["rx"] == [{"name": "Zerodol-P", "dose": "SOS"}] and w == []


def test_a_said_override_of_a_listed_brand_is_a_doctor_generic(monkeypatch):
    res = _correct(monkeypatch, {"rx": [{"name": "Crocin", "generic": "Paracetamol + Caffeine"}]},
                   "generic of crocin is paracetamol plus caffeine", [CROCIN])
    row = res["structured"]["rx"][0]
    assert (row["generic"], row["generic_source"], row["generic_pending"]) == ("Paracetamol + Caffeine", "doctor", True)
    assert row["generic_listed"] == "Paracetamol"                            # final review M1: the page's tick and restore


def test_letter_digit_tokens_and_numbers_must_be_said_exactly():             # re-review N1
    def kept(generic, said):
        p, _ = patch_generics(FORM, {"rx": [{"name": "Zerodol-P", "generic": generic}]}, said)
        return p["rx"][0].get("generic_source") == "doctor"
    assert not kept("Vitamin B12", "generic of zerodol p is vitamin d3")
    assert kept("Vitamin B12", "generic of zerodol p is vitamin b 12")
    # "Vitamin B1 + B6 + B12" is not a valid generic (a component needs 3 letters), so the valid spelling is tested
    B = "Vitamin B1 + Vitamin B6 + Vitamin B12"
    assert kept(B, "generic is vitamin b1 b6 b12")
    assert not kept(B, "generic is b1 b6 b12")                                 # "vitamin" is a letter word: it must be said
    assert not kept(B, "generic is vitamins")
    assert not kept("Vitamin B12", "generic is vitamin b")                    # half a token is not the token
    assert kept("Aceclofenac + Paracetamol", "generic of zerodol-p is aceclofenac plus paracetamol")   # the owner example
