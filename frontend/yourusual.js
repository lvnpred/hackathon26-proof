"use strict";
// "Your usual" strip (SH-B6): under the Rx table, the medicines this doctor prescribed most often for the sheet's diagnosis, as
// buttons. Nothing is added until a tap. A tap sends the row through the normal medicine check (POST /rx/check-row, with the
// suggestion's own words as the transcript so the look-alike check runs) and hands the answer to the page. The diagnosis goes
// in a POST body only, never a URL. Hidden when view-only, while the page is busy, or with no sheet. Loaded BEFORE app.js; also loads under node.
(function (root) {
  const URL_USUAL = "/api/v1/spoken/usual", URL_CHECK = "/api/v1/rx/check-row";
  const MAX_SHOWN_PER_LINE = 3, MAX_SHOWN = 6, DEBOUNCE_MS = 500, CHECK_MS = 30000;
  const MAX_LINES = 10, MAX_LINE_CHARS = 200, DX_SHOWN = 40;
  const str = (v) => (typeof v === "string" ? v : "");
  let H = null, timer = null, seq = 0, lastKey = null, pendingKey = null, shownSeq = null, sig = null, noteEl = null, groups = [], lines = [], note = "";
  const checking = new Set();

  const words = (it) => [str(it.form).replace(/\.$/, ""), str(it.name), str(it.strength), str(it.dose)].filter((w) => w.trim()).join(" ");
  function labelOf(it) {
    return words(it) + (str(it.timing) ? ", " + it.timing.toLowerCase() : "") + (str(it.duration) ? " × " + it.duration : "");
  }
  const phraseOf = (it) => [words(it), str(it.timing).toLowerCase(), str(it.duration)].filter((w) => w.trim()).join(" ");
  const keyOf = (it) => [it.name, it.strength, it.dose, it.timing, it.duration].map((v) => str(v).toLowerCase()).join("|");

  function shown(gs, ls, onSheet) {
    const have = new Set();
    (onSheet || []).forEach((r) => { [r && r.name, r && r.generic].forEach((v) => { const k = str(v).trim().toLowerCase(); if (k) have.add(k); }); });
    const out = [], seen = new Set();
    let total = 0;
    (gs || []).slice().sort((a, b) => a.line - b.line).forEach((g) => {
      const items = [];
      for (const it of g.items || []) {
        if (total >= MAX_SHOWN || items.length >= MAX_SHOWN_PER_LINE) break;
        const n = str(it.name).trim().toLowerCase(), gen = str(it.generic).trim().toLowerCase();
        if (have.has(n) || (gen && have.has(gen)) || seen.has(n)) continue;
        seen.add(n); items.push(it); total++;
      }
      if (items.length) out.push({ label: str((ls || [])[g.line]), items });
    });
    return out;
  }

  const el = () => root.document.getElementById("usualRx");
  const mk = (tag, cls, text) => { const n = root.document.createElement(tag); if (cls) n.className = cls; if (text) n.textContent = text; return n; };
  const blocked = () => !H || H.viewOnly() || H.working() || !H.hasSheet();

  function render() {
    const box = el();
    if (!box) return;
    const say = note; note = "";
    const fresh = H && H.sheetSeq() === shownSeq;         // the groups belong to this sheet; after an open or a new patient they do not
    const rows = blocked() || !fresh ? [] : shown(groups, lines, H.onSheet());
    const show = rows.length > 0 || (!!say && !blocked());
    const now = show ? JSON.stringify([rows.map((g) => [g.label, g.items.map((it) => [labelOf(it), it.count, checking.has(keyOf(it))])]), say]) : "";
    if (!say && now === sig) return;                      // unchanged: keep the buttons (and focus) and stay quiet for screen readers
    sig = now;
    if (!noteEl) { noteEl = mk("p", "usual-note"); noteEl.setAttribute("aria-live", "polite"); box.appendChild(noteEl); }   // one live node, empty until it has something to say
    while (box.firstChild && box.firstChild !== noteEl) box.removeChild(box.firstChild);
    noteEl.textContent = "";
    if (!show) { box.hidden = true; return; }
    rows.forEach((g) => {
      const p = mk("p", "usual-line");
      p.appendChild(mk("span", "usual-dx", g.label.length > DX_SHOWN ? g.label.slice(0, DX_SHOWN) + "…" : g.label));
      p.appendChild(mk("span", "usual-lead", " · Your usual:"));
      g.items.forEach((it) => {
        const b = mk("button", "usual-add");
        b.type = "button";
        b.setAttribute("aria-label", "Add " + labelOf(it));
        const plus = mk("span", "usual-plus", "+ "); plus.setAttribute("aria-hidden", "true");
        b.appendChild(plus); b.appendChild(mk("span", "usual-label", labelOf(it)));
        b.disabled = checking.has(keyOf(it));
        b.addEventListener("click", () => tap(it));
        p.appendChild(b);
        if (Number.isFinite(it.count) && it.count >= 2) p.appendChild(mk("span", "usual-count", it.count + " times"));
      });
      box.insertBefore(p, noteEl);
    });
    if (say) noteEl.textContent = say;
    box.hidden = false;
  }

  function wanted() {
    return (H.diagnosis() || []).map((s) => str(s).trim()).filter(Boolean).slice(0, MAX_LINES).map((s) => s.slice(0, MAX_LINE_CHARS));
  }

  function fetchNow() {
    timer = null;
    if (blocked()) { seq++; pendingKey = null; render(); return; }   // busy or another sheet: a lookup in flight is dropped
    const ls = wanted(), key = JSON.stringify(ls);
    if (key === pendingKey) { render(); return; }
    if (!ls.length || key === lastKey) {                 // nothing to ask: an older answer still in flight must not paint over this
      seq++; pendingKey = null; shownSeq = H.sheetSeq();
      if (!ls.length) { lines = []; groups = []; lastKey = key; }
      render(); return;
    }
    const tok = ++seq, at = H.sheetSeq();
    pendingKey = key;
    H.post(URL_USUAL, { diagnosis: ls }, CHECK_MS).then((res) => {
      if (tok !== seq) return;                           // the diagnosis changed while we waited: a newer lookup owns the strip
      pendingKey = null; lastKey = key; lines = ls;      // the answer depends on the diagnosis only, so it is kept even if the sheet changed
      groups = res && Array.isArray(res.groups) ? res.groups : [];
      shownSeq = !blocked() && JSON.stringify(wanted()) === key ? H.sheetSeq() : null;   // shown only on a sheet that has this diagnosis now
      render();
    }, () => {
      if (tok !== seq) return;
      pendingKey = null; lastKey = null; lines = []; groups = [];   // a convenience, never a blocker: no error text
      render();
    });
  }

  function refresh() {
    if (timer) root.clearTimeout(timer);
    timer = root.setTimeout(fetchNow, DEBOUNCE_MS);
  }

  function clear() {
    if (timer) root.clearTimeout(timer);
    timer = null; seq++; pendingKey = null; lastKey = null; groups = []; lines = []; shownSeq = null; note = ""; checking.clear();
    render();
  }

  async function tap(it) {
    const k = keyOf(it);
    if (!H || H.working() || H.viewOnly() || checking.has(k)) return;
    const was = H.sheetSeq();
    checking.add(k); note = ""; render();
    const row = { form: str(it.form), name: str(it.name), strength: str(it.strength), dose: str(it.dose), timing: str(it.timing), duration: str(it.duration), instructions: "" };
    let grounded = null;
    try {
      const res = await H.post(URL_CHECK, { row, transcript: phraseOf(it), age_sex: str(H.ageSex()) }, CHECK_MS);
      checking.delete(k);
      if (H.sheetSeq() === was && !H.viewOnly() && res && res.row && typeof res.row === "object") grounded = res.row;   // another sheet by now: the row must not land on it
    } catch (e) {
      checking.delete(k);
      if (H.sheetSeq() === was) note = "Could not add " + str(it.name) + ". " + root.RxState.errorText(e);
    }
    render();
    if (grounded) H.add(grounded);                      // outside the try: a fault in the page is not a failed check
  }

  function init(hooks) { H = hooks; }

  const api = { init, refresh, render, clear, labelOf, phraseOf, shown, URL_USUAL, MAX_SHOWN_PER_LINE, MAX_SHOWN, DEBOUNCE_MS, CHECK_MS };
  root.YourUsual = api;
  if (typeof module !== "undefined") module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
