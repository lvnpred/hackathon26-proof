"""Fill-in labels and duplicated profile fields on a letterhead (PQ-b, Task 1). Pure: no app, no DB."""
import copy

from doctor_dictation.templates import lines
from tests.template_fixtures import PROFILE

LABELS = ["Name: M F Age: Date:", "Visit After", "Submit", "O.P. No.", "Patient's Name", "Age/Sex",
          "BP:      Wt:      SpO2:", "Next visit on", "UHID", "Address:", "Mobile No.", "__________", ". . . ."]
NOT_LABELS = ["Reg. No.", "Reg. No. TS-12345", "Ph: 040 1234 5678", "Open Mon to Sat", "M / F", "Signature",
              "Timings 9 am - 5 pm", "Rx", "Date: 12/10/2026", "x" * 81, ""]


def _layout():
    return {"header": [{"type": "logo", "crop": [0, 0, .1, .1]}, {"type": "text", "field": "phone"},
                       {"type": "text", "text": "Name: M F Age: Date:"}],
            "footer": [{"type": "text", "text": "Visit After"}, {"type": "text", "text": "Open daily"}]}


def test_fill_in_labels_are_recognised():
    assert [t for t in LABELS if not lines.is_fill_in_label(t)] == []


def test_lines_that_are_not_labels_are_kept():
    assert [t for t in NOT_LABELS if lines.is_fill_in_label(t)] == []


def test_reg_no_is_never_a_fill_in_label():
    assert not any(lines.is_fill_in_label(t) for t in ("Reg. No.", "Regd. No:", "Registration No."))


def test_non_string_is_not_a_label():
    assert not lines.is_fill_in_label(None) and not lines.is_fill_in_label(5)


def test_fill_in_lines_reports_section_index_and_text_and_skips_field_blocks():
    assert lines.fill_in_lines(_layout()) == [{"section": "header", "index": 2, "text": "Name: M F Age: Date:"},
                                              {"section": "footer", "index": 0, "text": "Visit After"}]
    assert lines.fill_in_lines(None) == [] and lines.fill_in_lines({"header": "x"}) == []
    assert lines.fill_in_lines({"header": [None, 3, {"type": "text", "text": 5}]}) == []


def test_drop_fill_in_lines_removes_in_place_and_returns_texts():
    lay = _layout()
    assert lines.drop_fill_in_lines(lay) == ["Name: M F Age: Date:", "Visit After"]
    assert len(lay["header"]) == 2 and lay["footer"] == [{"type": "text", "text": "Open daily"}]
    assert lines.drop_fill_in_lines(None) == [] and lines.drop_fill_in_lines({"header": "x"}) == []


def test_duplicate_phone_as_field_blocks_and_as_a_footer_literal():
    lay = {"profile": {**PROFILE, "phone": "040 1234 5678; 98480 22338"},
           "header": [{"type": "text", "field": "phone"}],
           "footer": [{"type": "text", "text": "Ph: 98480-22338"}, {"type": "text", "field": "phone"}]}
    assert lines.duplicate_fields(lay) == [{"field": "phone", "header": [0], "footer": [0, 1]}]


def test_duplicate_address_literal_and_no_report_when_only_one_side_has_it():
    lay = {"profile": dict(PROFILE), "header": [{"type": "text", "field": "address"}],
           "footer": [{"type": "text", "text": "12 MG Road, Hyderabad - 500001"}]}
    assert lines.duplicate_fields(lay) == [{"field": "address", "header": [0], "footer": [0]}]
    only = copy.deepcopy(lay)
    only["footer"] = []
    assert lines.duplicate_fields(only) == []
    short = {"profile": {**PROFILE, "address": "Hyd Road"}, "header": [{"type": "text", "field": "address"}],
             "footer": [{"type": "text", "text": "Hyd Road"}]}
    assert lines.duplicate_fields(short) == []


def test_duplicate_fields_order_and_malformed_input():
    lay = {"profile": dict(PROFILE),
           "header": [{"type": "text", "field": "phone"}, {"type": "text", "field": "doctor_name"}],
           "footer": [{"type": "text", "field": "doctor_name"}, {"type": "text", "field": "phone"}]}
    assert [d["field"] for d in lines.duplicate_fields(lay)] == ["doctor_name", "phone"]
    assert lines.duplicate_fields(None) == [] and lines.duplicate_fields({"header": "x", "footer": 1}) == []
    assert lines.duplicate_fields({"header": [{"type": "text", "field": "phone"}],
                                   "footer": [{"type": "text", "field": "phone"}]}) == [
        {"field": "phone", "header": [0], "footer": [0]}]


def test_contact_and_phone_alone_are_labels_but_names_and_timings_are_not():
    assert lines.is_fill_in_label("Contact") and lines.is_fill_in_label("Phone")
    for t in ["Dr. Name", "Clinic Name", "Date of birth", "Timings: 10 am - 1 pm"]:
        assert not lines.is_fill_in_label(t), t
