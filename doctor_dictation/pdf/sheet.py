"""Print HTML for the prescription sheet. Pure and deterministic; every value is escaped."""
import re
from html import escape

from .layout import ALIGNS, MAX_DOCTORS, PROFILE_KEYS, Layout

DISCLAIMER = (
    "AI draft — doctor must verify before signing. "
    "STT + LLM may mishear drug names."
)

# status -> (symbol, label) for the Rx "Check" column (mirrors frontend pill()).
_CHECK = {
    "verified": ("✓", "Verified: in transcript and medicine list"),
    "unknown-medicine": ("!", "Needs check: not in medicine list"),
    "unverified-strength": ("±", "Needs check: strength not in known list"),
}
_CHECK_DEFAULT = ("?", "Needs check: name not clearly dictated")


def _esc(value) -> str:
    """HTML-escape any value (``None`` -> ``""``); never emits markup."""
    return escape(str(value if value is not None else ""))


def _list_items(values) -> str:
    """One ``<li>`` per non-empty value, or a single ``—`` placeholder."""
    items = values if isinstance(values, list) else []
    rendered = [f"<li>{_esc(v)}</li>" for v in items if str(v).strip()]
    return "".join(rendered) or "<li>—</li>"


def _profile_header(profile) -> str:
    """Doctor/clinic header for the top of the sheet, or ``""`` when unset.

    ``profile`` is ``meta["profile"]``: a dict of the six fields above. Every
    value is HTML-escaped and blank lines are dropped, so a missing profile
    (``None`` or all-empty) renders no header at all — the sheet never shows
    ``None``.
    """
    if not isinstance(profile, dict):
        return ""
    fields = {k: _esc(profile.get(k)) for k in PROFILE_KEYS}
    if not any(fields.values()):
        return ""
    lines = []
    who = " ".join(p for p in (fields["doctor_name"], fields["qualifications"]) if p)
    if who:
        lines.append(f'<div class="clinic-doctor">{who}</div>')
    if fields["clinic_name"]:
        lines.append(f'<div class="clinic-name">{fields["clinic_name"]}</div>')
    meta_bits = []
    if fields["reg_no"]:
        meta_bits.append(f'Reg. No: {fields["reg_no"]}')
    if fields["phone"]:
        meta_bits.append(f'Ph: {fields["phone"]}')
    if meta_bits:
        lines.append(f'<div class="clinic-meta">{" &nbsp;|&nbsp; ".join(meta_bits)}</div>')
    if fields["address"]:
        lines.append(f'<div class="clinic-addr">{fields["address"]}</div>')
    return '<div class="clinic-head">' + "".join(lines) + "</div>"


def _rx_rows(rx) -> str:
    """The Rx table body: one row per medicine, or a ``—`` placeholder."""
    rows = [
        r for r in (rx if isinstance(rx, list) else [])
        if isinstance(r, dict) and (r.get("name") or r.get("strength"))
    ]
    if not rows:
        return '<tr><td colspan="7">—</td></tr>'
    out = []
    for index, row in enumerate(rows, 1):
        medicine = " ".join(
            str(part) for part in (
                row.get("form") or "", row.get("name") or "", row.get("strength") or ""
            ) if str(part).strip()
        )
        symbol, label = _CHECK.get(row.get("status"), _CHECK_DEFAULT)
        out.append(
            "<tr>"
            f"<td>{index}</td>"
            f"<td>{_esc(medicine)}</td>"
            f"<td>{_esc(row.get('dose'))}</td>"
            f"<td>{_esc(row.get('timing'))}</td>"
            f"<td>{_esc(row.get('duration'))}</td>"
            f"<td>{_esc(row.get('instructions'))}</td>"
            f'<td title="{_esc(label)}">{_esc(symbol)}</td>'
            "</tr>"
        )
    return "".join(out)


_PX = {"title": 20, "subtitle": 15, "normal": 12, "small": 10}      # fixed role -> font size
_LOGO = re.compile(r"data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=]+")
_DANGER = set("\\\"'<>&") | {chr(c) for c in (*range(32), 0x7F, 0x2028, 0x2029)}


def _css_str(value, cap: int = 80) -> str:
    """Body of a CSS string: quotes, backslashes, angle brackets and controls become hex escapes."""
    return "".join(f"\\{ord(c):x} " if c in _DANGER else c for c in str(value or "")[:cap])


_CAP_NAME, _CAP_QUALS, _CAP_REG, _CAP_LINE = 60, 80, 30, 80      # per-field footer caps (a doctors line is at most ~185)
_JUSTIFY = {"left": "flex-start", "center": "center", "right": "flex-end"}


_DOCTOR_KEYS = ("doctor_name", "qualifications", "reg_no")


def _resolved(layout: Layout, live, authored: bool = False) -> dict:
    """Spec 9.4: a live value (clinic fields from the clinic, doctor fields from the author) wins over the
    layout's stored snapshot when it is not blank. When the print has an author the doctor fields come from the
    author ONLY (a blank stays blank), so one doctor's name is never printed beside another's registration number."""
    live = live if isinstance(live, dict) else {}
    out = {}
    for k in PROFILE_KEYS:
        value = live.get(k)
        value = value.strip() if isinstance(value, str) else ""
        out[k] = value if authored and k in _DOCTOR_KEYS else value or str(layout.profile.get(k, ""))
    return out


def _doctor_entries(doctors, values: dict) -> list:
    """``(name, qualifications, reg_no)`` per doctor: ``meta["doctors"]`` when it is a non-empty list, else the one
    author from the resolved profile. Entries without a name are skipped; at most MAX_DOCTORS."""
    rows = doctors if isinstance(doctors, list) and doctors else [
        {"name": values["doctor_name"], "qualifications": values["qualifications"], "reg_no": values["reg_no"]}]
    out = []
    for d in rows:
        if isinstance(d, dict) and str(d.get("name") or "").strip():
            out.append(tuple(str(d.get(k) or "").strip() for k in ("name", "qualifications", "reg_no")))
    return out[:MAX_DOCTORS]


def _line(b: dict, values: dict) -> str:
    return str(values.get(b["field"], "") if "field" in b else b["text"]).strip()


def _lines(b: dict, values: dict, entries: list) -> list:
    """The printable lines of a text or doctors block, blank ones dropped (the footer margin boxes use these)."""
    if b["type"] == "doctors":
        # each field is capped on its own, so a long qualification can never cut the registration number off
        return [", ".join(p for p in (name[:_CAP_NAME], quals[:_CAP_QUALS]) if p)
                + (f"  Reg. No: {reg[:_CAP_REG]}" if reg else "") for name, quals, reg in entries]
    line = _line(b, values)[:_CAP_LINE] if b["type"] == "text" else ""
    return [line] if line else []


def _doctors_html(b: dict, entries: list) -> str:
    """One entry per doctor (name, qualifications, registration no.) side by side; every value escaped."""
    if not entries:
        return ""
    color, bold = (f";color:{b['color']}" if "color" in b else ""), 700 if b["role"] == "title" else 400
    cells = []
    for name, quals, reg in entries:
        parts = [f'<div style="font-size:{_PX[b["role"]]}px;font-weight:{bold}">{_esc(name)}</div>']
        parts += [f'<div style="font-size:10px">{_esc(t)}</div>' for t in (quals, f"Reg. No: {reg}" if reg else "") if t]
        cells.append("<div>" + "".join(parts) + "</div>")
    return (f'<div class="lh-doctors" style="display:flex;flex-wrap:wrap;gap:2mm 10mm;'
            f'justify-content:{_JUSTIFY[b["align"]]};text-align:{b["align"]}{color}">' + "".join(cells) + "</div>")


def _layout_header(layout: Layout, logo, values: dict, entries: list) -> str:
    """Page-1 header blocks as flowing HTML; a blank line, an empty doctors list or an absent logo prints nothing."""
    out = []
    for b in layout.header:
        align, line = f"text-align:{b.get('align', 'left')}", _line(b, values) if b["type"] == "text" else ""
        if b["type"] == "rule":
            out.append(f'<hr style="border:0;border-top:{2 if b["thickness"] == "medium" else 1}px solid {b.get("color", "#999")}">')
        elif b["type"] == "logo" and isinstance(logo, str) and _LOGO.fullmatch(logo):
            out.append(f'<div style="{align}"><img src="{logo}" style="max-height:25mm"></div>')
        elif b["type"] == "doctors":
            out.append(_doctors_html(b, entries))
        elif line:
            color, bold = f";color:{b['color']}" if "color" in b else "", 700 if b["role"] == "title" else 400
            out.append(f'<div style="{align}{color};font-size:{_PX[b["role"]]}px;font-weight:{bold}">{_esc(line)}</div>')
    return '<div class="lh">' + "".join(out) + "</div>"


def _footer_boxes(layout: Layout, values: dict, entries: list) -> str:
    """Page-1 footer as @bottom-* margin boxes, one per alignment, styled by the box's first printed block."""
    css = []
    for align in ALIGNS:
        mine = [(b, _lines(b, values, entries)) for b in layout.footer
                if b["type"] in ("text", "doctors") and b["align"] == align]
        mine = [(b, lines) for b, lines in mine if lines]
        if mine:
            text = "\\A ".join(_css_str(ln, 200) for _b, lines in mine for ln in lines)
            css.append(f'@bottom-{align} {{ content:"{text}"; white-space:pre-line; vertical-align:top; '
                       f'font-size:{_PX[mine[0][0]["role"]]}px; text-align:{align}; }}')
    return "\n".join(css)


def _page_css(layout, name, op_no, date, values=None, entries=()) -> str:
    """Page 1 follows the layout; pages 2+ get an identifier line so a loose page is never anonymous."""
    values = values or {}
    ident = " | ".join(p for p in (_css_str(name), f"OP/IP No: {_css_str(op_no)}" if op_no else "", _css_str(date)) if p)
    top, bottom, footer = (18, 16, "") if layout is None else (8, max(10, round((1 - layout.body_bottom) * 297)), _footer_boxes(layout, values, list(entries)))
    return f"""@page {{ size: A4; margin: 18mm 14mm 16mm;
    @top-left {{ content: "{ident}"; font-size: 9px; color: #444; }}
    @top-right {{ content: "Page " counter(page) " of " counter(pages); font-size: 9px; color: #444; }} }}
  @page :first {{ margin: {top}mm 14mm {bottom}mm; @top-left {{ content: none; }} @top-right {{ content: none; }}
    {footer} }}"""


def build_sheet_html(structured: dict, meta: dict, layout: Layout | None = None) -> str:
    """Render ``structured`` + ``meta`` as one self-contained HTML document.

    ``structured`` is the validated form (see ``determinism.validate_structured``)
    and ``meta`` carries the header fields ``date`` / ``opNo`` and an optional
    ``profile`` (the six clinic fields), an optional ``doctors`` list for a
    ``doctors`` block, ``authored`` (True when the prescription has an author: doctor fields then never fall back to the
    layout's snapshot); with a layout, non-blank ``profile`` values win over the
    layout's stored snapshot. The result is a deterministic string
    with every value HTML-escaped.
    """
    s = structured if isinstance(structured, dict) else {}
    m = meta if isinstance(meta, dict) else {}
    date = _esc(m.get("date"))
    op_no = _esc(m.get("opNo") or s.get("opNo"))
    name = _esc(s.get("patientName"))
    age_sex = _esc(s.get("ageSex"))
    review = _esc(s.get("review")) or "—"
    values = _resolved(layout, m.get("profile"), m.get("authored") is True) if layout is not None else {}
    entries = _doctor_entries(m.get("doctors"), values) if layout is not None else []
    header = _profile_header(m.get("profile")) if layout is None else _layout_header(layout, m.get("logo"), values, entries)
    lh_mm = 0 if layout is None else max(0, round(layout.body_top * 297) - 8)    # the header fills down to body.top
    page_css = _page_css(layout, m.get("patientName") or s.get("patientName"), m.get("opNo") or s.get("opNo"),
                         m.get("date"), values, entries)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Patient Clinical Summary &amp; Prescription</title>
<style>
  {page_css}
  body {{ font-family: Arial, Helvetica, sans-serif; color: #111; margin: 0; }}
  .lh {{ min-height: {lh_mm}mm; margin-bottom: 4mm; }}
  tr {{ break-inside: avoid; }}
  h1 {{ font-size: 18px; text-align: center; text-transform: uppercase; margin: 0 0 6px; }}
  .sub {{ text-align: center; font-size: 12px; margin-bottom: 16px; }}
  .sec-title {{ font-size: 12px; font-weight: bold; text-transform: uppercase;
                border-bottom: 1px solid #999; margin: 14px 0 6px; padding-bottom: 2px; }}
  ul {{ margin: 0 0 6px; padding-left: 20px; }}
  table.rx {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  table.rx th, table.rx td {{ border: 1px solid #999; padding: 4px 6px; text-align: left; }}
  .disclaimer {{ margin-top: 18px; font-size: 11px; color: #555; font-style: italic; }}
  .clinic-head {{ text-align: center; margin-bottom: 12px; }}
  .clinic-doctor {{ font-size: 14px; font-weight: bold; }}
  .clinic-name {{ font-size: 13px; }}
  .clinic-meta, .clinic-addr {{ font-size: 11px; color: #333; }}
</style>
</head>
<body>
{header}
<h1>PATIENT CLINICAL SUMMARY &amp; PRESCRIPTION</h1>
<div class="sub">{date} &nbsp;|&nbsp; OP/IP No: {op_no} &nbsp;|&nbsp; {name} &nbsp; {age_sex}</div>
<div class="sec-title">Diagnosis / Clinical Impression</div>
<ul>{_list_items(s.get("diagnosis"))}</ul>
<div class="sec-title">Chief Complaints &amp; Brief History</div>
<ul>{_list_items(s.get("complaints"))}</ul>
<div class="sec-title">Investigations Advised</div>
<ul>{_list_items(s.get("investigations"))}</ul>
<div class="sec-title">Rx (MEDICATIONS)</div>
<table class="rx">
<thead><tr><th>#</th><th>Medicine</th><th>Dosage</th><th>Timing</th><th>Duration</th><th>Instructions</th><th>Check</th></tr></thead>
<tbody>{_rx_rows(s.get("rx"))}</tbody>
</table>
<div class="sec-title">Dietary &amp; General Advice</div>
<ul>{_list_items(s.get("advice"))}</ul>
<div class="sec-title">Review / Follow-up</div>
<div>{review}</div>
<div class="disclaimer">{DISCLAIMER}</div>
</body>
</html>
"""
