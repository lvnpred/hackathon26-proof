# I1-f: Steppers (Dictation, Profile, Letterhead)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three coarse dictation steps with four steps the page really knows, and add a Profile stepper (Clinic, My details, Letterhead) and a Letterhead stepper (Upload, Reading, Review, Accept), without changing what any of those screens does.

**Architecture:** New `frontend/steps.js` holds the stage rules (`window.StepsLogic`, pure, tested under node) and the DOM painters (`window.Steps`). `app.js` keeps one `setStep(stage, info)` that delegates; the Profile and Letterhead steppers only watch DOM state that `letterhead.js` already produces (hidden flags, `aria-busy`, labels), so `letterhead.js` is not edited. The visual polish from the canvas is plan I1-f2 (split to keep each plan under 500 lines).

**Tech Stack:** vanilla JS, CSS, pytest + node, Playwright MCP tools.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` "Iteration 1" section 6; contracts `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` fact 7; canvas boards `States.dc.html` and `Profile.dc.html` (visual reference only).

**Assumptions about earlier plans:** I1-e, I1-e2 and I1-e3 are applied (`app.js` calls `RxView.*`; `app.js?v=28`; `index.html` links `rx.css?v=2`). Nothing else is needed.

## Global Constraints

- No `git commit` or `git push`; finish with the changed-file list. Baseline first: `.venv/bin/python -m pytest tests/ -q`, note the count, expect count + 8 at the end.
- The truth rule (`app.js:91`, "coarse, truthful steps"): never show a stage as active that the page cannot know is active.
- No percentage anywhere: letterhead reading is one request (`letterhead.js` `upload()`, one `call()` with a 120 s timeout).
- `letterhead.js` is not edited; `tests/test_frontend_letterhead.py` and `tests/test_frontend_authorship.py` keep their assertions.
- DOM is built with `createElement`/`textContent`; state is a number or icon plus a hidden word ("done", "in progress", "problem"), never colour alone; no animation in this plan; targets are 44px.
- Browser checks use `DB_PATH` on a temp file (memory note "Single mode writes the real dev DB").

## Review Focus

- A failed transcription must mark Transcribing as the problem, not Structuring, and a failed `/api/format` must leave Listening and Transcribing done: `test_a_failure_marks_only...`.
- A reopened saved prescription must not claim it was just heard or transcribed: stage `opened` (`na` steps), same test.
- Discarding a draft or saving clinic details shows a "done" message in the Letterhead panel; it must not mark Accept as done: `test_the_letterhead_steps_follow...` (the message prefix `Done.` belongs to accept only; `test_the_words_the_steppers_read...` pins it).
- Cancelling during Reading must not leave the panel stuck busy: the Cancel link only clicks the existing Close button, whose handler aborts the request (`letterhead.js:358`).
- The review line must follow the count as the doctor resolves rows (`Steps.needs`), manual step 4.

## What the page can know (the evidence, and the change from the canvas)

| Canvas step | Known by the page? | Evidence | Decision |
|---|---|---|---|
| Listening | Yes: `MediaRecorder` runs between `setStep("listening")` (`app.js:398`) and stop | local state | keep |
| Transcribing | Yes: exactly while `fetch("/api/transcribe")` is in flight (`app.js:504`) | one request, resolves with the whole transcript | keep |
| Structuring + Checking medicines | **No separate signal.** `/api/format` is one request that extracts, grounds and repairs (`doctor_dictation/api/format.py:1`, `format_transcript` at `:81`); the response is not streamed (no `StreamingResponse`/`EventSource` anywhere in `doctor_dictation/` or `frontend/`) | the page sees only "request sent" and "answer came back" | **merge into one step "Structuring and checking"**, active while `/api/format` (or `/api/v1/correct`, `app.js:564`) is in flight |
| Your review | Yes: after the answer is rendered; the count comes from `openRows()` | local state | keep, with the live "N need you" line |

So the main progress has **four** steps, not five. Sub-texts only state what was measured: "00:23 recorded" (the timer), "9 words" (the transcript), "2 medicines checked" (rows in the answer). "Picture sent" from the canvas's Reading stage is also not shown: `fetch` gives no upload-complete signal, so the Reading step reads "Sending the picture and reading the pad" until the single answer arrives, with a Cancel link and no percentage.

### Task 1: The stage rules (`steps.js`, pure part)

**Files:** Create `frontend/steps.js`, `tests/test_frontend_steps.py`.

**Interfaces:**
- Produces: `StepsLogic.main(stage, info) -> {stage, chip: {text, cls}, steps: [{key, label, status, sub}]}`, `StepsLogic.profile({clinic, mine, active, lhDone, lhLocked}) -> [{key, label, status, sub}]`, `StepsLogic.letterhead({upload, review, busyLabel, done}) -> [{key, label, status, sub}]`; `status` is `todo|now|done|failed|na|locked`. Page API: `Steps.main(stage, patch)`, `Steps.needs(n)`.

- [ ] **Step 1: Write the failing tests.** Create `tests/test_frontend_steps.py` (the last three tests pass only after Tasks 2 and 3; they are in the same file so the whole file is the plan's guard):

```python
"""Steppers (I1-f). The stage rules run under node (no DOM); the wiring is checked as text, like tests/test_frontend_*.py.
Behaviour in a real browser is the manual checklist in the plan."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _read(name):
    return (FRONT / name).read_text(encoding="utf-8")


def _node(expr):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = "globalThis.window = globalThis; require(process.argv[1]); console.log(JSON.stringify(" + expr + "))"
    out = subprocess.run([node, "-e", script, str(FRONT / "steps.js")], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _status(stage, info="{}"):
    return f"StepsLogic.main({json.dumps(stage)}, {info}).steps.map((s) => s.status)"


def test_the_main_progress_has_four_steps_and_never_a_stage_the_page_cannot_know():
    r = _node('StepsLogic.main("listening", {}).steps.map((s) => s.label)')
    assert r == ["Listening", "Transcribing", "Structuring and checking", "Your review"]
    assert _node(_status("listening")) == ["now", "todo", "todo", "todo"]
    assert _node(_status("transcribing")) == ["done", "now", "todo", "todo"]
    assert _node(_status("structuring")) == ["done", "done", "now", "todo"]
    assert _node(_status("ready")) == ["done", "done", "done", "now"]
    assert _node(_status("idle")) == ["todo"] * 4 and _node(_status("no-such-stage")) == ["todo"] * 4


def test_words_come_from_what_the_page_measured():
    r = _node('StepsLogic.main("ready", {recorded:"00:48", words:142, rows:5, needs:2}).steps.map((s) => s.sub)')
    assert r == ["00:48 recorded", "142 words", "5 medicines checked", "2 medicines need you"]
    one = _node('StepsLogic.main("ready", {words:1, rows:1, needs:1}).steps.map((s) => s.sub)')
    assert one[1:] == ["1 word", "1 medicine checked", "1 medicine needs you"]
    assert _node('StepsLogic.main("structuring", {mode:"correct"}).steps[2].sub') == "Applying your correction"
    assert _node('StepsLogic.main("ready", {rows:3}).steps[3].sub') == "Everything checked. Ready to save."


def test_a_failure_marks_only_the_step_that_failed_and_a_reopened_prescription_claims_nothing_was_heard():
    assert _node(_status("failed-listening", '{reason:"No audio captured"}')) == ["failed", "todo", "todo", "todo"]
    assert _node(_status("failed-transcribing", '{reason:"No words found"}')) == ["done", "failed", "todo", "todo"]
    assert _node(_status("failed-structuring", '{reason:"x"}')) == ["done", "done", "failed", "todo"]
    assert _node('StepsLogic.main("failed-transcribing", {reason:"No words found"}).steps[1].sub') == "No words found"
    assert _node(_status("opened")) == ["na", "na", "na", "now"]
    assert _node('StepsLogic.main("failed-structuring", {}).chip') == {"text": "Problem", "cls": "failed"}


def test_the_profile_steps_follow_what_is_filled_in_and_what_has_focus():
    assert _node('StepsLogic.profile({}).map((s) => s.status)') == ["now", "todo", "todo"]
    assert _node('StepsLogic.profile({clinic:"x", mine:"y"}).map((s) => s.status)') == ["done", "done", "now"]
    assert _node('StepsLogic.profile({clinic:"x", mine:"y", active:"clinic"}).map((s) => s.status)') == ["now", "done", "todo"]
    locked = _node('StepsLogic.profile({clinic:"x", mine:"y", lhLocked:true})[2]')
    assert locked["status"] == "locked" and locked["sub"] == "Opens after you save"
    assert _node('StepsLogic.profile({clinic:"x", mine:"y", lhDone:true}).map((s) => s.status)') == ["done", "done", "done"]


def test_the_letterhead_steps_follow_the_panels_real_states_and_show_no_percentage():
    up = "{upload:true, review:false, busyLabel:'', done:''}"
    assert _node(f"StepsLogic.letterhead({up}).map((s) => s.status)") == ["now", "todo", "todo", "todo"]
    reading = _node("StepsLogic.letterhead({upload:true, review:false, busyLabel:'Uploading and reading your letterhead. This can take up to a minute…', done:''})")
    assert [s["status"] for s in reading] == ["done", "now", "todo", "todo"] and reading[1]["sub"] == "Sending the picture and reading the pad"
    assert _node("StepsLogic.letterhead({upload:false, review:true, busyLabel:'', done:''}).map((s) => s.status)") == ["done", "done", "now", "todo"]
    assert _node("StepsLogic.letterhead({upload:false, review:true, busyLabel:'Saving your edits…', done:''}).map((s) => s.status)") == ["done", "done", "now", "todo"]
    assert _node("StepsLogic.letterhead({upload:false, review:true, busyLabel:'Saving your letterhead…', done:''}).map((s) => s.status)") == ["done", "done", "done", "now"]
    assert _node("StepsLogic.letterhead({upload:true, review:false, busyLabel:'', done:'Done. The clinic letterhead is saved.'}).map((s) => s.status)") == ["done"] * 4
    assert _node("StepsLogic.letterhead({upload:true, review:false, busyLabel:'', done:'The draft was discarded.'}).map((s) => s.status)")[0] == "now"
    assert "%" not in _read("steps.js") and '<progress aria-label="Working"></progress>' in _read("index.html")


def test_the_words_the_steppers_read_still_exist_where_they_are_produced():
    lh, app = _read("letterhead.js"), _read("app.js")
    for text in ('"Uploading and reading your letterhead.', '"Saving your letterhead…"', '"Done. Your own letterhead is saved.', '"Done. The clinic letterhead is saved',
                 "Clinic letterhead: active."):
        assert text in lh, text
    assert 'el("lhPanel").setAttribute("aria-busy"' in lh and "lhPanel\").addEventListener(\"close\", () => { if (lh.abort && !lh.draft) lh.abort.abort(); })" in lh
    for stage in ('setStep("transcribing"', 'setStep("structuring"', 'setStep("failed-structuring"', 'setStep("opened")'):
        assert stage in app, stage
    assert 'setStep("working")' not in app and "agentChip.className" not in app


def test_the_page_loads_the_steppers_and_the_old_three_step_markup_is_gone():
    html, css = _read("index.html"), _read("styles.css")
    assert re.search(r'<ol id="steps" class="stp-list" aria-label="Assistant progress"></ol>', html) and 'data-step="working"' not in html
    assert html.index("steps.js?v=") < html.index("app.js?v=") and 'href="steps.css?v=1"' in html
    assert html.index('id="profSteps"') < html.index('id="profClinicPart"') and html.index('id="lhSteps"') < html.index('class="lh-body"')
    assert ".steps .step" not in css and ".step[data-step" not in css and "@page { margin: 14mm; }" in css


def test_steps_js_parses_builds_dom_safely_and_the_stylesheet_has_no_motion():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    assert subprocess.run([node, "--check", str(FRONT / "steps.js")], capture_output=True, text=True).returncode == 0
    js, css = _read("steps.js"), _read("steps.css")
    assert "innerHTML" not in js and "insertAdjacentHTML" not in js and "animation" not in css and "transition" not in css
    assert 'cancel.className = "stp-cancel"' in js and 'className = "stp-cancel lh-act"' not in js    # setBusy() disables .lh-act buttons; Cancel must stay enabled
```

- [ ] **Step 2: Run them.** `.venv/bin/python -m pytest tests/test_frontend_steps.py -q` -> expected `8 failed`.

- [ ] **Step 3: Write `frontend/steps.js`.**

```js
"use strict";
// Progress steppers: the main dictation steps, the Profile dialog and the Letterhead panel. The rules come first (pure,
// tested under node). A step is only ever shown as "now" or "done" when the page really knows it: the page knows when it
// records, when /api/transcribe is in flight and when /api/format (or /api/v1/correct) is in flight, nothing finer.
(function (root) {
  const MAIN = [["listening", "Listening"], ["transcribing", "Transcribing"], ["structuring", "Structuring and checking"], ["review", "Your review"]];
  const PROFILE = [["clinic", "Clinic"], ["mine", "My details"], ["letterhead", "Letterhead"]];
  const LETTERHEAD = ["Upload", "Reading", "Review", "Accept"];
  const plural = (n, one, many) => n + " " + (n === 1 ? one : many);
  const S = (status, sub) => ({ status, sub: sub || "" });
  const CHIP = { idle: ["Idle", "idle"], listening: ["Listening", "listening"], transcribing: ["Transcribing", "working"], structuring: ["Structuring", "working"],
    ready: ["Ready", "ready"], opened: ["Ready", "ready"], "failed-listening": ["Problem", "failed"], "failed-transcribing": ["Problem", "failed"], "failed-structuring": ["Problem", "failed"] };
  // stage: idle | listening | transcribing | structuring | ready | opened | failed-listening | failed-transcribing | failed-structuring
  // info: {recorded: "00:23", words, mode: "correct", rows, needs, reason}; an unknown stage is "idle".
  function main(stage, info) {
    info = info || {};
    const T = S("todo"), rec = info.recorded ? info.recorded + " recorded" : "", words = info.words ? plural(info.words, "word", "words") : "";
    const rows = info.rows | 0, needs = info.needs | 0, saved = S("na", "Saved earlier");
    const table = {
      idle: [T, T, T, T],
      listening: [S("now", "Recording"), T, T, T],
      transcribing: [S("done", rec), S("now", "Speech to text"), T, T],
      structuring: [S("done", rec), S("done", words), S("now", info.mode === "correct" ? "Applying your correction" : "Drafting the prescription and checking medicines"), T],
      ready: [S("done", rec), S("done", words), S("done", plural(rows, "medicine checked", "medicines checked")), S("now", needs ? plural(needs, "medicine needs you", "medicines need you") : "Everything checked. Ready to save.")],
      opened: [saved, saved, saved, S("now", "Reopened prescription")],
      "failed-listening": [S("failed", info.reason), T, T, T],
      "failed-transcribing": [S("done", rec), S("failed", info.reason), T, T],
      "failed-structuring": [S("done", rec), S("done", words), S("failed", info.reason), T],
    };
    const key = table[stage] ? stage : "idle";
    return { stage: key, chip: { text: CHIP[key][0], cls: CHIP[key][1] },
      steps: MAIN.map((m, i) => Object.assign({ key: m[0], label: m[1] }, table[key][i])) };
  }
  // f: {clinic, mine, lhDone, lhLocked, active}: filled-in flags, the part the focus is in, and whether Letterhead is locked
  // (its button is disabled while the form has unsaved changes).
  function profile(f) {
    const done = { clinic: !!f.clinic, mine: !!f.mine, letterhead: !!f.lhDone };
    const now = PROFILE.some((p) => p[0] === f.active) ? f.active : (PROFILE.find((p) => !done[p[0]]) || [""])[0];
    return PROFILE.map((p) => {
      const k = p[0], locked = k === "letterhead" && !!f.lhLocked;
      return { key: k, label: p[1], status: locked ? "locked" : k === now ? "now" : done[k] ? "done" : "todo", sub: locked ? "Opens after you save" : "" };
    });
  }
  // v: {upload: upload view shown, review: review view shown, busyLabel: the panel's busy text or "", done: the done message or ""}
  // The labels are the ones letterhead.js passes to setBusy / writes to #lhDone (tests pin them there).
  function letterhead(v) {
    const label = v.busyLabel || "";
    let at = 1;
    if (/^Uploading and reading/.test(label)) at = 2;
    else if (v.review) at = /^Saving your letterhead/.test(label) ? 4 : 3;
    else if (v.upload && /^Done\./.test(v.done || "")) at = 5;
    return LETTERHEAD.map((l, i) => ({ key: l.toLowerCase(), label: l, status: i + 1 < at ? "done" : i + 1 === at ? "now" : "todo",
      sub: at === 2 && i === 1 ? "Sending the picture and reading the pad" : "" }));
  }
  const logic = { main, profile, letterhead };
  root.StepsLogic = logic;
  if (typeof document === "undefined") return;
  // ---- DOM (createElement and textContent only) ----------------------------------------------------------------
  const NS = "http://www.w3.org/2000/svg", $ = (id) => document.getElementById(id);
  const WORD = { todo: "waiting", now: "in progress", done: "done", failed: "problem", na: "not needed", locked: "locked" };
  function mark(status) {
    if (status === "failed") return "!";
    if (status === "na") return "–";
    if (status !== "done") return "";
    const svg = document.createElementNS(NS, "svg"), p = document.createElementNS(NS, "path");
    [["width", 13], ["height", 13], ["viewBox", "0 0 24 24"], ["fill", "none"], ["stroke", "currentColor"], ["stroke-width", 3.2], ["stroke-linecap", "round"], ["stroke-linejoin", "round"], ["aria-hidden", "true"]].forEach((a) => svg.setAttribute(a[0], a[1]));
    p.setAttribute("d", "M5 12.5l4.2 4.2L19 7"); svg.appendChild(p);
    return svg;
  }
  // One <li> per step, built once and then updated, so a screen reader hears changes rather than a new list.
  function paint(ol, steps, numbered, clickable) {
    if (!ol) return;
    steps.forEach((s, i) => {
      let li = ol.children[i];
      if (!li) {
        li = document.createElement("li"); li.dataset.step = s.key;
        const dot = document.createElement("span"); dot.className = "dot"; dot.setAttribute("aria-hidden", "true");
        const box = document.createElement(clickable ? "button" : "div"); box.className = "stp-text";
        if (clickable) { box.type = "button"; box.dataset.target = s.key; }
        const b = document.createElement("b"), sub = document.createElement("span"), word = document.createElement("span");
        sub.className = "sub"; word.className = "sr-only";
        box.append(b, sub, word); li.append(dot, box); ol.appendChild(li);
      }
      li.className = "stp " + s.status;
      const dot = li.firstChild, box = li.lastChild;
      dot.textContent = ""; const m = mark(s.status);
      if (m) dot.append(m); else if (numbered) dot.textContent = String(i + 1);
      box.children[0].textContent = s.label; box.children[1].textContent = s.sub;
      box.children[2].textContent = " (" + WORD[s.status] + ")";
      if (s.status === "now") li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    });
  }
  // Main steps + the top-bar chip. Info accumulates over one dictation (recorded time, word count) and restarts at "listening".
  let info = {}, current = "idle";
  function setMain(stage, patch) {
    if (stage === "listening" || stage === "idle") info = {};
    if (!patch || !patch.reason) delete info.reason;
    info = Object.assign(info, patch || {}); current = stage;
    const r = main(stage, info);
    paint($("steps"), r.steps, false, false);
    const chip = $("agentChip");
    if (chip) { chip.textContent = r.chip.text; chip.className = "agent-chip " + r.chip.cls; }
  }
  function needs(n) { if (current === "ready") setMain("ready", { needs: n }); }     // the review line follows the count as the doctor resolves rows
  function initProfile() {
    const panel = $("profilePanel"), ol = $("profSteps");
    if (!panel || !ol) return;
    let active = "";
    const PART = { profClinicPart: "clinic", profMinePart: "mine" };
    const text = (id) => ($(id) ? $(id).value : "").trim();
    function update() {
      paint(ol, profile({ clinic: text("profClinic"), mine: text("profDoctor"), active,
        lhDone: /^Clinic letterhead: active/.test(($("profLhStatus") || {}).textContent || ""), lhLocked: !$("profLhHint").hidden }), true, true);
    }
    panel.addEventListener("focusin", (e) => { const f = e.target.closest("fieldset, section.prof-lh"); active = f ? (PART[f.id] || (f.classList.contains("prof-lh") ? "letterhead" : "")) : ""; update(); });
    panel.addEventListener("input", update);
    new MutationObserver(update).observe(panel, { attributes: true, attributeFilter: ["open"] });
    new MutationObserver(update).observe($("profLhStatus"), { childList: true, characterData: true, subtree: true });
    new MutationObserver(update).observe($("profLhHint"), { attributes: true, attributeFilter: ["hidden"] });
    ol.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-target]"); if (!b) return;
      const go = { clinic: "profClinic", mine: null, letterhead: "profileLetterheadBtn" }[b.dataset.target];
      const el = go ? $(go) : panel.querySelector("#profDoctorGrid input");
      if (el && !el.disabled) el.focus(); else $("profLhTitle").focus();
    });
    $("profLhTitle").tabIndex = -1;
    update();
  }
  function initLetterhead() {
    const panel = $("lhPanel"), ol = $("lhSteps");
    if (!panel || !ol) return;
    const cancel = document.createElement("button");     // no .lh-act class, so setBusy() leaves it enabled
    cancel.type = "button"; cancel.id = "lhCancelBtn"; cancel.className = "stp-cancel"; cancel.textContent = "Cancel and keep my current layout";
    $("lhProgress").appendChild(cancel);
    cancel.addEventListener("click", () => $("lhCloseBtn").click());     // closing the panel already aborts the upload (letterhead.js close handler)
    function update() {
      const busy = panel.getAttribute("aria-busy") === "true", label = busy ? ($("lhProgressText").textContent || "") : "";
      const steps = letterhead({ upload: !$("lhUpload").hidden, review: !$("lhReview").hidden, busyLabel: label, done: $("lhDone").hidden ? "" : $("lhDone").textContent });
      paint(ol, steps, true, false);
      cancel.hidden = !/^Uploading and reading/.test(label);
    }
    const o = new MutationObserver(update);
    o.observe(panel, { attributes: true, attributeFilter: ["aria-busy"] });
    [$("lhUpload"), $("lhReview"), $("lhDone")].forEach((n) => o.observe(n, { attributes: true, attributeFilter: ["hidden"], childList: true, characterData: true, subtree: true }));
    o.observe($("lhProgressText"), { childList: true, characterData: true, subtree: true });
    update();
  }
  root.Steps = { main: setMain, needs, initProfile, initLetterhead };
  initProfile(); initLetterhead();
})(typeof window !== "undefined" ? window : globalThis);
```

- [ ] **Step 4: Run the rule tests.** `.venv/bin/python -m pytest tests/test_frontend_steps.py -q -k "four_steps or words_come or failure or profile_steps or letterhead_steps"` -> expected `5 passed`.

### Task 2: The stylesheet, the markup and the `app.js` call sites

**Files:** Create `frontend/steps.css`; modify `frontend/index.html`, `frontend/styles.css`, `frontend/app.js` (`setStep` at `:94` and the 13 call sites, each named in a comment with its original line).

**Interfaces:** Consumes `Steps.main`, `Steps.needs`. Produces: stages `listening`, `transcribing`, `structuring`, `ready`, `opened`, `failed-listening`, `failed-transcribing`, `failed-structuring`, `idle`.

- [ ] **Step 1: Write `frontend/steps.css`.**

```css
/* Steppers (steps.js): main dictation steps, Profile dialog, Letterhead panel. State is icon or number plus a hidden word
   ("done", "in progress", "problem"), never colour alone. No motion here. */
:root { --st-ok:#17703a; --st-bad:#a8261d; --st-line:#c3cdc8; --st-muted:#566660; --st-ring:#dfe9ff; }
.sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }
.stp-list { list-style:none; margin:0 0 12px; padding:0; }
.stp-list .stp { display:flex; gap:12px; align-items:flex-start; position:relative; padding-bottom:14px; color:var(--st-muted); }
.stp-list .stp:not(:last-child)::before { content:""; position:absolute; left:10px; top:24px; bottom:2px; width:2px; background:#d6ded9; }
.stp-list .stp.done:not(:last-child)::before { background:#bcd4c5; }
.dot { width:22px; height:22px; flex:0 0 22px; border-radius:50%; display:flex; align-items:center; justify-content:center; border:2px solid var(--st-line); background:#fff; font-size:12px; font-weight:700; }
.stp.done .dot { background:var(--st-ok); border-color:var(--st-ok); color:#fff; }
.stp.now .dot { border-color:var(--accent); box-shadow:0 0 0 4px var(--st-ring); color:var(--accent); }
.stp.failed .dot { border-color:var(--st-bad); color:var(--st-bad); box-shadow:0 0 0 4px #fbe0dd; }
.stp.na .dot, .stp.locked .dot { border-style:dashed; }
.stp-text { display:block; text-align:left; background:none; border:0; padding:0; font:inherit; color:inherit; }
.stp-text b { display:block; font-size:13px; }
.stp-text .sub { display:block; font-size:12px; }
.stp.now, .stp.failed { color:var(--ink); }
.stp.failed .sub { color:var(--st-bad); }
.agent-chip.failed { background:#fdecea; border-color:#f3b6b0; color:var(--st-bad); }
/* Profile and Letterhead: a row of numbered steps */
.stepper { display:flex; list-style:none; margin:10px 0 4px; padding:0; }
.stepper .stp { flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; position:relative; font-size:12px; text-align:center; color:var(--st-muted); }
.stepper .stp:not(:last-child)::after { content:""; position:absolute; top:11px; left:calc(50% + 16px); right:calc(-50% + 16px); height:2px; background:#d6ded9; }
.stepper .stp.done:not(:last-child)::after { background:var(--st-ok); }
button.stp-text { cursor:pointer; min-height:44px; min-width:44px; text-align:center; }
button.stp-text:focus-visible { outline:3px solid #8fb2ff; outline-offset:2px; }
.stepper .stp-text { text-align:center; }
.stp-cancel { margin-top:8px; background:none; border:0; color:var(--accent); text-decoration:underline; min-height:44px; padding:0 8px; }
.stp-cancel[hidden] { display:none; }
.lh-panel .stepper { margin:0; padding:0 20px 8px; }
```

- [ ] **Step 2: Apply the edits.** From the repo root, paste as `python3 - <<'PY' ... PY`. It also deletes the old three-step styles (`styles.css:55-73`), swaps the three `<li>` for an empty `<ol id="steps">` that `steps.js` fills, adds the two empty stepper lists, and bumps `app.js?v=28` to `29`.

```python
# Run from the repo root (after I1-e, I1-e2, I1-e3). Every edit must match exactly once. Line numbers are the ORIGINAL app.js ones.
def edit(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (path, old[:70])
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)
def between(path, start, end, new):                     # replace [start, end) with new
    s = open(path, encoding="utf-8").read()
    a = s.index(start); b = s.index(end, a)
    open(path, "w", encoding="utf-8").write(s[:a] + new + s[b:])
A = "frontend/app.js"
between(A, "// ---- assistant status: coarse", "// ---- health badge", '''// ---- assistant status: four steps the page really knows (steps.js): Listening, Transcribing (/api/transcribe in flight),
// Structuring and checking (/api/format or /api/v1/correct in flight: one request, so no finer split), Your review.
const wordCount = (t) => String(t || "").split(/\\s+/).filter(Boolean).length;
function setStep(stage, info) { Steps.main(stage, info); }          // :94 was a 3-step list; the chip is updated by steps.js too

''')
edit(A, [
 ('    setStep("ready");\n    const viewOnlyNow', '    setStep("opened");                                  // :333 openDocument: nothing was heard this time\n    const viewOnlyNow'),
 ('check your microphone and try again."); setStep("idle"); return; }', 'check your microphone and try again."); setStep("failed-listening", { reason: "No audio captured" }); return; }   // :451'),
 ('  chunks = [];\n  setStep("working");', '  chunks = [];\n  setStep("transcribing", { recorded: timerEl.textContent });   // :454'),
 ('Press the mic and speak again."); setStep("idle"); return; }', 'Press the mic and speak again."); setStep("failed-transcribing", { reason: "No words found" }); return; }   // :457'),
 ('    showError(errorMessage(e, "Dictation failed"));\n    setStep("idle");', '    showError(errorMessage(e, "Dictation failed"));\n    setStep("failed-transcribing", { reason: "Could not transcribe" });   // :465'),
 ('  setWorking(true, "Transcribing…");\n  setStep("working");', '  setWorking(true, "Transcribing…");\n  setStep("transcribing");                              // :498'),
 ('  setWorking(true, "Structuring the prescription…");\n  setStep("working");', '  setWorking(true, "Structuring the prescription…");\n  setStep("structuring", { words: wordCount(transcript), mode: "dictate" });   // :530'),
 ('    renderSheet(state.structured);\n    setStep("ready");\n    const open = openRows().length;\n    setStatus("Draft ready', '    renderSheet(state.structured);\n    setStep("ready", { rows: (state.structured.rx || []).length, needs: openRows().length });   // :542\n    const open = openRows().length;\n    setStatus("Draft ready'),
 ('there is no need to dictate again.", true);\n    setStep("idle");', 'there is no need to dictate again.", true);\n    setStep("failed-structuring", { reason: "Could not structure it" });   // :551'),
 ('  setWorking(true, "Applying your correction…");\n  setStep("working");', '  setWorking(true, "Applying your correction…");\n  setStep("structuring", { words: wordCount(transcript), mode: "correct" });   // :562'),
 ('    renderSheet(state.structured);\n    setStep("ready");\n    const open = openRows().length;\n    setStatus("Correction merged', '    renderSheet(state.structured);\n    setStep("ready", { rows: (state.structured.rx || []).length, needs: openRows().length });   // :573\n    const open = openRows().length;\n    setStatus("Correction merged'),
 ('or edit the form directly.", true);\n    setStep("idle");', 'or edit the form directly.", true);\n    setStep("failed-structuring", { reason: "Could not apply it" });   // :583'),
 ('    : "All medicines are ready. You can Save.";\n  RxView.sync();', '    : "All medicines are ready. You can Save.";\n  RxView.sync();\n  Steps.needs(open);                                  // :954 updateGrounding keeps the review line in step'),
])
between("frontend/styles.css", "/* --- assistant coarse steps", ".status { text-align:center;", "")          # :55-73 old three-step styles
edit("frontend/index.html", [
 ('<link rel="stylesheet" href="rx.css?v=2" />\n', '<link rel="stylesheet" href="rx.css?v=2" />\n<link rel="stylesheet" href="steps.css?v=1" />\n'),
 ('''    <ol id="steps" class="steps" aria-label="Assistant status">
      <li class="step" data-step="listening"><span class="dot" aria-hidden="true"></span>Listening</li>
      <li class="step" data-step="working"><span class="dot" aria-hidden="true"></span>Working</li>
      <li class="step" data-step="ready"><span class="dot" aria-hidden="true"></span>Ready</li>
    </ol>''', '''    <ol id="steps" class="stp-list" aria-label="Assistant progress"></ol>'''),
 ('<p class="panel-hint">These details print at the top of every prescription.</p>\n', '<p class="panel-hint">These details print at the top of every prescription.</p>\n    <ol id="profSteps" class="stepper" aria-label="Profile steps"></ol>\n'),
 ('''    </div>
    <div class="lh-body">''', '''    </div>
    <ol id="lhSteps" class="stepper" aria-label="Letterhead steps"></ol>
    <div class="lh-body">'''),
 ('<script src="app.js?v=28"></script>', '<script src="steps.js?v=1"></script>\n<script src="app.js?v=29"></script>'),
])
```

- [ ] **Step 3: Run the tests.** `.venv/bin/python -m pytest tests/test_frontend_steps.py tests/test_frontend_authorship.py tests/test_frontend_letterhead.py tests/test_frontend_rxrow.py -q` -> all pass (`8` in the steps file). Then `.venv/bin/python -m pytest tests/ -q` -> expected baseline + 8.

- [ ] **Step 4: Leave uncommitted.** `git status --short`: `M frontend/app.js`, `M frontend/index.html`, `M frontend/styles.css`, `?? frontend/steps.js`, `?? frontend/steps.css`, `?? tests/test_frontend_steps.py`.

### Task 3: Browser check (Playwright MCP)

- [ ] **Step 1: Start the app on a temp database** (background): `cd <repo> && DB_PATH="$(mktemp -d)/f.db" STT_ENGINE=stub LLM_PROVIDER=stub .venv/bin/python -m uvicorn doctor_dictation.main:app --port 8791`. `browser_navigate` to `http://localhost:8791/`. Expected: four waiting steps (`Listening`, `Transcribing`, `Structuring and checking`, `Your review`), chip `Idle`.
- [ ] **Step 2: Drive the real pipeline without a microphone.** `browser_run_code_unsafe`:

```js
async (page) => {
  await page.route('**/api/transcribe', async (r) => { await new Promise(t => setTimeout(t, 800)); await r.fulfill({ json: { transcript: 'tablet amlodipine five milligram once daily for thirty days' } }); });
  await page.route('**/api/format', async (r) => { await new Promise(t => setTimeout(t, 1200)); await r.fulfill({ json: { engine: 'stub', transcript_sha256: 'x', structured: { patientName: 'Meera Nair', ageSex: '46 / F', rx: [
    { form: 'Tab.', name: 'Amlodipine', strength: '5 mg', dose: '1-0-0', timing: '', duration: '30 days', instructions: '', status: 'verified', lexicon_match: 'Amlodipine' },
    { form: 'Tab.', name: 'Prednisone', strength: '10 mg', dose: '1-0-1', timing: '', duration: '5 days', instructions: '', status: 'lookalike-check', lexicon_match: 'Prednisone' }] } } }); });
  const snap = () => page.evaluate(() => [agentChip.textContent, [...document.querySelectorAll('#steps li')].map(li => li.querySelector('b').textContent.slice(0, 5) + ':' + li.querySelector('.sr-only').textContent.trim() + '[' + li.querySelector('.sub').textContent + ']').join(' | ')]);
  const out = {};
  await page.evaluate(() => { timerEl.textContent = '00:23'; chunks = [new Blob(['x'], { type: 'audio/webm' })]; state.pendingMode = 'dictate'; window.__p = onRecordingStop(); });
  await page.waitForTimeout(300); out.at300ms = await snap();
  await page.waitForTimeout(1000); out.at1300ms = await snap();
  await page.evaluate(() => window.__p); out.done = await snap();
  return out; }
```
Expected: at 300 ms chip `Transcribing`, step 2 `(in progress)`, step 1 `(done)[00:23 recorded]`; at 1300 ms chip `Structuring`, step 2 `(done)[9 words]`, step 3 `(in progress)`; at the end chip `Ready`, step 3 `(done)[2 medicines checked]`, step 4 `(in progress)[1 medicine needs you]`. (Verified against a built copy while writing this plan.)
- [ ] **Step 3: A failure.** Replace the transcribe route with `r.fulfill({ json: { transcript: '' } })`, run the same `onRecordingStop` line. Expected: chip `Problem`, step 2 `(problem)[No words found]`, steps 3 and 4 waiting, and the page's existing red error with its message is unchanged.
- [ ] **Step 4: The review line follows the doctor.** With the Prednisone row needing you, click its `Confirm Prednisone as is` (I1-e2): step 4 sub changes to `Everything checked. Ready to save.`
- [ ] **Step 5: Reopened prescription.** Save (confirm the row first), reload, open the patient from Today: steps 1 to 3 show `(not needed)[Saved earlier]`, step 4 `(in progress)[Reopened prescription]`, chip `Ready`.
- [ ] **Step 6: Profile stepper.** Click `Profile`. Expected: `profSteps` lists `Clinic`, `My details`, `Letterhead` as buttons, each 44 px high (`browser_evaluate` `() => [...document.querySelectorAll("#profSteps button")].map(b => Math.round(b.getBoundingClientRect().height))` -> `[44,44,44]`); clicking `My details` puts focus in the doctor grid; typing in Clinic name marks Clinic done; changing any field makes Letterhead `locked` ("Opens after you save"), matching the existing "Save your profile changes first" hint.
- [ ] **Step 7: Letterhead stepper.** Open the letterhead manager: `Upload` is in progress, `Reading`, `Review`, `Accept` waiting. Route `**/api/v1/templates` (POST) to wait 5 s and then fulfil `{ status: 502, json: {} }` (nothing is created), choose any small PNG (`browser_file_upload`), press Upload: `Reading` is in progress with `Sending the picture and reading the pad`, a `Cancel and keep my current layout` link shows and no percentage. Click Cancel: the panel closes and reopening shows `Upload` again with no stale error.
- [ ] **Step 8: Clean up.** `browser_close`, stop uvicorn, `rm -rf .playwright-mcp` in the repo.

## Self-Review

- Spec coverage: honest set of steps and the canvas change (table above), chip kept in sync (`Steps.main` sets it), Profile and Letterhead steppers mapped to real states, no percentage, Cancel, tests for the pure logic, manual checks with a temp `DB_PATH`. Visual polish, Login and Team: plan I1-f2.
- Placeholder scan: none. Types: `setStep(stage, info)` stages match `StepsLogic.main`'s table; `Steps.needs` is called from `updateGrounding` (I1-e2).

**Decision needed:** accept four steps instead of the canvas's five, and "Sending the picture and reading the pad" instead of "Picture sent". Not done: any `letterhead.js` change, visual polish (I1-f2), the PDF or backend.
