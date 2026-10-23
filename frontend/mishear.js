"use strict";
// The "Corrected mishearings" section of the Team page's Medicines tab (plan SH-H2): the pairs (word the speech engine
// wrote -> name a doctor corrected it to) that are put first in that doctor's speech hints, with Remove. Built
// for admins by team.js, which hands over its request helper through init(). Loaded after clinlists.js, before team.js.
// Every value comes from speech or a doctor's typing, so the rows are built with textContent only.
(function () {
  const URL = "/api/v1/spoken/mishearings";
  const TAB = "teamTabMeds";
  const COLS = ["Heard as", "Corrected to", "Doctor", "Prescriptions", "Actions"];
  const HINT = "Words the speech engine wrote that were saved as another name on two or more prescriptions. For that doctor, a known " +
    "medicine name is put first in the speech hints. Removing a pair is not permanent: it comes back only after two new documents show it again.";
  const GONE = "That pair was already removed. The list has been refreshed.";
  const host = { send: async () => null, showErr: () => {}, errText: () => "" };
  const state = { items: [], seq: 0, loaded: false };
  const el = (id) => document.getElementById(id);

  function make(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (k === "hidden") node.hidden = Boolean(v); else node.setAttribute(k, v); });
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function init(h) { Object.assign(host, h); }
  function setLive(m) { el("teamMishearLive").textContent = m || ""; }
  const pairText = (m) => '"' + m.heard + '" to ' + m.spoken;

  function buildSection() {
    const hrow = make("tr");
    COLS.forEach((h) => hrow.append(make("th", { scope: "col" }, h)));
    const thead = make("thead", { id: "teamMishearHead" });
    thead.append(hrow);
    const table = make("table", { class: "team-table team-meds-table" });
    table.append(thead, make("tbody", { id: "teamMishearRows" }));
    const box = make("div", { id: "teamMishearBox", class: "team-table-box", hidden: true });
    box.append(table);
    const section = make("section", { id: "teamMishear", class: "team-mishear", "aria-labelledby": "teamMishearTitle" });
    section.append(make("h3", { id: "teamMishearTitle" }, "Corrected mishearings"), make("p", { class: "team-hint" }, HINT),
      make("p", { id: "teamMishearLive", class: "team-live", role: "status" }),
      make("p", { id: "teamMishearEmpty", class: "team-hint", hidden: true }, "No corrected mishearings yet."), box);
    return section;
  }

  function render() {
    const rows = el("teamMishearRows");
    rows.replaceChildren();
    el("teamMishearEmpty").hidden = !state.loaded || state.items.length > 0;
    el("teamMishearBox").hidden = state.items.length === 0;          // no column headings over an empty or loading list
    state.items.forEach((m) => {
      const tr = make("tr", { "data-id": String(Number(m.id)) });
      tr.append(make("td", {}, m.heard), make("td", { "data-label": COLS[1] }, m.spoken), make("td", { "data-label": COLS[2] }, m.doctor || ""),
        make("td", { "data-label": COLS[3] }, String(Number(m.confirm_count) || 0)));
      const cell = make("td", { class: "team-row-actions" });
      const b = make("button", { type: "button", class: "team-mishear-remove", "aria-label": "Remove the pair " + pairText(m) }, "Remove");
      b.addEventListener("click", () => { if (!b.disabled) removePair(m, Array.from(rows.children).indexOf(tr), b); });
      cell.append(b);
      tr.append(cell);
      rows.append(tr);
    });
  }

  async function load() {
    const mine = ++state.seq;                        // only the newest load may draw: an older answer arriving late is dropped
    state.items = []; state.loaded = false;
    render();                                        // never show old rows as current while (or after failing) to reload
    setLive("Loading…");
    const b = await host.send(URL);
    if (mine !== state.seq) return;
    setLive("");
    if (b) { state.items = Array.isArray(b.items) ? b.items : []; state.loaded = true; render(); }   // on a failure the table stays empty and the error box says why
  }

  function focusAfterRemoval(index) {                // the Remove button now at this index, else the previous row's, else the tab
    const buttons = Array.from(el("teamMishearRows").children).map((tr) => tr.querySelectorAll(".team-mishear-remove")[0]).filter(Boolean);
    (buttons[index] || buttons[index - 1] || el(TAB)).focus();
  }
  async function removePair(m, index, button) {
    const name = pairText(m);
    if (!window.confirm("Remove the pair " + name + "? " + m.spoken + " is no longer put first in this doctor's speech hints. " +
      "The pair comes back only after two new documents show it again.")) return;
    setLive("");
    button.disabled = true;                          // one DELETE per row, however often it is clicked
    const b = await host.send(URL + "/" + Number(m.id), { method: "DELETE" }, GONE);
    if (!b) button.disabled = false;
    const msg = b ? "" : host.errText();               // the row on screen may be stale: reload it, keep the error visible
    await load();
    host.showErr(msg);
    if (b) setLive("Removed the pair " + name + ".");
    if (b) focusAfterRemoval(index); else el(TAB).focus();
  }

  window.Mishearings = { init, buildSection, load, clearLive: () => setLive("") };
})();
