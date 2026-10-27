/* SheetSecs (plan C1): the sheet follows the section list from GET /api/v1/sections. It orders, titles and hides the
   seven built-in blocks, adds plain-text blocks for added sections, and reads them back into structured.extra.
   Browser global window.SheetSecs; also loads under node with a fake DOM (tests/test_frontend_sheetsecs.py). */
(function () {
  "use strict";
  const URL = "/api/v1/sections";
  const $ = (id) => document.getElementById(id);
  let H = { get: null, renderList: null };
  let secs = [];
  let drawn = false;                               // true once a render has drawn the added blocks from a loaded list

  const isObj = (v) => !!v && typeof v === "object" && !Array.isArray(v);
  const has = (s, key, kind) => {                  // the same rule as core.sections.has_data
    if (kind === "text") { const e = isObj(s.extra) ? s.extra[key] : null; return !!(isObj(e) && Array.isArray(e.lines) && e.lines.length); }
    const v = s[key];
    if (kind === "medication") return Array.isArray(v) && v.some((r) => isObj(r) && String(r.name || "").trim());
    if (kind === "review") return !!String(v || "").trim();
    return Array.isArray(v) ? v.length > 0 : !!v;
  };

  function init(h) { H = Object.assign(H, h || {}); }

  function load() {
    return Promise.resolve().then(() => H.get(URL)).then((j) => {
      secs = j && Array.isArray(j.sections) ? j.sections.filter((x) => isObj(x) && typeof x.key === "string") : [];
    }).catch(() => { secs = []; });                // a failed load leaves the static sheet as it is
  }

  const list = () => secs;

  // [[key, heading, kind], ...]: what the sheet shows, as core.sections.layout does.
  function plan(sl, s) {
    s = s || {};
    const extra = isObj(s.extra) ? s.extra : {};
    const out = [];
    for (const x of sl) {
      if (!x.on && !has(s, x.key, x.kind)) continue;
      const stored = x.kind === "text" && isObj(extra[x.key]) ? extra[x.key].heading : null;
      out.push([x.key, stored || x.heading, x.kind]);
    }
    const known = new Set(sl.map((x) => x.key));
    for (const k of Object.keys(extra)) {
      if (!known.has(k) && has(s, k, "text")) out.push([k, extra[k].heading || k, "text"]);
    }
    return out;
  }

  function extraBlock(key) {
    const w = document.createElement("div");
    w.className = "sec";
    w.dataset.sec = key;
    w.dataset.extra = key;
    const t = document.createElement("div");
    t.className = "sec-title";
    const ul = document.createElement("ul");
    ul.className = "editable-list prose-list";
    ul.dataset.extra = key;
    ul.id = "pEx-" + key;                           // the app's undo finds a deleted line's list by id
    w.appendChild(t);
    w.appendChild(ul);
    return w;
  }

  function render(s) {
    const body = $("sheetBody");
    if (!secs.length || !body) return;
    s = s || {};
    const pl = plan(secs, s);
    const keys = new Set(pl.map((p) => p[0]));
    const blocks = {};
    for (const w of [...body.children]) {
      const key = w.dataset && w.dataset.sec;
      if (!key) continue;
      if (w.dataset.extra && !keys.has(key)) { w.remove(); continue; }
      blocks[key] = w;
      if (!keys.has(key)) w.hidden = true;
    }
    const disclaimer = body.querySelector(".disclaimer");
    const extra = isObj(s.extra) ? s.extra : {};
    const shown = {};
    pl.forEach((p) => { shown[p[0]] = p; });
    const seq = secs.map((x) => x.key).concat(pl.map((p) => p[0]).filter((k) => !secs.some((x) => x.key === k)));
    for (const key of seq) {                       // list order; a hidden built-in keeps its place in it
      const p = shown[key];
      if (!p) { if (blocks[key]) body.insertBefore(blocks[key], disclaimer); continue; }
      const [, heading, kind] = p;
      const w = blocks[key] || extraBlock(key);
      w.hidden = false;
      const t = w.querySelector(".sec-title");
      if (t) t.textContent = heading;              // text, never markup
      if (kind === "text") {
        const ul = w.querySelector("ul");
        ul.dataset.heading = heading;
        H.renderList(ul, isObj(extra[key]) ? extra[key].lines : []);
      }
      body.insertBefore(w, disclaimer);
    }
    drawn = true;
  }

  function liLine(li) {
    const c = li.cloneNode ? li.cloneNode(true) : li;
    c.querySelectorAll(".x-btn").forEach((b) => b.remove());
    return String(c.textContent || "").replace(/\s+/g, " ").trim();
  }

  function read() {
    const out = {};
    const body = $("sheetBody");
    if (!body) return out;
    for (const ul of body.querySelectorAll("ul[data-extra]")) {
      const lines = [...ul.querySelectorAll("li")].map(liLine).filter(Boolean);
      if (lines.length) out[ul.dataset.extra] = { heading: ul.dataset.heading || ul.dataset.extra, lines };
    }
    return out;
  }

  // Files the sheet's added sections into base.extra. With no list loaded the sheet cannot show them, so base keeps its stored extra.
  function readBack(base) {
    if (!secs.length || !drawn) return base;       // blocks never drawn: the stored extra is all there is
    const ex = read();
    if (Object.keys(ex).length) base.extra = ex; else delete base.extra;
    return base;
  }

  window.SheetSecs = { init, load, list, plan, render, read, readBack, has };
})();
