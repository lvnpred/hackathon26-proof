"""Discharge PDF. Decision-tier events are already stripped by the fold."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from app.config import BANNER
from app.report.count_sheet import latin1


def write_discharge(path: Path, *, label: str, sheet: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=16)

    def line(text: str, size: int = 11, bold: bool = False) -> None:
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.multi_cell(0, 7, latin1(text), new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(127, 29, 29)
    line(BANNER, size=12, bold=True)
    pdf.set_text_color(28, 25, 21)
    line("Discharge sheet", size=18, bold=True)
    line(f"Session: {label}")
    line(sheet["narrative"])
    line("OPD medicines", bold=True)
    if not sheet["opd"]:
        line("None recorded.")
    for item in sheet["opd"]:
        name = item.get("generic") or item.get("name_as_read")
        line(f"{name} {item.get('strength') or ''} ({item.get('drug_class') or 'as read'})")
    line("Drugs recorded in the room", bold=True)
    if not sheet["drugs"]:
        line("None confirmed.")
    for item in sheet["drugs"]:
        name = item.get("generic") or item.get("name_as_heard")
        line(
            f"{name} {item.get('strength') or ''} {item.get('amount') or ''} {item.get('unit') or ''} {item.get('route') or ''}".strip()
        )
    line("Count", bold=True)
    count = sheet["count"]
    if count is None:
        line("No closing count recorded.")
    else:
        line(
            f"Opened {count['opened']}. Returned {count['returned']}. Unaccounted {count['unaccounted']}. {count.get('detail') or ''}"
        )
    line("Recorded readings", bold=True)
    if not sheet["readings"]:
        line("None.")
    for reading in sheet["readings"]:
        line(f"BP {reading['systolic']}/{reading['diastolic']}, HR {reading['hr']}")
    pdf.output(str(path))
