"""Printed sections of the prescription sheet. Pure; every value is escaped; a section with nothing to print is ``""``
(no heading, no placeholder). ``title`` arguments are trusted markup, values never are."""
from html import escape

from doctor_dictation.core.followup import date_label
from doctor_dictation.core.sections import layout


def esc(value) -> str:
    """HTML-escape any value (``None`` -> ``""``); never emits markup."""
    return escape(str(value if value is not None else ""))


SEP = " \u00b7 "


def _print_text():
    """The investigations printer, resolved per call; ``None`` only when that module itself is absent."""
    try:
        from doctor_dictation.core.investigations import print_text
    except ModuleNotFoundError as exc:
        if exc.name != "doctor_dictation.core.investigations":
            raise                                   # the module exists but is broken: fail loudly
        return None
    return print_text


def item_text(value) -> str:
    """Printable text of one list item (unescaped): a dict item goes through ``print_text`` when that module exists."""
    if isinstance(value, dict):
        printer = _print_text()
        text = printer(value) if printer else value.get("text")
        return "" if text is None else str(text).strip()
    return str(value if value is not None else "").strip()


def _items(values) -> list:
    """The printable values: only a list counts; ``None`` and blank items are skipped."""
    return [v for v in (values if isinstance(values, list) else []) if v is not None and str(v).strip()]


def prose_section(title: str, values) -> str:
    items = _items(values)
    if not items:
        return ""
    return (f'<div class="sec-title">{title}</div><div class="prose">'
            + "".join(f"<p>{esc(v)}</p>" for v in items) + "</div>")


def bullet_section(title: str, values) -> str:
    items = _items(values)
    if not items:
        return ""
    return f'<div class="sec-title">{title}</div><ul>' + "".join(f"<li>{esc(v)}</li>" for v in items) + "</ul>"


def list_section(title: str, values) -> str:
    """A titled bullet list under the same heading as the screen (owner, 2026-10-20); nothing when empty."""
    return bullet_section(title, [item_text(v) for v in (values if isinstance(values, list) else [])])


def inline_section(title: str, values) -> str:
    """A titled run of items that wraps onto the next line, a bold diamond between items (owner, 2026-10-23: saves
    paper); nothing when empty. Each item is an inline-block, so a name breaks only when it is wider than the line."""
    items = _items([item_text(v) for v in (values if isinstance(values, list) else [])])
    if not items:
        return ""
    return (f'<div class="sec-title">{title}</div><div class="inline-list">'
            + ' <span class="sep"></span> '.join(f'<span class="item">{esc(v)}</span>' for v in items) + "</div>")


def _rx_row(index: int, row: dict, with_instructions: bool) -> str:
    medicine = " ".join(        # the name prints in capitals (owner rule); form and strength keep their case ("500 mg")
        str(part) for part in (row.get("form") or "", str(row.get("name") or "").upper(), row.get("strength") or "")
        if str(part).strip()
    )
    name, generic = str(row.get("name") or "").strip(), str(row.get("generic") or "").strip()
    gen = f'<div class="gen">generic: {esc(generic)}</div>' if generic and generic.casefold() != name.casefold() else ""
    directions = SEP.join(f'<span class="dir">{esc(str(row.get(k)).strip())}</span>' for k in ("dose", "timing", "duration")
                          if row.get(k) is not None and str(row.get(k)).strip())
    last = f"<td>{esc(row.get('instructions'))}</td>" if with_instructions else ""
    return f"<tr><td>{index}</td><td>{esc(medicine)}{gen}</td><td>{directions}</td>{last}</tr>"


def rx_section(rx, title: str = "Rx (MEDICATIONS)") -> str:
    """The medicines table; a row prints only when it is a dict with a name or strength. The Instructions column
    prints only when some printed row has instructions."""
    rows = [r for r in (rx if isinstance(rx, list) else [])
            if isinstance(r, dict) and (str(r.get("name") or "").strip() or str(r.get("strength") or "").strip())]
    if not rows:
        return ""
    with_instructions = any(str(r.get("instructions") or "").strip() for r in rows)
    extra = "<th>Instructions</th>" if with_instructions else ""
    return (f'<div class="sec-title">{title}</div><table class="rx">\n'
            f"<thead><tr><th>#</th><th>Medicine</th><th>Directions</th>{extra}</tr></thead>\n"
            "<tbody>" + "".join(_rx_row(i, r, with_instructions) for i, r in enumerate(rows, 1)) + "</tbody>\n</table>")


VITALS = (("bp", "BP"), ("pulse", "Pulse"), ("weight", "Wt"), ("spo2", "SpO2"), ("temp", "Temp"))


def _vital_text(value) -> str:
    """A vital as text; only str, int and float count (not bool), anything else is empty."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    return str(value).strip()


def vitals_strip(vitals) -> str:
    """One centred line of the recorded vitals as stored (no unit added); ``""`` when none is filled in."""
    if not isinstance(vitals, dict):
        return ""
    parts = [f"{label} {esc(text)}" for key, label in VITALS
             if (text := _vital_text(vitals.get(key)))]
    return f'<div class="vitals">{SEP.join(parts)}</div>' if parts else ""


def patient_block(name, age_sex, date, op_no, vitals) -> str:
    """The patient header as two sides: name, age/sex and date (with the OP/IP number under them) on the left, the
    vitals line on the right when any is filled in. Raw values in; escaped here; ``""`` when there is nothing."""
    line = SEP.join(esc(v).strip() for v in (name, age_sex, date) if esc(v).strip())
    op = f'<div class="pt-op">OP/IP No: {esc(op_no)}</div>' if esc(op_no).strip() else ""
    right = vitals_strip(vitals)
    if not (line or op or right):
        return ""
    left = f'<div class="pt-l"><div class="pt-name">{line}</div>{op}</div>' if line else f'<div class="pt-l">{op}</div>'
    return f'<div class="pt">{left}' + (f'<div class="pt-r">{right}</div>' if right else "") + "</div>"


def review_section(title: str, review, review_date) -> str:
    """The follow-up under its screen heading, with the computed date in brackets; nothing when empty."""
    text = str(review or "").strip()
    if not text:
        return ""
    label = date_label(review_date)
    when = f' <span class="rev-date">({esc(label)})</span>' if label else ""
    return f'<div class="sec-title">{title}</div><div class="prose"><p>{esc(review)}{when}</p></div>'


def sections_html(structured: dict, secs) -> str:
    """Every section the sheet shows, in list order, one string per section joined by newlines. Headings are text."""
    s = structured
    extra = s.get("extra") if isinstance(s.get("extra"), dict) else {}
    out = []
    for key, heading, kind in layout(secs, s):
        title = esc(heading)
        if kind == "prose":
            out.append(prose_section(title, s.get(key)))
        elif kind == "investigations":
            out.append(inline_section(title, s.get(key)))
        elif kind == "medication":
            out.append(rx_section(s.get(key), title))
        elif kind == "list":
            out.append(list_section(title, s.get(key)))
        elif kind == "review":
            out.append(review_section(title, s.get(key), s.get("review_date")))
        else:
            out.append(prose_section(title, (extra.get(key) or {}).get("lines")))
    return "\n".join(out)
