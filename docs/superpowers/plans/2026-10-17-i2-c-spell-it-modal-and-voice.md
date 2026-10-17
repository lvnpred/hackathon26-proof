# I2-c: Spell It as an Accessible Modal, with a Paged List and Voice Input Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Summary.** Spell it is today an inline panel: a table row under the medicine (`frontend/rxview.js:106-154`), at most 6 names (`:149`) from at most 5 the server sends (`core/rowcheck.py:7`). This plan replaces it with a `<dialog>` modal: labelled, focus kept inside, Esc closes, focus returns to the Spell button; the typed field; a list with the generic and a reason per name ("sounds like", "your clinic uses it"); 8 names per page with Previous / Next, PageUp / PageDown and "Showing 1-8 of N"; arrow keys and Enter; a phone layout at 390 px; and a microphone button that records up to 4 seconds, sends it to the existing `/api/transcribe` and fills the field (never applied). The server sends `options` (up to 40) and `total`. The I1-e3 race rules stay. Spell it stays limited to name questions. Adds 10 tests: **1718** after I2-a only (1708 + 10), **1734** after I2-a and I2-b.

**Decision needed from the owner.** None beyond the index defaults (the 40-name cap, 8 per page and a 4-second voice clip are in section 6 as part of D4). Run after I2-a.

- **Goal:** A Spell it that works with the keyboard, on a phone and by voice, and never changes a row until the doctor presses Use this.
- **Architecture:** Server: `api/rx.py` adds `rowcheck.options(row)` (built by I2-a) to the check-row answer. Page: `frontend/suglist.js` (I2-a: `SugList.item`) gains `page()` and `list()`, shared by the inline Did you mean and the modal. New `frontend/spellmodal.js` owns the dialog (open, close, focus trap, keys, paging, voice). `frontend/rxview.js` keeps the row rules (`useName`: request token, confirmed set BEFORE the render, `how = "spell"`, Undo record) and asks `SpellModal` to show them. `app.js` adds `transcribeName(blob)` (the same route, no "working" state) and wires `SpellModal.init`.
- **Tech Stack:** vanilla JS (`<dialog>`, `MediaRecorder`, `getUserMedia`), FastAPI, pytest, node fake DOM. No new dependency.
- **Spec:** index `2026-10-17-i2-00-index.md` D4, sections 4.3, 4.5; I1 contracts 4.4 (check-row), 4.5 (name-only Spell rule, decision 2026-10-16 I1-e3).
- **Assumes from I2-a (re-find with `grep -n`):** `rowcheck.options(row, cap=40) -> (list, total)` and `MAX_OPTIONS`; `SugList.item(sug, {action, prefix, reason, cls})`, `SugList.reasonText`; `useName(tr, raw)` works without a panel; `rxview.js?v=3`, `rxstate.js?v=3`, `rx.css?v=3`.
- **Produces:** check-row `options`, `total`; `SugList.PAGE = 8`, `SugList.page(items, index, total)`, `SugList.list(box, items, opts)`; `window.SpellModal = {init, open, close, closeFor, isOpenFor, say, setChecking, busy}`; `RxState.voiceError(e, phase)`; removed: the inline panel, `RxState.paneWidth`, `--rx-pane`, `.rx-spell-*` CSS. Tests: `tests/test_spell_options.py` (2), `tests/test_frontend_suglist.py` (2), `tests/test_frontend_spell_modal_dom.py` (4), `tests/test_frontend_spell_voice_dom.py` (4); ported: `tests/test_frontend_rxspell_dom.py` (12 -> 11), `tests/test_frontend_rxspell.py` (7 -> 6), `tests/test_formulary_usage.py:151-155` (re-pinned).

## Global Constraints
- Spell it opens only on `confirm`-state rows (`RxState.rowState(...).canSpell`, `frontend/rxstate.js:92`) and confirms only name questions (`afterSpell`, `:106-108`). Unchanged.
- Voice input is a name to check: it fills the field; only Use this sends it to check-row. No new provider: the clip goes where dictation goes (`/api/transcribe`, `api/stt.py:48-70`).
- DOM by `createElement`/`textContent` only. No `innerHTML` in `rxview.js`, `suglist.js`, `spellmodal.js`.
- Performance: `rowcheck.options` under 50 ms per call (measured parts: one spelling pass 12-18 ms; I1-r1's 1,000-name layer budget).
- Offline tests (node fakes for `getUserMedia`, `MediaRecorder`, the transcribe call). No commits.

## Decisions (and why)
1. **One modal, native `<dialog>`.** `index.html` holds `<dialog id="spellDlg" role="dialog" aria-modal="true" aria-labelledby="spellTitle" aria-describedby="spellHint">`, opened with `showModal()` (the page already uses that pattern: `frontend/app.js:163`, `letterhead.js:110`), with the attribute fallback when `showModal` is missing. `showModal` makes the page behind inert; the script still wraps Tab and Shift+Tab inside, so the trap does not depend on the browser.
2. **Paging on the page.** The server returns up to 40 options and the true `total` (counted up to 100, `rowcheck.POOL_ALL`); the page shows 8 at a time. One request per open, so the stale-answer rules stay simple. Measured: 300 one-vowel typos of lexicon spellings found at most 8 distinct spellings (median 2, 90th percentile 4), so most lists are one page; a long list comes from clinic names and brand spellings, and the cap note says "type more letters".
3. **Keys.** In the field: Enter = Use this with the typed text; ArrowDown = first name. In the list: ArrowUp / ArrowDown move, Enter or Space = Use this with that name. Anywhere in the dialog: PageDown / PageUp = next / previous page; Esc = close; Tab / Shift+Tab wrap.
4. **Close while a check runs.** Allowed. The row keeps its "Checking this medicine..." spinner (`rxview.js:76-78`) and the answer still lands, unless the row was edited, deleted or undone meanwhile (`r.req !== tok`, `:170`). Today Esc is refused while checking (`:208`); a 30-second lock in a modal is worse than a visible row spinner.
5. **Focus.** Open: the field. Close (Esc, Close button, edit or delete of the row): the row's Spell button; if that button is gone (the row was confirmed), the row's state box (`.rx-state`, as today after Use this, `:181`).
6. **Voice.** Up to 4 seconds (`VOICE_MS`), or tap again to stop. The transcript is tidied (`RxState.cleanTyped`: "c e t i r i z i n e" -> "cetirizine"; a trailing full stop dropped; 60 characters), put in the field, focused, and announced: `Heard "cetirizine". Check it, then press Use this.` The main dictation mic is refused while the modal records, and the modal mic is refused while dictation records, while the page is working or for a view-only prescription.
7. **One suggestion component.** The inline "Did you mean X?" (I2-a) and every modal row are built by `SugList.item`, so the generic line and the reason text cannot drift apart.

## Review Focus (inputs most likely to bite)
| Input | Expected | Pinned in |
|---|---|---|
| Tab from the last control / Shift+Tab from the field | Focus wraps inside the dialog | Task 3 test 1 |
| Esc, then Spell again on another row | Closed, focus back on the first row's Spell button; the second opens fresh | Task 3 test 1 |
| 20 options, PageDown twice, Next at the end | `Showing 17-20 of 20`, Next disabled | Task 3 test 2 |
| 60 found, 40 sent | `Showing 1-8 of 40 (60 found: type more letters to narrow them)` | Task 2 test 1 |
| A hostile name `<img src=x onerror=1>` | Text, never markup | Task 2 test 2 |
| Close during a pending Use this, then edit the row | The answer is dropped; no confirm | Task 3 test 3 |
| Mic denied / no device / no `MediaRecorder` / no sound / empty transcript / upload 500 / timeout | One sentence each, the field untouched | Task 4 test 2 |
| View-only, `state.working`, main dictation recording | Mic disabled, nothing recorded | Task 4 test 3 |
| A transcript that lands after Close or after another row's Spell | Dropped | Task 4 test 4 |
| 390 x 844 | Dialog inside the viewport, list items 44 px, no page scroll | Task 5 live check |

## File Structure and line budgets
| File | Change | Lines now (after I2-a) -> after (budget) |
|---|---|---|
| `doctor_dictation/api/rx.py` | `options`, `total` in the answer | 70 -> 72 |
| `frontend/suglist.js` | `PAGE`, `page`, `list` | about 40 -> about 60 |
| `frontend/spellmodal.js` | NEW | about 170 (<= 220) |
| `frontend/rxview.js` | panel code out, modal calls in | about 280 -> about 230 |
| `frontend/rxstate.js` | `paneWidth` out, `voiceError` in | about 175 -> about 175 |
| `frontend/rx.css` | `.rx-spell-*` out, `.spell-*` in | about 62 -> about 60 |
| `frontend/index.html`, `app.js` | the dialog, the script tag, `transcribeName`, wiring, `?v=` | +16, +22 |

---

### Task 1: The server sends the options and a total
**Files:** Modify `doctor_dictation/api/rx.py`; Create `tests/test_spell_options.py`.

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-c: check-row sends the Spell it list: a generic and a reason per name, capped at 40, with the total found."""
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation.core import rowcheck

def test_check_row_returns_options_with_a_generic_a_reason_and_a_total(frozen_lexicon):
    c = TestClient(M.app)
    j = c.post("/api/v1/rx/check-row", json={"row": {"name": "Citrizene", "strength": "10 mg"}, "transcript": "tab citrizene 10 mg at night"}).json()
    assert j["suggestions"] == ["Cetirizine", "Ceftriaxone"]                         # unchanged (I1-r1)
    assert j["options"] == [{"name": "Cetirizine", "generic": "Cetirizine", "reason": "sounds"},
                            {"name": "Ceftriaxone", "generic": "Ceftriaxone", "reason": "sounds"}] and j["total"] == 2
    p = c.post("/api/v1/rx/check-row", json={"row": {"name": "Prednisone", "strength": "10 mg"}, "transcript": "tab prednisone 10 mg"}).json()
    assert [(o["name"], o["reason"]) for o in p["options"][:2]] == [("Prednisone", "matched"), ("Prednisolone", "lookalike")]
    assert c.post("/api/v1/rx/check-row", json={"row": {"name": "x" * 61}}).status_code == 400   # the I1-d input rules stay

def test_options_are_capped_and_the_total_says_how_many_were_found(monkeypatch):
    monkeypatch.setattr(rowcheck, "scored_spellings", lambda name, k: [(f"Zorb{i:02d}x", f"Zorb{i:02d}x", 0.9) for i in range(60)][:k])
    opts, total = rowcheck.options({"name": "Zorbex", "lexicon_match": ""})
    assert (len(opts), total, opts[0]["name"], opts[-1]["name"]) == (40, 60, "Zorb00x", "Zorb39x")
    assert rowcheck.options({"name": "Zorbex", "lexicon_match": ""}, cap=8)[0][7]["name"] == "Zorb07x"
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_spell_options.py -q`. Expected: test 1 FAIL (`KeyError: 'options'`); test 2 passes once I2-a is in (it pins the I2-a cap; to see it guard, set `MAX_OPTIONS = 41`, see it fail, restore).
- [ ] **Step 3: `api/rx.py`.** Import `options` beside `ground_one, suggestions` and change `_ground` (`:47-51`):
```python
    grounded = ground_one(row, raw, normalized, age_sex)
    listed, total = options(grounded)
    return {"row": grounded, "suggestions": suggestions(grounded), "options": listed, "total": total}
```
- [ ] **Step 4: Run.** Run: `.venv/bin/python -m pytest tests/test_spell_options.py tests/test_rx_check_row.py tests/test_formulary_usage.py tests/test_isolation_routes.py -q`. Expected: all pass.
- [ ] **Step 5: Timing (once, not a test).** Time `rowcheck.options` for `Citrizene`, `Croissin`, `Prednisone`, `Pantop`, `Azithro` with an empty layer, then with `F.activate(F.ClinicLayer(tuple((f"Name{i:04d}x", "") for i in range(1000))))`. Expected median under 50 ms each; report the numbers; if slower, report and do not add a cache here.
- [ ] **Step 6: Leave uncommitted.**

---

### Task 2: Paging and the list in the shared component
**Files:** Modify `frontend/suglist.js`; Create `tests/test_frontend_suglist.py`.

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-c: SugList paging and the list, the one component behind the inline Did you mean and the Spell it modal."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"
FAKE = """class N { constructor(t) { this.tagName = t.toUpperCase(); this.children = []; this._t = ""; this.className = ""; this.dataset = {}; this.attrs = {}; }
  get textContent() { return this._t + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children = []; this._t = String(v); }
  appendChild(c) { this.children.push(c); return c; } append(...k) { k.forEach((c) => this.appendChild(c)); } setAttribute(k, v) { this.attrs[k] = String(v); } }
globalThis.document = { createElement: (t) => new N(t) };"""

def _node(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    js = "globalThis.window = globalThis;" + FAKE + "require(process.argv[1]); console.log(JSON.stringify(" + expr + "))"
    out = subprocess.run([node, "-e", js, str(FRONT / "suglist.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)

def test_paging_labels_and_bounds():
    got = _node("""(() => { const mk = (n) => Array.from({ length: n }, (_, i) => ({ name: "N" + (i + 1) }));
      const p = (n, i, t) => { const r = SugList.page(mk(n), i, t); return [r.label, r.items.map((s) => s.name).join(","), r.hasPrev, r.hasNext, r.index]; };
      return [p(0, 0, 0), p(3, 0, 3), p(20, 0, 20), p(20, 2, 20), p(20, 9, 20), p(20, -1, 20), p(40, 0, 60), SugList.PAGE]; })()""")
    assert got[0] == ["No close names found. Type the name.", "", False, False, 0]
    assert got[1] == ["Showing 1-3 of 3", "N1,N2,N3", False, False, 0]
    assert got[2] == ["Showing 1-8 of 20", "N1,N2,N3,N4,N5,N6,N7,N8", False, True, 0]
    assert got[3] == ["Showing 17-20 of 20", "N17,N18,N19,N20", True, False, 2]
    assert got[4] == got[3] and got[5] == got[2]                                   # out of range: clamped
    assert got[6][0] == "Showing 1-8 of 40 (60 found: type more letters to narrow them)" and got[7] == 8

def test_the_list_is_text_only_with_a_generic_and_a_reason_per_name():
    got = _node("""(() => { const box = document.createElement("div");
      SugList.list(box, [{ name: "Crocin", generic: "Paracetamol", reason: "sounds" }, { name: "<img src=x onerror=1>", generic: "", reason: "clinic" },
                         { name: "Prednisolone", generic: "Prednisolone", reason: "lookalike" }]);
      return box.children.map((b) => [b.dataset.action, b.dataset.value, b.className, b.children.map((c) => [c.className, c.textContent])]); })()""")
    assert got[0] == ["pick", "Crocin", "rx-act sug spell-item", [["sug-name", "Crocin"], ["sug-gen", "generic: Paracetamol"], ["sug-why", "sounds like"]]]
    assert got[1][1] == "<img src=x onerror=1>" and got[1][3] == [["sug-name", "<img src=x onerror=1>"], ["sug-why", "your clinic uses it"]]
    assert got[2][3] == [["sug-name", "Prednisolone"], ["sug-why", "looks alike: a different medicine"]]
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_frontend_suglist.py -q`. Expected: 2 FAIL (`SugList.page is not a function`).
- [ ] **Step 3: `frontend/suglist.js`.** Add inside the module and export `PAGE, page, list`:
```js
  const PAGE = 8;
  // items: the options in server order; index: the page asked for (clamped); total: names the server found (may exceed items)
  function page(items, index, total) {
    const n = items.length, pages = Math.max(1, Math.ceil(n / PAGE)), i = Math.min(Math.max(0, Math.floor(+index) || 0), pages - 1);
    const from = n ? i * PAGE + 1 : 0, to = Math.min(n, (i + 1) * PAGE), more = +total > n ? +total : 0;
    const label = !n ? "No close names found. Type the name." : "Showing " + from + "-" + to + " of " + n + (more ? " (" + more + " found: type more letters to narrow them)" : "");
    return { items: items.slice(from ? from - 1 : 0, to), index: i, pages, from, to, label, hasPrev: i > 0, hasNext: i < pages - 1 };
  }
  function list(box, items, o) {
    box.textContent = "";
    items.forEach((s) => box.appendChild(item(s, Object.assign({ action: "pick", reason: true, cls: "spell-item" }, o))));
    return box;
  }
```
`item` builds `className = "rx-act sug " + o.cls` (I2-a); the list passes `cls: "spell-item"`, so the class is `rx-act sug spell-item`.

- [ ] **Step 4: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_frontend_suglist.py tests/test_frontend_generic_dom.py -q`. Expected: all pass.

---

### Task 3: The modal replaces the inline panel
**Files:** Create `frontend/spellmodal.js`, `tests/test_frontend_spell_modal_dom.py`; Modify `frontend/rxview.js`, `frontend/rxstate.js`, `frontend/rx.css`, `frontend/index.html`, `frontend/app.js`, `tests/test_frontend_rxspell_dom.py`, `tests/test_frontend_rxspell.py`, `tests/test_formulary_usage.py:151-155`.

- [ ] **Step 1: Extend the fake DOM** in `tests/test_frontend_rxspell_dom.py`: append to `_DOM`, after the existing `RxView.init(...)` call (so `flags`, `posts` and `tick` exist), a dialog and its parts by id, dialog key and click helpers, and the modal's init with fakes the tests control. `_run` requires `spellmodal.js` after `rxview.js`.
```js
const dlg = new El("dialog"); dlg.open = false; dlg.showModal = function () { this.open = true; }; dlg.close = function () { this.open = false; };
ROOT_EL.appendChild(dlg); ids.spellDlg = dlg;
[["spellTitle", "h2"], ["spellHint", "p"], ["spellInput", "input"], ["spellMic", "button"], ["spellMsg", "p"], ["spellList", "div"],
 ["spellPrev", "button"], ["spellPage", "p"], ["spellNext", "button"], ["spellClose", "button"], ["spellUse", "button"]]
  .forEach(([id, tag]) => { const n = new El(tag); n.id = id; n.value = ""; ids[id] = n; dlg.appendChild(n); });
const dkey = (k, target, shift) => (dlg.handlers.keydown || []).forEach((f) => f({ target: target || document.activeElement, key: k, shiftKey: !!shift, preventDefault() {} }));
const dclick = (el) => (dlg.handlers.click || []).forEach((f) => f({ target: el }));
flags.recording = false; flags.mic = "ok"; flags.audio = ["a1"]; const voice = [], gum = [];
class FakeRec { constructor() { this.state = "inactive"; this.mimeType = "audio/webm"; FakeRec.last = this; }
  start() { this.state = "recording"; } stop() { this.state = "inactive"; flags.audio.forEach((d) => this.ondataavailable({ data: d })); this.onstop(); } }
const stream = { stopped: 0, getTracks: () => [{ stop() { stream.stopped++; } }] };
SpellModal.init({ dialog: dlg, working: () => flags.working, recording: () => flags.recording,
  viewOnly: () => !!(globalThis.Authorship && Authorship.isViewOnly()), voiceMs: 0,
  media: () => ({ getUserMedia: () => { gum.push(1); return flags.mic === "ok" ? Promise.resolve(stream) : Promise.reject({ name: flags.mic }); } }),
  Recorder: () => (flags.noRecorder ? undefined : FakeRec), transcribe: (blob) => new Promise((res, rej) => voice.push({ blob, res, rej })) });
const reply = async (row, sugs, opts, total) => { posts.shift().res({ row, suggestions: sugs || [], options: opts || (sugs || []).map((n) => ({ name: n, generic: "", reason: "sounds" })), total }); await tick(); };
const openPanel = async (tr) => { click(spellBtn(tr)); await reply({}, ["Allopurinol"]); };
const useTyped = async (text) => { ids.spellInput.value = text; dclick(ids.spellUse); await tick(); };
const panels = () => (dlg.open ? 1 : 0);
```
(These replace the old `reply`, `openPanel`, `useTyped` and `panels` helpers; delete the old ones. `El` gains `this.id = ""` in its constructor. `Blob` is a global in node 18+.)

- [ ] **Step 2: Port the old Spell it DOM tests** in `tests/test_frontend_rxspell_dom.py` with these substitutions only, so each keeps its assertions: `tbody.querySelector("tr.rx-spell-row").querySelector("input")` -> `ids.spellInput`; `click(tbody.querySelector('[data-action="use"]'))` -> `dclick(ids.spellUse)`; `key(input, "Enter")` -> `dkey("Enter", ids.spellInput)`; `big._rx.panel.querySelector(".rx-msg").textContent` -> `ids.spellMsg.textContent`; `held: tr._rx.panel` -> `held: SpellModal.isOpenFor("2")` (expect `False` instead of `None`). DELETE `test_the_panel_box_is_sized_to_the_scroller_content_and_follows_its_width` (no panel, no pane width): 12 -> 11 tests. In `tests/test_frontend_rxspell.py` DELETE `test_the_pane_width_comes_from_the_element_that_scrolls_minus_its_padding` (7 -> 6), change the tokens of `test_the_panel_follows_the_spell_it_contract` to the modal (`'"/api/v1/rx/check-row"'`, `"SpellModal.open("`, `"r.req !== tok"`, `'H.pushUndo({ type: "respell"'`, `"H.transcript()"`, `"H.ageSex()"`, `'setAttribute("aria-haspopup", "dialog")'`) and its export line to `return { init, attach, renderRow, sync, onEdit, meta, wire, reasonFor, restore, isBlank };` (unchanged), and rename `test_the_spell_panel_stays_in_the_visible_pane_and_its_buttons_wrap` to `test_the_spell_modal_fits_a_phone_and_its_targets_are_44px`, asserting in `rx.css`: `dialog.spell-dlg { width:min(560px, calc(100vw - 32px)); max-height:calc(100vh - 32px); overflow:auto; }`, `.spell-item { min-height:44px; width:100%; }`, and `.spell-line { display:flex; flex-wrap:wrap; gap:8px; }`; and that `rx.css` no longer contains `rx-spell-box` or `--rx-pane`. In `tests/test_formulary_usage.py:151-155` (`test_the_page_shows_the_suggestions_in_the_order_the_server_sends`) re-pin the order rule on the new code: `line = next(t for t in modal.splitlines() if "res.options" in t)`, `".sort(" not in line and ".reverse(" not in line`, and `"SugList.page(" in modal`.
- [ ] **Step 3: Write the new failing tests** `tests/test_frontend_spell_modal_dom.py`:
```python
"""Plan I2-c: the Spell it modal: an accessible dialog, paging and keys, close while checking, one shared item builder."""
from pathlib import Path

from test_frontend_rxspell_dom import _run

HTML = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")

def test_the_modal_is_a_labelled_dialog_that_keeps_focus_and_gives_it_back():
    tag = HTML[HTML.index('<dialog id="spellDlg"'):].split(">", 1)[0]
    assert all(a in tag for a in ('role="dialog"', 'aria-modal="true"', 'aria-labelledby="spellTitle"', 'aria-describedby="spellHint"'))
    r = _run("""
      const tr = mkRow("m1", "unknown-medicine", { name: "Zyloprim" });
      await openPanel(tr);
      const opened = [panels(), ids.spellTitle.textContent, document.activeElement === ids.spellInput, spellBtn(tr).attrs["aria-expanded"]];
      ids.spellUse.focus(); dkey("Tab"); const wrapped = document.activeElement === ids.spellInput;
      dkey("Tab", ids.spellInput, true); const back = document.activeElement === ids.spellUse;
      dkey("Escape"); const closed = [panels(), document.activeElement === spellBtn(tr), spellBtn(tr).attrs["aria-expanded"]];
      console.log(JSON.stringify({ opened, wrapped, back, closed }));""")
    assert r == {"opened": [1, "Spell Zyloprim", True, "true"], "wrapped": True, "back": True, "closed": [0, True, "false"]}

def test_paging_with_keys_and_buttons_and_enter_uses_the_focused_name():
    r = _run("""
      const tr = mkRow("m2", "unknown-medicine", { name: "Zorbex" });
      click(spellBtn(tr));
      await reply({}, [], Array.from({ length: 20 }, (_, i) => ({ name: "Zorb" + (i + 1), generic: "", reason: "sounds" })), 20);
      const p1 = [ids.spellPage.textContent, ids.spellList.children.length, ids.spellPrev.disabled];
      dkey("PageDown"); dkey("PageDown"); const p3 = [ids.spellPage.textContent, ids.spellNext.disabled];
      dkey("PageUp"); const p2 = ids.spellPage.textContent;
      dkey("ArrowDown", ids.spellInput); const first = document.activeElement.dataset.value;
      dkey("ArrowDown"); const second = document.activeElement.dataset.value;
      dkey("Enter"); await tick();
      console.log(JSON.stringify({ p1, p3, p2, first, second, sent: posts[0].body.row.name, checking: tr._rx.checking }));""")
    assert r["p1"] == ["Showing 1-8 of 20", 8, True] and r["p3"] == ["Showing 17-20 of 20", True] and r["p2"] == "Showing 9-16 of 20"
    assert (r["first"], r["second"], r["sent"], r["checking"]) == ("Zorb9", "Zorb10", "Zorb10", True)

def test_close_while_checking_keeps_the_row_spinner_and_an_edit_still_drops_the_answer():
    r = _run("""
      const a = mkRow("m3", "lookalike-check", { name: "Prednisone" });
      await openPanel(a); await useTyped("Prednisolone");
      dclick(ids.spellClose); const during = [panels(), !!a.querySelector(".rx-checking")];
      await reply({ name: "Prednisolone", status: "verified", lexicon_match: "Prednisolone" });
      const landed = [confirmed.has("m3"), a._rx.how, cell(a, "name").textContent];
      const b = mkRow("m4", "lookalike-check", { name: "Prednisone" });
      await openPanel(b); await useTyped("Prednisolone"); dclick(ids.spellClose);
      RxView.onEdit(b, cell(b, "dose")); RxView.renderRow(b);
      await reply({ name: "Prednisolone", status: "verified" });
      console.log(JSON.stringify({ during, landed, dropped: [confirmed.has("m4"), cell(b, "name").textContent, b._rx.checking] }));""")
    assert r == {"during": [0, True], "landed": [True, "spell", "Prednisolone"], "dropped": [False, "Prednisone", False]}

def test_the_inline_suggestion_and_the_modal_list_are_built_by_one_component():
    r = _run("""
      const tr = mkRow("m5", "unknown-medicine", { name: "Croissin" }, { did_you_mean: "Crocin", did_you_mean_generic: "Paracetamol" });
      const inline = tr.querySelector('[data-action="dym"]');
      click(spellBtn(tr)); await reply({}, [], [{ name: "Crocin", generic: "Paracetamol", reason: "sounds" }], 1);
      const item = ids.spellList.children[0];
      const parts = (b) => b.children.map((c) => [c.className, c.textContent]);
      console.log(JSON.stringify({ inline: [inline.className, parts(inline)], item: [item.className, parts(item)] }));""")
    assert r["inline"] == ["rx-act sug ", [["sug-name", "Did you mean Crocin?"], ["sug-gen", "generic: Paracetamol"]]]
    assert r["item"] == ["rx-act sug spell-item", [["sug-name", "Crocin"], ["sug-gen", "generic: Paracetamol"], ["sug-why", "sounds like"]]]
```
- [ ] **Step 4: Run them.** Run: `.venv/bin/python -m pytest tests/test_frontend_spell_modal_dom.py tests/test_frontend_rxspell_dom.py -q`. Expected: FAIL (`Cannot find module .../spellmodal.js`).
- [ ] **Step 5: `frontend/index.html`.** Before the scripts add the dialog; add `<script src="spellmodal.js?v=1"></script>` after `rxview.js`; bump `rxview.js?v=4`, `rxstate.js?v=4`, `rx.css?v=4`, `app.js` by one (update the pins in `tests/test_frontend_rxspell.py`).
```html
<dialog id="spellDlg" class="panel spell-dlg no-print" role="dialog" aria-modal="true" aria-labelledby="spellTitle" aria-describedby="spellHint">
  <div class="spell-wrap"><h2 id="spellTitle">Spell the medicine</h2><p id="spellHint" class="panel-hint">Only this row changes. Pick a name, type it, or say it.</p>
    <div class="spell-line"><input id="spellInput" type="text" maxlength="60" autocomplete="off" spellcheck="false" aria-label="Medicine name" placeholder="p r e d n i s o l o n e">
      <button id="spellMic" type="button" class="rx-act" aria-pressed="false" aria-label="Say the name">Say it</button></div>
    <p id="spellMsg" class="rx-msg" role="alert"></p><div id="spellList" class="spell-list" role="group" aria-label="Did you mean"></div>
    <div class="spell-pager"><button id="spellPrev" type="button" class="rx-act">Previous</button><p id="spellPage" role="status" aria-live="polite"></p><button id="spellNext" type="button" class="rx-act">Next</button></div>
    <div class="panel-actions"><button id="spellClose" type="button">Close</button><button id="spellUse" type="button" class="primary">Use this</button></div></div>
</dialog>
```
- [ ] **Step 6: Create `frontend/spellmodal.js`** (an IIFE, `"use strict"`, `window.SpellModal`; a header comment says the row rules stay in `rxview.js`). State: `let H = null, cur = null, rec = null, tok = 0;` (`rec` is the voice recorder of Task 4). The parts with rules:
```js
  const micAllowed = () => !H.working() && !H.viewOnly() && !H.recording();
  function open(spec) {                                // spec: {rowid, title, opener, problem, load(), use(name), onClose()}
    if (cur) close(false);
    cur = Object.assign({ items: [], total: 0, page: 0, loading: !spec.problem, checking: false, tok: ++tok }, spec);
    $("spellTitle").textContent = spec.title; $("spellInput").value = ""; say(spec.problem || "");
    if (spec.opener) spec.opener.setAttribute("aria-expanded", "true");
    if (typeof H.dialog.showModal === "function") H.dialog.showModal(); else H.dialog.setAttribute("open", "");
    show(); $("spellInput").focus();
    if (spec.problem) return;
    const mine = cur.tok;
    spec.load().then((res) => {
      if (!cur || cur.tok !== mine) return;          // closed, or another row opened: drop it
      const opts = Array.isArray(res && res.options) ? res.options : (Array.isArray(res && res.suggestions) ? res.suggestions.map((n) => ({ name: String(n), generic: "", reason: "" })) : []);
      cur.items = opts.filter((o) => o && typeof o.name === "string" && o.name); cur.total = +(res && res.total) || cur.items.length; cur.loading = false; show();
    }).catch((e) => { if (cur && cur.tok === mine) { cur.loading = false; show(); say(RxState.errorText(e) + " You can still type the name."); } });
  }
  function onKey(e) {
    if (!cur) return;
    const items = [...$("spellList").children], i = items.indexOf(e.target);
    if (e.key === "Escape") { e.preventDefault(); close(true); }
    else if (e.key in PAGE_KEYS) { e.preventDefault(); cur.page += PAGE_KEYS[e.key]; show(); }          // { PageDown: 1, PageUp: -1 }
    else if (e.key === "Tab") {
      const f = focusables(), at = f.indexOf(document.activeElement);
      if (e.shiftKey && at <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && at === f.length - 1) { e.preventDefault(); f[0].focus(); }
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!items.length || (i < 0 && e.target !== $("spellInput"))) return;
      e.preventDefault(); items[i < 0 ? 0 : Math.min(items.length - 1, Math.max(0, i + (e.key === "ArrowDown" ? 1 : -1)))].focus();
    } else if (e.key === "Enter" && e.target === $("spellInput")) { e.preventDefault(); use($("spellInput").value); }
    else if ((e.key === "Enter" || e.key === " ") && i >= 0) { e.preventDefault(); use(items[i].dataset.value); }
  }
```
  The rest, each a few lines: `say(m)` sets `#spellMsg`; `focusables()` is `[spellInput, spellMic, ...list items, spellPrev, spellNext, spellClose, spellUse]` without disabled or hidden ones; `show()` renders `SugList.page(cur.items, cur.page, cur.total)` through `SugList.list`, writes the label (or `Looking for names...` while loading) to `#spellPage`, and disables Previous/Next at the ends and every button while `cur.checking` (the mic also when `!micAllowed()`); `close(refocus)` clears `cur`, calls `stopVoice()`, closes the dialog (or removes `open`), sets the opener's `aria-expanded="false"` and, with `refocus`, calls `spec.onClose()`; `isOpenFor(rowid)`, `closeFor(rowid, refocus)`, `setChecking(rowid, on)`; `use(name)` calls `cur.use(name)` unless checking; `onClick` maps `spellClose`, `spellUse`, `spellPrev`/`spellNext`, `spellMic` (`toggleVoice`) and `data-action="pick"` buttons, ignoring disabled ones; `init(hooks)` stores `H` (default `voiceMs: 4000`) and binds `keydown`, `click` and `cancel` (the browser's own Esc: `preventDefault` then `close(true)`) on the dialog. `stopVoice` and `toggleVoice` are empty until Task 4. Export `{ init, open, close, closeFor, isOpenFor, setChecking, say: (rowid, m) => { if (isOpenFor(rowid)) say(m); }, busy: () => !!rec }`.
- [ ] **Step 7: Rewire `frontend/rxview.js`.** Delete the panel code: `closePanel`, `say`, `busy`, the body of `openSpell`, the `r.panel` field (`fresh`), the panel lines in `renderRow` (`:47`), `sync` (`:93`), `onEdit` (`:241`), `restore` (`:248`), `onKey` and the `keydown` binding, `paneWidth` and the `--rx-pane` lines (`:224`, `:226-234`). Keep `useName`'s rules as they are (I2-a version). Then:
```js
  function openSpell(tr) {
    if (H.working() || viewOnly()) return;
    const rowid = tr.dataset.rowid, dictated = val(tr, "name"), opener = tr.querySelector('[data-action="spell"]');
    SpellModal.open({ rowid, title: "Spell " + (dictated || "medicine"), opener,
      problem: tooBig(dictated) ? RxState.typedProblem(dictated) + " You can still type the name." : "",
      load: () => H.post(URL_CHECK, bodyFor(tr), CHECK_MS), use: (name) => useName(tr, name),
      onClose: () => { const t = tr.querySelector('[data-action="spell"]') || tr.querySelector(".rx-state"); if (t) t.focus(); } });
  }
```
In `useName`: where it wrote to the panel it now calls `SpellModal.say(rowid, msg)` (and still sets `r.note` when the modal is not open for that row); `SpellModal.setChecking(rowid, true)` when the request starts and `false` in `fail`; on success `SpellModal.closeFor(rowid, false)` before `focusState(tr)`. `renderRow`: the Spell button gets `aria-haspopup="dialog"`, `aria-controls="spellDlg"` and `aria-expanded = String(SpellModal.isOpenFor(rowid))`; `if (SpellModal.isOpenFor(rowid) && !r.checking && !st.canSpell) SpellModal.closeFor(rowid, false);`. `onEdit` and `restore` call `SpellModal.closeFor(tr.dataset.rowid, false)`; `sync` closes the modal when its row is no longer connected. `rxstate.js`: delete `paneWidth` and its export.
- [ ] **Step 8: CSS and app.js.** `rx.css`: delete `:49-57` (`.rx-spell-*`, `#sheet.view-only .rx-spell-row`); add `dialog.spell-dlg { width:min(560px, calc(100vw - 32px)); max-height:calc(100vh - 32px); overflow:auto; }`, `.spell-wrap { padding:16px; display:flex; flex-direction:column; gap:10px; }`, `.spell-line { display:flex; flex-wrap:wrap; gap:8px; }`, `.spell-line input { font:inherit; min-height:44px; flex:1 1 200px; padding:0 12px; border:1px solid #9aa8a1; border-radius:8px; }`, `.spell-list { display:flex; flex-direction:column; gap:6px; }`, `.spell-item { min-height:44px; width:100%; justify-content:flex-start; flex-wrap:wrap; text-align:left; }`, `.spell-pager { display:flex; align-items:center; justify-content:space-between; gap:8px; }`, `.spell-item:focus-visible, .spell-dlg button:focus-visible, .spell-line input:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }`. `app.js` init block (`:1211`): `SpellModal.init({ dialog: $("spellDlg"), working: () => state.working, recording: () => !!(mr && mr.state === "recording"), viewOnly: () => !!(window.Authorship && Authorship.isViewOnly()), transcribe: transcribeName, media: () => navigator.mediaDevices, Recorder: () => window.MediaRecorder });` (`transcribeName` comes in Task 4; until then pass `transcribe: () => Promise.reject(new Error("later"))`).
- [ ] **Step 9: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_frontend_spell_modal_dom.py tests/test_frontend_rxspell_dom.py tests/test_frontend_rxspell.py tests/test_frontend_generic_dom.py tests/test_formulary_usage.py tests/test_frontend_rxrow.py -q`. Expected: all pass (modal 4, rxspell_dom 11, rxspell 6).

---

### Task 4: Voice input in the modal
**Files:** Modify `frontend/spellmodal.js` (the two voice functions), `frontend/rxstate.js` (`voiceError`), `frontend/app.js` (`transcribeName`, the mic guard); Create `tests/test_frontend_spell_voice_dom.py`.

- [ ] **Step 1: Write the failing tests.**
```python
"""Plan I2-c: the modal's microphone: record a few seconds, the existing /api/transcribe route, fill the field, never apply."""
from test_frontend_rxspell_dom import _run

OPEN = """const tr = mkRow("v1", "unknown-medicine", { name: "Citrizene" }); await openPanel(tr); const loads = posts.length;"""

def test_voice_fills_the_field_and_never_applies_it():
    r = _run(OPEN + """
      dclick(ids.spellMic); await tick(); const listening = [ids.spellMic.attrs["aria-pressed"], ids.spellMsg.textContent, SpellModal.busy()];
      dclick(ids.spellMic); await tick();                                       // stop: the clip goes to the transcribe hook
      const sent = [voice.length, voice[0].blob instanceof Blob, stream.stopped];
      voice[0].res("C e t i r i z i n e."); await tick();
      console.log(JSON.stringify({ listening, sent, field: ids.spellInput.value, msg: ids.spellMsg.textContent,
        focus: document.activeElement === ids.spellInput, checks: posts.length - loads, row: cell(tr, "name").textContent, busy: SpellModal.busy() }));""")
    assert r["listening"] == ["true", "Listening... tap Say it again to stop.", True] and r["sent"] == [1, True, 1]
    assert (r["field"], r["msg"]) == ("Cetirizine", 'Heard "Cetirizine". Check it, then press Use this.')
    assert (r["focus"], r["checks"], r["row"], r["busy"]) == (True, 0, "Citrizene", False)     # nothing sent to check-row, row unchanged

def test_each_voice_failure_is_one_sentence_and_the_field_is_untouched():
    r = _run(OPEN + """
      const out = [];
      const tryMic = async (setup, finish) => { ids.spellInput.value = "typed"; setup(); dclick(ids.spellMic); await tick();
        if (FakeRec.last && FakeRec.last.state === "recording") { dclick(ids.spellMic); await tick(); }
        if (finish) { finish(voice[voice.length - 1]); await tick(); }
        out.push([ids.spellMsg.textContent, ids.spellInput.value]); flags.mic = "ok"; flags.noRecorder = false; flags.audio = ["a1"]; FakeRec.last = null; };
      await tryMic(() => { flags.mic = "NotAllowedError"; });
      await tryMic(() => { flags.mic = "NotFoundError"; });
      await tryMic(() => { flags.noRecorder = true; });
      await tryMic(() => { flags.audio = []; });
      await tryMic(() => {}, (v) => v.res("  "));
      await tryMic(() => {}, (v) => { const e = new Error("boom"); e.status = 500; v.rej(e); });
      await tryMic(() => {}, (v) => v.rej({ aborted: true }));
      console.log(JSON.stringify(out));""")
    assert r == [["The microphone is blocked. Allow it in the browser, or type the name.", "typed"],
                 ["No microphone was found. Type the name.", "typed"],
                 ["Voice input is not supported in this browser. Type the name.", "typed"],
                 ["No sound was recorded. Try again, or type the name.", "typed"],
                 ["No name was heard. Try again, or type the name.", "typed"],
                 ["The server answered 500 (boom). Type the name instead.", "typed"],
                 ["Reading the name took too long. Type the name instead.", "typed"]]

def test_the_mic_is_off_for_view_only_while_working_and_while_dictation_records():
    r = _run(OPEN + """
      const out = [];
      for (const [k, v] of [["vo", true], ["working", true], ["recording", true]]) {
        if (k === "vo") globalThis.Authorship = { isViewOnly: () => true }; else flags[k] = v;
        SpellModal.setChecking("v1", false); dclick(ids.spellMic); await tick();
        out.push([k, ids.spellMic.disabled, gum.length]);
        globalThis.Authorship = undefined; flags.working = false; flags.recording = false;
      }
      console.log(JSON.stringify(out));""")
    assert r == [["vo", True, 0], ["working", True, 0], ["recording", True, 0]]

def test_a_late_transcript_after_close_or_another_row_is_dropped():
    r = _run(OPEN + """
      dclick(ids.spellMic); await tick(); dclick(ids.spellClose);                 // Close while recording: the mic is released
      const stopped = [FakeRec.last.state, stream.stopped, SpellModal.busy(), voice.length];
      await openPanel(tr); dclick(ids.spellMic); await tick(); dclick(ids.spellMic); await tick();   // a clip is sent, its answer pending
      dclick(ids.spellClose); const t2 = mkRow("v2", "unknown-medicine", { name: "Croissin" }); await openPanel(t2);
      voice[0].res("cetirizine"); await tick();
      console.log(JSON.stringify({ stopped, field: ids.spellInput.value, msg: ids.spellMsg.textContent, title: ids.spellTitle.textContent }));""")
    assert r == {"stopped": ["inactive", 1, False, 0], "field": "", "msg": "", "title": "Spell Croissin"}
```
- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_frontend_spell_voice_dom.py -q`. Expected: 4 FAIL (the voice stubs do nothing).
- [ ] **Step 3: `RxState.voiceError`** (`frontend/rxstate.js`, exported):
```js
  // One sentence for a failed voice capture; phase "mic" (getUserMedia, recorder, the clip) or "upload" (the transcribe call).
  function voiceError(e, phase) {
    const n = str(e && e.name), k = str(e && e.kind);
    if (n === "NotAllowedError" || n === "SecurityError") return "The microphone is blocked. Allow it in the browser, or type the name.";
    if (n === "NotFoundError" || n === "OverconstrainedError") return "No microphone was found. Type the name.";
    if (k === "no-recorder") return "Voice input is not supported in this browser. Type the name.";
    if (k === "no-audio") return "No sound was recorded. Try again, or type the name.";
    if (k === "no-speech") return "No name was heard. Try again, or type the name.";
    if (e && e.aborted) return "Reading the name took too long. Type the name instead.";
    if (phase === "upload") return errorText(e).replace(/\.$/, "") + ". Type the name instead.";
    return "The microphone could not start. Type the name.";
  }
```
- [ ] **Step 4: The voice functions** in `spellmodal.js` (replace the two stubs; add `let stream = null, timer = null, chunks = [];` beside `rec`):
```js
  function stopVoice() {                               // close, or another open: stop recording and release the mic
    if (timer) { clearTimeout(timer); timer = null; }
    const r = rec; rec = null;
    if (r && r.state === "recording") { r.onstop = () => {}; r.stop(); }
    if (stream) { stream.getTracks().forEach((t) => t.stop()); stream = null; }
    if ($("spellMic")) $("spellMic").setAttribute("aria-pressed", "false");
  }
  async function toggleVoice() {
    if (!cur || cur.checking || !micAllowed()) return;
    if (rec) { if (rec.state === "recording") rec.stop(); return; }
    const mine = cur.tok;
    try { stream = await H.media().getUserMedia({ audio: true }); }
    catch (e) { if (cur && cur.tok === mine) say(RxState.voiceError(e, "mic")); return; }
    if (!cur || cur.tok !== mine) { stopVoice(); return; }
    const R = H.Recorder();
    if (!R) { stopVoice(); say(RxState.voiceError({ kind: "no-recorder" }, "mic")); return; }
    chunks = []; rec = new R(stream);
    rec.ondataavailable = (ev) => { if (ev.data) chunks.push(ev.data); };
    rec.onstop = async () => {
      const type = rec && rec.mimeType; stopVoice();
      if (!cur || cur.tok !== mine) return;
      if (!chunks.length) { say(RxState.voiceError({ kind: "no-audio" }, "mic")); return; }
      say("Reading the name...");
      let text;
      try { text = await H.transcribe(new Blob(chunks, { type: type || "audio/webm" })); }
      catch (e) { if (cur && cur.tok === mine) say(RxState.voiceError(e, "upload")); return; }
      if (!cur || cur.tok !== mine) return;              // closed, or another row opened: drop it
      const name = RxState.cleanTyped(String(text || "").replace(/[.?!,;:]+$/, "")).slice(0, 60);
      if (!name) { say(RxState.voiceError({ kind: "no-speech" }, "upload")); return; }
      $("spellInput").value = name; $("spellInput").focus(); say('Heard "' + name + '". Check it, then press Use this.');
    };
    rec.start(); $("spellMic").setAttribute("aria-pressed", "true"); say("Listening... tap Say it again to stop.");
    if (H.voiceMs > 0) timer = setTimeout(() => { if (rec && rec.state === "recording") rec.stop(); }, H.voiceMs);
  }
```
`RxState.cleanTyped("C e t i r i z i n e")` joins the letters to `Cetirizine` (`frontend/rxstate.js:111-114`). The test harness sets `voiceMs: 0`, so no timer runs there.
- [ ] **Step 5: `frontend/app.js`.** Add after `transcribe` (`:480-503`) and pass it as `transcribe: transcribeName` in `SpellModal.init`; in the mic handler (`:342-346`) refuse while the modal records: `if (state.working || (window.SpellModal && SpellModal.busy())) return;`.
```js
// Spell it voice input (plan I2-c): the same route as dictation, a short timeout, no page-wide "working" state.
async function transcribeName(blob) {
  const fd = new FormData(); fd.append("audio", blob, "name.webm");
  const ctrl = new AbortController(), to = setTimeout(() => ctrl.abort(), 20000);
  try {
    const r = await fetch("/api/transcribe", { method: "POST", body: fd, signal: ctrl.signal }), j = await safeJson(r);
    if (!r.ok) { const err = new Error(j.hint || j.error || ""); err.status = r.status; throw err; }
    return String(j.transcript || "").trim();
  } catch (e) { if (e && e.name === "AbortError") { const err = new Error("timed out"); err.aborted = true; throw err; } throw e; }
  finally { clearTimeout(to); }
}
```
- [ ] **Step 6: Run, then leave uncommitted.** Run: `.venv/bin/python -m pytest tests/test_frontend_spell_voice_dom.py tests/test_frontend_spell_modal_dom.py tests/test_frontend_rxspell_dom.py tests/test_frontend_rxspell.py -q`. Expected: all pass.

---

### Task 5: Mutations, whole suite, live browser check
- [ ] **Step 1: Mutations** (apply alone, run the named file, see a failure, revert):

| # | Mutation | Must fail |
|---|---|---|
| M1 | `_ground` without `options` / `total` | `test_spell_options.py` 1 |
| M2 | `PAGE = 10` / no clamp in `page` | `test_frontend_suglist.py` 1 |
| M3 | `item` uses `innerHTML` | `test_frontend_suglist.py` 2 |
| M4 | no Tab wrap / Esc without `close(true)` | modal test 1 |
| M5 | PageDown ignored / ArrowDown from the field ignored | modal test 2 |
| M6 | `useName` drops the `r.req !== tok` check | modal test 3, rxspell_dom tests |
| M7 | the inline button built without `SugList.item` | modal test 4 |
| M8 | voice applies the name (calls `use`) | voice test 1 (`checks` 1) |
| M9 | `voiceError` maps NotFoundError like NotAllowedError | voice test 2 |
| M10 | `micAllowed` ignores `H.recording()` | voice test 3 |
| M11 | `onstop` without the `cur.tok !== mine` check | voice test 4 |
| M12 | `.sort()` on `res.options` | `test_formulary_usage.py:151-155` |

- [ ] **Step 2: Whole suite.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: the count measured before Task 1 plus 10: **1734 passed, 1 skipped** after I2-a and I2-b, or **1718** after I2-a only.
- [ ] **Step 3: Live browser check** (separate server on 8801, temp `DB_PATH`, blank keys, `ALLOW_STUB_PROVIDERS=1 STT_ENGINE=stub STUB_TRANSCRIPT='c e t i r i z i n e'`; never port 8000). Author the sheet with `formatTranscript("tab citrizene 10 mg at night. tab prednisone 10 mg twice daily")` through `browser_evaluate`. Then: open Spell it on Citrizene with the keyboard (Tab to it, Enter); check the title, the focus in the field, Tab cycling, Esc returning focus to the same Spell button. On Prednisone: the list shows Prednisone ("in the medicine list") and Prednisolone ("looks alike: a different medicine"). Voice: if the browser offers a fake microphone, press Say it twice and expect the field `cetirizine` and the "Heard" message, with the row unchanged until Use this; without one, expect the blocked-microphone sentence. Resize to 390 x 844: the dialog fits, items are full width and at least 44 px tall, no page scroll. Console: no errors. Stop the server, `lsof -i :8801` empty, delete the scratch folder; commit nothing; no secrets.
- [ ] **Step 4: Leave uncommitted.** Changed files: the File Structure table and the seven test files named in Produces.

## Regression list (must stay green)
I1-e3 race rules (all 11 ported tests in `tests/test_frontend_rxspell_dom.py`: undo during a pending check, late failure after undo, confirm from outside, view-only and working guards, name-only confirm, hand edit during a check, delete and undo, undo keeps a later dose edit, chip on view-only); Save gate (`tests/test_safety.py`); check-row input rules (`tests/test_rx_check_row.py`); I1-r1 order (`tests/test_formulary_usage.py`); the main dictation flow (`tests/test_frontend_steps.py`); print (the dialog is `no-print`).

## Self-Review
- D4: modal and a11y (Task 3), pagination with a cap and a total (Tasks 1-2), keyboard (Task 3), phone layout (Task 3 CSS, Task 5), voice with every failure (Task 4), race rules (ported tests), one list component (Task 3 test 4). Name questions only: unchanged `canSpell`/`afterSpell`.
- Test count: 2 + 2 + (4 - 1 - 1) + 4 = 10.
- Out of scope: spelling letter by letter as a separate mode ("Say the letters (later)" goes away; voice covers it); suggestions from the A3 list (backlog (l)); arrow keys in the Team tabs (backlog (h)).

**Decision needed:** none beyond the index defaults; run after I2-a.
