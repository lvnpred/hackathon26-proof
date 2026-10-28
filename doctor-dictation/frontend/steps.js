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
  // info: {recorded: "00:23", words, mode: "correct", rows, needs, reason, viewOnly}; an unknown stage is "idle".
  function main(stage, info) {
    info = info || {};
    const T = S("todo"), rec = info.recorded ? info.recorded + " recorded" : "", words = info.words ? plural(info.words, "word", "words") : "Transcript ready";
    const rows = info.rows | 0, needs = info.needs | 0, saved = S("na", "Saved earlier");
    // Step 4 while ready: the doctor's count wins; no medicine rows at all is never "everything checked".
    const live = info.rows === undefined ? null : rows;     // the live count, when the page passed one
    const review = needs ? plural(needs, "medicine needs you", "medicines need you") : rows ? "Everything checked. Ready to save." : "No medicines yet";
    const table = {
      idle: [T, T, T, T],
      listening: [S("now", "Recording"), T, T, T],
      transcribing: [S("done", rec), S("now", "Speech to text"), T, T],
      structuring: [S("done", rec), S("done", words), S("now", info.mode === "correct" ? "Applying your correction" : "Drafting the prescription and checking medicines"), T],
      ready: [S("done", rec), S("done", words), S("done", rows ? plural(rows, "medicine checked", "medicines checked") : ""), S("now", review)],
      opened: [saved, saved, saved, info.viewOnly ? S("na", "View only. You can print it.") : S("now", live === null ? "Reopened prescription" : "Reopened prescription. " + review)],
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
  // The labels are the ones letterhead.js passes to setBusy / writes to #lhDone (tests pin them there). Only the two accept
  // messages count as Accept: the "stop using" message also starts with "Done." but nothing was accepted.
  function letterhead(v) {
    const label = v.busyLabel || "";
    let at = 1;
    if (/^Uploading and reading/.test(label)) at = 2;
    else if (v.review) at = /^Saving your letterhead/.test(label) ? 4 : 3;
    else if (v.upload && /^Done\. (Your own|The clinic) letterhead is saved/.test(v.done || "")) at = 5;
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
    if (stage === "listening" || stage === "idle" || stage === "opened") info = {};
    if (!patch || !patch.reason) delete info.reason;
    info = Object.assign(info, patch || {}); current = stage;
    const r = main(stage, info);
    paint($("steps"), r.steps, false, false);
    const chip = $("agentChip");
    if (chip) { chip.textContent = r.chip.text; chip.className = "agent-chip " + r.chip.cls; }
    return r;                                                                       // tests read the result under node
  }
  function needs(c) { return current === "ready" || (current === "opened" && !info.viewOnly) ? setMain(current, { rows: c.rows, needs: c.needs }) : null; }     // the review line follows the count as the doctor resolves rows
  function initProfile() {
    const panel = $("profilePanel"), ol = $("profSteps");
    if (!panel || !ol) return;
    let active = "";
    const PART = { profClinicPart: "clinic", profMinePart: "mine" };
    const text = (id) => ($(id) ? $(id).value : "").trim();
    // The clinic line is #profLhStatus, the own-letterhead line is #profLhMine (hidden unless the doctor has one): both count.
    const shows = (id, re) => !!$(id) && !$(id).hidden && re.test($(id).textContent || "");
    function update() {
      paint(ol, profile({ clinic: text("profClinic"), mine: text("profDoctor"), active,
        lhDone: shows("profLhStatus", /^Clinic letterhead: active/) || shows("profLhMine", /^My own letterhead: active/), lhLocked: !$("profLhHint").hidden }), true, true);
    }
    panel.addEventListener("focusin", (e) => { const f = e.target.closest("fieldset, section.prof-lh"); active = f ? (PART[f.id] || (f.classList.contains("prof-lh") ? "letterhead" : "")) : ""; update(); });
    panel.addEventListener("input", update);
    new MutationObserver(update).observe(panel, { attributes: true, attributeFilter: ["open"] });
    new MutationObserver(update).observe($("profLhStatus"), { childList: true, characterData: true, subtree: true });
    new MutationObserver(update).observe($("profLhMine"), { attributes: true, attributeFilter: ["hidden"], childList: true, characterData: true, subtree: true });
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
      const steps = letterhead({ upload: !$("lhUpload").hidden, review: !$("lhReview").hidden, busyLabel: label, done: $("lhDone").hidden || !$("lhError").hidden ? "" : $("lhDone").textContent });     // a failed later upload shows an error: the old Done is stale
      paint(ol, steps, true, false);
      cancel.hidden = !/^Uploading and reading/.test(label);
    }
    const o = new MutationObserver(update);
    o.observe(panel, { attributes: true, attributeFilter: ["aria-busy"] });
    [$("lhUpload"), $("lhReview"), $("lhDone"), $("lhError")].forEach((n) => o.observe(n, { attributes: true, attributeFilter: ["hidden"], childList: true, characterData: true, subtree: true }));
    o.observe($("lhProgressText"), { childList: true, characterData: true, subtree: true });
    update();
  }
  root.Steps = { main: setMain, needs, initProfile, initLetterhead };
  initProfile(); initLetterhead();
})(typeof window !== "undefined" ? window : globalThis);
