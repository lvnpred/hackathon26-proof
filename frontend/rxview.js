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
  let H = null, seq = 0, bound = null, resizeBound = false, roBound = false, paneObs = null;
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
  const fresh = (src) => ({ meta: RxState.metaOf(src), how: (src && src.how) || "", note: "", checking: false, req: ++seq, panel: null });
  const rx = (tr) => tr._rx || (tr._rx = fresh(null));
  const rowOf = (tr) => Object.assign({ status: tr.dataset.status || "", name: val(tr, "name"), strength: val(tr, "strength") }, rx(tr).meta);
  const EMPTY = "Empty row: removed when you save";
  const reasonFor = (tr) => isBlank(tr) ? EMPTY : RxState.rowState(rowOf(tr), ctxOf(tr)).reason;     // the reason the row itself shows (the 409 panel uses it)
  const focusState = (tr) => { const s = tr.querySelector(".rx-state"); if (s) s.focus(); };
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
    if (r.panel && !r.checking && !st.canSpell) { r.panel.remove(); r.panel = null; }          // confirmed (or otherwise settled) from outside: no panel beside a missing Spell button
    if (blank) delete tr.dataset.rxstate; else tr.dataset.rxstate = st.state;
    med.querySelectorAll(".rx-extra").forEach((n) => n.remove());                       // generic line and chips: screen only
    if (!blank && r.meta.generic) med.appendChild(el("div", "rx-extra rx-sub no-print", "generic: " + r.meta.generic));
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
    box.children[1].textContent = st.reason; box.children[2].textContent = r.note;
    const acts = box.children[3], hadFocus = !!document.activeElement && [...acts.children].includes(document.activeElement);
    acts.textContent = "";
    if (r.checking) {                                 // only this row waits; the other rows keep working
      const c = el("div", "rx-checking"); c.append(el("span", "rx-spin"), el("span", null, "Checking this medicine..."));
      acts.appendChild(c);
    } else {
      if (st.canConfirm) { const b = btn("mini solid confirm-btn", "confirm", "Confirm as is"); b.disabled = vo; b.title = "Accept this medicine exactly as written"; b.setAttribute("aria-label", "Confirm " + name + " as is"); acts.appendChild(b); }
      if (st.canSpell) {
        const b = btn("mini", "spell"); b.disabled = vo; b.append(icon("pencil", 14), el("span", null, "Spell it"));
        b.title = "Pick or type the right name. Only this row changes."; b.setAttribute("aria-label", "Spell " + name);
        b.setAttribute("aria-expanded", String(!!r.panel)); b.setAttribute("aria-controls", "rxspell-" + tr.dataset.rowid);
        acts.appendChild(b);
      }
      if (st.canReopen) { const b = btn("mini confirm-btn", "confirm", "Reopen"); b.disabled = vo; b.title = "Reopen this row for checking"; acts.appendChild(b); }
    }
    if (hadFocus) (acts.querySelector('button[data-action="confirm"]') || box).focus();      // the rebuilt button takes over keyboard focus
  }
  function sync() {                                // the summary bar and the Save button, from the same rules as the rows
    if (!H) return;
    [...H.body.querySelectorAll("tr.rx-spell-row")].filter((p) => p._for && !p._for.isConnected).forEach((p) => p.remove());   // row deleted: its panel goes
    let needs = 0, checking = 0;
    const live = rows().filter((tr) => !isBlank(tr));
    live.forEach((tr) => { if (rx(tr).checking) checking++; if (RxState.rowState(rowOf(tr), ctxOf(tr)).needsYou) needs++; });
    const s = RxState.summary({ total: live.length, needs, checking });
    $("rxBar").hidden = !H.hasSheet();
    $("rxTitle").textContent = s.title;
    $("rxReady").lastChild.textContent = s.ready; $("rxNeeds").lastChild.textContent = s.needs;
    $("rxNeeds").dataset.state = needs ? "dose" : "ok";
    const vo = !!(window.Authorship && Authorship.isViewOnly());
    H.saveBtn.textContent = vo ? "View only" : s.saveLabel;
    H.saveBtn.disabled = H.working() || s.saveDisabled || vo;
  }
  // ---- Spell it: an inline panel under one row; the answer from check-row replaces that row's name only ----------------
  function bodyFor(tr, name) {                      // the request: this row, plus the page's grounding text (dropped when over the server's caps)
    const row = {}; COLS.forEach((c) => { row[c] = val(tr, c); });
    if (name) row.name = name;
    const t = H.transcript(), a = H.ageSex();
    return { row, transcript: typeof t === "string" && t.length <= 20000 ? t : "", age_sex: typeof a === "string" && a.length <= 40 ? a : "" };
  }
  function closePanel(tr, refocus) {
    const r = rx(tr);
    if (r.panel) { r.panel.remove(); r.panel = null; }
    renderRow(tr);
    if (refocus) { const b = tr.querySelector('[data-action="spell"]'); if (b) b.focus(); }
  }
  const say = (panel, msg) => { panel.querySelector(".rx-msg").textContent = msg || ""; };
  const busy = (panel, on) => { panel.querySelectorAll("button, input").forEach((n) => { if (n.dataset.action !== "later") n.disabled = on; }); };
  const tooBig = (s) => s.length > 60 || s.split(" ").length > 8;      // the server would answer 400 for these: do not ask it

  function openSpell(tr) {
    if (H.working() || viewOnly()) return;
    rows().forEach((o) => { if (o !== tr && rx(o).panel) closePanel(o); });
    const r = rx(tr);
    if (r.panel) { closePanel(tr, true); return; }
    const row = el("tr", "rx-spell-row no-print"), td = el("td"); td.colSpan = 8;
    row.id = "rxspell-" + tr.dataset.rowid; row._for = tr; row.appendChild(td);
    const head = el("div", "rx-spell-head"); head.append(el("b", null, "Spell " + (val(tr, "name") || "medicine")), el("span", "rx-hint", "Only this row changes"));
    const sugs = el("div", "rx-sugs"); sugs.appendChild(el("span", "rx-hint", "Looking for names..."));
    const input = el("input"); input.type = "text"; input.id = "rxin-" + tr.dataset.rowid; input.autocomplete = "off"; input.spellcheck = false; input.maxLength = 60;
    input.placeholder = "p r e d n i s o l o n e";
    const lab = el("label", "rx-hint", "Or type the name"); lab.htmlFor = input.id;
    const use = btn("primary", "use", "Use this"), later = btn("", "later", "Say the letters (later)");
    later.disabled = true; later.title = "Planned for later, only if it proves accurate";
    const close = btn("", "close-spell", "Close");
    const line = el("div", "rx-spell-line"); line.append(input, use, later, close);
    const msg = el("div", "rx-msg"); msg.setAttribute("role", "alert");
    const box = el("div", "rx-spell-box"); box.append(head, el("div", "rx-hint", "Did you mean"), sugs, lab, line, msg); td.appendChild(box);   // the box stays inside the visible pane (rx.css)
    paneWidth();
    tr.after(row); r.panel = row; renderRow(tr); input.focus();
    ["input", "keyup", "paste"].forEach((t) => row.addEventListener(t, (e) => e.stopPropagation()));   // typing here is not a sheet edit
    const tok = ++seq; row._tok = tok;
    const dictated = val(tr, "name");
    if (tooBig(dictated)) { sugs.textContent = ""; say(row, RxState.typedProblem(dictated) + " You can still type the name."); return; }
    H.post(URL_CHECK, bodyFor(tr), CHECK_MS).then((res) => {
      if (row._tok !== tok || !row.isConnected) return;
      const seen = new Set(), list = (Array.isArray(res && res.suggestions) ? res.suggestions : []).map(String).filter((s) => s && !seen.has(s.toLowerCase()) && seen.add(s.toLowerCase())).slice(0, 6);
      sugs.textContent = "";
      if (!list.length) sugs.appendChild(el("span", "rx-hint", "No close names found. Type the name below."));
      list.forEach((s) => { const b = btn("sug", "sug", s); b.dataset.value = s; sugs.appendChild(b); });   // the cell stays as dictated until one is tapped
    }).catch((e) => { if (row._tok === tok && row.isConnected) { sugs.textContent = ""; say(row, RxState.errorText(e) + " You can still type the name."); } });
  }

  async function useName(tr, raw) {
    const r = rx(tr), panel = r.panel;
    if (r.checking || H.working() || viewOnly() || !panel) return;
    const name = RxState.cleanTyped(raw), problem = RxState.typedProblem(name);
    if (problem) { say(panel, problem); panel.querySelector("input").focus(); return; }
    const rowid = tr.dataset.rowid, tok = ++seq, before = H.snapshot(tr), was = H.confirmed().has(rowid);
    r.req = tok; r.checking = true; r.note = ""; say(panel, ""); busy(panel, true); renderRow(tr); sync();
    const fail = (m) => {
      r.checking = false; r.note = m + " The row is unchanged.";
      if (r.panel) { say(r.panel, r.note); busy(r.panel, false); r.panel.querySelector("input").focus(); }
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
      if (RxState.afterSpell(row.status) === "you") { H.confirmed().add(rowid); r.how = "spell"; }     // confirmed BEFORE the render, or "you chose" is reset
      else { H.confirmed().delete(rowid); r.note = 'Name changed to "' + val(tr, "name") + '". It still needs your decision.'; }
      H.pushUndo({ type: "respell", rowid, data: before, wasConfirmed: was }, "Changed " + (before.name || "medicine") + " to " + val(tr, "name") + ".");
      closePanel(tr); H.changed(); focusState(tr);
    } catch (e) { if (tr.isConnected && tr._rx === r && r.req === tok) fail(RxState.errorText(e)); }
  }

  function pickChip(tr, value) {                   // a tap sets the cell; it confirms an unverified-strength row, never a dose-check one
    if (H.working() || viewOnly() || rx(tr).checking) return;
    const n = tr.querySelector('[data-col="strength"]'); if (n) n.textContent = value;
    const r = rx(tr);
    if (tr.dataset.status === "dose-check") { r.how = "chip-open"; r.meta = Object.assign({}, r.meta, { dose_note: "" }); }   // the old dose note is stale; a re-check on a chip tap is later work
    else { r.how = "chip"; H.confirmed().add(tr.dataset.rowid); }
    renderRow(tr); H.changed(); focusState(tr);
  }
  function onClick(e) {
    const b = e.target && e.target.closest ? e.target.closest("button[data-action]") : null;
    if (!b) return;                                 // pickChip, openSpell and useName each refuse when view-only or working
    const panel = b.closest("tr.rx-spell-row"), tr = panel ? panel._for : b.closest("tr[data-index]");
    if (!tr) return;
    const a = b.dataset.action;
    if (a === "chip") pickChip(tr, b.dataset.value);
    else if (a === "spell") openSpell(tr);
    else if (a === "close-spell") closePanel(tr, true);
    else if (a === "sug") useName(tr, b.dataset.value);
    else if (a === "use") useName(tr, panel.querySelector("input").value);
  }
  function onKey(e) {
    const panel = e.target && e.target.closest ? e.target.closest("tr.rx-spell-row") : null;
    if (!panel) return;
    if (e.key === "Escape") { e.preventDefault(); if (!rx(panel._for).checking) closePanel(panel._for, true); }   // a pending check is not cancelled
    else if (e.key === "Enter" && e.target.tagName === "INPUT") { e.preventDefault(); useName(panel._for, e.target.value); }
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
    paneWidth();
  }
  function paneWidth() {                           // the Spell panel is as wide as the visible content of the element that scrolls the table (rxstate.js paneWidth)
    const s = $("sheet"), t = s && s.querySelector ? s.querySelector("table.rx") : null, cs = window.getComputedStyle;
    if (!s || !cs) return;
    const a = cs(s), b = t ? cs(t) : {};
    const w = RxState.paneWidth({ sheetClient: s.clientWidth, sheetPadL: a.paddingLeft, sheetPadR: a.paddingRight,
      tableClient: t ? t.clientWidth : 0, tablePadL: b.paddingLeft, tablePadR: b.paddingRight, tableOverflowX: b.overflowX, tableDisplay: b.display }).width;
    if (w > 0) document.documentElement.style.setProperty("--rx-pane", w + "px");
    if (window.ResizeObserver && !paneObs) { paneObs = new ResizeObserver(paneWidth); paneObs.observe(s); if (t) paneObs.observe(t); }   // the scroller can change width without a window resize
  }
  // app.js calls these: attach() when a row is built, onEdit() after a hand edit, meta() for the undo snapshot.
  function attach(tr, src) { tr._rx = fresh(src); }
  function onEdit(tr, target) {
    const c = target && target.closest ? target.closest("[data-col]") : null, r = rx(tr);
    r.meta = RxState.afterEdit(r.meta, c ? c.dataset.col : ""); r.how = ""; r.note = "";
    r.checking = false; r.req = ++seq;                // a pending check must not overwrite the edit; its panel (suggestions of the old name) goes too
    if (r.panel) { r.panel.remove(); r.panel = null; }
  }
  function restore(rec) {                             // undo of "Use this": the row as it was; returns the element to focus
    const tr = rows().find((t) => t.dataset.rowid === rec.rowid);
    if (!tr) return null;
    ["name", "instructions"].forEach((c) => setCell(tr, c, rec.data[c] || ""));   // never the dose, timing or duration: a hand edit made after Use this stays
    tr.dataset.status = rec.data.status || ""; tr.dataset.lexicon = rec.data.lexicon_match || "";
    if (tr._rx) { if (tr._rx.panel) tr._rx.panel.remove(); tr._rx.checking = false; tr._rx.req = ++seq; }   // a pending check on the old state must be dropped
    tr._rx = fresh(rec.data);
    if (rec.wasConfirmed) H.confirmed().add(rec.rowid); else H.confirmed().delete(rec.rowid);   // before the render, like a row undo
    renderRow(tr); sync();
    return tr.querySelector(".rx-state");
  }
  const meta = (tr) => Object.assign({}, rx(tr).meta, { how: rx(tr).how });
  const wire = (tr) => { const m = rx(tr).meta || {}; return { heard: typeof m.heard === "string" ? m.heard : "", lookalike: typeof m.lookalike === "string" ? m.lookalike : "" }; };   // the only meta fields the server reads back
  return { init, attach, renderRow, sync, onEdit, meta, wire, reasonFor, restore, isBlank };
})();
