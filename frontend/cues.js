/* Cues (plan C1): the "What to say" panel lists each switched-on section's example phrase, always visible, so a
   doctor dictating from memory does not forget one. After a format or correction, a flag names each empty section.
   Headings and cues are text, never markup. Browser global window.Cues; also loads under node (tests/test_frontend_cues.py). */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  let getList = () => [];

  const has = (s, key, kind) => window.SheetSecs.has(s, key, kind);   // the one has-data rule (core.sections.has_data)
  const onList = () => { const l = getList(); return Array.isArray(l) ? l.filter((x) => x && x.on) : []; };

  function init(h) { if (h && typeof h.list === "function") getList = h.list; }

  function fill(ul, lines) {
    ul.textContent = "";
    for (const t of lines) { const li = document.createElement("li"); li.textContent = t; ul.appendChild(li); }
  }

  // A label is a word (or a few) at the start, then ":". "8:30" or "Dolo 650 at 8:30" is not one, so it never splits.
  const LABEL = /^([A-Za-z][A-Za-z /&()-]{0,30}):/;
  // One line per section: the cue alone, its label in a darker span. A section with no cue shows its heading.
  function addLine(ul, x) {
    const li = document.createElement("li"), cue = String(x.cue || "").trim();
    const m = LABEL.exec(cue);
    const lead = document.createElement("span"), rest = document.createElement("span");
    lead.className = "cue-lead"; rest.className = "cue-rest";
    if (!cue) lead.textContent = x.heading;
    else if (!m) rest.textContent = cue;
    else { lead.textContent = cue.slice(0, m[0].length); rest.textContent = cue.slice(m[0].length); }
    li.appendChild(lead); li.appendChild(rest); ul.appendChild(li);
  }

  // No section list (the fetch failed): the sheet's own visible headings, so the panel never goes missing.
  function sheetRows() {
    if (typeof document.querySelectorAll !== "function") return [];
    return [...document.querySelectorAll("#sheetBody .sec:not([hidden]) > .sec-title")]
      .map((t) => ({ heading: String(t.textContent || "").trim(), cue: "" })).filter((x) => x.heading);
  }

  function show() {
    const panel = $("cuePanel"), ul = $("cueList");
    if (!panel || !ul) return;
    const l = onList(), rows = l.length ? l : sheetRows();
    ul.textContent = "";
    rows.forEach((x) => addLine(ul, x));
    panel.hidden = !rows.length;
  }

  function hide() { const p = $("cuePanel"); if (p) p.hidden = true; }

  function emptyHeadings(list, s) {
    s = s || {};
    return (list || []).filter((x) => x.on && !has(s, x.key, x.kind)).map((x) => x.heading);
  }

  function flagEmpty(s) {
    const ul = $("emptyFlags");
    if (!ul) return;
    const heads = emptyHeadings(getList(), s);
    fill(ul, heads.map((h) => "Nothing dictated for " + h));
    ul.hidden = !heads.length;
  }

  function clearFlags() {
    const ul = $("emptyFlags");
    if (!ul) return;
    fill(ul, []);
    ul.hidden = true;
  }

  window.Cues = { init, show, hide, emptyHeadings, flagEmpty, clearFlags };
})();
