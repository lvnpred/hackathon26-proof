/* Cues (plan C1): while a first dictation records, the panel lists each switched-on section with its example phrase, so a
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

  function show() {
    const panel = $("cuePanel"), ul = $("cueList");
    if (!panel || !ul) return;
    const rows = onList();
    fill(ul, rows.map((x) => (String(x.cue || "").trim() ? x.heading + " — " + x.cue : x.heading)));
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
