"""Plan g, Task 2: the server keeps a doctor generic through validation, corrections, renames, learning and print."""
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.ops import apply_ops
from doctor_dictation.core.formulary import learnable
from doctor_dictation.pdf.sections import rx_section as _rx_rows   # the brief named sheet._rx_rows; print moved to sections

DOC = {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol", "generic_source": "doctor", "generic_pending": True}


def test_validate_keeps_a_doctor_generic_on_an_unknown_combination():
    out, _ = validate_structured({"rx": [DOC]}, "zerodol-p")
    r = out["rx"][0]
    assert (r["generic"], r["generic_source"], r["generic_pending"]) == ("Aceclofenac + Paracetamol", "doctor", True)


def test_validate_drops_an_invalid_doctor_generic_and_warns():
    out, warns = validate_structured({"rx": [{**DOC, "generic": "<b>x</b>"}]}, "zerodol-p")
    assert out["rx"][0]["generic_source"] != "doctor" and "generic_pending" not in out["rx"][0]
    assert any("generic" in w for w in warns)


def test_a_lexicon_generic_sent_by_the_client_is_never_trusted():
    out, _ = validate_structured({"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol", "generic_source": "lexicon"}]}, "zerodol-p")
    assert out["rx"][0]["generic"] == "" and out["rx"][0]["generic_source"] == ""


def test_a_hidden_generic_brand_still_shows_the_doctors_generic():          # Review Focus 2
    out, _ = validate_structured({"rx": [{**DOC, "name": "Fefol"}]}, "fefol")
    assert out["rx"][0]["generic"] == "Aceclofenac + Paracetamol"


def test_suggestion_kept_only_without_an_exact_match():
    out, _ = validate_structured({"rx": [{"name": "Zerodol-P", "generic_suggestion": "aceclofenac plus paracetamol"},
                                        {"name": "Crocin", "generic_suggestion": "Paracetamol"},
                                        {"name": "Zerodol-P", "generic_suggestion": "Zerodol-P"}]}, "zerodol-p crocin")
    assert [r["generic_suggestion"] for r in out["rx"]] == ["aceclofenac + paracetamol", "", ""]


def test_untouched_doctor_row_is_not_recalculated_on_a_correction_or_save():
    current = {"rx": [{**DOC, "status": "unknown-medicine", "lexicon_match": ""}, {"name": "Crocin", "status": "verified", "lexicon_match": "Paracetamol"}]}
    validated, _ = validate_structured(current, "")
    preserve_untouched_rx_status(current, {}, validated)
    assert validated["rx"][0]["generic"] == "Aceclofenac + Paracetamol" and validated["rx"][0]["generic_source"] == "doctor"
    status_less = {"rx": [{k: v for k, v in DOC.items()}]}                   # a prior row without a status keeps it too
    v2, _ = validate_structured(status_less, "")
    preserve_untouched_rx_status(status_less, {}, v2)
    assert v2["rx"][0]["generic"] == "Aceclofenac + Paracetamol"


def test_a_spoken_rename_drops_the_old_brands_doctor_generic():           # Review Focus 3
    _cur, _patch, _notes, _t = apply_ops({"rx": [dict(DOC)]}, {"replace": {"rx": [{"from": "Zerodol-P", "to": "Zerodol-SP"}]}})
    assert not any(k in _cur["rx"][0] for k in ("generic", "generic_source", "generic_pending"))


def test_learnable_leaves_doctor_generic_rows_to_the_overlay():
    assert learnable({"rx": [dict(DOC)]}, [0]) == []


def test_print_shows_the_doctors_generic_as_entered_and_never_the_suggestion():
    html = _rx_rows([{"name": "Zerodol-P", "generic": "aceclofenac + Paracetamol", "generic_source": "doctor",
                      "generic_suggestion": "Aceclofenac + Paracetamol"}, {"name": "Xyz", "generic": "", "generic_suggestion": "Secretol"}])
    assert "generic: aceclofenac + Paracetamol" in html and "Secretol" not in html


def test_a_blocked_name_keeps_the_doctors_generic_as_text_and_still_grades_unknown():   # controller ruling 3
    from doctor_dictation.core import determinism as D, overlay, overlay_state
    e = next(x for x in D.shipped_lexicon() if x["canonical"] == "Escitalopram")
    before = overlay_state._active.get()
    overlay.activate(overlay.state_from_rows([{"kind": "medicine", "entry_key": overlay.entry_key_of(e), "action": "hide",
                                               "data": {}, "base_sha": overlay.entry_sha(e)}]))
    try:
        out, _ = validate_structured({"rx": [{"name": "Escitalopram", "generic": "Escitalopram", "generic_source": "doctor",
                                              "generic_suggestion": "Citalopram"}]}, "escitalopram")
        r = out["rx"][0]
        assert (r["status"], r["lexicon_match"], r["did_you_mean"]) == ("unknown-medicine", "", "")
        assert (r["generic"], r["generic_source"], r["generic_pending"]) == ("Escitalopram", "doctor", False)
        assert r["generic_suggestion"] == ""                    # a hidden name gets no "AI suggests" (final review M3)
    finally:
        overlay_state._active.set(before)
