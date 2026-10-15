"""Spec 9.2/9.4: the doctors block and live profile values in the printed sheet. Pure HTML, offline."""
import pytest

from doctor_dictation.pdf import LayoutError, build_sheet_html, validate_layout

FORM = {"patientName": "Anita"}
META = {"date": "2026-10-14", "opNo": "RAO-20261014-001", "patientName": "Anita"}
TWO = [{"name": "Dr. A. Rao", "qualifications": "MBBS", "reg_no": "TS-1"},
       {"name": "Dr. S. Mehta", "qualifications": "DNB", "reg_no": ""}]


def _layout(header=None, footer=None, profile=None):
    return validate_layout({"header": header or [], "footer": footer or [], "body": {"top": 0.22, "bottom": 0.92},
                            "profile": profile or {}})


def test_doctors_block_is_in_the_vocabulary_for_header_and_footer():
    lay = _layout([{"type": "doctors", "ids": [1], "align": "center"}], [{"type": "doctors", "role": "small"}])
    assert lay.header[0] == {"type": "doctors", "role": "normal", "align": "center"}     # unknown keys dropped
    assert lay.footer[0] == {"type": "doctors", "role": "small", "align": "left"}
    with pytest.raises(LayoutError):
        _layout([{"type": "doctors", "role": "huge"}])


def test_doctors_block_prints_one_escaped_entry_per_doctor_in_order():
    html = build_sheet_html(FORM, {**META, "doctors": [{"name": "Dr. <b>X</b>", "qualifications": "MD"}] + TWO},
                            _layout([{"type": "doctors", "role": "title", "align": "center"}]))
    assert "Dr. &lt;b&gt;X&lt;/b&gt;" in html and "<b>X</b>" not in html
    assert html.index("Dr. &lt;b&gt;") < html.index("Dr. A. Rao") < html.index("Dr. S. Mehta")
    assert "Reg. No: TS-1" in html and "justify-content:center" in html


def test_doctors_block_without_a_list_prints_the_author_from_the_resolved_profile():
    lay = _layout([{"type": "doctors"}], profile={"doctor_name": "Dr. Snapshot", "qualifications": "MBBS"})
    assert "Dr. Live" in build_sheet_html(FORM, {**META, "profile": {"doctor_name": "Dr. Live"}}, lay)
    assert "Dr. Snapshot" in build_sheet_html(FORM, META, lay)
    assert "Dr. Snapshot" in build_sheet_html(FORM, {**META, "doctors": []}, lay)        # empty list: the author
    assert "lh-doctors" not in build_sheet_html(FORM, META, _layout([{"type": "doctors"}]))


def test_live_profile_values_win_over_the_snapshot_only_when_not_blank():
    lay = _layout([{"type": "text", "field": "doctor_name"}, {"type": "text", "field": "clinic_name"}],
                  profile={"doctor_name": "Dr. Snapshot", "clinic_name": "Snap Clinic"})
    html = build_sheet_html(FORM, {**META, "profile": {"doctor_name": "Dr. Author", "clinic_name": "  "}}, lay)
    assert "Dr. Author" in html and "Dr. Snapshot" not in html and "Snap Clinic" in html


def test_doctors_block_in_the_footer_becomes_margin_box_lines():
    lay = _layout(footer=[{"type": "doctors", "role": "small", "align": "center"}])
    html = build_sheet_html(FORM, {**META, "doctors": TWO}, lay)
    assert '@bottom-center { content:"Dr. A. Rao, MBBS  Reg. No: TS-1\\A Dr. S. Mehta, DNB"' in html
    assert "font-size:10px" in html.split("@bottom-center")[1]


def test_hostile_doctor_values_cannot_inject_markup_or_leave_the_style_block():
    evil = [{"name": 'x"; } </style><script>alert(1)</script>', "qualifications": "<img src=x>", "reg_no": "\\"}]
    lay = _layout([{"type": "doctors"}], [{"type": "doctors", "align": "right"}])
    html = build_sheet_html(FORM, {**META, "doctors": evil}, lay)
    assert html.count("</style>") == 1 and "<script>" not in html and "<img src=x>" not in html
    assert "\\22 " in html and "\\3c " in html


def test_hostile_footer_values_stay_inside_the_content_string():
    evil = [{"name": 'N\u2028"\n\\22 x</style>', "qualifications": 'Q\u2028"\n\\22 </style>', "reg_no": 'R\u2028"\n\\22 </style>'}]
    html = build_sheet_html(FORM, {**META, "doctors": evil}, _layout(footer=[{"type": "doctors", "align": "left"}]))
    assert html.count("</style>") == 1
    content = html.split("@bottom-left { content:\"")[1].split('"; white-space')[0]
    assert "\n" not in content and "\u2028" not in content and '"' not in content
    assert content.count("\\5c 22") == 3 and "\\22 " in content            # the typed backslash is escaped, never a live escape
    assert "Reg. No: R" in content


def test_a_long_qualifications_string_still_leaves_the_reg_no_in_the_footer_line():
    doc = [{"name": "Dr. A. Rao", "qualifications": "MBBS, MD, DM " * 30, "reg_no": "TS-12345"}]
    html = build_sheet_html(FORM, {**META, "doctors": doc}, _layout(footer=[{"type": "doctors", "align": "left"}]))
    assert "Reg. No: TS-12345" in html.split("@bottom-left")[1]


def test_page_css_default_values_does_not_crash_a_footer_text_block():
    from doctor_dictation.pdf.sheet import _page_css
    lay = _layout(footer=[{"type": "text", "field": "clinic_name"}, {"type": "text", "text": "Open 9-5"}])
    assert "Open 9-5" in _page_css(lay, "Anita", "OP-1", "2026-10-14")


def test_doctors_list_is_capped():
    many = [{"name": f"Dr. N{i:02d}"} for i in range(20)]
    html = build_sheet_html(FORM, {**META, "doctors": many}, _layout([{"type": "doctors"}]))
    assert "Dr. N11" in html and "Dr. N12" not in html


SNAP = {"doctor_name": "Dr. Pad Rao", "qualifications": "MS Pad", "reg_no": "TS-1 (Rao)",
        "clinic_name": "Snap Clinic", "address": "", "phone": ""}
BOTH = [{"type": "text", "field": "doctor_name"}, {"type": "text", "field": "reg_no"}, {"type": "doctors"}]


def test_an_authored_print_never_borrows_the_pads_registration_number():
    lay = _layout(BOTH, [{"type": "doctors", "align": "left"}], profile=SNAP)
    html = build_sheet_html(FORM, {**META, "authored": True, "profile": {"doctor_name": "Dr. S. Mehta"}}, lay)
    assert "Dr. S. Mehta" in html and "TS-1" not in html and "MS Pad" not in html and "Reg. No" not in html


def test_an_authored_print_with_blank_doctor_fields_prints_no_snapshot_doctor_line():
    lay = _layout(BOTH, [{"type": "doctors", "align": "left"}], profile=SNAP)
    html = build_sheet_html(FORM, {**META, "authored": True, "profile": {"clinic_name": "Live Clinic"}}, lay)
    assert "Dr. Pad Rao" not in html and "TS-1" not in html and "lh-doctors" not in html


def test_an_authored_print_still_fills_blank_clinic_fields_from_the_snapshot():
    lay = _layout([{"type": "text", "field": "clinic_name"}], profile=SNAP)
    assert "Snap Clinic" in build_sheet_html(FORM, {**META, "authored": True, "profile": {"doctor_name": "Dr. X"}}, lay)


def test_an_author_less_print_still_falls_back_to_the_snapshot_field_by_field():
    lay = _layout(BOTH, profile=SNAP)
    html = build_sheet_html(FORM, {**META, "profile": {"doctor_name": "Dr. Live"}}, lay)
    assert "Dr. Live" in html and "TS-1 (Rao)" in html and "MS Pad" in html
