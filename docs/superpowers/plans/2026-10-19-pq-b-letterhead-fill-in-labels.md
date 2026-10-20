# PQ-b: Letterhead fill-in labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop a letterhead from printing the paper pad's blank fill-in labels ("Name: M F Age: Date:", "Visit After",
"Submit") and from printing the same profile field (phone, address) at the top and the bottom without the doctor choosing.

**Architecture:** One pure module, `doctor_dictation/templates/lines.py`, decides which literal lines are fill-in labels
and which profile fields are duplicated. The vision builder uses it to drop labels from a new draft, and
`service.view` uses it to report them on every template, so an already-saved letterhead (gsr-clinic's) shows the same
lines pre-ticked "remove". The review screen gains a remove tick per line and a "where should it print" question per
duplicated field. A new route lets the doctor fix the lines of an **active** letterhead without uploading again.

**Tech Stack:** Python 3.12, FastAPI, pytest; vanilla JS (no framework), node for JS checks.

**Spec:** `docs/superpowers/plans/2026-10-19-prescription-quality-brainstorm.md` ("Decisions made", decision 5).
Shared contract: `docs/superpowers/plans/2026-10-19-pq-00-index.md`.

**Owner answers 2026-10-19:** Q4 the label word list is approved. Q5 **changed**: the duplicated phone/address question shows
"In both places" pre-selected (today's behaviour) and never blocks Accept or Save; the doctor may change it (Tasks 4-5
updated). Q6 a line the builder left out cannot be restored (re-upload): OK. Q7 fixing an active letterhead also
changes re-prints of old documents: OK.

## Global Constraints

- Build (1), (3), (4) of decision 5. Do **not** build fill-in slots (2) (backlog card al).
- "No separate operator fix for gsr-clinic: the delete-a-line screen (3) fixes it."
- The doctor's "Reg. No" is a profile field (`reg_no`): never treat it as a fill-in label.
- Files stay under 500 lines (`frontend/letterhead.js` is 367 now; new list logic goes into a new `frontend/lhlines.js`).
- Tests: `.venv/bin/python -m pytest`; the autouse `DB_PATH` fixture keeps the dev DB safe. Do not run the app.
- Bump `?v=` pins on changed static files (tests assert them). No commit without the owner's word.
- Baseline: the seven test files named in Task 0 pass (107 passed on `main` 9bf466e).

## Decisions this plan makes (owner answered 2026-10-19)

**Fill-in vocabulary (shared by builder and review).** A literal line is a fill-in label when, after normalising, every
word is a *label word* or a *filler word*, at least one is a label word, no word except `spo2` contains a digit, and the
line is at most 80 characters. A line of only punctuation/underscores ("________", ". . . .") also counts (a blank
writing line).

| Group | Label words (casefolded) | Kept out on purpose |
|---|---|---|
| Patient | `name`, `age`, `sex`, `gender`, `male`, `female`, `yrs`, `years`, `address`, `mobile`, `phone`, `contact` | — |
| Ids | `op`, `ip`, `uhid`, `mrd`, `mr` | `reg`, `regd`, `registration` (the doctor's Reg. No) |
| Date / visit | `date`, `visit`, `next`, `review`, `follow`, `followup`, `submit` | — |
| Vitals | `weight`, `wt`, `height`, `ht`, `bp`, `pulse`, `temp`, `temperature`, `spo2`, `kg` | — |
| Filler (never alone) | `m`, `f`, `no`, `id`, `of`, `the`, `patient`, `patients`, `on`, `after`, `up`, `and`, `or` | — |
| Not labels | — | `signature`, `sign` (the app prints no signature line; the doctor signs the printout by hand), `rx`, section headings (`diagnosis`, `advice`), timings |

Normalising: casefold; drop a dot between two letters (`O.P.` → `op`); drop apostrophes (`patient's` → `patients`);
every other non-alphanumeric character becomes a space. An empty string is not a label. Examples: "Name: M F Age: Date:" → label; "Visit After" → label;
"Submit" → label; "O.P. No." → label; "Reg. No." → **not** a label; "Ph: 040 1234 5678" → not (digits);
"Open Mon to Sat" → not; "M / F" → not (filler only).

**Duplicated profile field.** A field is duplicated when the header and the footer each hold it: a field block
(`{"type":"text","field":F}`, any of the six fields), or, for `phone` and `address` only, a literal line containing the
profile value (phone: any digit run of 6+ digits from the profile value appears in the line's digits; address: the
whitespace-collapsed casefolded profile address, 10+ characters, is a substring of the line or the line of it).
The screen asks "Top only / Bottom only / Both" with **Both pre-selected** (today's behaviour, owner Q5); it never
blocks Accept or Save. A field with no `keep` entry prints in both places.

**Existing (active) letterheads.** `service.edit` stays draft-only (existing 409 test kept). A new
`service.tidy` + `PUT /api/v1/templates/{id}/lines` changes only lines (edit text, remove, keep-choice) on a draft or an
active letterhead. Re-prints render with the current active letterhead (`doctor_dictation/api/persistence.py:138-168`),
so a tidy fixes old documents' re-prints too; it is audited (`template_tidy`).

**New drafts.** The builder removes fill-in lines before the draft is stored and lists them in a review-only key
`layout.skipped_labels` (like `doctor_hints`, `doctor_dictation/templates/builder.py:67-71`; `validate_layout` ignores
unknown keys, `doctor_dictation/pdf/layout.py:67-76`). The screen shows them as a note; there is no "restore".

## Review Focus

1. **A real tagline caught as a label** (e.g. "Male & Female" on a clinic for both — every word is vocabulary):
   it is dropped from a new draft. Expect it listed in the "left out" note so the doctor notices. Test:
   `test_build_lists_dropped_lines_in_skipped_labels` (Task 2).
2. **The doctor's "Reg. No." printed as a bare literal** ("Reg. No.", no number): must stay. Test:
   `test_reg_no_is_never_a_fill_in_label` (Task 1).
3. **Indexes shift after a removal**: two removals in one section plus a text edit on a third line must remove the right
   blocks. Test: `test_removals_use_the_stored_indexes_and_apply_after_text_edits` (Task 3).
4. **Every line removed**: a header with no text left (logo only, or empty) must still validate and print. Test:
   `test_removing_every_literal_line_leaves_a_valid_layout` (Task 3).
5. **A stale keep-choice** (the duplicate was already resolved in another tab): ignored, not a 500. Test:
   `test_keep_for_a_field_no_longer_duplicated_is_ignored` (Task 3).

Not covered (stated, not built): labels in Telugu/Hindi script (the prompt rule covers any language; the code filter is
English only); section headings printed on the pad body ("Diagnosis:") — outside the header/footer, not literal lines.

---

### Task 0: Preflight

- [ ] **Step 1: Re-read the files this plan edits** (earlier plans in the order may have changed them):
  `doctor_dictation/templates/{builder,service}.py`, `doctor_dictation/api/templates.py`, `frontend/letterhead.js`,
  `frontend/letterhead.css`, `frontend/index.html:205-266`. Line numbers below are from `main` 9bf466e.
- [ ] **Step 2: Run the baseline**
Run: `.venv/bin/python -m pytest -q tests/test_template_service.py tests/test_template_routes.py tests/test_letterhead_review.py tests/test_template_builder.py tests/test_frontend_letterhead.py tests/test_frontend_doctorgrid.py tests/test_isolation_routes.py`
Expected: all pass (107 on 9bf466e).

---

### Task 1: Shared line rules (`templates/lines.py`)

**Files:**
- Create: `doctor_dictation/templates/lines.py`
- Test: `tests/test_letterhead_lines.py` (new)

**Interfaces:**
- Produces:
  - `is_fill_in_label(text: str) -> bool`
  - `fill_in_lines(layout: dict) -> list[dict]` — `[{"section": "header"|"footer", "index": int, "text": str}]`, same
    shape and walk as `doctors.literal_warnings` (`doctor_dictation/templates/doctors.py:14-23`); malformed input → `[]`.
  - `drop_fill_in_lines(layout: dict) -> list[str]` — removes those blocks from `layout["header"]`/`["footer"]` in place,
    returns their texts in reading order (header first).
  - `duplicate_fields(layout: dict) -> list[dict]` — `[{"field": F, "header": [int], "footer": [int]}]`, one entry per
    field that appears in both sections, fields in `PROFILE_FIELDS` order, indexes ascending; uses `layout["profile"]`
    for the phone/address literal match.

- [ ] **Step 1: Write the failing tests**
```python
LABELS = ["Name: M F Age: Date:", "Visit After", "Submit", "O.P. No.", "Patient's Name", "Age/Sex",
          "BP:      Wt:      SpO2:", "Next visit on", "UHID", "Address:", "Mobile No.", "__________", ". . . ."]
NOT_LABELS = ["Reg. No.", "Reg. No. TS-12345", "Ph: 040 1234 5678", "Open Mon to Sat", "M / F", "Signature",
              "Timings 9 am - 5 pm", "Rx", "Date: 12/10/2026", "x" * 81, ""]
def test_fill_in_labels_are_recognised():
    assert [t for t in LABELS if not lines.is_fill_in_label(t)] == []
def test_lines_that_are_not_labels_are_kept():
    assert [t for t in NOT_LABELS if lines.is_fill_in_label(t)] == []
def test_reg_no_is_never_a_fill_in_label():
    assert not any(lines.is_fill_in_label(t) for t in ("Reg. No.", "Regd. No:", "Registration No."))
def test_fill_in_lines_reports_section_index_and_text_and_skips_field_blocks():
    lay = {"header": [{"type": "logo", "crop": [0, 0, .1, .1]}, {"type": "text", "field": "phone"},
                      {"type": "text", "text": "Name: M F Age: Date:"}],
           "footer": [{"type": "text", "text": "Visit After"}, {"type": "text", "text": "Open daily"}]}
    assert lines.fill_in_lines(lay) == [{"section": "header", "index": 2, "text": "Name: M F Age: Date:"},
                                        {"section": "footer", "index": 0, "text": "Visit After"}]
    assert lines.fill_in_lines(None) == [] and lines.fill_in_lines({"header": "x"}) == []
def test_drop_fill_in_lines_removes_in_place_and_returns_texts():
    lay = ...  # the layout of the previous test
    assert lines.drop_fill_in_lines(lay) == ["Name: M F Age: Date:", "Visit After"]
    assert len(lay["header"]) == 2 and lay["footer"] == [{"type": "text", "text": "Open daily"}]
def test_duplicate_phone_as_field_blocks_and_as_a_footer_literal():
    lay = {"profile": {**PROFILE, "phone": "040 1234 5678; 98480 22338"},
           "header": [{"type": "text", "field": "phone"}],
           "footer": [{"type": "text", "text": "Ph: 98480-22338"}, {"type": "text", "field": "phone"}]}
    assert lines.duplicate_fields(lay) == [{"field": "phone", "header": [0], "footer": [0, 1]}]
def test_duplicate_address_literal_and_no_report_when_only_one_side_has_it():
    # header field "address"; footer literal "12 MG Road, Hyderabad - 500001" → [{"field": "address", "header": [0], "footer": [0]}]
    # header only → []; a 9-character profile address never matches a literal
```

(`PROFILE` from `tests/template_fixtures.py:12-13`.)

- [ ] **Step 2: Run to verify they fail**
Run: `.venv/bin/python -m pytest -q tests/test_letterhead_lines.py`
Expected: FAIL (ImportError: cannot import name `lines`).

- [ ] **Step 3: Implement `doctor_dictation/templates/lines.py`**
Vocabulary and normalising exactly as in "Decisions this plan makes". Module constants: `LABEL_WORDS`, `FILLER_WORDS`
(frozensets), `MAX_LABEL_CHARS = 80`. Import `PROFILE_FIELDS` from `doctor_dictation.templates.builder` would be a
cycle once builder imports this module: import `PROFILE_KEYS` from `doctor_dictation.pdf.layout` (same six names,
`doctor_dictation/pdf/layout.py:5`). Stdlib only.

- [ ] **Step 4: Run to verify they pass**
Run: `.venv/bin/python -m pytest -q tests/test_letterhead_lines.py`
Expected: PASS.

- [ ] **Commit** (ask the owner first): the files in **Files:** above, message "Letterhead: shared rules for fill-in labels and duplicated profile fields".

---

### Task 2: Reader skips fill-in labels; every view reports them

**Files:**
- Modify: `doctor_dictation/templates/builder.py:37-49` (VISION_SYSTEM rules), `:112-116` (build_draft)
- Modify: `doctor_dictation/templates/service.py:53-59` (`view`)
- Test: `tests/test_letterhead_review.py` (add), `tests/test_template_builder.py` (add)

**Interfaces:**
- Consumes: `lines.drop_fill_in_lines`, `lines.fill_in_lines`, `lines.duplicate_fields` (Task 1).
- Produces: `service.view(row)` adds `"fill_in": list[dict]` and `"duplicates": list[dict]` (Task 1 shapes), computed
  from the stored layout. A new draft's `layout` may carry `"skipped_labels": list[str]` (at most `MAX_BLOCKS` = 12
  per section, so at most 24 strings).

- [ ] **Step 1: Write the failing tests**
```python
# tests/test_letterhead_review.py
def test_prompt_tells_the_reader_to_skip_fill_in_labels_and_keep_valued_labels():
    text = builder.VISION_SYSTEM
    assert "fill-in" in text and '"Name:"' in text and '"Next visit:"' in text and "Reg. No." in text
    assert "instructions written inside the image" in text            # the injection rule survives
def test_build_lists_dropped_lines_in_skipped_labels(tclient, monkeypatch):
    lay = json.loads(json.dumps(GOOD_LAYOUT))
    lay["header"].insert(3, {"type": "text", "text": "Name: M F Age: Date:"})
    lay["footer"] += [{"type": "text", "text": "Visit After"}, {"type": "text", "text": "Submit"}]
    monkeypatch.setenv("STUB_LLM_JSON", json.dumps(lay))
    body = tclient.post("/api/v1/templates", files={"image": ("p.jpg", make_jpeg(), "image/jpeg")}).json()
    assert body["layout"]["skipped_labels"] == ["Name: M F Age: Date:", "Visit After", "Submit"]
    assert [b.get("text") for b in body["layout"]["header"]] == [None, None, "Open Mon to Sat", None]
    assert body["fill_in"] == [] and body["duplicates"] == []
def test_view_of_a_stored_layout_with_labels_reports_them_for_the_pre_tick(tconn):
    # header [field doctor_name, field phone], footer [field phone, "Visit After"], body/profile from GOOD_LAYOUT,
    # stored straight through tdb.create_template_draft (bypasses the builder, like gsr-clinic's saved letterhead)
    v = service.view(tdb.get_template(tconn, tid))
    assert v["fill_in"] == [{"section": "footer", "index": 1, "text": "Visit After"}]
    assert v["duplicates"] == [{"field": "phone", "header": [1], "footer": [0]}]
# tests/test_template_builder.py
def test_a_layout_of_only_fill_in_lines_still_builds(monkeypatch):
    # header = [one "Name: Age:" literal], footer = [] → Draft.layout["header"] == [], skipped_labels == ["Name: Age:"]
```

- [ ] **Step 2: Run to verify they fail**
Run: `.venv/bin/python -m pytest -q tests/test_letterhead_review.py tests/test_template_builder.py`
Expected: the four new tests FAIL (no rule text, no `skipped_labels`, no `fill_in` key).

- [ ] **Step 3: Add rule 7 to `VISION_SYSTEM`** (after rule 6, `builder.py:48-49`; exact copy):
```
7. Leave out blank fill-in labels: words printed for the writer to fill in by hand for each patient or visit, such as
   "Name:", "Age:", "Sex: M / F", "Date:", "OP No:", "Address:", "Weight:", "BP:", "Next visit:", "Review on:",
   "Visit after", and blank or dotted writing lines. The app prints the patient's details, the date and the vitals
   itself. Keep printed text that carries a value, such as "Reg. No. 12345" or "Ph: 040 1234 5678".
```

- [ ] **Step 4: Drop labels in `build_draft`** — after `validate_layout(layout)` succeeds (`builder.py:113-116`), call
  `skipped = drop_fill_in_lines(layout)`; set `layout["skipped_labels"] = skipped` only when non-empty. Then
  re-validate is not needed (removing blocks cannot break the vocabulary).
- [ ] **Step 5: Extend `service.view`** with `"fill_in": lines.fill_in_lines(lay)` and
  `"duplicates": lines.duplicate_fields(lay)`.
- [ ] **Step 6: Run to verify they pass**
Run: `.venv/bin/python -m pytest -q tests/test_letterhead_review.py tests/test_template_builder.py tests/test_template_service.py tests/test_template_routes.py`
Expected: PASS (existing `body` shape checks in `test_template_routes.py:26-31` only read keys, so the new keys do not
break them).

- [ ] **Commit** (ask the owner first): the files in **Files:** above, message "Letterhead reader skips blank fill-in labels; the review view reports labels and duplicated fields".

---

### Task 3: Remove a line, choose where a duplicated field prints, fix an active letterhead

**Files:**
- Modify: `doctor_dictation/templates/lines.py` (add `apply_line_changes`)
- Modify: `doctor_dictation/templates/service.py:120-147` (`edit`), add `tidy` after it
- Modify: `doctor_dictation/api/templates.py:33-36` (`EditBody`), `:166-174` (pass `keep`), add the route
- Test: `tests/test_template_service.py`, `tests/test_template_routes.py`, `tests/test_isolation_routes.py:18-22`

**Interfaces:**
- Consumes: `lines.duplicate_fields` (Task 1).
- Produces:
  - `lines.apply_line_changes(layout: dict, line_edits: list, keep: list) -> None` — mutates `layout`; raises
    `TemplateError(400, ...)`. A line edit is `{"section", "index", "text": str}` or `{"section", "index", "remove": true}`
    (`text` optional with `remove`). `keep` is a list of `{"field": F, "where": "header"|"footer"|"both"}`.
  - `service.edit(conn, template_id, profile, lines, keep=None, actor=None, user=None) -> dict` (draft only, as today).
  - `service.tidy(conn, template_id, lines, keep, actor=None, user=None) -> dict` — draft or active; 404 when missing
    or not `visible`; 409 when archived; audit `template_tidy`, detail `{"clinic", "removed": int, "edited": int,
    "keep": [{"field", "where"}]}` (no line text in the audit).
  - Route `PUT /api/v1/templates/{template_id}/lines`, body `{"lines": [...], "keep": [...]}` (both `Any`, validated by
    the service so bad shapes answer 400), returns `service.view`.
  - `PUT /api/v1/templates/{id}` accepts an optional `keep` too.

Rules for `apply_line_changes` (an order the signature does not fix):
1. Validate every entry first (existing messages at `service.py:131-140`; `remove` must be `True` when present; `text`
   required unless `remove` is `True`; removing a non-literal block → 400 "only literal text lines can be removed").
   Indexes refer to the stored layout.
2. `keep` entries: `field` in the six profile keys, `where` in the three values, else 400. Compute
   `duplicate_fields(layout)` once, on the stored layout. `header` → remove that entry's footer indexes; `footer` →
   remove its header indexes; `both` → nothing. A field not in the duplicates is ignored.
3. Apply text edits (strip) to lines not being removed; then delete the union of removals per section in descending
   index order.
4. `edit`/`tidy` then run `validate_layout` as today (`service.py:142-145`), so a cleared text without `remove` stays a
   400 (`pdf/layout.py:49-52` unchanged).

- [ ] **Step 1: Write the failing tests**
```python
# tests/test_template_service.py — helper fresh_draft(tconn) -> int stores this layout with header [logo, field doctor_name, "Open Mon to Sat", rule, field phone,
# "Name: Age:"] and footer [field address, "Visit After", field phone], created with tdb.create_template_draft
def test_remove_deletes_literal_lines_and_refuses_other_blocks(tconn):
    out = service.edit(tconn, fresh_draft(tconn), {}, [{"section": "header", "index": 5, "remove": True},
                                        {"section": "footer", "index": 1, "remove": True}])
    assert [b.get("text") for b in out["layout"]["header"]][-1] is None and len(out["layout"]["footer"]) == 2
    assert out["fill_in"] == []
    for bad in ([{"section": "header", "index": 1, "remove": True}], [{"section": "header", "index": 2, "remove": "yes"}]):
        with pytest.raises(TemplateError) as e:
            service.edit(tconn, fresh_draft(tconn), {}, bad)
        assert e.value.status == 400
def test_removals_use_the_stored_indexes_and_apply_after_text_edits(tconn):
    # one call: remove footer 1, edit header 2 → "Open daily", remove header 5
    # → header texts == [None, None, "Open daily", None, None]; footer fields == ["address", "phone"]
def test_removing_every_literal_line_leaves_a_valid_layout(tconn):
    # remove header 2, 5 and footer 1; then service.active_layout_for_save after accept is not (None, None)
def test_keep_header_removes_the_footer_copy_and_both_keeps_both(tconn):
    out = service.edit(tconn, fresh_draft(tconn), {}, [], keep=[{"field": "phone", "where": "header"}])
    assert [b.get("field") for b in out["layout"]["footer"]] == ["address", None] and out["duplicates"] == []
    # where "both" → layout unchanged; where "middle" or field "ssn" → 400
def test_keep_for_a_field_no_longer_duplicated_is_ignored(tconn):
    # keep address/header on a layout where address is footer-only → 200, layout unchanged
def test_a_cleared_line_without_remove_is_still_rejected(tconn):
    # text "  " with no remove → 400 "edit rejected: ..."
def test_tidy_fixes_an_active_letterhead_and_audits_it(tconn):
    # accept the draft, then service.tidy(remove "Visit After", keep phone header, actor="demo")
    # → view status "active", fill_in == [], duplicates == [], ("template_tidy", "demo") in _audit(tconn);
    # active_layout_for_save(tconn)[0].footer has no "Visit After"; tidy on an archived row → 409, on 999 → 404
# tests/test_template_routes.py
def test_put_lines_route_on_an_active_template(tclient):
    # upload, accept, PUT /{id}/lines {"lines": [{"section": "header", "index": 2, "remove": True}], "keep": []} → 200,
    # GET /active shows the header without "Open Mon to Sat"; PUT /999/lines → 404; "keep": "x" → 400
```

Add `("PUT", "/api/v1/templates/{id}/lines"): {"lines": [], "keep": []}` to `BODIES` in
`tests/test_isolation_routes.py:18-22`; the id-route sweep (`:33-37`) then covers the new route for cross-clinic 404.

- [ ] **Step 2: Run to verify they fail**
Run: `.venv/bin/python -m pytest -q tests/test_template_service.py tests/test_template_routes.py`
Expected: new tests FAIL (`remove` reaches `block["text"] = None` path → 400 for valid input; no `tidy`; 405 on the route).

- [ ] **Step 3: Implement `apply_line_changes`, `edit(keep=...)`, `tidy`, `EditBody.keep`, the route**
`edit` keeps its profile handling (`service.py:127-130`) and replaces its line loop (`:131-141`) with
`apply_line_changes(lay, lines, keep or [])`. `tidy` loads the row like `set_doctors` does (`service.py:285-289`),
then the same apply + validate + `tdb.update_template_layout`. Route follows `set_template_doctors`
(`api/templates.py:177-185`).

- [ ] **Step 4: Run to verify they pass**
Run: `.venv/bin/python -m pytest -q tests/test_template_service.py tests/test_template_routes.py tests/test_isolation_routes.py tests/test_letterhead_review.py`
Expected: PASS, including the unchanged `test_accept_or_edit_non_draft_is_409_and_missing_is_404`
(`tests/test_template_service.py:104-113`) and the malformed-line parametrisation (`tests/test_template_routes.py:155-166`).

- [ ] **Commit** (ask the owner first): the files in **Files:** above, message "Letterhead lines: remove a line, choose where a duplicated field prints, fix an active letterhead".

---

### Task 4: Review screen: remove ticks and the duplicate question (draft)

**Files:**
- Create: `frontend/lhlines.js` (pure plan/payload + DOM render/collect; `window.LhLines`, `module.exports` like
  `frontend/dates.js:65`)
- Modify: `frontend/letterhead.js:136-143` (drop `literalLines`), `:155-167` (`renderWarnings` selects
  `input.lh-line-text` only), `:221-230` (`renderReview` uses `LhLines.render`), `:250-256` (`collect` uses
  `LhLines.collect`); `accept` (`:291-295`) is not gated by the duplicate question
- Modify: `frontend/index.html:11` (`letterhead.css?v=9`), `:266` (`lhlines.js?v=1` before `letterhead.js?v=12`),
  `:209-210` add `<p id="lhSkipped" class="panel-hint" hidden></p>` and `<div id="lhDupes"></div>` inside `lhLinesBox`
- Modify: `frontend/letterhead.css` (rules `.lh-line-row`, `.lh-line-why`, `.lh-dupe`)
- Test: `tests/test_frontend_lhlines.py` (new), `tests/test_frontend_letterhead.py:38-40`,
  `tests/test_frontend_doctorgrid.py:43`

**Interfaces:**
- Consumes: view keys `fill_in`, `duplicates`, `layout.skipped_labels` (Task 2); request shape (Task 3).
- Produces (`window.LhLines`):
  - `plan(view) -> {rows: [{section, index, text, remove: bool, label: bool, warn: bool}], dupes: [{field, header:
    [int], footer: [int], where: "both"}], skipped: [str]}` (every duplicate starts as `"both"`, owner Q5) — one row per literal line in reading order; `remove`/`label` true when the
    line is in `view.fill_in`; `warn` true when in `view.warnings`.
  - `payload(rows, answers) -> {lines: [...], keep: [...]}` — a row with `remove` or empty trimmed `text` becomes
    `{section, index, remove: true}`, else `{section, index, text}`; `answers` maps field → `"header"|"footer"|"both"`;
    one `keep` entry per answered field (no `missing` list: nothing is ever unanswered).
  - `render(box, view)` fills `#lhLines`, `#lhDupes`, `#lhSkipped`; `collect(box) -> payload(...)` reads them back.

Screen copy (exact):
- Remove tick label: "Remove this line". Note under a pre-ticked line: "Looks like a blank label from the paper pad.
  The app prints the patient's details itself."
- Duplicate legend: "{Phone} prints at the top and at the bottom. Keep it:"; radios "At the top only", "At the bottom
  only", "In both places" ("In both places" checked when the screen opens). Field names from `PROFILE_LABEL`
  (`letterhead.js:9-10`). No "choose first" message: the question never blocks.
- Skipped note: "Left out as blank labels from the paper pad: " + texts joined with "; ".

- [ ] **Step 1: Write the failing tests**
```python
# tests/test_frontend_lhlines.py — run frontend/lhlines.js under node via require (skip when node is missing)
def test_plan_pre_ticks_fill_in_lines_and_marks_warnings():
    view = {"layout": {"header": [{"type": "text", "field": "phone"}, {"type": "text", "text": "Name: Age:"},
                                  {"type": "text", "text": "Dr. X"}], "footer": [{"type": "text", "text": "Visit After"}]},
            "fill_in": [{"section": "header", "index": 1, "text": "Name: Age:"}, {"section": "footer", "index": 0, "text": "Visit After"}],
            "warnings": [{"section": "header", "index": 2, "text": "Dr. X"}], "duplicates": []}
    rows = node_plan(view)["rows"]
    assert [(r["section"], r["index"], r["remove"], r["warn"]) for r in rows] == [
        ("header", 1, True, False), ("header", 2, False, True), ("footer", 0, True, False)]
def test_a_duplicate_starts_as_both():                                   # owner Q5
    view = {"layout": {"header": [], "footer": []}, "fill_in": [], "warnings": [],
            "duplicates": [{"field": "phone", "header": [0], "footer": [1]}]}
    assert node_plan(view)["dupes"] == [{"field": "phone", "header": [0], "footer": [1], "where": "both"}]
def test_payload_turns_ticks_and_empty_text_into_removals_and_sends_the_choice():
    # rows: header 1 remove; header 2 text "  " → remove; footer 0 text "Open daily"
    # answers {"phone": "both"} → keep == [{"field": "phone", "where": "both"}]; no "missing" key in the result
    # answers {"phone": "header"} → keep == [{"field": "phone", "where": "header"}]
# tests/test_frontend_letterhead.py
def test_letterhead_assets_are_cache_busted():                       # changed pins
    html = _read("index.html")
    assert "letterhead.js?v=12" in html and "letterhead.css?v=9" in html
    assert html.index("lhlines.js?v=1") < html.index("letterhead.js?v=")
def test_review_screen_has_the_remove_and_duplicate_controls():
    html, js = _read("index.html"), _read("lhlines.js")
    assert 'id="lhDupes"' in html and 'id="lhSkipped"' in html
    assert "Remove this line" in js and "At the top only" in js and "In both places" in js
    assert "Choose where the" not in js + _read("letterhead.js")        # owner Q5: the question never blocks
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js       # server text is never markup
```

Also change `tests/test_frontend_doctorgrid.py:43` to `"letterhead.css?v=9", "letterhead.js?v=12"`, and extend
`test_letterhead_js_parses` (`tests/test_frontend_letterhead.py:77-82`) to run `node --check` on `lhlines.js` too.

- [ ] **Step 2: Run to verify they fail**
Run: `.venv/bin/python -m pytest -q tests/test_frontend_lhlines.py tests/test_frontend_letterhead.py tests/test_frontend_doctorgrid.py`
Expected: FAIL (no `lhlines.js`, old pins).

- [ ] **Step 3: Implement `frontend/lhlines.js`, wire `letterhead.js`, add the HTML hooks, CSS and pins**
A ticked row disables its text input. `saveEdits` (`letterhead.js:279-286`) sends `{profile, lines, keep}`;
`render` checks "In both places" for each duplicate; `updatePreview`, `saveEdits` and `accept` send the current
choices and are never blocked by the question (owner Q5); "Use built-in layout" is not blocked either (it prints nothing from the layout). All text through `textContent` / `createElement` (rule at `tests/test_frontend_letterhead.py:33-35`).

- [ ] **Step 4: Run to verify they pass**
Run: `.venv/bin/python -m pytest -q tests/test_frontend_lhlines.py tests/test_frontend_letterhead.py tests/test_frontend_doctorgrid.py`
Expected: PASS. `wc -l frontend/letterhead.js` under 500.

- [ ] **Commit** (ask the owner first): the files in **Files:** above, message "Letterhead review: remove a line (labels pre-ticked) and choose where a duplicated field prints".

---

### Task 5: Fix the lines of an active letterhead (how gsr-clinic's gets fixed)

**Files:**
- Modify: `frontend/letterhead.js:18` (`lh` gains `clinicView`, `mineView`, `tidy`), `:48-62` (`refreshStatus`
  stores the views and adds the nudge), `:100-105` (`show` gains a `"tidy"` view), `:257-263` (`loadPreview(id)` takes
  the template id), add `openTidy(view)` and `saveTidy()`
- Modify: `frontend/index.html:184-185` add two buttons after `lhStopBtn`; `:212-238` wrap the doctors, scope, fill
  hint, "Clinic details" and "Doctors" parts in `<div id="lhDetailsPart">`; `:240-245` add
  `<button id="lhTidySaveBtn" type="button" class="primary lh-act" hidden>Save changes</button>`
- Test: `tests/test_frontend_letterhead.py` (add); pins already bumped in Task 4 (bump again only if Task 4 shipped
  separately: `letterhead.js?v=13`)

**Interfaces:**
- Consumes: `/current` views with `id`, `fill_in`, `duplicates` (Task 2); `PUT /{id}/lines` (Task 3);
  `LhLines.render/collect` (Task 4).
- Produces: buttons `lhTidyBtn` ("Fix lines on the clinic letterhead", shown when `lh.clinicView` and the upload view
  is showing) and `lhTidyMineBtn` ("Fix lines on my letterhead", shown when `lh.mineView`).

Behaviour:
- `refreshStatus` appends to the status line, when the clinic view has `fill_in` or `duplicates`: " Some lines on it
  look like blank labels from the paper pad or print twice. Press Fix lines to check them."
- `openTidy(view)`: `show("tidy")` shows `lhReview` with `lhDetailsPart` hidden, and in the foot only `lhTidySaveBtn`
  (Accept, Re-upload, Use built-in and Update preview hidden); `LhLines.render`; `loadPreview(view.id)`.
- `saveTidy()`: never blocked by the duplicate question (it starts as "In both places"); `PUT /{id}/lines`; on 200 re-render from the
  returned view, redraw the preview, show in `lhDone`: "Saved. New prescriptions and re-prints use the fixed
  letterhead."
- Closing the panel clears `lh.tidy`; `openPanel` (`letterhead.js:106-113`) still prefers a draft, else the upload view.

- [ ] **Step 1: Write the failing tests**
```python
def test_active_letterhead_can_be_fixed_without_a_new_upload():
    html, js = _read("index.html"), _read("letterhead.js")
    for elem_id in ("lhTidyBtn", "lhTidyMineBtn", "lhTidySaveBtn", "lhDetailsPart"):
        assert f'id="{elem_id}"' in html, elem_id
    assert '"/lines"' in js and "Fix lines on the clinic letterhead" in html
    assert "New prescriptions and re-prints use the fixed letterhead." in js
def test_tidy_mode_hides_accept_and_the_details_part():
    js = _read("letterhead.js")
    show = js[js.index("function show("):js.index("async function openPanel")]
    assert '"tidy"' in show and "lhAcceptBtn" in show and "lhDetailsPart" in show
```

- [ ] **Step 2: Run to verify they fail**
Run: `.venv/bin/python -m pytest -q tests/test_frontend_letterhead.py`
Expected: the two new tests FAIL.

- [ ] **Step 3: Implement** the buttons, `show("tidy")`, `openTidy`, `saveTidy`, `loadPreview(id)` (draft callers
  pass `lh.draft.id`), and the status nudge.

- [ ] **Step 4: Run the whole letterhead set**
Run: `.venv/bin/python -m pytest -q tests/test_frontend_letterhead.py tests/test_frontend_lhlines.py tests/test_frontend_doctorgrid.py tests/test_template_service.py tests/test_template_routes.py tests/test_letterhead_review.py tests/test_template_builder.py tests/test_letterhead_lines.py tests/test_isolation_routes.py tests/test_isolation_letterhead.py`
Expected: PASS. Then the full suite: `.venv/bin/python -m pytest -q` → PASS.

- [ ] **Step 5: Manual check for the owner** (not run by the executor; listed for the owner): on gsr-clinic, open
  Profile → Upload or manage letterhead → Fix lines on the clinic letterhead; "Name: M F Age: Date:", "Visit After"
  and "Submit" show ticked; the phone question shows "In both places" selected; choose "At the top only"; Save; re-print OP-20261019-001 and confirm one patient line and
  one phone.

- [ ] **Commit** (ask the owner first): the files in **Files:** above, message "Letterhead: fix the lines of an active letterhead without a new upload".

---

## Existing tests that change

| Test | Change |
|---|---|
| `tests/test_frontend_letterhead.py:38-40` | pins `letterhead.js?v=12`, `letterhead.css?v=9`, `lhlines.js?v=1` order |
| `tests/test_frontend_doctorgrid.py:43` | same pins |
| `tests/test_frontend_letterhead.py:77-82` | also `node --check frontend/lhlines.js` |
| `tests/test_isolation_routes.py:18-22` | `BODIES` entry for `PUT /api/v1/templates/{id}/lines` |
| All others in Task 0's list | unchanged; new tests are added beside them |

## Out of scope

Fill-in slots (backlog card al); non-English label words in the code filter; a "restore" for a line the builder left
out (the doctor re-uploads); vitals printing (plans d/e); labels drawn inside the pad body.
