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


STATUSES = ["verified", "unknown-medicine", "unverified-name", "unverified-strength", "lookalike-check", "dose-check", "", None]


def test_the_printout_has_no_check_column_and_prints_the_same_for_every_status():
    """Decision 2026-10-16: the printed prescription carries no verification marks; checking is a screen task."""
    rows = [{"form": "Tab.", "name": "Prednisone", "strength": "10 mg", "dose": "1-0-1", "timing": "After food",
             "duration": "5 days", "instructions": "with milk", "status": s} for s in STATUSES]
    html = build_sheet_html({"patientName": "Anita Rao", "rx": rows}, META)
    table = html[html.index('<table class="rx">'):html.index("</table>")]
    assert "<th>Check</th>" not in table and table.count("<th>") == 4 and "title=" not in table
    assert not any(mark in table for mark in ("✓", "≈", "±", "Needs check", "Verified:"))
    cells = [tr.count("<td>") for tr in table.split("<tr>")[2:]]
    assert cells == [4] * len(STATUSES)                                    # four cells per medicine, whatever its status
    printed = {tr.split("</td>", 1)[1].split("</tr>")[0] for tr in table.split("<tr>")[2:]}      # without the row number
    assert len(printed) == 1                                               # identical rows: the status does not print
    assert '<table class="rx">' not in build_sheet_html({"rx": []}, META)


def test_the_medicine_cell_prints_the_generic_on_a_second_line_under_a_brand():
    rows = [{"form": "Tab.", "name": "Crocin", "strength": "500 mg", "generic": "Paracetamol", "status": "verified"},
            {"form": "Tab.", "name": "Cetirizine", "strength": "10 mg", "generic": "Cetirizine", "status": "verified"},
            {"form": "Tab.", "name": "Citrizene", "strength": "10 mg", "generic": "", "status": "unknown-medicine"},
            {"form": "Cap.", "name": "Zyloric", "strength": "100 mg", "status": "verified"},            # saved before I2-a: no key
            {"form": "Tab.", "name": "Evil", "generic": "<b>x</b>"},
            {"form": "Tab.", "name": "Amlo", "strength": "5 mg", "generic": "Amlodipine", "status": "verified"},   # an alias kept as dictated
            {"form": "Tab.", "name": "cetirizine", "strength": "10 mg", "generic": "CETIRIZINE"}]             # same name, other case: no line
    html = build_sheet_html({"rx": rows}, META)
    table = html[html.index('<table class="rx">'):html.index("</table>")]
    cells = [tr.split("<td>")[2].split("</td>")[0] for tr in table.split("<tr>")[2:]]
    assert cells == ['Tab. CROCIN 500 mg<div class="gen">generic: Paracetamol</div>', "Tab. CETIRIZINE 10 mg",
                     "Tab. CITRIZENE 10 mg", "Cap. ZYLORIC 100 mg", 'Tab. EVIL<div class="gen">generic: &lt;b&gt;x&lt;/b&gt;</div>',
                     'Tab. AMLO 5 mg<div class="gen">generic: Amlodipine</div>', "Tab. CETIRIZINE 10 mg"]
    assert table.count("<th>") == 3 and ".gen { font-size: 10px; color: #444;" in html
    brand = [{"form": "Tab.", "name": "Crocin", "strength": "500 mg", "generic": "Paracetamol", "status": s} for s in STATUSES]
    again = build_sheet_html({"rx": brand}, META)
    cells = {tr.split("<td>")[2].split("</td>")[0] for tr in again[again.index('<table class="rx">'):again.index("</table>")].split("<tr>")[2:]}
    assert cells == {'Tab. CROCIN 500 mg<div class="gen">generic: Paracetamol</div>'}      # the status never changes what prints


def test_the_pdf_never_loads_frontend_css_and_the_browser_print_shows_the_same_line():
    from pathlib import Path
    html = build_sheet_html({"rx": [{"name": "Crocin", "generic": "Paracetamol"}]}, META)
    assert "<link" not in html and "rx.css" not in html and "<script" not in html        # server HTML, its own <style> only
    css = (Path(__file__).resolve().parents[1] / "frontend" / "rx.css").read_text(encoding="utf-8")
    assert "@media print { .rx-gen { font-size:10px; color:#444; } }" in css
    js = (Path(__file__).resolve().parents[1] / "frontend" / "genericedit.js").read_text(encoding="utf-8")
    assert '"rx-sub rx-gen" + (m.generic ? "" : " no-print")' in js       # the line is not a screen-only element (only an empty, open box is)


def test_investigations_print_as_dictated_with_the_full_name():
    html = build_sheet_html({"investigations": [{"text": "RFT", "canonical": "Renal Function Test", "status": "verified", "source": "dictated"},
                                                {"text": "Uroflow at home", "canonical": "", "status": "new", "source": "dictated"},
                                                "CBC"]}, META)
    assert "RFT (Renal Function Test)" in html and "Uroflow at home" in html and "CBC" in html
    assert "verified" not in html and "dictated" not in html          # status and source never print


def test_an_investigation_canonical_is_escaped():
    html = build_sheet_html({"investigations": [{"text": "X", "canonical": "<b>y</b>", "status": "new", "source": "doctor"}]}, META)
    assert "&lt;b&gt;y&lt;/b&gt;" in html and "<b>y</b>" not in html
