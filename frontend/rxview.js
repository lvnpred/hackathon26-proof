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
  };
  let H = null, seq = 0, bound = null, resizeBound = false, roBound = false;
  const $ = (id) => document.getElementById(id);
  const val = (tr, c) => { const n = tr.querySelector('[data-col="' + c + '"]'); return (n ? n.textContent : "").replace(/\s+/g, " ").trim(); };
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
  const fresh = (src) => ({ meta: RxState.metaOf(src), how: (src && src.how) || "", note: "", req: ++seq });
  const rx = (tr) => tr._rx || (tr._rx = fresh(null));
  const rowOf = (tr) => Object.assign({ status: tr.dataset.status || "", name: val(tr, "name"), strength: val(tr, "strength") }, rx(tr).meta);
  const EMPTY = "Empty row: removed when you save";
  const reasonFor = (tr) => isBlank(tr) ? EMPTY : RxState.rowState(rowOf(tr), ctxOf(tr)).reason;     // the reason the row itself shows (the 409 panel uses it)
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
    if (blank) delete tr.dataset.rxstate; else tr.dataset.rxstate = st.state;
    med.querySelectorAll(".rx-extra").forEach((n) => n.remove());                       // generic line and chips: screen only
    if (!blank && r.meta.generic) med.appendChild(el("div", "rx-extra rx-sub no-print", "generic: " + r.meta.generic));
    if (st.chips.length) {
      const box = el("div", "rx-extra rx-chips no-print");
      box.appendChild(el("span", "rx-hint", "Strengths:"));
      st.chips.forEach((c) => {
        const b = btn("rx-chip" + (c.usual ? " usual" : ""), "chip", c.label);
        b.disabled = vo;
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
    if (st.canConfirm) { const b = btn("mini solid confirm-btn", "confirm", "Confirm as is"); b.disabled = vo; b.title = "Accept this medicine exactly as written"; b.setAttribute("aria-label", "Confirm " + name + " as is"); acts.appendChild(b); }
    if (st.canReopen) { const b = btn("mini confirm-btn", "confirm", "Reopen"); b.disabled = vo; b.title = "Reopen this row for checking"; acts.appendChild(b); }
    if (hadFocus) (acts.querySelector('button[data-action="confirm"]') || box).focus();      // the rebuilt button takes over keyboard focus
  }
  function sync() {                                // the summary bar and the Save button, from the same rules as the rows
    if (!H) return;
    let needs = 0;
    const live = rows().filter((tr) => !isBlank(tr));
    live.forEach((tr) => { if (RxState.rowState(rowOf(tr), ctxOf(tr)).needsYou) needs++; });
    const s = RxState.summary({ total: live.length, needs, checking: 0 });
    $("rxBar").hidden = !H.hasSheet();
    $("rxTitle").textContent = s.title;
    $("rxReady").lastChild.textContent = s.ready; $("rxNeeds").lastChild.textContent = s.needs;
    $("rxNeeds").dataset.state = needs ? "dose" : "ok";
    const vo = !!(window.Authorship && Authorship.isViewOnly());
    H.saveBtn.textContent = vo ? "View only" : s.saveLabel;
    H.saveBtn.disabled = H.working() || s.saveDisabled || vo;
  }
  function pickChip(tr, value) {                   // a tap sets the cell; it confirms an unverified-strength row, never a dose-check one
    if (H.working()) return;
    const n = tr.querySelector('[data-col="strength"]'); if (n) n.textContent = value;
    const r = rx(tr);
    if (tr.dataset.status === "dose-check") { r.how = "chip-open"; r.meta = Object.assign({}, r.meta, { dose_note: "" }); }   // the old dose note is stale; the re-check is I1-e3
    else { r.how = "chip"; H.confirmed().add(tr.dataset.rowid); }
    renderRow(tr); H.changed();
    const s = tr.querySelector(".rx-state"); if (s) s.focus();
  }
  function onClick(e) {
    const b = e.target && e.target.closest ? e.target.closest('button[data-action="chip"]') : null;
    if (b && !(window.Authorship && Authorship.isViewOnly())) pickChip(b.closest("tr[data-index]"), b.dataset.value);
  }
  function init(hooks) {
    H = hooks;
    if (bound !== H.body) { H.body.addEventListener("click", onClick); bound = H.body; }          // a second init() must not bind twice
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
  }
  const meta = (tr) => Object.assign({}, rx(tr).meta, { how: rx(tr).how });
  const wire = (tr) => { const m = rx(tr).meta || {}; return { heard: typeof m.heard === "string" ? m.heard : "", lookalike: typeof m.lookalike === "string" ? m.lookalike : "" }; };   // the only meta fields the server reads back
  return { init, attach, renderRow, sync, onEdit, meta, wire, reasonFor, isBlank };
})();
