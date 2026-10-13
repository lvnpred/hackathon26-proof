# B2a: PDF Renderer and Layout Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
- **Goal:** Replace `doctor_dictation/pdf.py` with a `pdf/` package: validated layout vocabulary, layout-aware sheet HTML with a page-2+ identifier line, and a pooled Chromium renderer.
- **Architecture:** `layout.py` validates layouts (pure). `sheet.py` builds print HTML with CSS paged media (`@page :first` for page 1, `@page` margin boxes for pages 2+). `renderer.py` runs one Chromium on one worker thread behind a bounded queue. The save path calls `render_prescription(..., layout=None)` and stays fail-soft.
- **Tech Stack:** Python 3.12, Playwright sync API (Chromium 153 verified), pytest, pypdf (one optional test).
- **Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` 7A.2, 7A.5, 7A.6, 8.2; contracts `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` 2, 3, 4.5, 5. Plan 11 of 15.
- **Adds 20 tests.** Run `.venv/bin/python -m pytest tests/ -q` first, note the count C; expect C + 20 at the end (the real-Chromium test skips without Playwright, pypdf or a browser, and still counts).
- **Assumptions about earlier plans:** B1a: package `doctor_dictation` and `pyproject.toml` exist; `doctor_dictation/pdf.py` has today's content; `tests/test_pdf.py` imports `from doctor_dictation.pdf import build_sheet_html, render_pdf`. B1e: the save route (`api/persistence.py`, `create_document`) holds the fail-soft block calling `build_sheet_html` and `render_pdf`; `create_app()` in `api/app.py` has a lifespan running `init_db()`; four tests in `tests/test_safety.py` patch `render_pdf` on the route module. Locate each with `grep -n`.

## Global Constraints
- No file over 500 lines. No `git commit`/`git push` (user rule): every task ends "leave uncommitted".
- Tests are offline and never need Playwright. `render_pdf(html, out_path)` and `build_sheet_html(structured, meta)` stay importable from `doctor_dictation.pdf`; `layout=None` keeps today's sheet.
- Dictated and LLM-written values are HTML-escaped, or hex-escaped inside CSS strings; the model never supplies HTML.
- **Rendering approach (checked with real Chromium 153 + Playwright 1.63):** `@page` margin boxes plus `@page :first` printed the identifier and `Page N of M` on pages 2-5 and nothing on page 1: chosen. Playwright `header_template` and `<thead>` repetition both also print on page 1, and an absolutely positioned header at a negative offset is clipped: rejected. The header flows at the top of page 1; the footer is text in `@bottom-*` margin boxes (footer colour, rule and logo unsupported). Telugu and Devanagari embedded real fonts (the Docker image needs Noto fonts, plan D0b). One worker did 20 sequential and 12 concurrent renders (0.4 s cold, about 80 ms warm).

## Review Focus
1. Patient name containing `"`, `</style>` or a backslash must not leave the CSS string (Task 2).
2. A layout colour like `#fff;background:url(x)`, or block type `html`, is rejected (Task 1).
3. A hung Chromium gives `PdfUnavailable` at the timeout (Save still succeeds); a dead Chromium is relaunched on the next render (Task 3).

### Task 1: Package skeleton and `layout.py`
- **Files:** Move `doctor_dictation/pdf.py` to `doctor_dictation/pdf/sheet.py`; Create `doctor_dictation/pdf/__init__.py`, `layout.py`; Test `tests/test_pdf_layout.py`.
- **Interfaces:** Produces `Layout(header, footer, body_top, body_bottom, profile)`, `LayoutError`, `validate_layout(raw)`, `DEFAULT_LAYOUT`, `PROFILE_KEYS`, `ALIGNS`.
- [ ] **Step 1: Package.** `mkdir doctor_dictation/pdf && git mv doctor_dictation/pdf.py doctor_dictation/pdf/sheet.py` (`mv` if untracked).
- [ ] **Step 2: Failing test** `tests/test_pdf_layout.py` (run it: expect `ImportError: cannot import name 'DEFAULT_LAYOUT'`):
```python
"""validate_layout: the vocabulary gate between a (possibly LLM-written) layout and the renderer."""
import copy

import pytest

from doctor_dictation.pdf import DEFAULT_LAYOUT, LayoutError, validate_layout

GOOD = {"header": [{"type": "logo", "crop": [0.05, 0.02, 0.2, 0.1]}, {"type": "text", "field": "doctor_name", "color": "#1a3c6e"},
                   {"type": "text", "text": "Open 9 to 5"}, {"type": "rule"}],
        "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"}],
        "body": {"top": 0.22, "bottom": 0.92}, "profile": {"doctor_name": "Dr. A. Rao"}}

def test_valid_layout_is_normalised_with_defaults_filled():
    layout = validate_layout(GOOD)
    assert layout.body_top == 0.22 and layout.profile["address"] == "" and layout.header[2]["align"] == "left"
    assert DEFAULT_LAYOUT.header[0]["field"] == "doctor_name"

@pytest.mark.parametrize("change", [
    lambda r: r["header"].append({"type": "html", "html": "<b>x</b>"}),
    lambda r: r["header"][0].update(crop=[0.1, 0.1, 1.2, 0.5]),
    lambda r: r["body"].update(top=0.9, bottom=0.5),
    lambda r: r["body"].update(bottom=True),
    lambda r: r["header"][1].update(color="red"),
    lambda r: r["header"][3].update(color="#fff;background:url(x)"),
    lambda r: r["header"][2].update(text="x" * 201),
    lambda r: r["header"][1].update(text="both"),
    lambda r: r["header"].extend([{"type": "rule"}] * 12),
    lambda r: r["footer"].append({"type": "logo", "crop": [0, 0, 1, 1]}),
    lambda r: r["profile"].update(phone="9" * 201),
])
def test_invalid_layouts_raise(change):
    raw = copy.deepcopy(GOOD)
    change(raw)
    with pytest.raises(LayoutError):
        validate_layout(raw)
```
- [ ] **Step 3: Create `doctor_dictation/pdf/layout.py`:**
```python
"""Layout vocabulary (spec 7A.2). Pure stdlib: the only way an LLM-written layout reaches the renderer."""
import re
from dataclasses import dataclass

PROFILE_KEYS = ("doctor_name", "qualifications", "reg_no", "clinic_name", "address", "phone")
ALIGNS, MAX_TEXT, MAX_BLOCKS = ("left", "center", "right"), 200, 12   # characters per line; blocks per header/footer
_ENUMS = {"role": (("title", "subtitle", "normal", "small"), "normal"), "align": (ALIGNS, "left"),
          "thickness": (("thin", "medium"), "thin")}
_FIELDS = {"text": ("role", "align"), "logo": ("align",), "rule": ("thickness",)}   # enum keys each block type takes
_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

class LayoutError(ValueError):
    """Outside the vocabulary; ``str(e)`` is safe to show."""

@dataclass(frozen=True)
class Layout:
    header: tuple; footer: tuple      # normalised block dicts in print order
    body_top: float; body_bottom: float   # fractions of the page height: the blank printable area
    profile: dict                     # all six PROFILE_KEYS, "" when unknown

def _check(ok, where, why):
    if not ok:
        raise LayoutError(f"{where}: {why}")

def _num(v, where):
    _check(type(v) in (int, float) and 0 <= v <= 1, where, "must be a number from 0 to 1")
    return float(v)

def _block(raw, where, in_header):
    kind = raw.get("type") if isinstance(raw, dict) else None
    _check(kind in _FIELDS, where, f"unknown block type {str(kind)[:30]!r}")
    out = {"type": kind}
    for key in _FIELDS[kind]:
        out[key] = raw.get(key, _ENUMS[key][1])
        _check(out[key] in _ENUMS[key][0], where, f"{key} must be one of {', '.join(_ENUMS[key][0])}")
    if raw.get("color", "") != "" and kind != "logo":
        _check(isinstance(raw["color"], str) and _HEX.fullmatch(raw["color"]), where, "color must be hex such as #1a3c6e")
        out["color"] = raw["color"]
    if kind == "text":
        _check(("field" in raw) != ("text" in raw), where, "needs exactly one of field or text")
        key = "field" if "field" in raw else "text"
        _check(raw[key] in PROFILE_KEYS if key == "field" else isinstance(raw[key], str) and raw[key].strip()
               and len(raw[key]) <= MAX_TEXT, where, f"field must be a profile field, or text 1 to {MAX_TEXT} characters")
        out[key] = raw[key]
    if kind == "logo":
        crop = raw.get("crop")
        _check(in_header and isinstance(crop, list) and len(crop) == 4, where, "logo needs a 4-number crop, header only")
        x0, y0, x1, y1 = out["crop"] = [_num(v, f"{where}.crop") for v in crop]
        _check(x0 < x1 and y0 < y1, where, "crop needs x0 < x1 and y0 < y1")
    return out

def _blocks(raw, name):
    _check(isinstance(raw, list) and len(raw) <= MAX_BLOCKS, name, f"must be a list of at most {MAX_BLOCKS} blocks")
    return tuple(_block(b, f"{name}[{i}]", name == "header") for i, b in enumerate(raw))

def validate_layout(raw) -> Layout:
    """Return a normalised ``Layout`` or raise ``LayoutError``."""
    _check(isinstance(raw, dict) and isinstance(raw.get("body"), dict) and isinstance(raw.get("profile", {}), dict),
           "layout", "must be an object with a body object (and an object profile)")
    top, bottom, profile = _num(raw["body"].get("top"), "body.top"), _num(raw["body"].get("bottom"), "body.bottom"), raw.get("profile", {})
    _check(top < bottom, "body", "needs 0 <= top < bottom <= 1")
    _check(all(isinstance(v, str) and len(v) <= MAX_TEXT for v in profile.values()), "profile", "values must be short text")
    return Layout(_blocks(raw.get("header", []), "header"), _blocks(raw.get("footer", []), "footer"),
                  top, bottom, {k: profile.get(k, "") for k in PROFILE_KEYS})

DEFAULT_LAYOUT = validate_layout({
    "header": [{"type": "text", "field": "doctor_name", "role": "title", "align": "center"},
               {"type": "text", "field": "clinic_name", "align": "center"}, {"type": "rule"}],
    "footer": [{"type": "text", "field": "address", "role": "small", "align": "center"}], "body": {"top": 0.18, "bottom": 0.92}})
```
- [ ] **Step 4:** Create `doctor_dictation/pdf/__init__.py` as below, then run `.venv/bin/python -m pytest tests/ -q`: expect C + 12 passed (existing `tests/test_pdf.py` still imports `doctor_dictation.pdf`). Leave uncommitted.
```python
from .layout import ALIGNS, DEFAULT_LAYOUT, PROFILE_KEYS, Layout, LayoutError, validate_layout
from .sheet import DISCLAIMER, build_sheet_html, render_pdf
```

### Task 2: Layout-aware `sheet.py`
- **Files:** Modify `doctor_dictation/pdf/sheet.py`; Test `tests/test_pdf_sheet.py`.
- **Interfaces:** Produces `build_sheet_html(structured, meta, layout=None)`. `meta` keys: `date`, `opNo`, `patientName` (falls back to the form's), `profile` (only when `layout is None`), `logo` (png/jpeg `data:` URI cropped by B2b, or absent).
- [ ] **Step 1: Failing test** `tests/test_pdf_sheet.py` (run it: expect `TypeError: build_sheet_html() takes 2 positional arguments`):
```python
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
```
- [ ] **Step 2: Edit `sheet.py`** (find anchors with `grep -n`):
  1. Replace the module docstring and the `from html import escape` / `from pathlib import Path` lines with:
```python
"""Print HTML for the prescription sheet. Pure and deterministic; every value is escaped."""
import re
from html import escape
from pathlib import Path   # removed again in Task 3

from .layout import ALIGNS, PROFILE_KEYS, Layout
```
  2. Delete the `_PROFILE_KEYS = (...)` line and its comment; in `_profile_header` rename `_PROFILE_KEYS` to `PROFILE_KEYS`.
  3. Insert immediately above `def build_sheet_html`:
```python
_PX = {"title": 20, "subtitle": 15, "normal": 12, "small": 10}      # fixed role -> font size
_LOGO = re.compile(r"data:image/(?:png|jpeg);base64,[A-Za-z0-9+/=]+")
_DANGER = set("\\\"'<>&") | {chr(c) for c in (*range(32), 0x7F, 0x2028, 0x2029)}

def _css_str(value) -> str:
    """Body of a CSS string: quotes, backslashes, angle brackets and controls become hex escapes."""
    return "".join(f"\\{ord(c):x} " if c in _DANGER else c for c in str(value or "")[:80])

def _line(b: dict, layout: Layout) -> str:
    return str(layout.profile.get(b["field"], "") if "field" in b else b["text"]).strip()

def _layout_header(layout: Layout, logo) -> str:
    """Page-1 header blocks as flowing HTML; a blank profile line or an absent logo prints nothing."""
    out = []
    for b in layout.header:
        align, line = f"text-align:{b.get('align', 'left')}", _line(b, layout) if b["type"] == "text" else ""
        if b["type"] == "rule":
            out.append(f'<hr style="border:0;border-top:{2 if b["thickness"] == "medium" else 1}px solid {b.get("color", "#999")}">')
        elif b["type"] == "logo" and isinstance(logo, str) and _LOGO.fullmatch(logo):
            out.append(f'<div style="{align}"><img src="{logo}" style="max-height:25mm"></div>')
        elif line:
            color, bold = f";color:{b['color']}" if "color" in b else "", 700 if b["role"] == "title" else 400
            out.append(f'<div style="{align}{color};font-size:{_PX[b["role"]]}px;font-weight:{bold}">{_esc(line)}</div>')
    return '<div class="lh">' + "".join(out) + "</div>"

def _footer_boxes(layout: Layout) -> str:
    """Page-1 footer as @bottom-* margin boxes, one per alignment, styled by the box's first line."""
    css = []
    for align in ALIGNS:
        mine = [b for b in layout.footer if b["type"] == "text" and b["align"] == align and _line(b, layout)]
        if mine:
            text = "\\A ".join(_css_str(_line(b, layout)) for b in mine)
            css.append(f'@bottom-{align} {{ content:"{text}"; white-space:pre-line; vertical-align:top; '
                       f'font-size:{_PX[mine[0]["role"]]}px; text-align:{align}; }}')
    return "\n".join(css)

def _page_css(layout, name, op_no, date) -> str:
    """Page 1 follows the layout; pages 2+ get an identifier line so a loose page is never anonymous."""
    ident = " | ".join(p for p in (_css_str(name), f"OP/IP No: {_css_str(op_no)}" if op_no else "", _css_str(date)) if p)
    top, bottom, footer = (18, 16, "") if layout is None else (8, max(10, round((1 - layout.body_bottom) * 297)), _footer_boxes(layout))
    return f"""@page {{ size: A4; margin: 18mm 14mm 16mm;
    @top-left {{ content: "{ident}"; font-size: 9px; color: #444; }}
    @top-right {{ content: "Page " counter(page) " of " counter(pages); font-size: 9px; color: #444; }} }}
  @page :first {{ margin: {top}mm 14mm {bottom}mm; @top-left {{ content: none; }} @top-right {{ content: none; }}
    {footer} }}"""
```
  4. Change the signature to `def build_sheet_html(structured: dict, meta: dict, layout: Layout | None = None) -> str:` and replace the line `header = _profile_header(m.get("profile"))` with:
```python
    header = _profile_header(m.get("profile")) if layout is None else _layout_header(layout, m.get("logo"))
    lh_mm = 0 if layout is None else max(0, round(layout.body_top * 297) - 8)    # the header fills down to body.top
    page_css = _page_css(layout, m.get("patientName") or s.get("patientName"), m.get("opNo") or s.get("opNo"), m.get("date"))
```
  5. In the template replace the `  body {{ ... margin: 24px; }}` line with:
```python
  {page_css}
  body {{ font-family: Arial, Helvetica, sans-serif; color: #111; margin: 0; }}
  .lh {{ min-height: {lh_mm}mm; margin-bottom: 4mm; }}
  tr {{ break-inside: avoid; }}
```
- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/test_pdf_sheet.py tests/test_pdf.py -q`: expect 9 passed (3 new; the 6 existing assertions untouched). Leave uncommitted.

### Task 3: `renderer.py`, final `__init__.py`, remove the old `render_pdf`
- **Files:** Create `doctor_dictation/pdf/renderer.py`; Modify `__init__.py`, `sheet.py`; Test `tests/test_pdf_renderer.py`.
- **Interfaces:** Produces `PdfUnavailable(RuntimeError)`, `PdfRenderer`, `ChromiumPoolRenderer(launcher, *, queue_size=16, timeout=30.0)` with `render`/`close`, `get_renderer()`, `close_renderer()`, `render_prescription(structured, meta, out_path, layout=None)`, wrapper `render_pdf`. Tests replace the renderer by patching `doctor_dictation.pdf.renderer.get_renderer`.
- [ ] **Step 1: Failing test** `tests/test_pdf_renderer.py` (run it: expect `ImportError: cannot import name 'PdfUnavailable'`):
```python
"""ChromiumPoolRenderer with a fake browser (offline); the real-Chromium check skips without Playwright."""
import threading
import time
from pathlib import Path

import pytest

from doctor_dictation.pdf import PdfUnavailable, build_sheet_html, close_renderer
from doctor_dictation.pdf import renderer as R

class FakeBrowser:
    """Browser, context and page in one; records which thread wrote each PDF."""
    def __init__(self): self.fail, self.delay, self.threads, self.up, self.stopped = False, 0, set(), True, 0
    def new_context(self, **kw): return self
    new_page = new_context
    def set_content(self, *a, **kw): pass
    close = set_content
    def is_connected(self): return self.up
    def pdf(self, path, **kw):
        if self.fail: raise OSError("disk full")
        time.sleep(self.delay); self.threads.add(threading.get_ident()); Path(path).write_bytes(b"%PDF-fake")

def make(**kw):
    browser, launches = FakeBrowser(), []
    def launcher():
        launches.append(1)
        return browser, lambda: setattr(browser, "stopped", browser.stopped + 1)
    return R.ChromiumPoolRenderer(launcher, **kw), browser, launches

def run_threads(n, target):
    threads = [threading.Thread(target=target, args=(i,)) for i in range(n)]
    [t.start() for t in threads]; [t.join(60) for t in threads]

def test_lazy_start_one_worker_thread_and_clean_close(tmp_path):
    pool, browser, launches = make()
    assert launches == []
    browser.delay, done = 0.02, []
    run_threads(12, lambda i: done.append(pool.render("<p>x</p>", tmp_path / f"{i}.pdf")))
    assert len(done) == 12 and len(launches) == 1 and len(browser.threads) == 1
    assert threading.get_ident() not in browser.threads
    pool.close()
    assert browser.stopped == 1
    with pytest.raises(PdfUnavailable, match="shut down"):
        pool.render("<p>x</p>", tmp_path / "late.pdf")
    close_renderer()                                            # a no-op when nothing was rendered

def test_full_queue_and_slow_render_raise_pdf_unavailable(tmp_path):
    pool, browser, _ = make(queue_size=1, timeout=0.2)
    browser.delay, errors = 0.6, []
    def go(i):
        try: pool.render("<p>x</p>", tmp_path / f"{i}.pdf")
        except PdfUnavailable as e: errors.append(str(e))
    run_threads(3, go)
    assert any("queue is full" in e for e in errors) and any("took over" in e for e in errors)
    pool.close()

def test_failures_are_pdf_unavailable_and_a_dead_chromium_is_relaunched(tmp_path):
    def broken(): raise PdfUnavailable("PDF renderer unavailable: chromium missing")
    with pytest.raises(PdfUnavailable, match="chromium"):
        R.ChromiumPoolRenderer(broken).render("<p>x</p>", tmp_path / "a.pdf")
    pool, browser, launches = make()
    browser.fail, browser.up = True, False                      # the render fails and chromium is gone
    with pytest.raises(PdfUnavailable, match="chromium"):
        pool.render("<p>x</p>", tmp_path / "a.pdf")
    browser.fail, browser.up = False, True
    assert pool.render("<p>x</p>", tmp_path / "a.pdf").exists() and len(launches) == 2
    pool.close()

def test_real_chromium_identifier_line_only_on_pages_two_and_later(tmp_path):
    PdfReader = pytest.importorskip("pypdf").PdfReader; pytest.importorskip("playwright.sync_api")
    html = build_sheet_html({"patientName": "Anita Rao", "rx": [{"name": f"D{i}"} for i in range(70)]}, {"opNo": "OP-77", "date": "d"})
    pool = R.ChromiumPoolRenderer(timeout=60)
    try: pages = [p.extract_text() for p in PdfReader(str(pool.render(html, tmp_path / "s.pdf"))).pages]
    except PdfUnavailable: pytest.skip("Chromium is not installed")
    finally: pool.close()
    assert len(pages) >= 2 and "Anita Rao | OP/IP No" not in pages[0]
    assert all(f"Anita Rao | OP/IP No: OP-77 | d Page {n} of {len(pages)}" in t for n, t in enumerate(pages[1:], 2))
```
- [ ] **Step 2: Create `doctor_dictation/pdf/renderer.py`:**
```python
"""Pooled headless-Chromium PDF renderer: one browser owned by one worker thread, a bounded queue."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Callable, Protocol

from .sheet import build_sheet_html

class PdfUnavailable(RuntimeError):
    """No PDF could be produced; callers fall back to browser print-to-PDF."""

class PdfRenderer(Protocol):
    def render(self, html: str, out_path: Path) -> Path: ...     # raises PdfUnavailable

def _no(why) -> PdfUnavailable:
    return PdfUnavailable(f"PDF renderer unavailable: {why}. Install it with 'pip install playwright' then "
                          "'playwright install chromium'; otherwise use browser print-to-PDF.")

def launch_chromium():
    """Start Playwright and Chromium; return ``(browser, stop)``. Playwright is imported lazily."""
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
    except Exception as e:  # not installed, or a broken install
        raise _no(f"Playwright (chromium) is not usable ({str(e)[:100]})") from e
    try:
        browser = pw.chromium.launch()
    except Exception as e:
        pw.stop()
        raise _no(f"chromium would not start ({str(e)[:100]})") from e
    return browser, lambda: (browser.close(), pw.stop())

class ChromiumPoolRenderer:
    """The one-thread executor is the worker: lazy, launches Chromium on its first job, the only Playwright thread."""

    def __init__(self, launcher: Callable = launch_chromium, *, queue_size: int = 16, timeout: float = 30.0):
        self._launcher, self._timeout, self._slots = launcher, timeout, threading.BoundedSemaphore(queue_size)
        self._lock, self._pool, self._browser, self._stop, self._closed = threading.Lock(), None, None, None, False

    def render(self, html: str, out_path) -> Path:
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self._closed:
                raise _no("the renderer was shut down")
            self._pool = self._pool or ThreadPoolExecutor(1, thread_name_prefix="pdf-worker")
            if not self._slots.acquire(blocking=False):
                raise _no("the PDF queue is full")
            job = self._pool.submit(self._job, html, out)
        job.add_done_callback(lambda _: self._slots.release())
        try:
            return job.result(timeout=self._timeout)
        except FutureTimeout:
            job.cancel()
            raise _no(f"chromium took over {self._timeout:g}s") from None

    def _job(self, html: str, out: Path) -> Path:        # runs on the worker thread only
        self._browser, self._stop = (self._browser, self._stop) if self._browser else self._launcher()
        try:
            context = self._browser.new_context(java_script_enabled=False)    # the sheet needs no scripts
            try:
                page, part = context.new_page(), out.with_name(out.name + ".part")
                page.set_content(html, wait_until="load", timeout=int(self._timeout * 1000))
                page.pdf(path=str(part), prefer_css_page_size=True, print_background=True)
                os.replace(part, out)
                return out
            finally:
                context.close()
        except Exception as e:
            if not self._browser.is_connected():         # chromium died: relaunch on the next job
                self._close_browser()
            raise _no(f"could not render with chromium ({e})") from e

    def _close_browser(self) -> None:
        stop, self._browser, self._stop = self._stop, None, None
        stop and stop()

    def close(self) -> None:
        with self._lock:
            self._closed, pool = True, self._pool
        if pool is not None:
            pool.submit(self._close_browser).result(timeout=10)
            pool.shutdown(wait=True)

_default, _default_lock = None, threading.Lock()

def get_renderer() -> PdfRenderer:
    global _default
    with _default_lock:
        _default = _default or ChromiumPoolRenderer()
        return _default

def close_renderer() -> None:
    """App shutdown: stop the worker and its browser; a no-op when no PDF was ever rendered."""
    global _default
    with _default_lock:
        renderer, _default = _default, None
    if renderer is not None and hasattr(renderer, "close"):
        renderer.close()

def render_prescription(structured: dict, meta: dict, out_path, layout=None) -> Path:
    """Build the sheet and render it; raises ``PdfUnavailable`` (or OSError) so the caller can fail soft."""
    return get_renderer().render(build_sheet_html(structured, meta, layout), Path(out_path))
```
- [ ] **Step 3: Replace `__init__.py`:**
```python
from pathlib import Path

from . import renderer as _renderer
from .layout import DEFAULT_LAYOUT, Layout, LayoutError, validate_layout
from .renderer import PdfRenderer, PdfUnavailable, close_renderer, render_prescription
from .sheet import DISCLAIMER, build_sheet_html

def render_pdf(html: str, out_path) -> Path:
    return _renderer.get_renderer().render(html, Path(out_path))
```
- [ ] **Step 4:** In `sheet.py` delete `def render_pdf` through end of file and the `from pathlib import Path` line (`grep -n "Path\|render_pdf" doctor_dictation/pdf/sheet.py` prints nothing).
- [ ] **Step 5: Run** `.venv/bin/python -m pytest tests/ -q`: expect C + 19 passed. Without Playwright `tests/test_pdf.py::test_render_pdf_writes_file_or_raises` still passes: `PdfUnavailable` is a `RuntimeError` naming chromium. Leave uncommitted.

### Task 4: Wire the save path, shutdown and the `pdf` extra
- **Files:** Modify the save-route module (`grep -rn render_pdf doctor_dictation/api`), the lifespan module (`grep -rn "def lifespan" doctor_dictation`), `pyproject.toml`, `tests/test_safety.py`.
- [ ] **Step 1: Retarget the four patches** in `tests/test_safety.py` (setup lines only). Add `import types` and, once near the helpers:
```python
def _use_renderer(monkeypatch, fn):
    fake = types.SimpleNamespace(render=fn)
    monkeypatch.setattr("doctor_dictation.pdf.renderer.get_renderer", lambda: fake)
```
  Change each `monkeypatch.setattr(M, "render_pdf", X)` (`fake_render`, two `boom`, `capture`) to `_use_renderer(monkeypatch, X)`. Append this test (put the lifespan module found above in the dotted path):
```python
def test_app_shutdown_closes_the_pdf_renderer(client_db, monkeypatch):
    calls = []
    monkeypatch.setattr("doctor_dictation.api.app.close_renderer", lambda: calls.append(1))
    with TestClient(M.app):
        pass
    assert calls == [1]
```
  Run `.venv/bin/python -m pytest tests/test_safety.py -q`: the four retargeted tests and the new one fail (the route still calls the old functions).
- [ ] **Step 2: Route.** Replace the import of `build_sheet_html, render_pdf` with `from doctor_dictation import pdf as pdf_pkg`, and the `build_sheet_html(...)` plus `render_pdf(...)` calls inside the `try:` with the block below. Leave `except Exception: pdf_path = None` as is.
```python
            rendered = pdf_pkg.render_prescription(
                validated,
                {"date": dbmod._utcnow()[:10], "opNo": validated.get("opNo") or "",
                 "patientName": validated.get("patientName") or "",
                 "profile": _profile_dict(dbmod.get_profile(conn))},
                dbmod.pdf_dir() / f"encounter_{encounter_id}.pdf",
                layout=None,   # B2b passes the clinic's active template here
            )
            pdf_path = str(rendered)
```
- [ ] **Step 3: Shutdown.** In the lifespan module add `from doctor_dictation.pdf import close_renderer` and call `close_renderer()` right after `yield`. Nothing starts at startup; Chromium launches on the first Save.
- [ ] **Step 4: Extra.** `grep -n playwright pyproject.toml`; if absent add `pdf = ["playwright>=1.40"]` under `[project.optional-dependencies]` (extend an existing `pdf` list rather than repeat the key). Run `.venv/bin/python -m pytest tests/ -q`: expect C + 19 + 1 = C + 20 passed. Leave uncommitted.

### Task 5: Final verification (contracts section 5)
- [ ] **Step 1:** Full suite equals C + 20; `wc -l doctor_dictation/pdf/*.py` shows each file under 500.
- [ ] **Step 2: Real render** (needs `.venv/bin/pip install playwright pypdf && .venv/bin/playwright install chromium`). Run `uvicorn doctor_dictation.main:app --port 8001`, load a form with 40+ medicines, Save twice. `pdftotext -f 2 -l 2 <pdf> -` shows `<name> | OP/IP No: ... | <date>` and `Page 2 of N`; page 1 shows neither. `pgrep -fl headless_shell` shows one browser after both saves and none after Ctrl-C. Without Chromium, Save returns 200 with `pdf_path` null and browser print still works.
- [ ] **Step 3: Report** changed files: `doctor_dictation/pdf/{__init__,layout,sheet,renderer}.py`, the route and lifespan modules, `pyproject.toml`, `tests/test_pdf_{layout,sheet,renderer}.py`, `tests/test_safety.py`. Not done by design: using a template (B2b passes `layout=`), logo cropping, footer colour/rule/logo, fonts in the image (D0b).