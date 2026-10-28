"""The printed sheet's layout: the gap under the letterhead (E1) and the two-sided patient block (E5)."""
import pytest
from doctor_dictation.pdf import build_sheet_html, sections, validate_layout
from letterhead_fixtures import DOCTORS_LAYOUT

META = {"date": "25 Oct 2026", "opNo": "OP-1", "patientName": "Ravi"}
TITLE = "PATIENT CLINICAL SUMMARY"
TALL = validate_layout({"header": [{"type": "text", "field": "clinic_name", "role": "title", "align": "center"}, {"type": "rule"}],
                        "footer": [], "body": {"top": 0.30, "bottom": 0.92}, "profile": {"clinic_name": "Rao Clinic"}})
PNG = "data:image/png;base64,iVBORw0KGgo="


def _render(tmp_path, sheet, layout=None, meta=META):
    PdfReader = pytest.importorskip("pypdf").PdfReader; pytest.importorskip("playwright.sync_api")
    from doctor_dictation.pdf import PdfUnavailable, close_renderer, render_pdf
    seen = []
    try:
        try: path = render_pdf(build_sheet_html(sheet, meta, layout), tmp_path / "a.pdf")
        except PdfUnavailable as e:
            if "not usable" in str(e) or "would not start" in str(e): pytest.skip("Chromium is not installed")
            raise
    finally:
        close_renderer()
    for page in PdfReader(str(path)).pages:
        page.extract_text(visitor_text=lambda text, cm, tm, font, size: seen.append((text.strip(), tm[4] * cm[0] + cm[4], tm[5] * cm[3] + cm[5])) if text.strip() else None)
    return seen


def _y(seen, needle):
    return next(y for text, _x, y in seen if needle in text)


def test_letterhead_block_reserves_no_height():
    html = build_sheet_html({}, META, TALL)
    assert ".lh { margin-bottom: 4mm; }" in html and "min-height" not in html


def test_title_sits_close_under_the_last_letterhead_line(tmp_path):
    seen = _render(tmp_path, {"patientName": "Ravi"}, TALL)
    assert _y(seen, "Rao Clinic") - _y(seen, TITLE) <= 40   # 4 mm margin + the rule + one line; was about 230 pt


def test_logo_and_two_doctor_letterheads_never_overlap_the_title(tmp_path):
    logo = validate_layout({"header": [{"type": "logo", "crop": [0, 0, 0.2, 0.1]}, {"type": "text", "field": "clinic_name", "align": "center"}],
                            "footer": [], "body": {"top": 0.25, "bottom": 0.92}, "profile": {"clinic_name": "Logo Clinic"}})
    two = validate_layout(DOCTORS_LAYOUT)
    for layout, last, meta in ((two, "Rao Clinic", {**META, "doctors": [{"name": "Dr A One"}, {"name": "Dr B Two"}]}),
                               (logo, "Logo Clinic", {**META, "logo": PNG})):
        seen = _render(tmp_path, {"patientName": "Ravi"}, layout, meta)
        assert _y(seen, last) - _y(seen, TITLE) >= 8


# --- E5: the two-sided patient block ----------------------------------------------------------------------------

VITALS = {"pulse": "80/min", "spo2": "99%", "temp": "99"}


def test_patient_block_puts_name_age_date_left_and_vitals_right():
    html = sections.patient_block("Kodanda Pani", "65 / M", "25 Oct 2026", "OP-20261025-002", VITALS)
    assert '<div class="pt-name">Kodanda Pani · 65 / M · 25 Oct 2026</div>' in html
    left, right = html.split('<div class="pt-r">')
    assert "Pulse 80/min · SpO2 99% · Temp 99" in right and "pt-l" in left
    assert left.index("pt-name") < left.index("OP/IP No: OP-20261025-002")


def test_no_vitals_means_no_right_block():
    html = sections.patient_block("Ravi", "", "25 Oct 2026", "OP-1", None)
    assert "pt-r" not in html and '<div class="pt-name">Ravi · 25 Oct 2026</div>' in html
    assert "OP/IP No" not in sections.patient_block("Ravi", "", "", "", None) and sections.patient_block("", "", "", "", None) == ""


def test_patient_values_are_escaped():
    html = sections.patient_block("<b>x</b>", "", "", "<b>y</b>", None)
    assert "<b>" not in html and html.count("&lt;b&gt;") == 2


def test_a_long_name_wraps_beside_the_vitals_without_overlap(tmp_path):
    name = "Venkata Subrahmanyeswara Lakshmi Narasimha Rao Bahadur Jr " + "Q" * 60   # the last token (60 letters) has no space to break at
    vit = {"bp": "120/80", "pulse": "80/min", "temp": "99", "spo2": "99%", "weight": "64 kg"}
    seen = _render(tmp_path, {"patientName": name, "ageSex": "65 / M", "vitals": vit})
    words = set(name.split())
    name_right = max(x + len(t) * 6.5 for t, x, _y in seen if set(t.split()) & words)   # 15 px bold: about 6.5 pt a bold character
    vitals_left = min(x for t, x, _y in seen if t.startswith(("BP", "Pulse", "Temp", "SpO2", "Wt")))
    assert name_right < vitals_left
    assert not any("Q" * 60 in t for t, _x, _y in seen)   # the unbroken token is split, not left to run under the vitals


def test_larger_font_for_the_name_line():
    html = build_sheet_html({"patientName": "Ravi"}, META)
    assert ".pt-name { font-size: 15px; font-weight: bold; }" in html and ".sub" not in html
