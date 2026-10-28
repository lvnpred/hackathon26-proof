"""E5: the browser print shows name/age/date bold on the left (OP under them) and the vitals on the right, like the PDF.
Text checks on the files, like tests/test_frontend_rxrow.py; the screen layout is unchanged."""
import re
from pathlib import Path

FRONT = Path(__file__).resolve().parents[1] / "frontend"
HTML = (FRONT / "index.html").read_text(encoding="utf-8")
CSS = (FRONT / "styles.css").read_text(encoding="utf-8")


def _print_block():
    start = CSS.index("@media print")
    return CSS[start:CSS.index("\n}\n", start)]


def test_block_wraps_patient_row_and_vitals_and_vitals_print():
    m = re.search(r'<div class="patient-block">(.*?)<div id="sheetBody" inert>', HTML, re.S)
    assert m and 'class="sub patient-row"' in m.group(1) and 'id="pVitals"' in m.group(1)
    tag = re.search(r'<div[^>]*id="pVitals"[^>]*>', HTML).group(0)
    assert "no-print" not in tag


def test_print_orders_name_age_date_then_op_full_width():
    p = _print_block()
    for sel, order in (("#pName", 1), ("#pAge", 2), ("#pDate", 3), ("#pOp", 4)):
        assert re.search(re.escape(sel) + r"\s*\{[^}]*order\s*:\s*%d\b" % order, p), sel
    assert re.search(r"#pOp\s*\{[^}]*flex-basis\s*:\s*100%", p)
    assert re.search(r"\.patient-block\s*\{[^}]*display\s*:\s*flex", p)


def test_print_hides_empty_vitals_and_hint_and_pf_border():
    p = _print_block()
    assert ".vl:has(+ .pv:empty)" in p and "#pVitals .pv:empty" in p and "#pVitals .vhint" in p
    assert re.search(r"\.patient-block\s+\.pf\s*\{[^}]*border\s*:\s*0", p)


def test_print_hides_the_whole_vitals_box_when_no_vital_is_filled_and_wins_over_sheet_sub():
    p = _print_block()
    assert "#sheet #pVitals:not(:has(.pv:not(:empty)))" in p
    assert re.search(r"#sheet #pVitals\s*\{[^}]*flex\s*:\s*0 1 38%", p)
