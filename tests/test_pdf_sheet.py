"""build_sheet_html with a layout: page-1 letterhead, pages 2+ identifier line, escaping. Pure HTML."""
from doctor_dictation.pdf import build_sheet_html, validate_layout

LAYOUT = validate_layout({
    "header": [{"type": "text", "field": "doctor_name", "role": "title", "color": "#1a3c6e"},
               {"type": "text", "field": "qualifications"}, {"type": "logo", "crop": [0, 0, 0.2, 0.1]}],
    "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"},
               {"type": "text", "text": "Open 9 to 5", "align": "center"}],
    "body": {"top": 0.22, "bottom": 0.92}, "profile": {"doctor_name": "Dr. <i>Rao</i>", "address": "Plot 5"}})
META, FORM = {"date": "2026-10-13", "opNo": "OP-77", "patientName": "Anita Rao"}, {"patientName": "Anita Rao"}

def test_layout_header_resolves_profile_escapes_and_skips_blank_lines_and_bad_logos():
    html = build_sheet_html(FORM, META, LAYOUT)
    assert "Dr. &lt;i&gt;Rao&lt;/i&gt;" in html and "<i>Rao</i>" not in html and "color:#1a3c6e;font-size:20px" in html
    assert "<img" not in html and "qualifications" not in html and "AI draft" in html
    ok = "data:image/png;base64,iVBORw0KGgo="
    assert f'<img src="{ok}"' in build_sheet_html(FORM, {**META, "logo": ok}, LAYOUT)
    assert "<img" not in build_sheet_html(FORM, {**META, "logo": 'data:image/png;base64,AA"onerror="x'}, LAYOUT)

def test_page_one_footer_boxes_and_pages_two_plus_identifier_line():
    for layout in (None, LAYOUT):
        html = build_sheet_html(FORM, META, layout)
        first = html.index("@page :first")
        assert 'content: "Anita Rao | OP/IP No: OP-77 | 2026-10-13"' in html[:first]
        assert 'content: "Page " counter(page) " of " counter(pages)' in html[:first]
        assert "@top-left { content: none; }" in html[first:]
    html = build_sheet_html(FORM, META, LAYOUT)
    assert '@bottom-center { content:"Plot 5\\A Open 9 to 5"' in html and "margin: 8mm 14mm 24mm" in html  # (1-0.92)*297

def test_hostile_patient_name_cannot_leave_the_style_block():
    evil = 'x"; } </style><script>alert(1)</script> \\'
    html = build_sheet_html({"patientName": evil}, {**META, "patientName": evil})
    assert html.count("</style>") == 1 and "<script>" not in html and "\\3c " in html and "\\22 " in html
    assert 'class="clinic-doctor"' in build_sheet_html(FORM, {"profile": {"doctor_name": "A. Rao"}})   # layout=None
