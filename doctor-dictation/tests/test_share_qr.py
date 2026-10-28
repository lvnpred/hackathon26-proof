"""Plan FB-D Task 1: the QR on the printed prescription. Pure and offline."""
from pathlib import Path

from doctor_dictation.pdf import build_sheet_html
from doctor_dictation.pdf.qr import qr_data_uri, share_block

URL = "https://gsr.lightday.online/s/rao/" + "Ab3_-" * 4 + "xy"
FORM = {"patientName": "Asha Verma", "opNo": "OP-1", "rx": []}
META = {"date": "26 Oct 2026", "opNo": "OP-1"}


def test_the_qr_is_an_svg_data_uri_and_the_same_url_gives_the_same_image():
    uri = qr_data_uri(URL)
    assert uri.startswith("data:image/svg+xml") and uri == qr_data_uri(URL) != qr_data_uri(URL + "z")


def test_the_sheet_carries_the_qr_and_caption_only_when_a_link_is_given():
    html = build_sheet_html(FORM, {**META, "share": {"url": URL, "until": "2 Nov 2026"}})
    assert 'class="share-qr"' in html and "Scan to download · valid until 2 Nov 2026" in html
    assert html.index('class="disclaimer"') < html.index('class="share-qr"')
    assert build_sheet_html(FORM, {**META, "share": None}) == build_sheet_html(FORM, META)   # byte-identical without a link
    assert share_block({"url": URL, "until": "<b>"}).count("&lt;b&gt;") == 1 and share_block({}) == share_block("x") == ""


def test_segno_is_a_base_requirement():
    reqs = (Path(__file__).resolve().parents[1] / "doctor_dictation" / "requirements.txt").read_text()
    assert "segno>=1.6,<2" in reqs
