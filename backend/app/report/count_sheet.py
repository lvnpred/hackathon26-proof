"""A count sheet. It records counts and evidence. It gives no advice."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from app.config import BANNER


def write_count_sheet(
    path: Path,
    *,
    case: dict,
    ledger: list[dict],
    discrepancies: list[dict],
    narrative: str,
    model: str,
    trace: list[dict],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.add_page()
    def line(text: str, size: int = 11, bold: bool = False, height: int = 7) -> None:
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.multi_cell(0, height, text, new_x="LMARGIN", new_y="NEXT")

    pdf.set_text_color(127, 29, 29)
    line(BANNER, size=12, bold=True, height=8)
    pdf.ln(2)
    pdf.set_text_color(28, 25, 21)
    line("Count sheet", size=18, bold=True, height=10)
    line(f"Session: {case['label']}")
    line(f"Case: {case['id']}")
    line(f"Status: {case['status']}")
    line(f"Narrative model: {model}")
    pdf.ln(2)
    line("Ledger", size=13, bold=True, height=8)
    line("Item | opened | tray | field | bucket | unaccounted")
    for row in ledger:
        line(
            f"{row['item_type']} | {row['opened']} | {row['tray']} | {row['field']} | {row['bucket']} | {row['unaccounted']}"
        )
    pdf.ln(2)
    line("Discrepancies", size=13, bold=True, height=8)
    if not discrepancies:
        line("None.")
    for row in discrepancies:
        line(
            f"{row['status']} {row['rule_id']} {row['kind']} {row.get('item_type') or ''}: {row.get('detail') or ''}"
        )
        if row.get("evidence"):
            line("Evidence: " + ", ".join(row["evidence"]))
    pdf.ln(2)
    line("Narrative", size=13, bold=True, height=8)
    line(narrative or "No narrative.")
    if trace:
        pdf.ln(2)
        line("Tool calls", size=13, bold=True, height=8)
        for call in trace:
            line(f"{call.get('tool')} {call.get('arguments')}", size=10, height=6)
    pdf.ln(4)
    line(
        "Models: SAM 3.1 (sam-3.1), Muse Voice Transcribe (muse-voice-transcribe-1.0), "
        "Muse Spark Open, Muse Spark 1.3. Rules decide the count. The model only writes sentences.",
        size=9,
        height=5,
    )
    pdf.output(str(path))
