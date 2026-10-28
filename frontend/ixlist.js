"use strict";
// Investigation items on the sheet (plan PQ-h, task 9). The server sends each test as {text, canonical, status, source};
// this file draws one <li class="ix-item"> per test with its status chip, "Keep" (red only), "Remember for this clinic"
// with a "Full name" box, and an x button; "+ Add test" sits after the list. app.js only calls in: render, read,
// rememberIndexes, remove/insert (delete and Undo), showBlocked (the 409) and blockedMessage. DOM is built with
// createElement and textContent only, never markup (the x button takes only the fixed X_ICON line icon).
window.IxList = (function () {
  const X_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';
  const CHIPS = { verified: "In list", new: "New test", "not-dictated": "Not dictated" };
  const STATUSES = ["verified", "new", "not-dictated", ""], SOURCES = ["dictated", "doctor"];
  const TEXT_CHARS = 200, MAX_ITEMS = 12, LOOKUP_URL = "/api/v1/investigations/lookup", LOOKUP_MS = 8000;
  // Python's str.isspace set (what its \s and strip() use), as in genericedit.js, so blanks drop exactly as the
  // server's coerce_items drops them and the 409's indexes and remember_investigations point at the same tests.
  const WS = "[\\t-\\r\\x1c-\\x20\\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000]";
  const WS_RUN = new RegExp(WS + "+", "g"), WS_EDGE = new RegExp("^" + WS + "+|" + WS + "+$", "g");
  const NON_ALNUM = /[^\p{L}\p{N}]+/gu;                                // Python's [\W_]+ (Unicode)
  let H = { post: null, onChange() {}, onRemove() {}, working: () => false };
  const busy = () => !!(H.working && H.working());
  const viewOnly = () => !!(window.Authorship && Authorship.isViewOnly());
  const strip = (s) => s.replace(WS_EDGE, "");
  const changed = () => { if (H.onChange) H.onChange(); };
  function el(tag, cls, t) { const n = document.createElement(tag); if (cls) n.className = cls; if (t != null) n.textContent = t; return n; }

  // investigations.key: casefold, "&" as " and ", every run of non-alphanumerics one space, trimmed.
  function key(t) {
    const folded = (typeof t === "string" ? t : "").toUpperCase().toLowerCase().replace(/&/g, " and ");   // close to str.casefold
    return folded.replace(NON_ALNUM, " ").trim();
  }
  // investigations.coerce_items, for one item's text: whitespace runs to one space, stripped, 200 code points, stripped.
  function clean(raw) { return typeof raw === "string" ? strip([...strip(raw.replace(WS_RUN, " "))].slice(0, TEXT_CHARS).join("")) : ""; }
  // investigations.coerce_items for one value: a string is a dictated item; null when it is dropped.
  function coerce(v) {
    const raw = typeof v === "string" ? v : v && typeof v === "object" ? v.text : null;
    const text = clean(raw);
    if (!text) return null;
    const d = typeof v === "object" ? v : {};
    return { text, canonical: typeof d.canonical === "string" ? d.canonical : "",
      status: STATUSES.includes(d.status) ? d.status : "", source: SOURCES.includes(d.source) ? d.source : "dictated" };
  }
  // investigations.print_text: text, plus " (canonical)" when the two differ by name.
  function printText(item) {
    if (typeof item === "string") return strip(item);
    if (!item || typeof item !== "object") return "";
    const text = typeof item.text === "string" ? strip(item.text) : "";
    const canonical = typeof item.canonical === "string" ? strip(item.canonical) : "";
    return text && canonical && key(text) !== key(canonical) ? text + " (" + canonical + ")" : text;
  }

  const textOf = (li) => clean((li.querySelector(".ix-text") || { textContent: "" }).textContent);
  const itemOf = (li) => ({ text: textOf(li), canonical: li._ix.canonical, status: li._ix.status, source: li._ix.source });
  const canRemember = (li) => !!textOf(li) && (li._ix.status === "new" || li._ix.edited);

  // Redraws everything but the text: data-status/-source, the chip, the printed full name, Keep, Remember.
  function paint(li) {
    const s = li._ix, item = itemOf(li);
    li.dataset.status = s.status; li.dataset.source = s.source;
    const chip = li.querySelector(".ix-chip");
    chip.textContent = CHIPS[s.status] || ""; chip.dataset.chip = s.status; chip.hidden = !CHIPS[s.status];
    const full = printText(item), shown = item.text && full !== item.text ? full.slice(item.text.length) : "";
    li.querySelector(".ix-full").textContent = shown;                       // " (Renal Function Test)": prints
    const keep = li.querySelector(".ix-keep");
    if (keep) keep.hidden = s.status !== "not-dictated";
    const lab = li.querySelector(".ix-remember"), box = li.querySelector(".ix-fullname");
    if (lab) {
      const can = canRemember(li);
      lab.hidden = !can;
      lab.querySelector("input").checked = can && s.remember;
      box.hidden = !(can && s.remember);
      const input = box.querySelector("input");
      if (document.activeElement !== input) input.value = s.canonical;
    }
    const x = li.querySelector(".x-btn");
    if (x) x.setAttribute("aria-label", item.text ? "Delete test: " + item.text.slice(0, 30) : "Delete test");
  }

  function lookup(li) {                                                     // newest answer wins: each edit bumps seq
    const seq = ++li._ix.seq, text = textOf(li);
    if (!text || !H.post) return;
    Promise.resolve(H.post(LOOKUP_URL, { text }, LOOKUP_MS)).then((j) => {
      if (seq !== li._ix.seq || !li.isConnected || !j) return;
      li._ix.status = j.status === "verified" ? "verified" : "new";
      if (!li._ix.typedFull) li._ix.canonical = typeof j.canonical === "string" ? j.canonical : "";
      paint(li); changed();
    }, () => { if (seq === li._ix.seq && li.isConnected) { li._ix.status = "new"; paint(li); } });   // the server regrades on save
  }
  function onInput(e, li, span) {
    if (e) e.stopPropagation();                                             // app.js's list fixer must not touch this li
    if (viewOnly()) return;
    if (span.children && span.children.length) span.textContent = span.textContent;   // markup that slipped in becomes text
    const s = li._ix;
    s.source = "doctor"; s.edited = true; s.status = ""; li.classList.remove("ix-blocked");
    if (!s.typedFull) s.canonical = "";                                     // the old match named the old text
    s.seq++;                                                                // an answer for the old text is stale now
    clearTimeout(s.timer);
    s.timer = setTimeout(() => lookup(li), api.DEBOUNCE_MS);
    paint(li); changed();
  }
  function onPaste(e, li, span) {                                           // plain text only, on one line (genericedit.js)
    e.preventDefault();
    const t = ((e.clipboardData && e.clipboardData.getData("text/plain")) || "").replace(/[\r\n]+/g, " ");
    if (document.execCommand && document.execCommand("insertText", false, t)) return;   // fires its own input event
    const sel = window.getSelection && window.getSelection();
    if (sel && sel.rangeCount) { const rg = sel.getRangeAt(0); rg.deleteContents(); rg.insertNode(document.createTextNode(t)); rg.collapse(false); }
    onInput(null, li, span);
  }
  function editable(li, span) {
    span.contentEditable = "true"; span.spellcheck = false;
    span.setAttribute("role", "textbox"); span.setAttribute("aria-label", "Test name");
    span.addEventListener("input", (e) => onInput(e, li, span));
    span.addEventListener("paste", (e) => onPaste(e, li, span));
    span.addEventListener("drop", (e) => e.preventDefault());               // no dragged markup
    span.addEventListener("beforeinput", (e) => { const t = String(e.inputType || ""); if (t.indexOf("format") === 0 || t === "insertParagraph" || t === "insertLineBreak") e.preventDefault(); });
    span.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); span.blur(); } });
  }
  function button(cls, text, fn) {
    const b = el("button", cls, text); b.type = "button"; b.contentEditable = "false";
    b.addEventListener("click", (e) => { if (e && e.stopPropagation) e.stopPropagation(); if (!busy() && !viewOnly()) fn(); });
    return b;
  }
  function keep(li) {                                                       // the doctor wants the test the dictation never named
    const s = li._ix;
    s.source = "doctor"; s.status = s.canonical ? "verified" : "new";
    li.classList.remove("ix-blocked"); paint(li); changed();
    const t = li.querySelector(".ix-text"); if (t) t.focus();
  }
  function rememberBox(li) {
    const lab = el("label", "ix-remember no-print"), cb = el("input", "ix-remember-cb");
    cb.type = "checkbox";
    cb.addEventListener("input", (e) => e.stopPropagation());
    cb.addEventListener("change", (e) => {
      if (e && e.stopPropagation) e.stopPropagation();
      const s = li._ix;
      if (viewOnly() || busy()) { cb.checked = s.remember; return; }
      s.remember = cb.checked === true;
      if (s.remember) s.before = { canonical: s.canonical, source: s.source };
      else if (s.before) { s.canonical = s.before.canonical; s.source = s.before.source; s.typedFull = false; }   // the hidden box changes nothing
      paint(li); changed();
      if (s.remember) li.querySelector(".ix-fullname-input").focus();
    });
    lab.append(cb, el("span", null, " Remember for this clinic"));
    const box = el("label", "ix-fullname no-print"), input = el("input", "ix-fullname-input");
    input.type = "text"; input.maxLength = TEXT_CHARS; input.setAttribute("aria-label", "Full name");
    input.placeholder = "Full name";
    input.addEventListener("input", (e) => {
      if (e && e.stopPropagation) e.stopPropagation();
      if (viewOnly()) return;
      const s = li._ix;
      s.canonical = clean(input.value); s.typedFull = true; s.source = "doctor";   // the doctor's full name: kept by the server
      paint(li); changed();
    });
    box.append(el("span", null, "Full name "), input);
    return [lab, box];
  }
  function build(item, state) {
    const li = el("li", "ix-item");
    li._ix = Object.assign({ remember: false, edited: false, typedFull: false, seq: 0, timer: null }, state || {},
      { canonical: item.canonical, status: item.status, source: item.source });
    // Always built: view-only can start or end after this render (openDocument renders before Authorship.onOpen). A
    // locked page gets what Authorship.enforce would do (data-ro, a disabled x), so Authorship.clear unlocks it; the
    // #sheet.view-only CSS hides the controls and every handler refuses while view-only.
    const span = el("span", "ix-text", item.text);
    editable(li, span);
    li.append(span, el("span", "ix-full"), el("span", "ix-chip no-print"));
    li.appendChild(button("ix-keep ix-act no-print", "Keep", () => keep(li)));
    li.append(...rememberBox(li));
    // Not button(): its click handler stops propagation, and app.js routes the x from #sheet (IxList.remove).
    const x = el("button", "x-btn no-print", ""); x.type = "button"; x.contentEditable = "false";
    x.innerHTML = X_ICON;
    x.dataset.action = "delete-ix"; x.title = "Delete this test"; x.setAttribute("aria-label", "Delete this test");
    li.appendChild(x);
    if (viewOnly()) { span.contentEditable = "false"; span.dataset.ro = "1"; x.disabled = true; }
    paint(li);
    return li;
  }
  // "+ Add test" after the list, built once; the #sheet.view-only CSS hides it. Off at MAX_ITEMS (the server's
  // LIST_ITEM_LIMIT), so no test is added that Save would drop.
  function addButton(ul) {
    let b = ul.nextSibling;
    if (!(b && b.classList && b.classList.contains("ix-add"))) {
      b = button("ix-add ix-act no-print", "+ Add test", () => {
        if (ul.querySelectorAll("li.ix-item").length >= MAX_ITEMS) return;
        const li = build({ text: "", canonical: "", status: "", source: "doctor" }, { edited: true });
        ul.appendChild(li); addButton(ul); changed();
        li.querySelector(".ix-text").focus();
      });
      ul.after(b);
    }
    const full = ul.querySelectorAll("li.ix-item").length >= MAX_ITEMS;
    b.disabled = full;
    if (full) b.setAttribute("title", "At most " + MAX_ITEMS + " tests"); else b.removeAttribute("title");
    return b;
  }

  function init(hooks) { H = Object.assign(H, hooks || {}); }
  function render(ul, values) {
    ul.querySelectorAll("li.ix-item").forEach((li) => { if (li._ix) clearTimeout(li._ix.timer); });
    ul.textContent = "";
    (Array.isArray(values) ? values : []).map(coerce).filter(Boolean).forEach((item) => ul.appendChild(build(item)));
    addButton(ul);
  }
  // The tests the save sends, with the li each came from: blank ones dropped exactly as the server drops them.
  function rows(ul) { return [...ul.querySelectorAll("li.ix-item")].map((li) => ({ li, item: itemOf(li) })).filter((r) => r.item.text); }
  function read(ul) { return rows(ul).map((r) => r.item); }
  // remember_investigations: indexes into read(ul) (same list, same order) of the ticked tests.
  function rememberIndexes(ul) {
    const out = [];
    rows(ul).forEach((r, i) => { if (r.li._ix.remember && canRemember(r.li)) out.push(i); });
    return out;
  }
  function remove(li) {
    const ul = li.parentNode, pos = ul ? [...ul.children].indexOf(li) : -1;
    clearTimeout(li._ix.timer); li._ix.seq++;                               // a pending lookup never lands on a removed test
    const s = li._ix, item = itemOf(li), state = { remember: s.remember, edited: s.edited, typedFull: s.typedFull, before: s.before };
    li.remove();
    if (ul) addButton(ul);
    const rec = { item: Object.assign(item, { state }), pos };
    if (H.onRemove) H.onRemove(rec.item, pos);
    changed();
    return rec;
  }
  function insert(ul, item, pos) {                                          // Undo: the test comes back where it was
    const c = coerce(item) || { text: "", canonical: "", status: "", source: "doctor" };
    const li = build(c, item && item.state);
    ul.insertBefore(li, ul.children[pos] || null);
    addButton(ul);
    return li;
  }
  // The 409's investigations_block [{index, text}]: index counts read()'s list; the text must match too, else the first
  // red dictated test with that text is marked. Focus goes to the first marked test's Keep. Returns how many were marked.
  function showBlocked(ul, block) {
    const list = rows(ul), marked = [];
    (Array.isArray(block) ? block : []).forEach((b) => {
      const k = key(b && b.text);
      let r = b && Number.isInteger(b.index) ? list[b.index] : null;
      if (!r || key(r.item.text) !== k || marked.includes(r.li)) r = list.find((x) => key(x.item.text) === k && x.item.source === "dictated" && !marked.includes(x.li)) || null;
      if (!r) return;
      r.li._ix.status = "not-dictated"; r.li.classList.add("ix-blocked"); paint(r.li); marked.push(r.li);
    });
    if (marked.length) { const f = marked[0].querySelector(".ix-keep") || marked[0].querySelector(".ix-text"); if (f) f.focus(); }
    return marked.length;
  }
  // The 409 message: medicines, tests or both.
  function blockedMessage(meds, tests) {
    const m = meds + " medicine" + (meds > 1 ? "s" : "") + " need" + (meds > 1 ? "" : "s") + " a check";
    const t = tests + " test" + (tests > 1 ? "s were" : " was") + " not heard in the dictation";
    const it = tests > 1 ? "them" : "it";
    if (meds && tests) return "Save blocked: " + m + ", and " + t + ". Resolve the medicines (the list below jumps to each one), keep or remove the " + (tests > 1 ? "tests" : "test") + ", then Save again.";
    if (tests) return "Save blocked: " + t + ". Keep " + it + " or remove " + it + ", then Save again.";
    return "Save blocked: " + m + ". Resolve them in the sheet (the list below jumps to each one), then Save again.";
  }
  const api = { init, render, read, rememberIndexes, insert, remove, showBlocked, printText, blockedMessage, key, DEBOUNCE_MS: 400 };
  return api;
})();
