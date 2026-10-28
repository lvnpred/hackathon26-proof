"use strict";
// The generic line under a medicine name (plan g, task 7): the editable generic, "Add generic" for a combination brand,
// the "AI suggests" line and the "Remember for this clinic" tick. rxview.js calls render() from renderRow, so one place
// draws the line; app.js reads rememberIndexes() for the save. DOM is built with createElement and textContent only.
window.GenericEdit = (function () {
  // The client mirror of doctor_dictation/core/doctor_generic.generic_problem: same messages, same rules, same order.
  // The server stays the authority. WS is Python's str.isspace set (what its \s and strip() use), not JavaScript's \s.
  const MESSAGES = {
    empty: "Type the generic, or press Cancel.",
    long: "The generic is too long (160 characters at most).",
    parts: "Separate the ingredients with +, for example Aceclofenac + Paracetamol.",
    many: "At most 6 ingredients.",
    chars: "Use letters, digits, spaces and . , ' ( ) / - only.",
  };
  const MAX_CHARS = 160, MAX_PARTS = 6;
  const WS = "[\\t-\\r\\x1c-\\x20\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]";
  const WS_RUN = new RegExp(WS + "+", "g"), WS_EDGE = new RegExp("^" + WS + "+|" + WS + "+$", "g");
  const PLUS = /(?<![\p{L}\p{N}_])plus(?![\p{L}\p{N}_])/giu;          // Python's \bplus\b, IGNORECASE, Unicode word characters
  const PART = /^(?:[0-9]+-)?[A-Za-z][A-Za-z0-9 .,'()/-]*$/;           // ASCII digits only, like the server's [0-9]
  const strip = (s) => s.replace(WS_EDGE, "");
  const fold = (s) => s.toUpperCase().toLowerCase();                   // close to str.casefold (ß, ſ, final sigma)
  function problem(raw) {
    if (typeof raw !== "string" || !strip(raw)) return MESSAGES.empty;
    const text = strip(raw.replace(WS_RUN, " ")).replace(PLUS, "+");
    if ([...text].length > MAX_CHARS) return MESSAGES.long;              // code points, like Python's len()
    const parts = text.split("+").map(strip);
    if (parts.some((p) => !p)) return MESSAGES.parts;
    const distinct = new Map();
    parts.forEach((p) => { if (!distinct.has(fold(p))) distinct.set(fold(p), p); });
    if (distinct.size > MAX_PARTS) return MESSAGES.many;
    for (const p of distinct.values()) if (!PART.test(p) || (p.match(/[A-Za-z]/g) || []).length < 3) return MESSAGES.chars;
    return "";
  }
  // The message for a row's own doctor generic ("" when it has none, or it is fine).
  const problemOf = (m) => (m && m.generic_source === "doctor" && m.generic ? problem(m.generic) : "");

  let H = null;
  const viewOnly = () => !!(window.Authorship && Authorship.isViewOnly());
  const ui = (tr) => tr._ge || (tr._ge = { open: false });               // page only: the empty box is open (Add generic, Type my own)
  function el(tag, cls, t) { const n = document.createElement(tag); if (cls) n.className = cls; if (t != null) n.textContent = t; return n; }
  const nameOf = (tr) => { const n = tr.querySelector('[data-col="name"]'); return (n ? n.textContent : "").replace(/\s+/g, " ").trim(); };
  function button(cls, text, fn) {
    const b = el("button", "rx-act mini " + cls, text); b.type = "button";
    b.addEventListener("click", () => { if (!(H && H.working()) && !viewOnly()) fn(); });
    return b;
  }

  // The doctor's generic for this row: "" removes a doctor generic; text makes it the doctor's, pending until confirmed.
  function apply(tr, text) {
    const r = tr._rx;
    if (!r || viewOnly()) return;
    const m = Object.assign({}, r.meta);
    if (!text) {
      if (m.generic_source !== "doctor") return;                       // nothing of the doctor's to remove
      const listed = typeof m.generic_listed === "string" ? m.generic_listed : "";
      m.generic = listed; m.generic_source = listed ? "lexicon" : ""; m.generic_pending = false;   // the listed generic comes back
      if (listed) { m.generic_listed = ""; m.remember_generic = false; }
    } else {
      // Q20: replaces a listed generic; only this prescription unless ticked. generic_listed (page only, never sent)
      // keeps the listed text, so clearing the override restores it.
      if (m.generic_source === "lexicon") m.generic_listed = String(m.generic || "");
      m.generic = text; m.generic_source = "doctor"; m.generic_pending = true;
    }
    r.meta = m; r.note = "";
    H.confirmed().delete(tr.dataset.rowid);
    RxView.renderRow(tr);                                               // a focused span is kept, only the state cell and the tick change
    H.changed();
  }
  function open(tr) {
    ui(tr).open = true; RxView.renderRow(tr);
    const s = tr.querySelector(".rx-gen-text"); if (s) s.focus();
  }

  function onPaste(e, tr, span) {                                       // plain text only, on one line
    e.preventDefault();
    const t = ((e.clipboardData && e.clipboardData.getData("text/plain")) || "").replace(/[\r\n]+/g, " ");
    if (document.execCommand && document.execCommand("insertText", false, t)) return;   // fires its own input event
    const sel = window.getSelection && window.getSelection();
    if (sel && sel.rangeCount) { const rg = sel.getRangeAt(0); rg.deleteContents(); rg.insertNode(document.createTextNode(t)); rg.collapse(false); }
    onInput(null, tr, span);
  }
  function onInput(e, tr, span) {
    if (e) e.stopPropagation();                                         // app.js's sheet listener would treat it as a cell edit
    if (span.children && span.children.length) span.textContent = span.textContent;   // markup that slipped in becomes text
    const text = span.textContent.trim();
    if (span.parentNode) span.parentNode.className = "rx-sub rx-gen" + (text ? "" : " no-print");
    apply(tr, text);
  }
  function editable(tr, span) {
    span.contentEditable = "true"; span.spellcheck = false;
    span.setAttribute("role", "textbox"); span.setAttribute("aria-label", "Generic of " + (nameOf(tr) || "this medicine"));
    span.addEventListener("input", (e) => onInput(e, tr, span));
    span.addEventListener("paste", (e) => onPaste(e, tr, span));
    span.addEventListener("drop", (e) => e.preventDefault());            // no dragged markup
    span.addEventListener("beforeinput", (e) => { const t = String(e.inputType || ""); if (t.indexOf("format") === 0 || t === "insertParagraph" || t === "insertLineBreak") e.preventDefault(); });
    span.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); span.blur(); } });
    span.addEventListener("blur", () => {                               // the screen shows what saves and prints
      const r = tr._rx, text = span.textContent.trim();
      if (!r) return;
      const closing = ui(tr).open && !text && r.meta.generic_source !== "doctor";   // an empty box left: back to the button or suggestion
      if (closing) ui(tr).open = false;
      if (closing || text !== String(r.meta.generic || "")) RxView.renderRow(tr);   // e.g. a listed generic emptied: its text comes back
    });
  }
  function remember(tr, r, line) {                                      // the tick: only on a doctor generic that replaced a listed one
    const m = r.meta, want = m.generic_source === "doctor" && !!m.generic_listed && !!m.generic;
    const old = line.querySelector(".rx-remember");
    if (!want) { if (old) old.remove(); return; }
    if (old) return;
    const lab = el("label", "rx-remember no-print"), cb = el("input", "rx-gen-remember");
    cb.type = "checkbox"; cb.checked = m.remember_generic === true;
    cb.addEventListener("input", (e) => e.stopPropagation());
    cb.addEventListener("change", (e) => {
      e.stopPropagation();
      const rr = tr._rx; if (!rr || viewOnly()) return;
      rr.meta = Object.assign({}, rr.meta, { remember_generic: cb.checked === true });
      H.changed();
    });
    lab.append(cb, el("span", null, " Remember for this clinic"));
    line.appendChild(lab);
  }
  function line(tr, r) {                                                // "generic: X": prints (the browser print shows it too)
    const m = r.meta, ln = el("div", "rx-sub rx-gen" + (m.generic ? "" : " no-print"), "generic: ");
    const span = el("span", "rx-gen-text", m.generic);
    if (!r.checking) editable(tr, span);                               // always: view-only can start or end after this render
    if (!r.checking && viewOnly()) { span.contentEditable = "false"; span.dataset.ro = "1"; }   // as Authorship.enforce does; clear() unlocks it
    ln.appendChild(span); remember(tr, r, ln);
    return ln;
  }
  function suggestion(tr, r) {                                          // screen only: the suggestion never prints
    const m = r.meta, unknown = m.generic_suggestion_unknown || [], ln = el("div", "rx-sugg no-print" + (unknown.length ? " amber" : ""));
    if (unknown.length) ln.setAttribute("title", "Not in the medicine list: " + unknown.join(", "));
    const t = el("span", "rx-sugg-text", "AI suggests: "); t.appendChild(el("b", null, m.generic_suggestion)); ln.appendChild(t);
    ln.append(button("rx-use-gen", "Use this", () => {                 // always built; rx.css hides them while view-only
      apply(tr, String(tr._rx.meta.generic_suggestion || "").trim());
      const s = tr.querySelector(".rx-state"); if (s) s.focus();
    }), button("rx-own-gen", "Type my own", () => open(tr)));
    return ln;
  }
  function kindOf(tr, r, blank) {
    if (blank) return "";
    const m = r.meta, gen = String(m.generic || "").trim();
    if (ui(tr).open || m.generic_source === "doctor" || (gen && !RxState.sameName(gen, nameOf(tr)))) return "line";
    if (gen) return "";                                                 // a generic-named row: rxview.js draws its "generic" tag
    if (String(m.generic_suggestion || "").trim()) return "sugg";
    return String(m.combo_base || "").trim() ? "add" : "";              // view-only: rx.css hides the button, the click refuses
  }
  // Draws (or removes) div.rx-genbox under the name; returns what it drew ("line", "sugg", "add" or "").
  function render(tr, r, st, hooks) {
    if (hooks) H = hooks;
    const med = tr.querySelector("td.med");
    if (!med || !r) return "";
    const kind = kindOf(tr, r, !st || !st.state);
    let box = med.querySelector(".rx-genbox");
    if (!kind) { if (box) box.remove(); ui(tr).open = false; return ""; }
    if (!box) { box = el("div", "rx-genbox"); med.appendChild(box); }  // built once per row, not an .rx-extra
    const span = box.querySelector(".rx-gen-text");
    if (span && document.activeElement === span) { remember(tr, r, span.parentNode); return "line"; }   // never rebuild a focused span
    box.textContent = "";
    if (kind === "line") box.appendChild(line(tr, r));
    else if (kind === "sugg") box.appendChild(suggestion(tr, r));
    else {
      const base = String(r.meta.combo_base).trim(), b = button("no-print rx-add-gen", "Add generic", () => open(tr));
      b.setAttribute("title", "A combination of " + base + ": add its generic"); box.appendChild(b);
    }
    return kind;
  }
  // The save's remember_generics: indexes (in the order given, the order of confirmed_rows) of ticked doctor generics.
  function rememberIndexes(rows) {
    const out = [];
    (Array.isArray(rows) ? rows : []).forEach((tr, i) => {
      const m = tr && tr._rx && tr._rx.meta;
      if (m && m.generic_source === "doctor" && m.remember_generic === true) out.push(i);
    });
    return out;
  }
  return { render, problem, problemOf, rememberIndexes, MESSAGES };
})();
