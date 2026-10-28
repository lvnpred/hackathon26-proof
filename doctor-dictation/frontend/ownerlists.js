"use strict";
// The app owner's "Shared lists" tab on the Team page (plan PQ-f, Task 11): propose changes to the shipped medicine and
// investigation lists, then download them as a file for the operator. Nothing here changes any clinic's list. Built only
// for the owner by team.js, which hands over its request helper through init(). The edit dialog is listedit.js.
(function () {
  const BASE = "/api/v1/owner/lists/";
  const HINT = "Changes here do not change any clinic's list. Download the file and give it to the operator to apply, commit and deploy.";
  const KINDS = {
    medicine: { label: "Medicines", cols: ["Medicine", "Generic", "Brands", "Status", "Actions"], add: "Add a medicine", none: "Nothing in this list yet." },
    investigation: { label: "Investigations", cols: ["Test", "Print", "Category", "Status", "Actions"], add: "Add a test", none: "No investigations in this list yet." },
  };
  const host = { send: async () => null, showErr: () => {}, errText: () => "" };
  const st = { kind: "medicine", items: [], adds: [], loaded: false, seq: 0 };
  const el = (id) => document.getElementById(id);

  function make(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (k === "hidden") node.hidden = Boolean(v); else node.setAttribute(k, v); });
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function init(h) { Object.assign(host, h); }
  function setLive(m) { el("ownerListLive").textContent = m || ""; }
  const pendingCount = () => st.items.filter((i) => i.pending).length + st.adds.length;

  function buildPanel() {
    const switchBar = make("div", { class: "team-tabs", role: "group", "aria-label": "List" });
    Object.entries(KINDS).forEach(([kind, k]) => {
      const b = make("button", { id: "ownerKind-" + kind, type: "button", class: "team-tab", "aria-pressed": String(kind === st.kind) }, k.label);
      b.addEventListener("click", () => switchKind(kind));
      switchBar.append(b);
    });
    const search = make("input", { id: "ownerListFilter", type: "search", autocomplete: "off", "aria-label": "Filter the list" });
    search.addEventListener("input", render);
    const bar = make("div", { class: "team-filter" });
    bar.append(search);
    const add = make("button", { id: "ownerListAdd", type: "button", class: "primary team-list-add" }, KINDS[st.kind].add);
    add.addEventListener("click", addEntry);
    const dl = make("button", { id: "ownerListDownload", type: "button", class: "team-list-act" }, "Download changes (0)");
    dl.disabled = true;
    dl.addEventListener("click", download);
    const table = make("table", { class: "team-table team-meds-table" });
    table.append(make("thead"), make("tbody", { id: "ownerListRows" }));
    const tableBox = make("div", { class: "team-table-box" });
    tableBox.append(table);
    const panel = make("div", { id: "teamShared", class: "team-tab-body", role: "tabpanel", "aria-labelledby": "teamTabShared", hidden: true });
    panel.append(make("p", { class: "team-hint" }, HINT), switchBar, make("p", { id: "ownerListLive", class: "team-live", role: "status" }),
      add, dl, bar, make("p", { id: "ownerListEmpty", class: "team-hint", hidden: true }, KINDS[st.kind].none), tableBox);
    return panel;
  }

  function cells(kind, row) {                          // [name, 2nd, 3rd] for a shipped row or a pending add
    const e = row.entry || {};
    const d = (row.pending && row.pending.data) || {};
    if (kind === "investigation") return [e.canonical || d.name || row.entry_key, d.print !== undefined ? d.print : e.print || "", d.category !== undefined ? d.category : e.category || ""];
    const brands = Array.isArray(d.brands) ? d.brands : Array.isArray(e.brands) ? e.brands : [];
    return [e.canonical || d.name || row.entry_key, e.canonical || d.generic || "", brands.join(", ")];
  }
  function status(row) {
    if (!row.pending) return row.safety ? "Safety entry" : "";
    return "Pending change" + (row.isAdd ? " (new entry)" : "");
  }
  function rows() {
    return st.items.map((i) => ({ ...i, safety: Boolean(i.entry && i.entry.safety) }))
      .concat(st.adds.map((a) => ({ entry_key: a.entry_key, entry: {}, pending: a, isAdd: true })));
  }

  function render() {
    const k = KINDS[st.kind];
    const text = el("ownerListFilter").value.trim().toLowerCase();
    const body = el("ownerListRows");
    body.replaceChildren();
    const all = rows();
    el("ownerListEmpty").hidden = !st.loaded || all.length > 0;
    el("ownerListEmpty").textContent = k.none;
    el("ownerListAdd").textContent = k.add;
    Object.keys(KINDS).forEach((x) => el("ownerKind-" + x).setAttribute("aria-pressed", String(x === st.kind)));
    const n = pendingCount();
    const dl = el("ownerListDownload");
    dl.textContent = "Download changes (" + n + ")";
    dl.disabled = n === 0;
    const head = el("ownerListRows").parentNode.children[0];
    const hr = make("tr");
    k.cols.forEach((h) => hr.append(make("th", { scope: "col" }, h)));
    head.replaceChildren(hr);
    all.forEach((row) => {
      const [a, b, c] = cells(st.kind, row);
      if (text && ![row.entry_key, a, b, c].join(" ").toLowerCase().includes(text)) return;
      const tr = make("tr", { "data-key": row.entry_key });
      tr.append(make("td", {}, a), make("td", { "data-label": k.cols[1] }, b), make("td", { "data-label": k.cols[2] }, c), make("td", { "data-label": k.cols[3] }, status(row)));
      const cell = make("td", { class: "team-row-actions" });
      ["Edit"].concat(row.pending ? ["Discard change"] : []).forEach((label) => {
        const btn = make("button", { type: "button", class: "team-list-act", "aria-label": label + " " + a }, label);
        btn.addEventListener("click", () => { if (!btn.disabled) (label === "Edit" ? editEntry(row, a) : discard(row, a, tr)); });
        cell.append(btn);
      });
      tr.append(cell);
      body.append(tr);
    });
  }

  async function load(kind) {
    if (kind) st.kind = kind;
    const mine = ++st.seq;                              // only the newest load may draw
    st.items = []; st.adds = []; st.loaded = false;
    render();
    setLive("Loading…");
    const b = await host.send(BASE + st.kind);
    if (mine !== st.seq) return;
    setLive("");
    if (b) { st.items = b.items || []; st.adds = b.pending || []; st.loaded = true; render(); }
  }
  function switchKind(kind) {
    if (kind === st.kind) return;
    st.kind = kind;
    setLive("");
    host.showErr("");
    load();
  }

  function focusRow(key) {
    const tr = Array.from(el("ownerListRows").children).find((r) => r.getAttribute("data-key") === key);
    const first = tr && tr.querySelectorAll("button")[0];
    (first || el("ownerListAdd")).focus();
  }
  async function change(body, name, done, tr) {          // one write, then reload and say what happened or show the server's words
    setLive("");
    const btns = tr ? tr.querySelectorAll("button") : [];
    btns.forEach((x) => { x.disabled = true; });          // one POST per row, however often it is clicked
    const kind = st.kind;
    const b = await host.send(BASE + kind + "/changes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const msg = b ? "" : host.errText();
    const same = st.kind === kind;                        // the owner may have switched lists while the POST was out
    if (same) await load(kind);
    host.showErr(msg);
    if (b) setLive(done(name));
    if (same) focusRow(body.entry_key);
  }
  async function editEntry(row, name) {
    const item = row.isAdd
      ? { entry_key: row.entry_key, entry: { safety: pendingSafety(row) }, shipped: null, pending: row.pending }
      : { entry_key: row.entry_key, entry: { ...row.entry, safety: pendingSafety(row) }, shipped: row.entry, pending: row.pending };
    const r = await window.ListEdit.open(st.kind, item, { owner: true });
    if (!r) return focusRow(row.entry_key);
    const body = { op: row.isAdd ? "add" : "edit", entry_key: row.entry_key, data: r.data };   // an owner edit of a pending add stays an add
    await change(body, (r.data && r.data.name) || name, (n) => "Saved " + n + " as a pending change.");
  }
  function pendingSafety(row) {
    const d = (row.pending && row.pending.data) || {};
    return typeof d.safety === "boolean" ? d.safety : Boolean(row.entry && row.entry.safety);
  }
  async function addEntry() {
    const r = await window.ListEdit.open(st.kind, null, { owner: true });
    if (!r) return el("ownerListAdd").focus();
    await change({ op: "add", entry_key: r.entry_key, data: r.data }, r.data.name || "", (n) => "Added " + n + " as a pending change.");
  }
  async function discard(row, name, tr) {
    if (!window.confirm("Discard the pending change to " + name + "?")) return;
    await change({ op: "drop", entry_key: row.entry_key, data: {} }, name, (n) => "Discarded the change to " + n + ".", tr);
  }

  async function download() {
    const kind = st.kind, btn = el("ownerListDownload");
    if (btn.disabled) return;
    btn.disabled = true;
    host.showErr("");
    try {
      const r = await fetch(BASE + kind + "/export");
      if (!r.ok) { let b = {}; try { b = await r.json(); } catch (e) { /* not JSON */ } host.showErr((b && b.error) || "Could not download the changes (code " + r.status + "). Try again."); return; }
      const m = /filename="?([^";]+)"?/.exec((r.headers && r.headers.get("Content-Disposition")) || "");
      const name = m ? m[1] : "list-changes-" + kind + ".json";
      const url = URL.createObjectURL(await r.blob());
      const a = make("a", { href: url, download: name });
      document.body.append(a);
      a.click();
      if (a.parentNode && a.parentNode.removeChild) a.parentNode.removeChild(a);
      URL.revokeObjectURL(url);
      setLive("Downloaded " + name + ".");
    } catch (e) {
      host.showErr("Could not reach the server. Check your connection and try again.");
    } finally {
      btn.disabled = pendingCount() === 0;
    }
  }

  window.OwnerLists = { init, buildPanel, load, clearLive: () => setLive("") };
})();
