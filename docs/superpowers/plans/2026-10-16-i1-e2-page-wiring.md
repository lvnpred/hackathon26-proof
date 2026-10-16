# I1-e2: Medication Row UI, Page Wiring and the Save Gate

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load the row UI from plan I1-e into the page: the new state cell and chips in every medicine row, a sticky summary bar ("6 medicines", "4 ready", "2 need you") that owns the Save button ("Resolve 2 to save" / "Save prescription"), and a block panel that can no longer confirm medicines in bulk.

**Architecture:** One guarded script edits `frontend/index.html` and `frontend/app.js` (each edit names its current line and must match exactly once). `app.js` gets hooks, not logic: all rules stay in `rxstate.js`. The server gate (`core/safety.py:9-26`, called at `api/persistence.py:194`) stays authoritative and unchanged.

**Tech Stack:** vanilla JS, pytest (static checks), Playwright MCP tools for the browser check.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` "Iteration 1" sections 1, 3 and 5; contracts `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` sections 4.1 and 4.5.

**Assumptions about earlier plans:** plan I1-e is applied (its three files and 9 tests exist). Nothing from I1-a to I1-d is required: rows without the new fields behave as today.

## Global Constraints

- No `git commit` or `git push`; finish with the changed-file list. Baseline first: run `.venv/bin/python -m pytest tests/ -q`, note the count (944 + 9 from I1-e when written), expect count + 2 at the end.
- HTTP codes and JSON shapes do not change: the save request still carries `confirmed_rows` (`app.js:655`, `:1062`).
- Existing tests keep their assertions. One setup value changes: `tests/test_frontend_authorship.py:118` pins `app.js?v=26`; the script turns that into "version 26 or newer", the precedent of `tests/test_frontend_letterhead.py:62-65`.
- `setWorking` (`app.js:116`) must keep `Authorship.enforce()` as its last line (`tests/test_frontend_authorship.py:70-74`); the new `RxView.sync()` goes before it.
- Browser checks run the app with `DB_PATH` pointing at a temp file. Never run single mode against the real dev DB (memory note "Single mode writes the real dev DB").

## Review Focus

- Reopening a saved document starts with no confirmations (`state.confirmed.clear()`, `app.js:323`), so its unverified rows need you again and Save stays off. Same rule the server applies; now it is visible up front. Checked in the manual list, step 13.
- A fully blank row must not count (`readRx` drops it before the server sees it): `openRows` now skips it via `RxView.isBlank`; manual step 11.
- A colleague's view-only prescription must not be changed by a chip tap or re-enabled by the bar: manual step 12 and the `isViewOnly` tests in I1-e.
- After a save is in flight (`state.working`), taps do nothing and Save stays off: `RxView.sync()` is called from `setWorking`.
- A stale page can still reach the server gate (409): the block panel stays as a safety net, manual step 10.

## Decisions (with the reason)

| Question | Decision | Why |
|---|---|---|
| Keep the old `#blockPanel` / "Confirm all & Save"? | Keep the panel and the 409 handling; **remove "Confirm all & Save"** and the per-row "Confirm" buttons in it. Rows get a "Go to row" button. | With Save disabled while anything needs you, the server's 409 can only happen from a stale page. Bulk-confirming unverified medicines contradicts "resolve each one". The panel still tells the truth if the server disagrees. `confirmed_rows` is untouched. |
| Where do Save and Print live? | Move `.save-row` into the sticky summary bar (ids unchanged). | The doctor resolves rows far from the bottom of a long sheet; the bar keeps the count and Save in view. Text "💾 Save" becomes "Save prescription". |
| Printing | Everything new is `no-print`; the old symbol still prints from `span.rx-print-sym`. | Browser print (`app.js:1206`) stays as before. The canvas says statuses never print; the PDF's Check column (`doctor_dictation/pdf/sheet.py:14-19`) still prints `✓ ! ± ?` and maps `lookalike-check` and `dose-check` to `?`. Dropping or extending it is a backend change: **flagged, not done**. |

### Why every UI-allowed save is accepted, and every UI block is a server block

`screen_unverified` blocks a row when `status != "verified"` and its index is not in `confirmed_rows` (`core/safety.py:21-26`). The page sends `status` from `tr.dataset.status` and `confirmed_rows` from `state.confirmed` (`app.js:655`), and `RxState.rowState(...).needsYou` is exactly that predicate. `test_needs_you_agrees_with_the_servers_save_gate...` (I1-e) runs both over nine statuses (including `null`, `""` and an unknown future one) times confirmed or not and requires identical answers. Rows the server never sees (fully blank) are skipped on both sides.

### Task 1: Load the files, wire `app.js`, move Save into the bar

**Files:**
- Modify: `frontend/index.html`, `frontend/app.js`, `tests/test_frontend_authorship.py:118`
- Test: `tests/test_frontend_rxrow.py` (append, and add `import re` to its imports)

**Interfaces:**
- Consumes: `RxState`, `RxView` (I1-e). Produces: `app.js` calls `RxView.init`, `attach`, `renderRow`, `sync`, `onEdit`, `meta`, `isBlank`; I1-e3 adds `RxView.restore` and more hooks.

- [ ] **Step 1: Append the failing tests.** Add `import re` after `import json`, then append:

```python
def test_the_page_loads_the_new_files_before_app_js_and_holds_save_in_the_bar():
    html = _read("index.html")
    pos = [html.index(s) for s in ("rxstate.js?v=", "rxview.js?v=", "app.js?v=")]
    assert pos == sorted(pos) and re.search(r'href="rx\.css\?v=\d+"', html)
    bar = html[html.index('id="rxBar"'):html.index('id="sheet"')]
    assert 'id="saveBtn"' in bar and 'id="printBtn"' in bar and 'aria-describedby="rxNeeds"' in bar and 'id="rxNeeds" class="rx-count" data-state="dose" role="status"' in bar
    assert html.count('id="saveBtn"') == 1 and "confirmAllBtn" not in html and "Confirm all" not in html
    assert int(re.search(r"app\.js\?v=(\d+)", html).group(1)) >= 27

def test_app_js_edits_are_hooks_and_the_save_request_still_carries_confirmed_rows():
    app = _read("app.js")
    for token in ("RxView.init({", "RxView.attach(tr, r);", "RxView.onEdit(tr, e.target);", "Object.assign(rec, RxView.meta(tr))", "function renderCheck(tr) { RxView.renderRow(tr); }",
                  "if (state.confirmed.has(k.rowid)) confirmed_rows.push(i);", "      confirmed_rows,\n"):
        assert token in app, token
    assert "PILL" not in app and "confirmAllBtn" not in app and "statusText(" not in app
    assert "RxView.isBlank(tr)" in app.split("function openRows()")[1].split("function updateGrounding()")[0]
    body = app.split("function setWorking(")[1].split("\n}\n")[0]
    assert body.index("RxView.sync()") < body.index("Authorship.enforce()") and body.rstrip().splitlines()[-1].count("Authorship.enforce()") == 1
```

- [ ] **Step 2: Run them.** `.venv/bin/python -m pytest tests/test_frontend_rxrow.py -q` -> expected `2 failed, 9 passed`.

- [ ] **Step 3: Apply the edits.** Run from the repo root as `python3 - <<'PY' ... PY` (paste the whole script). Each edit names the original line it changes.

```python
# Run from the repo root. Every edit asserts it matched exactly once, so a drifted file stops the script instead of half-editing.
def edit(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (path, old[:60])
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)
def between(path, start, end, new):                     # replace [start, end) with new
    s = open(path, encoding="utf-8").read()
    a = s.index(start); b = s.index(end, a)
    open(path, "w", encoding="utf-8").write(s[:a] + new + s[b:])
A = "frontend/app.js"
between(A, "const PILL = {", "// ---- small helpers", "")                                       # :57-63 PILL, PILL_DEFAULT
between(A, "// The check pill: verified", "function renderSheet(s)",                             # :893-926 renderCheck
        "// The row's state cell is built by rxview.js from the rules in rxstate.js.\nfunction renderCheck(tr) { RxView.renderRow(tr); }\n\n")
between(A, "function updateGrounding()", "// ---- inline-edit invalidation", '''function updateGrounding() {                            // :954 now a sentence plus the summary bar
  if (!state.structured) { groundingEl.hidden = true; RxView.sync(); return; }
  const open = openRows().length;
  groundingEl.hidden = false;
  groundingEl.className = "grounding " + (open ? "warn" : "ok");
  groundingEl.textContent = open
    ? open + (open > 1 ? " medicines need" : " medicine needs") + " you. Resolve each one in the sheet, then Save."
    : "All medicines are ready. You can Save.";
  RxView.sync();
}

''')
between(A, "function statusText(s)", "function refreshBlockPanel()", "")                      # :994 statusText
between(A, '    const btn = document.createElement("button");\n    btn.type = "button";\n    btn.className = "confirm-btn";', "    li.appendChild(btn);",
        '''    const btn = document.createElement("button");        // :1010-1020 refreshBlockPanel: jump to the row, no confirming here
    btn.type = "button";
    btn.textContent = "Go to row";
    btn.addEventListener("click", () => {
      const tr = rxBody.querySelector('tr[data-rowid="' + b.rowid + '"]');
      if (tr) { tr.scrollIntoView({ block: "center" }); const s = tr.querySelector(".rx-state"); if (s) s.focus(); }
    });
''')
between(A, '$("confirmAllBtn").addEventListener', "// ---- Save, then Print", "")                 # :1029-1036 "Confirm all & Save"
edit(A, [
 ('''  recBtn.classList.toggle("busy", on);\n''', '''  recBtn.classList.toggle("busy", on);\n  RxView.sync();                                     // after :128 Save follows the medicines, not just "busy"\n'''),
 ('''  tr.appendChild(check);\n  renderCheck(tr);''', '''  tr.appendChild(check);\n  RxView.attach(tr, r);                               // :874 rxRow keeps the extra row fields\n  renderCheck(tr);'''),
 ('''!state.confirmed.has(tr.dataset.rowid));''', '''!state.confirmed.has(tr.dataset.rowid) && !RxView.isBlank(tr));'''),   # :951 openRows
 ('''  tr.dataset.status = "";\n  renderCheck(tr);''', '''  tr.dataset.status = "";\n  RxView.onEdit(tr, e.target);                        // :974 a hand edit drops stale reasons\n  renderCheck(tr);'''),
 ('''+ statusText(b.status) + " ");''', '''+ RxState.rowState({ status: b.status }, {}).reason + " ");'''),
 ('''  return rec;\n}\nfunction deleteRow''', '''  return Object.assign(rec, RxView.meta(tr));       // :756 snapshotRow: heard, generic, chips survive delete + undo\n}\nfunction deleteRow'''),
 ('''Confirm below (or in the row) or dictate a correction, then Save again.");''', '''Resolve them in the sheet (the list below jumps to each one), then Save again.");'''),
 ('''  groundingEl.hidden = true;\n  highlightToday();''', '''  groundingEl.hidden = true;\n  RxView.sync();                                      // :1251 newPatient hides the bar\n  highlightToday();'''),
 ('''// ---- init ------------------------------------------------------------------\n''', '''// ---- init ------------------------------------------------------------------\nRxView.init({\n  body: rxBody, saveBtn, confirmed: () => state.confirmed, working: () => state.working,\n  changed: () => { markDirty(); updateGrounding(); }, hasSheet: () => !sheetEl.classList.contains("empty"),\n});\n'''),
])
edit("frontend/index.html", [
 ('<link rel="stylesheet" href="styles.css?v=9" />\n', '<link rel="stylesheet" href="styles.css?v=9" />\n<link rel="stylesheet" href="rx.css?v=1" />\n'),
 ('''      <strong>Confirm these medicines before saving</strong>\n      <ul id="blockList"></ul>\n      <button id="confirmAllBtn" type="button">Confirm all &amp; Save</button>\n''',
  '''      <strong>The server still blocked these medicines. Resolve them in the sheet.</strong>\n      <ul id="blockList"></ul>\n'''),
 ('''    <section id="sheet" class="empty">''', '''    <div id="rxBar" class="rx-bar no-print" hidden>
      <div class="rx-bar-main">
        <strong id="rxTitle"></strong>
        <span id="rxReady" class="rx-count" data-state="ok"></span>
        <span id="rxNeeds" class="rx-count" data-state="dose" role="status"></span>
      </div>
      <div class="save-row no-print"><button id="saveBtn" class="save no-print" type="button" hidden aria-describedby="rxNeeds">Save prescription</button><button id="printBtn" class="save print no-print" type="button" hidden disabled title="Save first, then print">🖨 Print</button></div>
    </div>
    <section id="sheet" class="empty">'''),
 ('''    <div class="save-row no-print"><button id="saveBtn" class="save no-print" type="button" hidden>💾 Save</button><button id="printBtn" class="save print no-print" type="button" hidden disabled title="Save first, then print">🖨 Print</button></div>\n''', ''),
 ('<script src="app.js?v=26"></script>', '<script src="rxstate.js?v=1"></script>\n<script src="rxview.js?v=1"></script>\n<script src="app.js?v=27"></script>'),
])
edit("tests/test_frontend_authorship.py", [('("auth.js?v=4", "authorship.js?v=4", "app.js?v=26"))', '("auth.js?v=4", "authorship.js?v=4")) and int(re.search(r"app\\.js\\?v=(\\d+)", html).group(1)) >= 26')])
```

- [ ] **Step 4: Run the tests.** `.venv/bin/python -m pytest tests/test_frontend_rxrow.py tests/test_frontend_authorship.py tests/test_frontend_doctorgrid.py tests/test_frontend_letterhead.py tests/test_frontend_auth.py tests/test_frontend_team.py -q` -> expected all pass (`11` rxrow tests among them). Then `.venv/bin/python -m pytest tests/ -q` -> expected baseline + 2.

- [ ] **Step 5: Leave uncommitted.** `git status --short` lists `M frontend/app.js`, `M frontend/index.html`, `M tests/test_frontend_authorship.py`, `M tests/test_frontend_rxrow.py` plus the I1-e files.

### Task 2: Browser check (Playwright MCP)

No code. The page needs a sheet; the check renders a fixture through the page's own `renderSheet` (a top-level function, reachable from `browser_evaluate`) so no speech or LLM engine is needed. Replace `<repo>` with the repo root.

- [ ] **Step 1: Start the app on a temp database.** Run in a terminal (background):

```bash
cd <repo> && DB_PATH="$(mktemp -d)/e2.db" STT_ENGINE=stub LLM_PROVIDER=stub .venv/bin/python -m uvicorn doctor_dictation.main:app --port 8791
```
Expected: `Uvicorn running on http://127.0.0.1:8791`. If the port is busy use another. The temp directory proves the real `doctor_dictation/data/app.db` is not used.

- [ ] **Step 2: Open the page.** `browser_navigate` to `http://localhost:8791/`, then `browser_console_messages` with level `error`. Expected: only 404s for `/api/v1/auth/me`, `/api/v1/users`, `/favicon.ico` (single mode) and possibly a 500 for `/api/health` with stub engines; no `RxView` or `RxState` errors.

- [ ] **Step 3: Render the fixture.** `browser_evaluate` with:

```js
() => { state.structured = {}; state.transcript = "tablet prednisone ten milligram";
  renderSheet({ patientName: "Meera Nair", ageSex: "46 / F", rx: [
   {form:"Tab.",name:"Amlodipine",strength:"",dose:"1-0-0",timing:"After food",duration:"30 days",instructions:"",status:"unverified-strength",lexicon_match:"Amlodipine",strength_options:["2.5 mg","5 mg","10 mg"],usual_strength:"5 mg"},
   {form:"Tab.",name:"Prednisone",strength:"10 mg",dose:"1-0-1",timing:"After food",duration:"5 days",instructions:"",status:"lookalike-check",lexicon_match:"Prednisone",heard:"prednisone",lookalike:"Prednisolone"},
   {form:"Cap.",name:"Omeprazole",strength:"20 mg",dose:"1-0-0",timing:"Before food",duration:"14 days",instructions:"",status:"verified",lexicon_match:"Omeprazole",source:"lexicon"},
   {form:"Tab.",name:"Zyloric",strength:"100 mg",dose:"0-0-1",timing:"",duration:"30 days",instructions:"",status:"verified",lexicon_match:"Allopurinol",generic:"Allopurinol",source:"lexicon"},
   {form:"Tab.",name:"Rantac-D",strength:"150 mg",dose:"1-0-1",timing:"Before food",duration:"10 days",instructions:"",status:"verified",lexicon_match:"Rantac-D",source:"clinic"}]});
  return [rxTitle.textContent, rxReady.textContent, rxNeeds.textContent, saveBtn.textContent, saveBtn.disabled]; }
```
Expected: `["5 medicines","3 ready","2 need you","Resolve 2 to save",true]`. (`browser_take_screenshot` can hang in some headless setups; use `browser_snapshot` and computed styles instead.)

- [ ] **Step 4: Check the five states by words.** `browser_snapshot`. Expected pill text per row: `Check dose`, `Confirm medicine`, `Matched`, `Matched`, `Known to your clinic`; reasons: `No strength was dictated. Tap one below.`, `Heard "prednisone". It looks like Prednisolone. They are different medicines.`; Zyloric shows `generic: Allopurinol`; chips `5 mg` (marked "usual", first), `2.5 mg`, `10 mg`.

- [ ] **Step 5: Chip tap.** `browser_click` the button named `Set strength to 10 mg`. Expected: strength cell reads `10 mg`, pill `Confirmed by you`, reason `You chose the strength 10 mg.`, bar `1 needs you`, focus on the row's state box.

- [ ] **Step 6: Confirm as is.** `browser_click` `Confirm Prednisone as is`. Expected: `0 need you`, Save enabled with text `Save prescription`. Then click `Reopen` on that row: back to `1 needs you`, Save disabled.

- [ ] **Step 7: A hand edit.** Click into Omeprazole's name, type `x`. Expected: that row shows `Confirm row` / `You changed this row. Confirm it before saving.`; bar `2 need you`; chips and generic lines of other rows unchanged. Delete the `x`: the row stays "needs you" (an edit never restores verification).

- [ ] **Step 8: Keyboard and size.** Press Tab through a row: the order is the row's cells, then its action buttons, never a hidden control. `browser_evaluate`: `() => [...document.querySelectorAll(".rx-act")].every(b => b.getBoundingClientRect().height >= 44)` -> `true`. `() => getComputedStyle(document.querySelector(".rx-act")).outlineStyle` after focusing it by Tab -> not `none`.

- [ ] **Step 9: Print.** `browser_emulate_media` with `media: "print"`, then `browser_evaluate`: `() => ["#rxBar",".rx-state",".rx-chips",".rx-sub"].map(s => { const n = document.querySelector(s); return n ? getComputedStyle(n).display : "absent"; })` -> every entry `none` or `absent`; `() => getComputedStyle(document.querySelector(".rx-print-sym")).display` -> `inline`. Reset with `media: null`.

- [ ] **Step 10: Save, and the safety net.** Make `0 need you` (confirm every open row), wrap fetch with `browser_evaluate`: `() => { window.__r = []; const f = window.fetch; window.fetch = (u, i) => { window.__r.push([u, i && i.body]); return f(u, i); }; }`, click Save. Expected: status `Saved — document 1...`; `browser_evaluate` `() => window.__r.filter(r => r[0] === "/api/v1/documents")` shows a body whose `confirmed_rows` lists the indices you confirmed and the call returned 200 (the status line). Then re-render the fixture, and force a stale save: `() => { saveBtn.disabled = false; saveBtn.click(); }`. Expected: 409 handled: the block panel appears with `Go to row` buttons and no `Confirm all & Save`; clicking one moves focus to that row's state box.

- [ ] **Step 11: Blank row and undo.** Re-render, clear every cell of row 5 by `browser_evaluate` (`() => { document.querySelectorAll("#pRx tr[data-index]")[4].querySelectorAll("[data-col]").forEach(c => { c.textContent = ""; c.dispatchEvent(new Event("input", { bubbles: true })); }); return [rxTitle.textContent, rxNeeds.textContent]; }`): the title drops to `4 medicines` and the blank row is not counted. Click the delete button of the Zyloric row, then `Undo`: the row returns with its `generic: Allopurinol` line and the state `Matched`.

- [ ] **Step 12: View-only.** Re-render, then `browser_evaluate`: `() => { Authorship.onOpen({ author: { name: "Dr Test" }, can_edit: false }); document.querySelector(".rx-chip").click(); return [saveBtn.disabled, getComputedStyle(document.querySelector(".rx-act")).display]; }`. Expected: `[true,"none"]` and the strength cell unchanged.

- [ ] **Step 13: Reopen a saved document.** Reload the page, open the saved patient from the Today list (confirm the dialog). Expected: rows the doctor had confirmed show as needing you again; Save is `Resolve N to save`; Print works as before. Close the browser (`browser_close`), stop uvicorn, and delete the folder the tool created in the repo: `rm -rf .playwright-mcp`.

## Self-Review

- Spec coverage: states, chips, generic line, summary bar and Save text (Task 1 plus I1-e); gate agreement proven in tests and the table above; old block panel decided; keyboard, 44px, reduced motion (no animation exists until I1-e3, which adds the rule), print (steps 8-9). Spell it: I1-e3.
- Placeholder scan: none.
- The 409 text and "Go to row" use only existing ids (`state.lastBlock`, `data-rowid`).

**Decision needed:** (1) approve removing "Confirm all & Save"; (2) decide whether the PDF's Check column (`pdf/sheet.py:14-19`) should be dropped or extended with `lookalike-check` and `dose-check` (a backend task, not in these plans). Not done: Spell it, any backend change, any commit.
