# PQ-e Compact Print Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The printed prescription stops wasting space: empty sections vanish, short lists sit on one line, the Rx
table loses its sparse columns, and vitals print once as a strip under the patient line.

**Architecture:** All section rendering moves out of `doctor_dictation/pdf/sheet.py` into a new pure module
`doctor_dictation/pdf/sections.py` (one function per section, each returns `""` when it has nothing to print).
`build_sheet_html` only stitches the pieces. Investigation items reach the shipped print rule of plan h through a
small adapter that falls back to `item["text"]` while plan h's module does not exist yet.

**Tech Stack:** Python 3.12, `html.escape`, pytest. The PDF is this HTML rendered by Chromium (Playwright); no
template engine.

**Spec:** `docs/superpowers/plans/2026-10-19-prescription-quality-brainstorm.md` section 6 ("Print layout: save
space") and "Decisions made"; shared contract `docs/superpowers/plans/2026-10-19-pq-00-index.md` (Vitals, Investigations).

**Owner answers 2026-10-19:** Q14 the 60-character inline limit (`INLINE_ITEM_MAX`) is OK. Q15 **changed**: the labels
are "Directions" (Rx column, as planned), "Pulse" (not "P") and "Wt". The other vitals labels (`BP`, `SpO2`, `Temp`)
are not single letters, so they stay; "P" was the only single-letter label and is now spelled out. Task 4 and its
tests updated.

## Global Constraints

- Files stay under 500 lines (`sheet.py` is 332 today; it shrinks).
- Every printed value is HTML-escaped; `sheet.py` stays pure (no DB, network, clock).
- `structured.vitals = {"bp", "pulse", "weight", "spo2", "temp"}`, strings, `""` when not dictated (plan d). Print it
  once under the patient line; print nothing when every value is empty or the key is absent.
- An investigation is a plain string (legacy) or an item `{"text", "canonical", "status", "source"}`; items print
  through `doctor_dictation.core.investigations.print_text(item) -> str` (plan h).
- The generic line under a brand stays exactly as today (`sheet.py:96-97`: `<div class="gen">generic: …</div>`, not
  printed when it equals the name case-insensitively).
- The review date label stays: `<span class="rev-date">(Sat 24 Oct 2026)</span>` after the review text.
- The disclaimer line "AI draft — doctor must verify before signing. STT + LLM may mishear drug names." always prints
  (`sheet.py:10-13`, `:329`).
- The printout carries no verification marks and is identical for every row status and schedule
  (`tests/test_pdf_sheet.py:40-52`, `tests/test_frontend_schedule_dom.py:121-133`).
- Tests: `.venv/bin/python -m pytest`. No commit without the owner's word; "Commit" steps mean "ask, then commit".

## Decisions taken in this plan

| Question | Decision | Why |
|---|---|---|
| `print_text` before plan h exists | Local adapter `sections.item_text`, falling back to `item["text"]` when the module `doctor_dictation.core.investigations` is absent | The index runs e (order 5) before h (order 8), and h depends on e, so "h lands first" is a cycle. The adapter makes h's print rule apply with no edit to the print code. It catches only the absence of that one module, so a broken plan-h module still fails loudly. |
| Separator | `" · "` (space, U+00B7, space) | Matches the spec sketch ("BP 130/80 · Pulse 82", "Fluids 3 L/day · Rest"); a comma clashes with items that contain commas. |
| What "short list" means | Inline when every item is at most 60 characters (`INLINE_ITEM_MAX = 60`); otherwise the titled bullet list as today | Advice items are often sentences; a run-on paragraph of sentences is harder to read than bullets. |
| Inline labels | `Investigations:`, `Advice:`, `Review:` (bold), as in the spec sketch | The titled section heading costs a full line each. |
| Rx columns | `#`, `Medicine`, `Directions`, and `Instructions` only when some printed row has instructions | Spec idea 5. `Directions` = dose · timing · duration, blanks skipped. |
| Vitals labels | `BP`, `Pulse`, `Wt`, `SpO2`, `Temp`, in that order; the value prints as stored, no unit added | Owner Q15: "Pulse", not "P" (no single-letter labels); "Wt" stays. Units belong to the stored value (plan d). |
| Browser print fallback (`window.print()` of the on-screen sheet) | Not changed | It runs only when the server PDF fails (`frontend/app.js:1173-1180`); it prints the editable screen DOM, not this HTML (`frontend/styles.css:190-205`), and the PDF never loads frontend CSS (`tests/test_pdf_sheet.py:76-83`). Mirroring it needs screen work in `app.js` (over 500 lines). Listed as later. |
| Complaints and diagnosis side by side (spec idea 4) | Out; later | Long history prose in a half-width column grows the page; needs a real-PDF look first. |
| Group investigations by category (spec idea 3) | Out; belongs after plan h | Needs the catalogue's `category`. |

## Review Focus

1. **A document saved before this change** (string investigations, no `vitals` key, review without `review_date`)
   reprints with no error, no `—` placeholder, and no vitals line. Owned by Task 1 and Task 4.
2. **Plan h's module exists but fails to import** (a bug inside it): the print must raise, not silently print raw
   `text`. Owned by Task 2 (`test_item_text_reraises_a_broken_investigations_module`).
3. **Hostile text** in an investigation item, a vitals value or a directions part (`<b>x</b>`) prints escaped.
   Owned by Tasks 2, 3, 4.
4. **A row with only some directions** ("1-0-1", no timing, "5 days") prints `1-0-1 · 5 days`, never a dangling
   or doubled separator. Owned by Task 3.
5. **Malformed vitals** (a string, a list, `None`, numbers such as `82`, unknown keys, whitespace values) print
   either the valid parts or nothing, never crash. Owned by Task 4.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `doctor_dictation/pdf/sections.py` | Create (~130 lines) | One renderer per body section; all return `""` when empty |
| `doctor_dictation/pdf/sheet.py` | Modify `:16-32` (remove list/prose helpers), `:81-108` (remove `_rx_rows`), `:269-270` (review), `:283-308` (CSS), `:311-329` (body) | Page CSS, header, stitching |
| `tests/test_pdf_compact.py` | Create | Tests for this plan |
| `tests/test_pdf.py:25-26`, `tests/test_pdf_sheet.py:46-52,:69`, `tests/test_sections_prose.py:25-33,:128`, `tests/test_followup_routes.py:63` | Modify | Old assertions of the "—" placeholder, the six-column table and the review `<div>` |

Checked and unchanged: `tests/test_datefmt.py:144,:183` (patient line and `rev-date` span keep their markup),
`tests/test_frontend_schedule_dom.py:127-130`, `tests/test_combination_brands.py:77-79`,
`tests/test_pdf_renderer.py:71` (70 rows still span 2+ pages), `tests/test_letterhead_print.py`, the doctor tests.
No static frontend file changes, so no `?v=` pin moves.

---

### Task 1: Skip empty sections

**Files:**
- Create: `doctor_dictation/pdf/sections.py`
- Modify: `doctor_dictation/pdf/sheet.py:16-32`, `:81-108`, `:269-270`, `:311-329`
- Test: `tests/test_pdf_compact.py`; modify `tests/test_pdf.py:25-26`, `tests/test_pdf_sheet.py:52`,
  `tests/test_sections_prose.py:25`, `:30`

**Interfaces:**
- Consumes: nothing new.
- Produces (all in `sections.py`, all return `str`, `""` when nothing prints):
  - `esc(value) -> str` — moved from `sheet._esc` (`sheet.py:16-18`); `sheet.py` imports it as `_esc`.
  - `prose_section(title: str, values) -> str` — `<div class="sec-title">{title}</div><div class="prose"><p>…</p></div>`.
  - `bullet_section(title: str, values) -> str` — `<div class="sec-title">{title}</div><ul><li>…</li></ul>`.
  - `rx_section(rx) -> str` — `<div class="sec-title">Rx (MEDICATIONS)</div><table class="rx">…</table>`.
  - `review_line(review, review_date) -> str`.
  - `title` arguments are trusted markup (`"Chief Complaints &amp; Brief History"`); values are escaped.

- [ ] **Step 0: Preflight.** Re-read `doctor_dictation/pdf/sheet.py` in full; plans a-d may have moved lines.

- [ ] **Step 1: Write the failing tests** in `tests/test_pdf_compact.py`

```python
from doctor_dictation.pdf import DISCLAIMER, build_sheet_html
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
    assert "Chief Complaints" not in html and html.index("Viral fever") < html.index("Crocin") < html.index("1 week")

def test_a_document_saved_before_this_change_reprints_without_placeholders():   # Review Focus 1
    old = {"patientName": "Old", "diagnosis": ["Gastritis"], "complaints": ["epigastric pain", "nausea"],
           "investigations": ["CBC"], "review": "after 1 week", "rx": []}
    html = build_sheet_html(old, {"date": "2026-10-01"})
    assert "—</" not in html and "Gastritis" in html and "CBC" in html and "after 1 week" in html
```

- [ ] **Step 2: Run to verify they fail.**
Run: `.venv/bin/python -m pytest -q tests/test_pdf_compact.py`
Expected: 4 FAIL (placeholders and empty headings still print).

- [ ] **Step 3: Create `sections.py` with the five functions above** and wire `build_sheet_html`'s body to them.
Behaviour equals today's markup for a filled section (`sheet.py:21-32`, `:81-108`, `:269-270`, `:314-328`); the only
change is `""` instead of the `—` placeholder and its heading. A list value that is not a `list` counts as empty;
an rx row prints only when it is a dict with a name or strength (`sheet.py:83-86`); a list item that is `None` or blank after `strip()` is skipped (today `None` prints as "None", `sheet.py:24`). `review_line` returns
`<div class="sec-title">Review / Follow-up</div><div>{review}{rev-date span}</div>`, or `""` when the review is blank.
Delete `_list_items`, `_prose_items`, `_rx_rows` from `sheet.py` (no other callers: checked with grep).

- [ ] **Step 4: Update the old placeholder assertions.**
  - `tests/test_pdf.py:25-26`: rename to `test_sheet_html_empty_sections_print_nothing`; assert
    `'colspan="6"' not in html and "<li>—</li>" not in html and DISCLAIMER in html` (the bare `"—"` check passes on
    the disclaimer's dash alone and proves nothing).
  - `tests/test_pdf_sheet.py:52`: `assert '<table class="rx">' not in build_sheet_html({"rx": []}, META)`.
  - `tests/test_sections_prose.py:25`: keep `Chief < Diagnosis`; replace the `Investigations Advised` index with
    `"Investigations" not in html` (that test dictates none).
  - `tests/test_sections_prose.py:30`: `'<p>—</p>' not in empty and "Review" not in empty and 'class="rev-date"' not in empty`.

- [ ] **Step 5: Run the print tests.**
Run: `.venv/bin/python -m pytest -q tests/test_pdf_compact.py tests/test_pdf.py tests/test_pdf_sheet.py tests/test_sections_prose.py tests/test_followup_routes.py tests/test_datefmt.py`
Expected: all PASS.

- [ ] **Step 6: Commit** (ask first): `git add doctor_dictation/pdf/sections.py doctor_dictation/pdf/sheet.py tests/test_pdf_compact.py tests/test_pdf.py tests/test_pdf_sheet.py tests/test_sections_prose.py` — message `Print: skip empty sections instead of printing a dash`.

---

### Task 2: Inline short lists, the investigation item adapter, inline review line

**Files:**
- Modify: `doctor_dictation/pdf/sections.py`, `doctor_dictation/pdf/sheet.py` (body + CSS)
- Test: `tests/test_pdf_compact.py`; modify `tests/test_sections_prose.py:28`, `:33`, `:128`,
  `tests/test_followup_routes.py:63`

**Interfaces:**
- Consumes: Task 1's `esc`, `bullet_section`, `review_line`.
- Produces:
  - `SEP = " · "`, `INLINE_ITEM_MAX = 60` (module constants in `sections.py`).
  - `item_text(value) -> str` — str → stripped value; dict → `print_text(value)` when plan h's module exists, else
    `str(value.get("text") or "").strip()`; anything else → `str(value).strip()` (`None` → `""`). Unescaped.
  - `list_section(label: str, title: str, values) -> str` — `""` when no item has text; inline
    `<div class="inl"><span class="inl-label">{label}:</span> a · b</div>` when every item is ≤ `INLINE_ITEM_MAX`
    characters; else `bullet_section(title, …)` over the item texts.
  - `review_line` now returns `<div class="inl"><span class="inl-label">Review:</span> {review}{ rev-date span}</div>`.
- Body calls: `list_section("Investigations", "Investigations Advised", s.get("investigations"))` and
  `list_section("Advice", "Dietary &amp; General Advice", s.get("advice"))`, at today's positions.
- Contract note for plan h: `determinism.validate_structured` stringifies list items (`determinism.py:366`,
  `str(x)`), which would turn an item dict into `"{'text': …}"`. Plan h must keep item dicts there; this plan prints
  whatever reaches the sheet.

- [ ] **Step 1: Write the failing tests**

```python
import builtins, sys, types
import pytest
from doctor_dictation.pdf import sections
MOD = "doctor_dictation.core.investigations"

def test_short_lists_print_on_one_line_with_a_label():
    html = build_sheet_html({"investigations": ["CBC", "RFT"], "advice": ["Fluids 3 L/day", "Rest"]}, META)
    assert '<span class="inl-label">Investigations:</span> CBC · RFT</div>' in html
    assert '<span class="inl-label">Advice:</span> Fluids 3 L/day · Rest</div>' in html and "<li>" not in html

def test_a_list_with_one_long_item_keeps_the_titled_bullets():
    long = "Avoid oily and spicy food, take small frequent meals, no alcohol"   # 64 characters
    html = build_sheet_html({"advice": ["Rest", long]}, META)
    assert "Dietary &amp; General Advice" in html and f"<li>{long}</li>" in html and "<li>Rest</li>" in html

def test_item_text_without_plan_h_prints_the_dictated_text(monkeypatch):
    monkeypatch.setitem(sys.modules, MOD, None)                       # module absent, before and after plan h lands
    assert sections.item_text({"text": " RFT ", "canonical": "Renal Function Test"}) == "RFT"
    assert sections.item_text({"canonical": "x"}) == "" and sections.item_text(" CBC ") == "CBC" and sections.item_text(None) == ""

def test_item_text_uses_plan_h_print_text_for_items_only(monkeypatch):
    fake = types.ModuleType(MOD); fake.print_text = lambda item: item["text"] + " (Renal Function Test)"
    monkeypatch.setitem(sys.modules, MOD, fake)
    assert sections.item_text({"text": "RFT"}) == "RFT (Renal Function Test)" and sections.item_text("RFT") == "RFT"
    html = build_sheet_html({"investigations": ["CBC", {"text": "RFT"}, {"text": "<b>x</b>"}]}, META)
    assert "CBC · RFT (Renal Function Test) · &lt;b&gt;x&lt;/b&gt; (Renal Function Test)</div>" in html   # Review Focus 3

def test_item_text_reraises_a_broken_investigations_module(monkeypatch):   # Review Focus 2
    def broken(name, *a, **k):
        if name == MOD: raise ModuleNotFoundError("No module named 'rapidfuzz'", name="rapidfuzz")
        return real(name, *a, **k)
    real = builtins.__import__
    monkeypatch.delitem(sys.modules, MOD, raising=False); monkeypatch.setattr(builtins, "__import__", broken)
    with pytest.raises(ModuleNotFoundError):
        sections.item_text({"text": "RFT"})

def test_review_prints_inline_with_its_date_label():
    html = build_sheet_html({"review": "1 week", "review_date": "2026-10-24"}, META)
    assert '<span class="inl-label">Review:</span> 1 week <span class="rev-date">(Sat 24 Oct 2026)</span></div>' in html
```

- [ ] **Step 2: Run to verify they fail.**
Run: `.venv/bin/python -m pytest -q tests/test_pdf_compact.py`
Expected: the six new tests FAIL (`sections` has no `item_text`; lists still print bullets).

- [ ] **Step 3: Implement `item_text`, `list_section`, the inline `review_line`, and CSS** in `sheet.py`'s
`<style>`: `.inl { font-size: 12px; margin: 8px 0 0; }` and `.inl-label { font-weight: bold; }`. The import
adapter is the one non-obvious part; resolve it on each call (a cached `None` would hide plan h after a reload):

```python
def _print_text():
    try:
        from doctor_dictation.core.investigations import print_text
    except ModuleNotFoundError as exc:
        if exc.name != "doctor_dictation.core.investigations":
            raise                                   # plan h's module exists but is broken: fail loudly
        return None
    return print_text
```

- [ ] **Step 4: Update the old review and bullet assertions.**
  - `tests/test_sections_prose.py:28`: expect the Review inline markup from the new test above.
  - `tests/test_sections_prose.py:33`: `'<span class="inl-label">Investigations:</span> CBC</div>' in build_sheet_html({"investigations": ["CBC"]}, META)`.
  - `tests/test_sections_prose.py:128` and `tests/test_followup_routes.py:63`: `"<div>1 week</div>"` /
    `"<div>after 1 week</div>"` become `'<span class="inl-label">Review:</span> 1 week</div>'` /
    `'<span class="inl-label">Review:</span> after 1 week</div>'`; the `rev-date` absence checks stay.

- [ ] **Step 5: Run.**
Run: `.venv/bin/python -m pytest -q tests/test_pdf_compact.py tests/test_sections_prose.py tests/test_followup_routes.py tests/test_datefmt.py tests/test_pdf.py`
Expected: all PASS.

- [ ] **Step 6: Commit** (ask first) — message `Print: short investigation and advice lists on one line; review inline`.

---

### Task 3: Tighter Rx table

**Files:**
- Modify: `doctor_dictation/pdf/sections.py` (`rx_section`)
- Test: `tests/test_pdf_compact.py`; modify `tests/test_pdf_sheet.py:46`, `:49`, `:69`

**Interfaces:**
- Consumes: Task 1's `rx_section(rx) -> str`, Task 2's `SEP`.
- Produces: `rx_section` prints header `<th>#</th><th>Medicine</th><th>Directions</th>` plus
  `<th>Instructions</th>` only when at least one printed row has non-blank `instructions`. Directions cell =
  `SEP.join` of the non-blank, stripped, escaped `dose`, `timing`, `duration`. The medicine cell (form name strength
  + generic line, `sheet.py:91-97`) is unchanged.

- [ ] **Step 1: Write the failing tests**

```python
def _table(html): return html[html.index('<table class="rx">'):html.index("</table>")]

def test_directions_share_one_column_and_instructions_drop_when_all_empty():
    rows = [{"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "1-0-1", "timing": "After food", "duration": "5 days"},
            {"form": "Tab.", "name": "Zerodol-P", "dose": "1-0-1", "duration": "3 days", "instructions": "  "}]
    t = _table(build_sheet_html({"rx": rows}, META))
    assert t.count("<th>") == 3 and "<th>Directions</th>" in t and "Instructions" not in t
    assert "<td>1-0-1 · After food · 5 days</td>" in t and "<td>1-0-1 · 3 days</td>" in t   # Review Focus 4
    assert "·  ·" not in t and "<td> · " not in t

def test_one_row_with_instructions_brings_the_column_back_for_every_row():
    rows = [{"name": "A", "dose": "1-0-0"}, {"name": "B", "instructions": "<b>with milk</b>"}]
    t = _table(build_sheet_html({"rx": rows}, META))
    assert t.count("<th>") == 4 and [tr.count("<td>") for tr in t.split("<tr>")[2:]] == [4, 4]
    assert "<td>&lt;b&gt;with milk&lt;/b&gt;</td>" in t and "<td></td>" in t                # Review Focus 3

def test_the_generic_line_stays_under_the_brand():
    t = _table(build_sheet_html({"rx": [{"form": "Tab.", "name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}]}, META))
    assert '<td>Tab. Zerodol-P<div class="gen">generic: Aceclofenac + Paracetamol</div></td>' in t
```

- [ ] **Step 2: Run to verify they fail.**
Run: `.venv/bin/python -m pytest -q tests/test_pdf_compact.py -k "directions or instructions or generic_line"`
Expected: the first two FAIL (six columns today); the generic test PASSES already (it guards the move).

- [ ] **Step 3: Rewrite `rx_section`'s header and row cells** per the Interfaces block.

- [ ] **Step 4: Update `tests/test_pdf_sheet.py`.**
  - `:46`: `table.count("<th>") == 4` (those rows carry `"with milk"`); `:49`: `cells == [4] * len(STATUSES)`.
  - `:69`: `table.count("<th>") == 3` (no instructions there). `:50-51` and `:65-73` stay (the row-identity and
    medicine-cell checks still hold).

- [ ] **Step 5: Run.**
Run: `.venv/bin/python -m pytest -q tests/test_pdf_compact.py tests/test_pdf_sheet.py tests/test_frontend_schedule_dom.py tests/test_combination_brands.py tests/test_confirmed_marker.py tests/test_confirmed_strength_marker.py`
Expected: all PASS.

- [ ] **Step 6: Commit** (ask first) — message `Print: one Directions column; Instructions only when used`.

---

### Task 4: Vitals strip under the patient line

**Files:**
- Modify: `doctor_dictation/pdf/sections.py`, `doctor_dictation/pdf/sheet.py:313` (insert after the `.sub` line) and CSS
- Test: `tests/test_pdf_compact.py`

**Interfaces:**
- Consumes: `structured["vitals"]` from plan d (may be absent on old documents); Task 2's `SEP`.
- Produces: `VITALS = (("bp", "BP"), ("pulse", "Pulse"), ("weight", "Wt"), ("spo2", "SpO2"), ("temp", "Temp"))` and
  `vitals_strip(vitals) -> str` — `<div class="vitals">BP 130/80 · Pulse 82 · Wt 64 kg</div>` (owner Q15); each part is
  `f"{label} {value}"` with the value `str(...).strip()` and escaped; blank values skipped; unknown keys ignored;
  `""` when `vitals` is not a dict or every value is blank. CSS: `.vitals { text-align: center; font-size: 12px; margin: -12px 0 12px; }`
  (sits tight under `.sub`).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to verify they fail.**
Run: `.venv/bin/python -m pytest -q tests/test_pdf_compact.py -k vitals`
Expected: the first and third FAIL (no strip yet); the second PASSES (guards the empty case).

- [ ] **Step 3: Implement `vitals_strip` and insert `{vitals_strip(s.get("vitals"))}` right after the `.sub`
line in `build_sheet_html`, plus the CSS rule.**

- [ ] **Step 4: Run.**
Run: `.venv/bin/python -m pytest -q tests/test_pdf_compact.py tests/test_datefmt.py tests/test_pdf.py`
Expected: all PASS.

- [ ] **Step 5: Commit** (ask first) — message `Print: vitals strip under the patient line`.

---

### Task 5: Tighter spacing and a real-render check

**Files:**
- Modify: `doctor_dictation/pdf/sheet.py` CSS (`:288-298`)
- Test: `tests/test_pdf_compact.py`

**Interfaces:**
- Consumes: everything above. Produces nothing new.
- CSS values: `.sub { margin-bottom: 8px; }` (was 16px, `:289`), `.sec-title { margin: 10px 0 4px; }` (was
  `14px 0 6px`, `:291`), `table.rx th, table.rx td { padding: 3px 6px; }` (was `4px 6px`, `:296`),
  `.disclaimer { margin-top: 12px; }` (was 18px, `:298`). Font sizes do not change.

- [ ] **Step 1: Write the tests** (the render test skips without Chromium, like `tests/test_pdf_renderer.py:69-77`)

```python
def test_spacing_rules_are_the_compact_values():
    html = build_sheet_html({}, META)
    assert ".sub { text-align: center; font-size: 12px; margin-bottom: 8px; }" in html
    assert "margin: 10px 0 4px;" in html and "padding: 3px 6px;" in html and ".disclaimer { margin-top: 12px;" in html

def test_owner_like_sheet_renders_one_page_without_dashes(tmp_path):
    PdfReader = pytest.importorskip("pypdf").PdfReader; pytest.importorskip("playwright.sync_api")
    from doctor_dictation.pdf import PdfUnavailable, render_pdf
    s = {"patientName": "Rajinikanth", "ageSex": "78 / M", "complaints": ["C/o fever with chills, 3 days."],
         "diagnosis": ["Viral fever"], "investigations": ["X-ray of the head and hip", "CT scan", "MRI"], "rx": [], "advice": [], "review": ""}
    try: pages = [p.extract_text() for p in PdfReader(str(render_pdf(build_sheet_html(s, META), tmp_path / "a.pdf"))).pages]
    except (PdfUnavailable, RuntimeError): pytest.skip("Chromium is not installed")
    assert len(pages) == 1 and "• —" not in pages[0] and "MEDICATIONS" not in pages[0] and "AI draft" in pages[0]
```

- [ ] **Step 2: Run to verify the first fails.**
Run: `.venv/bin/python -m pytest -q tests/test_pdf_compact.py -k "spacing or owner_like"`
Expected: spacing FAIL; render PASS or SKIP.

- [ ] **Step 3: Change the four CSS values.**

- [ ] **Step 4: Run the whole suite.**
Run: `.venv/bin/python -m pytest -q`
Expected: all PASS (the render tests may SKIP).

- [ ] **Step 5: Owner check.** Ask the owner to reprint one real prescription (gsr-clinic) and compare it with the
earlier PDF: no `—` lines, one-line investigations, vitals strip when dictated.

- [ ] **Step 6: Commit** (ask first) — message `Print: tighter spacing; one-page render check`.

---

## Later (deliberately not in this plan)

- Group investigations by category ("Blood: CBC, RFT · Imaging: USG KUB") — after plan h's catalogue.
- Complaints and diagnosis side by side (spec idea 4).
- The browser-print fallback mirroring the compact layout (screen DOM in `frontend/app.js`, `frontend/styles.css:190`).
- Configurable labels or the 60-character threshold per clinic.

## Self-review notes

- Spec 6 ideas 1, 2, 5, 6 → Tasks 1, 2, 3, 4; ideas 3 and 4 → Later. Evidence lines ("—" row, "• —", "—" review,
  bullets per line, blank space) → Tasks 1, 1, 1, 2, 5.
- Names used across tasks: `esc`, `prose_section`, `bullet_section`, `list_section`, `rx_section`, `review_line`,
  `item_text`, `vitals_strip`, `SEP`, `INLINE_ITEM_MAX`, `VITALS` — all defined in `doctor_dictation/pdf/sections.py`.
