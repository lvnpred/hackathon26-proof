"use strict";
// The clinic's Medicines and Investigations tabs on the Team page (plan PQ-f): the effective list (shared list plus the
// clinic's changes) as a table with a filter and the row actions (edit, hide, reset, keep mine / take new, approve,
// and Remove for names the clinic learned), plus Add. The edit form is listedit.js. Built only for admins by team.js,
// which hands over its request helper through init(). Loaded before team.js.
(function () {
  const LISTS = "/api/v1/lists/";
  const MEDS = "/api/v1/formulary";
  const BADGE = { shipped: "Shared list", "clinic-added": "Added by clinic", "clinic-edited": "Edited by clinic", hidden: "Hidden", learned: "Learned" };
  const FLAG = { "shipped-changed": "Updated in the shared list", "safety-override": "Safety entry: the shared list is used" };
  const KINDS = {
    medicine: { tab: "teamTabMeds", panel: "teamMeds", rows: "teamMedRows", live: "teamMedLive", empty: "teamMedEmpty", filter: "teamMedFilter", only: "teamMedOnly",
      add: "Add a medicine", addId: "teamMedAdd", cols: ["Medicine", "Generic", "Brands", "Source", "Actions"], none: "Nothing in this list yet.",
      hint: "The medicines your clinic's doctors can dictate: the shared list plus your clinic's changes. Names your doctors confirmed on saved documents show as Learned, " +
        "and your clinic recognises them when dictating. Removing a learned name is not permanent: it comes back only after two new documents confirm it again." },
    investigation: { tab: "teamTabTests", panel: "teamTests", rows: "teamTestRows", live: "teamTestLive", empty: "teamTestEmpty", filter: "teamTestFilter", only: "teamTestOnly",
      add: "Add a test", addId: "teamTestAdd", cols: ["Test", "Print", "Category", "Source", "Actions"], none: "No investigations in this list yet.",
      hint: "The investigations your clinic's doctors can dictate: the shared list plus your clinic's changes." },
  };
  const host = { send: async () => null, showErr: () => {}, errText: () => "" };
  const state = { medicine: { items: [], seq: 0 }, investigation: { items: [], seq: 0 } };
  const el = (id) => document.getElementById(id);

  function make(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (k === "hidden") node.hidden = Boolean(v); else node.setAttribute(k, v); });
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function init(h) { Object.assign(host, h); }
  function setLive(kind, m) { el(KINDS[kind].live).textContent = m || ""; }

  function buildPanel(kind) {
    const k = KINDS[kind];
    const hrow = make("tr");
    k.cols.forEach((h) => hrow.append(make("th", { scope: "col" }, h)));
    const thead = make("thead");
    thead.append(hrow);
    const table = make("table", { class: "team-table team-meds-table" });          // stacked per row on a phone (team.css)
    table.append(thead, make("tbody", { id: k.rows }));
    const tableBox = make("div", { class: "team-table-box" });
    tableBox.append(table);
    const search = make("input", { id: k.filter, type: "search", autocomplete: "off", "aria-label": "Filter the list" });
    const only = make("input", { id: k.only, type: "checkbox" });
    const onlyLabel = make("label", { class: "team-only" });
    onlyLabel.append(only, make("span", {}, "Only changed or flagged"));
    const bar = make("div", { class: "team-filter" });
    bar.append(search, onlyLabel);
    search.addEventListener("input", () => rerender(kind));      // one event each: the text box on input, the checkbox on change
    only.addEventListener("change", () => rerender(kind));
    const add = make("button", { id: k.addId, type: "button", class: "primary team-list-add" }, k.add);
    add.addEventListener("click", () => addEntry(kind));
    const panel = make("div", { id: k.panel, class: "team-tab-body", role: "tabpanel", "aria-labelledby": k.tab, hidden: true });
    panel.append(make("p", { class: "team-hint" }, k.hint), make("p", { id: k.live, class: "team-live", role: "status" }),
      add, bar, make("p", { id: k.empty, class: "team-hint", hidden: true }, k.none), tableBox);
    return panel;
  }

  function names(kind, item) {                       // what the row calls the entry; a learned name is a brand with its generic beside it
    const e = item.entry || {};
    const brands = Array.isArray(e.brands) ? e.brands : [];
    if (kind === "investigation") return [e.canonical || item.entry_key, e.print || "", e.category || ""];
    if (item.badge === "learned") return [brands[0] || e.canonical || item.entry_key, brands[0] ? e.canonical || "" : "", ""];
    const generic = e.canonical || item.entry_key;       // a listed medicine is keyed by its generic
    return [generic, generic, brands.join(", ")];
  }
  function changed(item) { return item.badge !== "shipped" || Boolean(item.flag) || Boolean(item.pending); }
  function matches(kind, item, text) {
    if (!text) return true;
    const e = item.entry || {};
    const hay = [item.entry_key, ...names(kind, item), ...(e.aliases || []), ...(e.brands || [])].join(" ").toLowerCase();
    return hay.includes(text);
  }
  function sourceCell(item) {
    const td = make("td", { "data-label": "Source" });
    td.append(make("div", {}, BADGE[item.badge] || item.badge));
    if (item.flag) td.append(make("div", { class: "team-flag" }, FLAG[item.flag] || item.flag));
    if (item.flag && item.flag_reason) td.append(make("div", { class: "team-flag-reason" }, item.flag_reason));   // why the row is set aside
    if (item.pending) {
      const p = item.pending;
      const d = p.data || {};
      const value = d.generic || d.print || d.name || "";
      td.append(make("div", { class: "team-pending" }, "Pending (" + Number(p.count) + " of " + Number(p.threshold) + ")" + (value ? ": " + value : "")));
    }
    return td;
  }
  function render(kind) {
    const k = KINDS[kind], s = state[kind];
    const text = el(k.filter).value.trim().toLowerCase();
    const only = el(k.only).checked;
    const rows = el(k.rows);
    rows.replaceChildren();
    el(k.empty).hidden = !s.loaded || s.items.length > 0;
    s.items.forEach((item) => {
      if ((only && !changed(item)) || !matches(kind, item, text)) return;
      const [a, b, c] = names(kind, item);
      const tr = make("tr", { "data-key": item.entry_key });
      tr.append(make("td", {}, a), make("td", { "data-label": k.cols[1] }, b), make("td", { "data-label": k.cols[2] }, c), sourceCell(item));
      const cell = make("td", { class: "team-row-actions" });
      rowActions(kind, item).forEach((x) => cell.append(rowButton(kind, item, a, x, rows, tr)));
      tr.append(cell);
      rows.append(tr);
    });
  }
  function rerender(kind) { render(kind); }

  // Row actions by state (the labels are the page's wording): shipped Edit, Hide | clinic-added and clinic-edited Edit,
  // Reset to default | hidden Reset to default | learned Edit, Remove | a pending-only doctor addition Edit, Reset to
  // default | flag shipped-changed adds Keep mine, Take new | flag safety-override Reset to default | pending adds
  // Approve now first. Hiding a clinic's own addition is refused by the server ("use Reset"), so it is never offered.
  function rowActions(kind, item) {
    const acts = [];
    const learnedName = kind === "medicine" && item.badge === "learned" && item.formulary_id !== null && item.formulary_id !== undefined;
    if (item.pending) acts.push("Approve now");
    if (item.badge !== "hidden") acts.push("Edit");
    if (item.badge === "shipped" && item.flag !== "safety-override") acts.push("Hide");
    else if (learnedName) acts.push("Remove");
    else acts.push("Reset to default");
    if (item.flag === "shipped-changed") acts.push("Keep mine", "Take new");
    return acts;
  }
  const POST = { "Approve now": "approve", Hide: "hide", "Reset to default": "reset", "Keep mine": "keep-mine", "Take new": "take-new" };
  const DONE = { approve: (n) => "Approved " + n + ".", hide: (n) => "Hidden " + n + ".", reset: (n) => n + " is back to the default.",
    "keep-mine": (n) => "Kept your version of " + n + ".", "take-new": (n) => "Took the shared version of " + n + ".", add: (n) => "Added " + n + ".", edit: (n) => "Saved " + n + "." };
  function rowButton(kind, item, name, label, rows, tr) {
    const isRemove = label === "Remove";
    const b = isRemove ? make("button", { type: "button", class: "team-med-remove" }, "Remove") : make("button", { type: "button", class: "team-list-act" }, label);
    b.setAttribute("aria-label", isRemove ? "Remove " + name + " from your clinic's medicines" : label + " " + name);
    b.addEventListener("click", () => {
      if (b.disabled) return;                               // a change for this row is already on its way
      if (isRemove) return removeLearned(item, name, Array.from(rows.children).indexOf(tr));
      if (label === "Edit") return editEntry(kind, item, name);
      return act(kind, item, name, POST[label], tr);
    });
    return b;
  }
  function confirmText(op, item, name) {
    if (op === "hide") return "Hide " + name + " from your clinic's list? Doctors will no longer find it when dictating. You can bring it back with Reset to default.";
    return item.shipped ? "Reset " + name + " to the shared list? Your clinic's changes to it will be removed."
      : "Reset " + name + "? It is not on the shared list, so it will be removed from your clinic's list.";
  }
  async function change(kind, item, name, body, key, tr) {   // one write: reload the list, then say what happened or show the server's words
    setLive(kind, "");
    const btns = tr ? tr.querySelectorAll("button") : [];
    btns.forEach((x) => { x.disabled = true; });             // one POST per row, however often it is clicked
    const b = await host.send(LISTS + kind + "/changes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!b) btns.forEach((x) => { x.disabled = false; });
    const msg = b ? "" : host.errText();                    // a 4xx means the row on screen may be stale: reload it, keep the error visible
    await load(kind);
    host.showErr(msg);
    if (b) setLive(kind, DONE[body.op](name));
    focusRow(kind, key, b ? null : item.entry_key);
  }
  function focusRow(kind, key, retry) {                     // the changed row's first button, else the Add button
    const rows = Array.from(el(KINDS[kind].rows).children);
    const tr = rows.find((r) => r.getAttribute("data-key") === key) || rows.find((r) => r.getAttribute("data-key") === retry);
    const first = tr && tr.querySelectorAll("button")[0];
    (first || el(KINDS[kind].addId)).focus();
  }
  async function act(kind, item, name, op, tr) {
    if ((op === "hide" || op === "reset") && !window.confirm(confirmText(op, item, name))) return;
    await change(kind, item, name, { op, entry_key: item.entry_key, data: {} }, item.entry_key, tr);
  }
  async function edited(kind, item, name, r) {
    if (!r) return focusRow(kind, item ? item.entry_key : "", null);
    await change(kind, item, (r.data && r.data.name) || name, r, r.entry_key);
  }
  async function editEntry(kind, item, name) { await edited(kind, item, name, await window.ListEdit.open(kind, item, { owner: false })); }
  async function addEntry(kind) { await edited(kind, null, "", await window.ListEdit.open(kind, null, { owner: false })); }

  async function load(kind) {
    const s = state[kind];
    const mine = ++s.seq;                            // only the newest load may draw: an older answer arriving late is dropped
    s.items = []; s.loaded = false;
    render(kind);                                    // never show old rows as current while (or after failing) to reload
    setLive(kind, "Loading…");
    const b = await host.send(LISTS + kind);
    if (mine !== s.seq) return;
    setLive(kind, "");
    if (b) { s.items = b.items || []; s.loaded = true; render(kind); }   // on a failure the table stays empty and the error box says why
  }

  function focusAfterRemoval(index) {                // next row's Remove, else the previous row's, else the tab
    const rows = Array.from(el(KINDS.medicine.rows).children);
    const withButton = rows.map((tr, i) => ({ i, b: tr.querySelectorAll(".team-med-remove")[0] })).filter((x) => x.b);
    const next = withButton.find((x) => x.i >= index);
    const prev = withButton.filter((x) => x.i < index).pop();
    (next || prev || { b: el(KINDS.medicine.tab) }).b.focus();
  }
  async function removeLearned(item, name, index) {
    if (!window.confirm("Remove " + name + " from your clinic's medicines? Doctors will be asked about it again, " +
      "and it comes back only after two new documents confirm it.")) return;
    setLive("medicine", "");
    const b = await host.send(MEDS + "/" + Number(item.formulary_id), { method: "DELETE" }, "That medicine was already removed. The list has been refreshed.");
    const msg = b ? "" : host.errText();               // the row on screen may be stale: reload it, keep the error visible
    await load("medicine");
    host.showErr(msg);
    if (b) setLive("medicine", "Removed " + name + ". It comes back only after two new documents confirm it.");
    if (b) focusAfterRemoval(index); else el(KINDS.medicine.tab).focus();
  }

  window.ClinicLists = { init, buildPanel, load, rerender, clearLive: () => Object.keys(KINDS).forEach((k) => setLive(k, "")), kinds: KINDS };
})();
