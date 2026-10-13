"""Verify the sheet -> HTML builder + PDF renderer (Tasks 7/8).

Offline and deterministic: ``build_sheet_html`` has no DB, network, clock, or
randomness, so these tests need no fixtures or isolation. ``render_pdf`` is
allowed to *fail soft* when the Chromium renderer is not installed, so its test
tolerates either a real PDF file or a clear ``RuntimeError`` mentioning chromium
— the suite never requires Playwright.

Run:  ./.venv-arm64/Scripts/python -m pytest tests/ -q
"""
from doctor_dictation.pdf import build_sheet_html, render_pdf


def test_sheet_html_escapes_and_has_sections():
    html = build_sheet_html(
        {"patientName": "<b>x</b>", "rx": [{"name": "A", "status": "verified"}]},
        {"date": "2026-10-12", "opNo": "OP-1"},
    )
    # Values are HTML-escaped (escaped form present, raw tag absent anywhere).
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "<b>" not in html
    assert "MEDICATIONS" in html


def test_sheet_html_empty_rx_placeholder():
    assert "—" in build_sheet_html({}, {})


# --- clinic/doctor profile header (Task 3) ---------------------------------

def test_sheet_header_shows_profile():
    html = build_sheet_html({}, {"profile": {"doctor_name": "A. Rao", "reg_no": "12345", "clinic_name": "Meridian"}})
    assert "A. Rao" in html and "12345" in html and "Meridian" in html


def test_sheet_header_absent_profile_no_crash():   # Review Focus #3
    html = build_sheet_html({"patientName": "X"}, {})
    assert "PATIENT CLINICAL SUMMARY" in html and "None" not in html


def test_sheet_header_escapes_profile():
    html = build_sheet_html({}, {"profile": {"doctor_name": "<b>x</b>"}})
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html


def test_render_pdf_writes_file_or_raises(tmp_path):
    """Render to a real ``%PDF-`` file, or fail soft with a chromium message.

    The renderer is optional in this environment: when Playwright/Chromium is
    absent the function must raise ``RuntimeError`` that names chromium so the
    endpoint can fall back to browser print-to-PDF. Either outcome passes.
    """
    html = build_sheet_html({"patientName": "Anita"}, {})
    try:
        p = render_pdf(html, tmp_path / "s.pdf")
        assert p.read_bytes()[:5] == b"%PDF-"
    except RuntimeError as e:
        assert "chromium" in str(e).lower()  # renderer not installed here
