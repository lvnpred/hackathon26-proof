"use strict";
// The medication rows on screen: state cell, strength chips, generic line, summary bar. Rules live in rxstate.js;
// app.js hands over what it owns once, through RxView.init(hooks). DOM is built with createElement and textContent only.
window.RxView = (function () {
  const NS = "http://www.w3.org/2000/svg", COLS = ["form", "name", "strength", "dose", "timing", "duration", "instructions"];
  const ICONS = {
    "check-circle": [["circle", { cx: 12, cy: 12, r: 9 }], ["path", { d: "M8 12.5l2.7 2.7L16 9.5" }]],
    capsule: [["rect", { x: 3, y: 9, width: 18, height: 6, rx: 3, transform: "rotate(-35 12 12)" }], ["path", { d: "M9.2 7.2l5.6 9.6" }]],
    triangle: [["path", { d: "M12 4l9 16H3z" }], ["path", { d: "M12 10v4M12 17.2v.1" }]],
    "shield-check": [["path", { d: "M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z" }], ["path", { d: "M9 12l2.2 2.2L15.5 10" }]],
    book: [["path", { d: "M5 4h10a3 3 0 013 3v13H8a3 3 0 01-3-3z" }], ["path", { d: "M5 17a3 3 0 013-3h10" }]],
    pencil: [["path", { d: "M4 20l4-1 11-11-3-3L5 16z" }]],
  };
  const URL_CHECK = "/api/v1/rx/check-row", CHECK_MS = 30000;
  let H = null, seq = 0, bound = null, resizeBound = false, roBound = false;
  const $ = (id) => document.getElementById(id);
  const val = (tr, c) => { const n = tr.querySelector('[data-col="' + c + '"]'); return (n ? n.textContent : "").replace(/\s+/g, " ").trim(); };
  const viewOnly = () => !!(window.Authorship && Authorship.isViewOnly());
  const setCell = (tr, c, v) => { const n = tr.querySelector('[data-col="' + c + '"]'); if (n) n.textContent = v; };
  const rows = () => [...H.body.querySelectorAll("tr[data-index]")];
  const isBlank = (tr) => COLS.every((c) => !val(tr, c));
  function el(tag, cls, t) { const n = document.createElement(tag); if (cls) n.className = cls; if (t != null) n.textContent = t; return n; }
  function btn(cls, action, t) { const b = el("button", "rx-act " + cls, t); b.type = "button"; b.dataset.action = action; return b; }
  function icon(name, size) {
    const svg = document.createElementNS(NS, "svg");
    const put = (n, a) => Object.keys(a).forEach((k) => n.setAttribute(k, a[k]));
    put(svg, { width: size || 16, height: size || 16, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2.4, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" });
    (ICONS[name] || []).forEach((p) => { const n = document.createElementNS(NS, p[0]); put(n, p[1]); svg.appendChild(n); });
    return svg;
  }
  const fresh = (src) => ({ meta: RxState.metaOf(src), how: (src && src.how) || "", note: "", checking: false, req: ++seq });
  const rx = (tr) => tr._rx || (tr._rx = fresh(null));
  const rowOf = (tr) => Object.assign({ status: tr.dataset.status || "", name: val(tr, "name"), strength: val(tr, "strength") }, rx(tr).meta);
  const EMPTY = "Empty row: removed when you save";
  const reasonFor = (tr) => isBlank(tr) ? EMPTY : RxState.rowState(rowOf(tr), ctxOf(tr)).reason;     // the reason the row itself shows (the 409 panel uses it)
  const focusState = (tr) => { const s = tr.querySelector(".rx-state"); if (s) s.focus(); };
  const focusAfterSpell = (tr) => { const c = tr.querySelector('button[data-action="confirm"].solid'); if (c) c.focus(); else focusState(tr); };   // a row still awaiting a decision: Enter confirms it
  const ctxOf = (tr) => ({ confirmed: H.confirmed().has(tr.dataset.rowid), strength: val(tr, "strength"), how: rx(tr).how });
  function renderRow(tr) {
    if (!H) return;
    const med = tr.querySelector("td.med"), cell = tr.querySelector("td.check");
    if (!med || !cell) return;
    const r = rx(tr), vo = !!(window.Authorship && Authorship.isViewOnly());
    if (!H.confirmed().has(tr.dataset.rowid) && r.how && r.how !== "chip-open") r.how = "";   // reopened: the old "you chose" no longer applies
    const blank = isBlank(tr);                                                           // nothing typed: neutral line, no pill, no buttons
    const st = blank ? { state: "", icon: "", label: "", reason: EMPTY, chips: [], canConfirm: false, canReopen: false } : RxState.rowState(rowOf(tr), ctxOf(tr));
    const name = val(tr, "name") || "this row";
    if (SpellModal.isOpenFor(tr.dataset.rowid) && !r.checking && st.state === "you" && !r.spellFromConfirmed) SpellModal.closeFor(tr.dataset.rowid, false);   // confirmed from outside while open: the dialog goes (one opened on an already confirmed row stays)
    if (blank) delete tr.dataset.rxstate; else tr.dataset.rxstate = st.state;
    med.querySelectorAll(".rx-extra").forEach((n) => n.remove());                       // generic line and chips: screen only
    const gen = r.meta.generic, nm = val(tr, "name");
    const drew = window.GenericEdit ? GenericEdit.render(tr, r, st, H) : "";                     // the generic line, Add generic, AI suggests: genericedit.js
    if (!blank && gen && !drew && RxState.sameName(gen, nm)) {                                   // a generic-named row: screen only (Q1)
      const tag = el("span", "rx-extra rx-gen-tag no-print", "generic"), nameEl = med.querySelector('[data-col="name"]');
      if (nameEl) nameEl.after(tag); else med.appendChild(tag);                        // directly after the name, not after the strength
    }
    const genProblem = blank || !window.GenericEdit ? "" : GenericEdit.problemOf(r.meta);       // a doctor generic the server would refuse
    if (genProblem) st.canConfirm = false;                                                       // stays in confirm until fixed or cleared
    const sch = blank ? "" : RxState.scheduleOf(r.meta);                                                                         // information only (Q10): never printed, never a state
    if (sch) {
      const s = el("span", "rx-extra rx-sched no-print", "Schedule " + sch), tag = med.querySelector(".rx-gen-tag");
      s.setAttribute("title", "Schedule " + sch + " medicine (Drugs and Cosmetics Rules). Information only: nothing on this row changes.");
      if (tag) tag.after(s); else med.appendChild(s);
    }
    if (st.chips.length) {
      const box = el("div", "rx-extra rx-chips no-print");
      box.appendChild(el("span", "rx-hint", "Strengths:"));
      st.chips.forEach((c) => {
        const b = btn("rx-chip" + (c.usual ? " usual" : ""), "chip", c.label);
        b.disabled = vo || r.checking;
        b.dataset.value = c.label; b.setAttribute("aria-label", "Set strength to " + c.label + (c.usual ? " (usual)" : ""));
        if (c.usual) b.appendChild(el("span", "rx-usual", "usual"));
        box.appendChild(b);
      });
      med.appendChild(box);
    }
    let box = cell.querySelector(".rx-state");
    if (!box) {                                   // built once, so the role=status line stays one live region
      cell.textContent = "";
      box = el("div", "rx-state no-print"); box.tabIndex = -1;
      box.append(el("span", "rx-pill"), el("div", "rx-reason"), el("div", "rx-note"), el("div", "rx-acts"));
      box.children[1].setAttribute("role", "status"); box.children[2].setAttribute("role", "alert");
      cell.append(box);
    }
    box.children[0].hidden = blank; box.children[0].dataset.state = st.state; box.children[0].title = st.reason; box.children[0].textContent = "";
    if (!blank) box.children[0].append(icon(st.icon), el("span", null, st.label));
    box.children[1].textContent = st.reason; box.children[2].textContent = r.note || genProblem;
    const acts = box.children[3], hadFocus = !!document.activeElement && [...acts.children].includes(document.activeElement);
    acts.textContent = "";
    if (r.checking) {                                 // only this row waits; the other rows keep working
      const c = el("div", "rx-checking"); c.append(el("span", "rx-spin"), el("span", null, "Checking this medicine..."));
      acts.appendChild(c);
    } else {
      if (st.didYouMean) { const b = SugList.item(st.didYouMean, { action: "dym", prefix: "Did you mean " }); b.disabled = vo || H.working(); b.setAttribute("aria-disabled", String(b.disabled)); acts.appendChild(b); }
      if (!blank && st.spelledUndo) {
        const h = st.spelledUndo.heard, b = btn("mini spelled-undo", "spelled-undo", 'Heard "' + h + '" · Undo');
        b.dataset.value = h; b.disabled = vo || H.working(); b.setAttribute("aria-disabled", String(b.disabled));
        b.title = "You spelled this name. Undo puts back the words that were heard."; b.setAttribute("aria-label", "Undo spelling: use " + h + " for this row");
        acts.appendChild(b);
      }
      if (st.canConfirm) { const b = btn("mini solid confirm-btn", "confirm", "Confirm as is"); b.disabled = vo; b.title = "Accept this medicine exactly as written"; b.setAttribute("aria-label", "Confirm as is: " + name); acts.appendChild(b); }
      if (st.canSpell) {
        const b = btn("mini", "spell"); b.disabled = vo; b.append(icon("pencil", 14), el("span", null, st.spellLabel));
        b.title = "Pick or type the right name. Only this row changes."; b.setAttribute("aria-label", st.spellLabel + ": " + name);
        b.setAttribute("aria-haspopup", "dialog"); b.setAttribute("aria-controls", "spellDlg"); b.setAttribute("aria-expanded", String(SpellModal.isOpenFor(tr.dataset.rowid)));
        acts.appendChild(b);
      }
      if (st.canReopen) { const b = btn("mini confirm-btn", "confirm", "Reopen"); b.disabled = vo; b.title = "Reopen this row for checking"; acts.appendChild(b); }
    }
    if (hadFocus) (acts.querySelector('button[data-action="confirm"]') || box).focus();      // the rebuilt button takes over keyboard focus
  }
  function sync() {                                // the summary bar and the Save button, from the same rules as the rows
    if (!H) return;
    SpellModal.sweep();                            // row deleted: its dialog goes
    let needs = 0, checking = 0;
    const live = rows().filter((tr) => !isBlank(tr));
    live.forEach((tr) => { if (rx(tr).checking) checking++; if (needsYou(tr)) needs++; });
    const s = RxState.summary({ total: live.length, needs, checking });
    $("rxBar").hidden = !H.hasSheet();
    $("rxTitle").textContent = s.title;
    $("rxReady").lastChild.textContent = s.ready; $("rxNeeds").lastChild.textContent = s.needs;
    $("rxNeeds").dataset.state = needs ? "dose" : "ok";
    const vo = !!(window.Authorship && Authorship.isViewOnly());
    rows().forEach((tr) => ['[data-action="dym"]', '[data-action="spelled-undo"]'].forEach((q) => { const b = tr.querySelector(q); if (b) { b.disabled = vo || H.working(); b.setAttribute("aria-disabled", String(b.disabled)); } }));   // looks as dead as it is while busy
    H.saveBtn.textContent = vo ? "View only" : s.saveLabel;
    H.saveBtn.disabled = H.working() || s.saveDisabled || vo;
  }
  // ---- Spell it: a dialog (spellmodal.js) for one row; the answer from check-row replaces that row's name only ----------------
  function bodyFor(tr, name) {                      // the request: this row, plus the page's grounding text (dropped when over the server's caps)
    const row = {}; COLS.forEach((c) => { row[c] = val(tr, c); });
    if (name) row.name = name;
    const t = H.transcript(), a = H.ageSex();
    return { row, transcript: typeof t === "string" && t.length <= 20000 ? t : "", age_sex: typeof a === "string" && a.length <= 40 ? a : "" };
  }
  const tooBig = (s) => s.length > 60 || s.split(" ").length > 8;      // the server would answer 400 for these: do not ask it

  function openSpell(tr) {
    if (H.working()) { if (H.notify) H.notify("Wait for the page to finish."); return; }
    if (viewOnly()) return;
    const rowid = tr.dataset.rowid, dictated = val(tr, "name");
    rx(tr).spellFromConfirmed = H.confirmed().has(rowid);
    SpellModal.open({ rowid, title: "Spell " + (dictated || "medicine"), opener: () => tr.querySelector('[data-action="spell"]'), alive: () => tr.isConnected,
      problem: tooBig(dictated) ? RxState.typedProblem(dictated) + " You can still type the name." : "",
      load: () => H.post(URL_CHECK, bodyFor(tr), CHECK_MS), search: (name, signal) => H.post(URL_CHECK, bodyFor(tr, name), CHECK_MS, signal), use: (name) => useName(tr, name),
      onClose: () => { const t = tr.querySelector('[data-action="spell"]') || tr.querySelector(".rx-state"); if (t) t.focus(); } });
  }

  async function useName(tr, raw) {
    const r = rx(tr), rowid = tr.dataset.rowid;
    if (r.checking || H.working() || viewOnly()) return;
    const name = RxState.cleanTyped(raw), problem = RxState.typedProblem(name);
    if (problem) { if (SpellModal.isOpenFor(rowid)) SpellModal.say(rowid, problem, true); else { r.note = problem; renderRow(tr); } return; }
    const tok = ++seq, before = H.snapshot(tr), was = H.confirmed().has(rowid), mtok = SpellModal.tokenFor(rowid);
    r.req = tok; r.checking = true; r.note = ""; SpellModal.say(rowid, ""); SpellModal.setChecking(rowid, true); renderRow(tr); sync();
    const fail = (m) => {
      r.checking = false; r.note = m + " The row is unchanged.";
      SpellModal.setChecking(rowid, false); SpellModal.say(rowid, r.note, true);
      renderRow(tr); sync();
    };
    try {
      const res = await H.post(URL_CHECK, bodyFor(tr, name), CHECK_MS);
      if (!tr.isConnected || tr._rx !== r || r.req !== tok) return;           // deleted, edited or undone while we waited: drop the answer
      const row = res && res.row;
      if (!row || typeof row !== "object") { fail("The answer was not understood."); return; }
      setCell(tr, "name", typeof row.name === "string" && row.name.trim() ? row.name.trim() : name);   // only the name and the instructions marker come back;
      if (typeof row.instructions === "string") setCell(tr, "instructions", row.instructions);         // form, strength, dose, timing, duration stay as dictated
      tr.dataset.status = typeof row.status === "string" ? row.status : "";
      tr.dataset.lexicon = typeof row.lexicon_match === "string" ? row.lexicon_match : "";
      r.meta = RxState.metaOf(row); r.checking = false; r.how = ""; r.note = "";
      if (RxState.afterSpell(row.status) === "you") { H.confirmed().add(rowid); r.how = "spell"; stripMarker(tr); }   // the doctor chose the name: the check-row marker goes
      // (confirmed is updated BEFORE the render, or "you chose" is reset)
      else { H.confirmed().delete(rowid); r.note = 'Name changed to "' + val(tr, "name") + '". It still needs your decision.'; }
      H.pushUndo({ type: "respell", rowid, data: before, wasConfirmed: was }, "Changed " + (before.name || "medicine") + " to " + val(tr, "name") + ".");
      const keep = !!mtok && SpellModal.tokenFor(rowid) === mtok, ae = document.activeElement;      // focus moves only if the dialog that asked is still the one open, or nothing has focus
      SpellModal.closeFor(rowid, false); renderRow(tr); H.changed(); if (keep || !ae || ae === document.body) focusAfterSpell(tr);
    } catch (e) { if (tr.isConnected && tr._rx === r && r.req === tok) fail(RxState.errorText(e)); }
  }

  function stripMarker(tr) {                       // true when the Instructions cell changed
    const n = tr.querySelector('[data-col="instructions"]');
    if (!n) return false;
    const was = n.textContent, now = RxState.stripMarker(was);
    if (now === was) return false;
    n.textContent = now; return true;
  }
  function pickChip(tr, value) {                   // a tap sets the cell; it confirms an unverified-strength row, never a dose-check one
    if (H.working() || viewOnly() || rx(tr).checking) return;
    const n = tr.querySelector('[data-col="strength"]'); if (n) n.textContent = value;
    const r = rx(tr);
    if (tr.dataset.status === "dose-check") { r.how = "chip-open"; r.meta = Object.assign({}, r.meta, { dose_note: "" }); }   // the old dose note is stale; a re-check on a chip tap is later work
    else { r.how = "chip"; H.confirmed().add(tr.dataset.rowid); stripMarker(tr); }   // the doctor settled the strength: its marker must not print
    renderRow(tr); H.changed(); focusState(tr);
  }
  function onClick(e) {
    const b = e.target && e.target.closest ? e.target.closest("button[data-action]") : null;
    if (!b) return;                                 // pickChip, openSpell and useName each refuse when view-only or working
    const tr = b.closest("tr[data-index]");
    if (!tr) return;
    const a = b.dataset.action;
    if (a === "chip") pickChip(tr, b.dataset.value);
    else if (a === "spell") openSpell(tr);
    else if (a === "dym" || a === "spelled-undo") useName(tr, b.dataset.value);   // Undo of a spelling: the heard words, checked like any typed name
  }
  function onKey(e) {                              // ArrowLeft / ArrowRight step between a row's buttons; Tab and Shift+Tab stay native
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;   // Alt+Left is the browser's Back
    const b = e.target && e.target.closest ? e.target.closest("button") : null;
    if (!b || !b.parentNode || !b.parentNode.classList.contains("rx-acts")) return;   // a medicine cell (contenteditable) keeps its caret keys
    const btns = [...b.parentNode.children].filter((n) => n.tagName === "BUTTON" && !n.disabled), i = btns.indexOf(b);
    const to = btns[i + (e.key === "ArrowRight" ? 1 : -1)];
    e.preventDefault();
    if (to) to.focus();
  }
  function init(hooks) {
    H = hooks;
    if (bound !== H.body) { H.body.addEventListener("click", onClick); H.body.addEventListener("keydown", onKey); bound = H.body; }   // a second init() must not bind twice
    [["rxReady", "check-circle"], ["rxNeeds", "triangle"]].forEach((p) => { const n = $(p[0]); if (!n.children.length) n.append(icon(p[1], 14), el("span")); });
    topbarHeight();
    const tb = document.querySelector(".topbar");
    if (tb && window.ResizeObserver && !roBound) { new ResizeObserver(topbarHeight).observe(tb); roBound = true; }      // the top bar can wrap after init (profile text, fonts)
    if (!resizeBound && window.addEventListener) { window.addEventListener("resize", topbarHeight); resizeBound = true; }
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(topbarHeight);
  }
  function topbarHeight() {                        // the sticky bar sits under the top bar, whatever height it wraps to
    const t = document.querySelector(".topbar");
    if (t) document.documentElement.style.setProperty("--topbar-h", t.offsetHeight + "px");
  }
  // app.js calls these: attach() when a row is built, onEdit() after a hand edit, meta() for the undo snapshot.
  function attach(tr, src) { tr._rx = fresh(src); }
  function onEdit(tr, target) {
    const c = target && target.closest ? target.closest("[data-col]") : null, r = rx(tr);
    r.meta = RxState.afterEdit(r.meta, c ? c.dataset.col : ""); r.how = ""; r.note = "";
    r.checking = false; r.req = ++seq;                // a pending check must not overwrite the edit; its dialog (suggestions of the old name) closes too
    SpellModal.closeFor(tr.dataset.rowid, false);
  }
  function restore(rec) {                             // undo of "Use this": the row as it was; returns the element to focus
    const tr = rows().find((t) => t.dataset.rowid === rec.rowid);
    if (!tr) return null;
    ["name", "instructions"].forEach((c) => setCell(tr, c, rec.data[c] || ""));   // never the dose, timing or duration: a hand edit made after Use this stays
    tr.dataset.status = rec.data.status || ""; tr.dataset.lexicon = rec.data.lexicon_match || "";
    SpellModal.closeFor(rec.rowid, false);
    if (tr._rx) { tr._rx.checking = false; tr._rx.req = ++seq; }   // a pending check on the old state must be dropped
    tr._rx = fresh(rec.data);
    if (rec.wasConfirmed) H.confirmed().add(rec.rowid); else H.confirmed().delete(rec.rowid);   // before the render, like a row undo
    renderRow(tr); sync();
    return tr.querySelector(".rx-state");
  }
  const meta = (tr) => Object.assign({}, rx(tr).meta, { how: rx(tr).how });
  // The fields the server reads back: heard + lookalike always; a doctor-entered generic (and its pending flag), a non-empty suggestion and spelled_heard.
  const wire = (tr) => {
    const m = rx(tr).meta || {}, s = (v) => (typeof v === "string" ? v : "");
    const w = { heard: s(m.heard), lookalike: s(m.lookalike) };
    if (m.generic_source === "doctor") { w.generic = s(m.generic); w.generic_source = "doctor"; w.generic_pending = m.generic_pending === true; }
    if (s(m.generic_suggestion)) w.generic_suggestion = m.generic_suggestion;
    if (s(m.spelled_heard)) w.spelled_heard = m.spelled_heard;          // a correction keeps the Undo on rows it leaves alone
    return w;
  };
  const needsYou = (tr) => !isBlank(tr) && RxState.rowState(rowOf(tr), ctxOf(tr)).needsYou;       // the bar, the open rows and the block panel share this
  // Keyboard flow: after a confirm the cursor goes to the next row that still needs the doctor (same order as the sheet), wrapping to the
  // top, then to the first red test's Keep (#pIx), then to Save. A row with no Confirm button gets its first action. Called only right after a
  // confirm and when a sheet first appears.
  const openList = () => rows().filter(needsYou);
  const redKeep = () => {                          // a test the doctor never said (dictated, not-dictated) blocks Save: it comes first
    const ul = $("pIx"), li = ul && ul.querySelector('li.ix-item[data-status="not-dictated"][data-source="dictated"]'), k = li && li.querySelector(".ix-keep");
    return k && !k.hidden ? k : null;
  };
  function focusRow(tr) {
    const box = tr.querySelector(".rx-acts"), acts = box ? [...box.children].filter((b) => b.dataset && b.dataset.action && !b.disabled) : [];
    const pick = acts.find((b) => b.dataset.action === "confirm" && b.className.split(/\s+/).includes("solid")) || acts[0] || tr.querySelector(".rx-state");
    if (pick) pick.focus({ preventScroll: false });
  }
  function afterConfirm(tr) {
    if (!H || viewOnly()) return;
    const open = openList(), all = rows(), at = all.indexOf(tr);
    if (!open.length) { const k = redKeep(); if (k) k.focus({ preventScroll: false }); else if (!H.saveBtn.disabled) H.saveBtn.focus({ preventScroll: false }); return; }
    focusRow(open.find((t) => all.indexOf(t) > at) || open[0]);
  }
  function typingElsewhere() {                     // the answer arrives late: never pull focus out of a field the doctor is in
    const a = document.activeElement;
    if (!a || a === document.body) return false;
    const tag = String(a.tagName || "").toUpperCase(), ce = a.isContentEditable || (a.getAttribute && ["", "true", "plaintext-only"].includes(a.getAttribute("contenteditable")));
    if (tag === "INPUT" || tag === "TEXTAREA" || ce) return true;
    const sheet = $("sheet"); let inSheet = false, inActs = false;
    for (let n = a; n; n = n.parentNode) { if (n === sheet) inSheet = true; if (n.className && String(n.className).split(/\s+/).includes("rx-acts")) inActs = true; }
    return inSheet && !inActs;
  }
  function focusFirst() {                          // a sheet just appeared: start on the first flagged row, or leave focus alone
    if (!H || viewOnly() || typingElsewhere()) return;
    const open = openList();
    if (open.length) focusRow(open[0]);
  }
  // The sentence for a block-panel entry; a confirmed row the server still refuses on its generic says so.
  const blockReason = (tr, b) => (b && b.generic === "invalid" && !needsYou(tr) ? "The generic you entered was not accepted. Edit it or clear it." : reasonFor(tr));
  // A block-panel entry still stands while the row needs you, or while the doctor generic the server refused is still there
  // (cleared or fixed: the entry goes, it never lingers until the next save).
  const blockStands = (tr, b) => needsYou(tr) || (!!b && b.generic === "invalid" && !!window.GenericEdit && GenericEdit.problemOf(rx(tr).meta) !== "");
  return { init, attach, renderRow, sync, onEdit, meta, wire, needsYou, blockReason, blockStands, reasonFor, restore, isBlank, stripMarker, afterConfirm, focusFirst };
})();
