import builtins, sys, types
import pytest
from doctor_dictation.pdf import DISCLAIMER, build_sheet_html, sections, validate_layout
MOD = "doctor_dictation.core.investigations"
META = {"date": "17 Oct 2026", "opNo": "OP-1", "patientName": "Ravi"}

def test_an_empty_sheet_prints_no_placeholders_and_keeps_the_disclaimer():
    html = build_sheet_html({"patientName": "Ravi", "rx": [], "advice": [], "review": ""}, META)
    for gone in ("<li>—</li>", "<p>—</p>", "<div>—</div>", 'colspan="6"', 'class="sec-title"', '<table class="rx">'):
        assert gone not in html
    assert DISCLAIMER in html and "PATIENT CLINICAL SUMMARY" in html and "OP/IP No: OP-1" in html

def test_whitespace_only_items_and_nameless_rows_count_as_empty():
    s = {"complaints": ["  "], "investigations": ["", " "], "rx": [{"dose": "1-0-1"}, "x"], "advice": [None], "review": "  "}
    assert 'class="sec-title"' not in build_sheet_html(s, META)

def test_only_the_filled_sections_print_in_the_old_order():
    s = {"diagnosis": ["Viral fever"], "rx": [{"name": "Crocin"}], "review": "1 week"}
    html = build_sheet_html(s, META)
    assert "Chief Complaints" not in html and html.index("Viral fever") < html.index("CROCIN") < html.index("1 week")

def test_a_document_saved_before_this_change_reprints_without_placeholders():   # Review Focus 1
    old = {"patientName": "Old", "diagnosis": ["Gastritis"], "complaints": ["epigastric pain", "nausea"],
           "investigations": ["CBC"], "review": "after 1 week", "rx": []}
    html = build_sheet_html(old, {"date": "2026-10-01"})
    assert "—</" not in html and "Gastritis" in html and "CBC" in html and "after 1 week" in html


def test_a_whitespace_only_rx_name_prints_no_row():
    html = build_sheet_html({"rx": [{"name": "  ", "dose": "1-0-1"}]}, META)
    assert '<table class="rx">' not in html and "1-0-1" not in html

def test_a_filled_sheet_prints_all_six_sections_in_order():
    s = {"complaints": ["C-fever"], "diagnosis": ["D-viral"], "investigations": ["I-CBC"], "rx": [{"name": "R-Crocin"}],
         "advice": ["A-rest"], "review": "V-1 week"}
    html = build_sheet_html(s, META)
    marks = ["C-fever", "D-viral", "I-CBC", "R-CROCIN", "A-rest", "V-1 week"]
    assert [html.index(m) for m in marks] == sorted(html.index(m) for m in marks)

def test_lists_print_as_titled_bullets_under_the_screen_headings():          # owner 2026-10-20: match the screen
    html = build_sheet_html({"investigations": ["CBC", "RFT"], "advice": ["Fluids 3 L/day", "Rest"]}, META)
    assert '<div class="sec-title">Investigations Advised</div><ul><li>CBC</li><li>RFT</li></ul>' in html
    assert '<div class="sec-title">Dietary &amp; General Advice</div><ul><li>Fluids 3 L/day</li><li>Rest</li></ul>' in html
    assert "inl-label" not in html

def test_a_list_with_one_long_item_keeps_the_titled_bullets():
    long = "Avoid oily and spicy food, take small frequent meals, no alcohol"   # 64 characters
    html = build_sheet_html({"advice": ["Rest", long]}, META)
    assert "Dietary &amp; General Advice" in html and f"<li>{long}</li>" in html and "<li>Rest</li>" in html

def test_item_text_without_plan_h_prints_the_dictated_text(monkeypatch):
    monkeypatch.setitem(sys.modules, MOD, None)
    assert sections.item_text({"text": " RFT ", "canonical": "Renal Function Test"}) == "RFT"
    assert sections.item_text({"canonical": "x"}) == "" and sections.item_text(" CBC ") == "CBC" and sections.item_text(None) == ""

def test_item_text_uses_plan_h_print_text_for_items_only(monkeypatch):
    fake = types.ModuleType(MOD); fake.print_text = lambda item: item["text"] + " (Renal Function Test)"
    monkeypatch.setitem(sys.modules, MOD, fake)
    assert sections.item_text({"text": "RFT"}) == "RFT (Renal Function Test)" and sections.item_text("RFT") == "RFT"
    html = build_sheet_html({"investigations": ["CBC", {"text": "RFT"}, {"text": "<b>x</b>"}]}, META)
    assert "<li>CBC</li><li>RFT (Renal Function Test)</li><li>&lt;b&gt;x&lt;/b&gt; (Renal Function Test)</li>" in html

def test_item_text_reraises_a_broken_investigations_module(monkeypatch):
    def broken(name, *a, **k):
        if name == MOD: raise ModuleNotFoundError("No module named 'rapidfuzz'", name="rapidfuzz")
        return real(name, *a, **k)
    real = builtins.__import__
    monkeypatch.delitem(sys.modules, MOD, raising=False); monkeypatch.setattr(builtins, "__import__", broken)
    with pytest.raises(ModuleNotFoundError):
        sections.item_text({"text": "RFT"})

def test_review_prints_under_its_heading_with_its_date_label():
    html = build_sheet_html({"review": "1 week", "review_date": "2026-10-24"}, META)
    assert '<div class="sec-title">Review / Follow-up</div><div class="prose"><p>' + '1 week <span class="rev-date">(Sat 24 Oct 2026)</span></p></div>' in html


def _d(*parts): return "<td>" + " · ".join(f'<span class="dir">{p}</span>' for p in parts) + "</td>"
def _table(html): return html[html.index('<table class="rx">'):html.index("</table>")]

def test_directions_share_one_column_and_instructions_drop_when_all_empty():
    rows = [{"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "1-0-1", "timing": "After food", "duration": "5 days"},
            {"form": "Tab.", "name": "Zerodol-P", "dose": "1-0-1", "duration": "3 days", "instructions": "  "}]
    t = _table(build_sheet_html({"rx": rows}, META))
    assert t.count("<th>") == 3 and "<th>Directions</th>" in t and "Instructions" not in t
    assert _d("1-0-1", "After food", "5 days") in t and _d("1-0-1", "3 days") in t
    assert "·  ·" not in t and "<td> · " not in t

def test_one_row_with_instructions_brings_the_column_back_for_every_row():
    rows = [{"name": "A", "dose": "1-0-0"}, {"name": "B", "instructions": "<b>with milk</b>"}]
    t = _table(build_sheet_html({"rx": rows}, META))
    assert t.count("<th>") == 4 and [tr.count("<td>") for tr in t.split("<tr>")[2:]] == [4, 4]
    assert "<td>&lt;b&gt;with milk&lt;/b&gt;</td>" in t and "<td></td>" in t

def test_the_generic_line_stays_under_the_brand():
    t = _table(build_sheet_html({"rx": [{"form": "Tab.", "name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}]}, META))
    assert '<td>Tab. ZERODOL-P<div class="gen">generic: Aceclofenac + Paracetamol</div></td>' in t

def test_directions_are_escaped_and_blank_parts_skipped():
    t = _table(build_sheet_html({"rx": [{"name": "A", "dose": "<i>1</i>", "timing": " ", "duration": "3 d"}]}, META))
    assert _d("&lt;i&gt;1&lt;/i&gt;", "3 d") in t

def test_item_text_gives_empty_when_print_text_returns_none(monkeypatch):
    monkeypatch.setattr(sections, "_print_text", lambda: (lambda value: None))
    assert sections.item_text({"text": "RFT"}) == ""


def test_vitals_print_once_under_the_patient_line_in_a_fixed_order():
    v = {"temp": "99 F", "bp": "130/80", "pulse": "82", "weight": "64 kg", "spo2": ""}
    html = build_sheet_html({"vitals": v, "complaints": ["C/o fever"]}, META)
    assert '<div class="vitals">BP 130/80 · Pulse 82 · Wt 64 kg · Temp 99 F</div>' in html
    assert "· P 82" not in html                                           # owner Q15: no single-letter label
    assert html.count('class="vitals"') == 1 and html.index("OP/IP No") < html.index("BP 130/80") < html.index("C/o fever")


def test_no_vitals_line_when_absent_empty_or_malformed():                 # Review Focus 1 and 5
    for v in (None, "", "BP 130/80", ["130/80"], {}, {"bp": " ", "pulse": ""}, {"height": "170 cm"}):
        assert 'class="vitals"' not in build_sheet_html({"vitals": v} if v is not None else {}, META)


def test_vitals_values_are_stringified_and_escaped():                    # Review Focus 3 and 5
    html = build_sheet_html({"vitals": {"pulse": 82, "bp": "<b>1</b>"}}, META)
    assert '<div class="vitals">BP &lt;b&gt;1&lt;/b&gt; · Pulse 82</div>' in html


def test_vitals_strip_accepts_only_text_and_numbers():
    assert sections.vitals_strip({"bp": True, "pulse": [1], "temp": {"a": 1}, "weight": 64.5}) == '<div class="vitals">Wt 64.5</div>'
    assert sections.vitals_strip({"bp": False}) == "" and sections.vitals_strip({"pulse": object()}) == ""


def test_spacing_rules_are_the_compact_values():
    html = build_sheet_html({}, META)
    assert ".sub { text-align: center; font-size: 12px; margin-bottom: 8px; }" in html
    assert "margin: 10px 0 4px;" in html and "padding: 3px 6px;" in html and ".disclaimer { margin-top: 12px;" in html
    assert ".vitals { text-align: center; font-size: 12px; margin: -4px 0 8px; }" in html


def _render_pages(tmp_path, sheet, name="a.pdf", visitor=None, edit=None, layout=None):
    PdfReader = pytest.importorskip("pypdf").PdfReader; pytest.importorskip("playwright.sync_api")
    from doctor_dictation.pdf import PdfUnavailable, close_renderer, render_pdf
    try:
        try: path = render_pdf((edit or (lambda h: h))(build_sheet_html(sheet, META, layout)), tmp_path / name)
        except PdfUnavailable as e:
            if "not usable" in str(e) or "would not start" in str(e): pytest.skip("Chromium is not installed")
            raise                                   # a real render failure or timeout must fail the test
    finally:
        close_renderer()
    pages = PdfReader(str(path)).pages
    return [p.extract_text(visitor_text=visitor) if visitor else p.extract_text() for p in pages]


def test_owner_like_sheet_renders_one_page_without_dashes(tmp_path):
    s = {"patientName": "Rajinikanth", "ageSex": "78 / M", "complaints": ["C/o fever with chills, 3 days."],
         "diagnosis": ["Viral fever"], "investigations": ["X-ray of the head and hip", "CT scan", "MRI"], "rx": [], "advice": [], "review": ""}
    pages = _render_pages(tmp_path, s)
    assert len(pages) == 1 and "• —" not in pages[0] and "MEDICATIONS" not in pages[0] and "AI draft" in pages[0]


def test_typical_prescription_with_vitals_renders_on_one_page(tmp_path):
    s = {"patientName": "Rajinikanth", "ageSex": "78 / M", "vitals": {"bp": "130/80", "pulse": 82, "weight": "64 kg"},
         "complaints": ["C/o fever with chills, 3 days."], "diagnosis": ["Viral fever"], "investigations": ["CBC", "RFT"],
         "rx": [{"name": f"Drug {i}", "dose": "1-0-1", "duration": "5 days"} for i in range(5)], "advice": ["Rest"], "review": "1 week"}
    def gap(edit=None):
        ys = {}
        def visit(text, cm, tm, font_dict, font_size):
            for key in ("Rajinikanth", "BP 130/80"):
                if key in text: ys[key] = tm[5] * cm[3] + cm[5]      # page-space y in points, up is larger
        pages = _render_pages(tmp_path, s, name="g.pdf", visitor=visit, edit=edit)
        assert len(pages) == 1 and "BP 130/80" in pages[0]
        return ys["Rajinikanth"] - ys["BP 130/80"]
    # The vitals line is 12px = 9pt tall, so a gap under 9pt means it overlaps the patient line.
    MIN_GAP = 12 * 0.75
    assert gap() >= MIN_GAP
    overlapping = lambda h: h.replace("margin: -4px 0 8px;", "margin: -12px 0 8px;")
    assert "margin: -12px 0 8px;" in overlapping(build_sheet_html(s, META))
    assert gap(overlapping) < MIN_GAP                         # shows the guard catches the overlap


# ---- final fix wave: page-break behaviour (real renders, letterhead) ----
IDENT = "Ravi | OP/IP No: OP-1 | 17 Oct 2026"
HEADINGS = ("CHIEF COMPLAINTS", "DIAGNOSIS", "INVESTIGATIONS", "RX (MEDICATIONS)", "DIETARY & GENERAL ADVICE")
ADVICE = "Take plenty of fluids and rest well, avoid oily and spicy food, and return at once if the fever persists beyond three days or breathing worsens."


def _letterhead_pages(tmp_path, n, advice=True):
    from letterhead_fixtures import DOCTORS_LAYOUT
    layout = validate_layout(DOCTORS_LAYOUT)
    s = {"patientName": "Ravi", "diagnosis": ["Viral fever"],
         "complaints": [f"Complaint line {i} with some more words to fill." for i in range(n)],
         "advice": [ADVICE, ADVICE + " Also keep hydrated."] if advice else []}
    return _render_pages(tmp_path, s, name=f"lh{n}.pdf", edit=None, layout=layout)


def test_a_section_heading_is_never_the_last_line_of_a_page(tmp_path):
    for n in range(24, 31):                                   # the sweep crosses the page break
        pages = _letterhead_pages(tmp_path, n)
        for text in pages[:-1]:
            body = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("Page ")]
            assert not body[-1].upper().startswith(HEADINGS), f"n={n}: heading {body[-1]!r} left at a page foot"


def test_the_disclaimer_stays_with_the_last_section_text(tmp_path):
    seen_two_pages = False
    for n in range(28, 33):
        pages = _letterhead_pages(tmp_path, n, advice=False)
        if len(pages) < 2: continue
        seen_two_pages = True
        rest = pages[-1].replace(IDENT, "").replace(DISCLAIMER, "")
        rest = "\n".join(l for l in rest.splitlines() if l.strip() and not l.strip().startswith("Page "))
        assert rest.strip(), f"n={n}: the disclaimer is alone on the last page"
    assert seen_two_pages


def test_pages_after_the_first_start_with_the_identifier_line(tmp_path):
    pages = _letterhead_pages(tmp_path, 40)
    assert len(pages) >= 2 and IDENT not in pages[0]
    assert all(IDENT in p for p in pages[1:])


def test_each_direction_part_is_a_nowrap_span():
    t = _table(build_sheet_html({"rx": [{"name": "A", "dose": "1-0-0", "timing": "<b>After food</b>", "duration": "5 days"}]}, META))
    assert ('<td><span class="dir">1-0-0</span> · <span class="dir">&lt;b&gt;After food&lt;/b&gt;</span> · '
            '<span class="dir">5 days</span></td>') in t
    assert ".dir { white-space: nowrap; }" in build_sheet_html({}, META)


def test_the_medicine_name_prints_in_capitals_and_the_rest_keeps_its_case():
    html = sections.rx_section([{"form": "Tab.", "name": "Zerodol-p", "strength": "500 mg",
                                 "generic": "Aceclofenac + Paracetamol", "dose": "1-0-1"}])
    assert "Tab. ZERODOL-P 500 mg" in html and "generic: Aceclofenac + Paracetamol" in html
    assert "Zerodol-p" not in html
