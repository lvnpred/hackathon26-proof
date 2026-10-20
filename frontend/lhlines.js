"use strict";
// Letterhead review: one remove tick per literal line (blank pad labels start ticked) and a "where should it print"
// question per field the pad shows twice. Pure plan/payload functions plus DOM render/collect. All text goes in through
// textContent: letterhead text is read from a photo by a vision model, so it is never markup.
(function (root) {
  const WHERE = [["header", "At the top only"], ["footer", "At the bottom only"], ["both", "In both places"]];
  const WHY = "Looks like a blank label from the paper pad. The app prints the patient's details itself.";
  const SECTIONS = ["header", "footer"];
  const same = (a, b) => a.section === b.section && a.index === b.index;

  // View -> what the screen shows. Every duplicate starts as "both" (owner Q5): the question never blocks.
  function plan(view) {
    const v = view || {}, layout = v.layout || {}, fill = v.fill_in || [], warns = v.warnings || [], rows = [];
    SECTIONS.forEach((section) => (layout[section] || []).forEach((b, index) => {
      if (!b || b.type !== "text" || typeof b.text !== "string") return;
      const at = { section: section, index: index };
      const label = fill.some((f) => same(f, at));
      rows.push({ section: section, index: index, text: b.text, remove: label, label: label, warn: warns.some((w) => same(w, at)) });
    }));
    const dupes = (v.duplicates || []).map((d) => ({ field: d.field, header: d.header || [], footer: d.footer || [], where: "both" }));
    return { rows: rows, dupes: dupes, skipped: ((layout.skipped_labels) || []).slice() };
  }

  // Screen state -> request body. A ticked or emptied line is removed; one keep entry per answered field.
  function payload(rows, answers) {
    const lines = (rows || []).map((r) => (r.remove || !String(r.text).trim()
      ? (r.orig === undefined ? { section: r.section, index: r.index, remove: true }
        : { section: r.section, index: r.index, remove: true, text: String(r.orig) })
      : { section: r.section, index: r.index, text: String(r.text).trim() }));
    const keep = Object.keys(answers || {}).map((f) => ({ field: f, where: answers[f] }));
    return { lines: lines, keep: keep };
  }

  const make = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const byId = (id) => document.getElementById(id);

  function renderRow(r, n, ctl, opts) {
    const row = make("div", "lh-line-row");
    const w = make("label", "field", (r.section === "header" ? "Top line " : "Bottom line ") + ctl.seen[r.section]);
    const inp = make("input", "lh-line-text");
    inp.id = "lhLine" + n; inp.value = r.text; inp.dataset.section = r.section; inp.dataset.index = String(r.index);
    w.appendChild(inp); row.appendChild(w);
    const rm = make("label", "lh-line-rm"), box = make("input");
    box.type = "checkbox"; box.id = "lhLineRm" + n;
    box.setAttribute("aria-label", "Remove this line (" + (r.section === "header" ? "top" : "bottom") + " line " + ctl.seen[r.section] + ")");
    box.checked = r.remove && (opts.unticked || []).indexOf(r.text) < 0;
    inp.disabled = box.checked;
    box.addEventListener("change", () => { inp.disabled = box.checked; });
    rm.appendChild(box); rm.appendChild(document.createTextNode(" Remove this line"));
    row.appendChild(rm);
    if (r.label) {
      const why = make("p", "lh-line-why", WHY);
      why.id = "lhLineWhy" + n;
      box.setAttribute("aria-describedby", why.id);
      row.appendChild(why);
    }
    ctl.rows.push({ section: r.section, index: r.index, label: r.label, orig: r.text, text: inp, remove: box });
    return row;
  }

  function renderDupe(d, ctl, opts) {
    const fs = make("fieldset", "lh-dupe"), name = (opts.labels || {})[d.field] || d.field;
    fs.appendChild(make("legend", "", name + " prints at the top and at the bottom. Keep it:"));
    const radios = [];
    WHERE.forEach((o) => {
      const l = make("label", "lh-dupe-opt"), r = make("input");
      r.type = "radio"; r.name = "lhDupe_" + d.field; r.value = o[0]; r.checked = o[0] === d.where;
      l.appendChild(r); l.appendChild(document.createTextNode(" " + o[1]));
      fs.appendChild(l); radios.push(r);
    });
    ctl.dupes.push({ field: d.field, radios: radios });
    return fs;
  }

  // opts: labels {field: "Phone"}, unticked [texts a re-render must leave unticked].
  function render(box, view, opts) {
    opts = opts || {};
    const p = plan(view), lines = byId("lhLines"), dupes = byId("lhDupes"), skipped = byId("lhSkipped");
    const ctl = { rows: [], dupes: [], seen: { header: 0, footer: 0 } };
    lines.textContent = ""; dupes.textContent = "";
    p.rows.forEach((r, n) => { ctl.seen[r.section] += 1; lines.appendChild(renderRow(r, n, ctl, opts)); });
    p.dupes.forEach((d) => dupes.appendChild(renderDupe(d, ctl, opts)));
    skipped.textContent = p.skipped.length ? "Left out as blank labels from the paper pad: " + p.skipped.join("; ") : "";
    skipped.hidden = !p.skipped.length;
    box.hidden = !(p.rows.length || p.dupes.length || p.skipped.length);
    box._lh = ctl;
  }

  function collect(box) {
    const ctl = box._lh || { rows: [], dupes: [] }, answers = {};
    ctl.dupes.forEach((d) => {
      const on = d.radios.filter((r) => r.checked)[0];
      answers[d.field] = on ? on.value : "both";
    });
    return payload(ctl.rows.map((r) => ({ section: r.section, index: r.index, text: r.text.value, orig: r.orig, remove: r.remove.checked })), answers);
  }

  // Texts of pre-ticked labels the doctor unticked: a re-render after a save keeps them unticked.
  function unticked(box) {
    return ((box._lh || {}).rows || []).filter((r) => r.label && !r.remove.checked).map((r) => r.orig);
  }

  root.LhLines = { plan, payload, render, collect, unticked };
  if (typeof module !== "undefined" && module.exports) module.exports = root.LhLines;
})(typeof window !== "undefined" ? window : globalThis);
