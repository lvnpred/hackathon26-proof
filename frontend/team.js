"use strict";
// Team panel (spec 8.2): the clinic's users, add one, disable/enable, reset a password.
// Builds its own dialog, so index.html carries only the #teamOpenBtn button. Loaded after auth.js,
// whose fetch wrapper adds the X-DD-Client header and sends a 401 to the login page.
(function () {
  const API = "/api/v1/users";
  const MEDS = "/api/v1/formulary";
  const t = { me: null, dialog: null, tabs: null, names: {}, seq: 0, admin: false };
  const el = (id) => document.getElementById(id);
  const FIELDS = [
    ["teamNewUsername", "Username (3 to 40 letters, digits, '.', '_' or '-')", "username"],
    ["teamNewDisplay", "Display name", "display_name"],
    ["teamNewDoctor", "Doctor name, as printed (optional)", "doctor_name"],
    ["teamNewQual", "Qualifications (optional)", "qualifications"],
    ["teamNewReg", "Registration no. (optional)", "reg_no"],
  ];

  function make(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "hidden") node.hidden = Boolean(v); else node.setAttribute(k, v);
    });
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function build() {
    const d = make("dialog", { id: "teamPanel", class: "panel team-panel no-print", "aria-labelledby": "teamTitle" });
    const head = make("div", { class: "team-head" });
    head.append(make("h2", { id: "teamTitle", tabindex: "-1" }, "Team"), make("button", { id: "teamCloseBtn", type: "button" }, "Close"));
    const secretActions = make("div", { class: "team-secret-actions" });
    secretActions.append(make("button", { id: "teamCopyBtn", type: "button" }, "Copy"),
      make("button", { id: "teamSecretDoneBtn", type: "button" }, "Done, hide it"),
      make("span", { id: "teamCopyStatus", class: "team-copy-status" }));
    const secret = make("div", { id: "teamSecret", class: "team-secret", hidden: true });
    secret.append(make("p", { id: "teamSecretReady", class: "team-secret-ready", role: "status" }),
      make("p", { id: "teamSecretFor", class: "team-secret-for" }),
      make("code", { id: "teamSecretValue", class: "team-secret-value" }),
      make("p", { class: "team-secret-warn" }, "Copy it now: it will not be shown again. Give it to them in person; " +
        "they must choose their own password when they first sign in."),
      secretActions);
    const hrow = make("tr");
    ["Name", "Username", "Status", "Last sign-in", "Actions"].forEach((h) => hrow.append(make("th", { scope: "col" }, h)));
    const thead = make("thead");
    thead.append(hrow);
    const table = make("table", { class: "team-table" });
    table.append(thead, make("tbody", { id: "teamRows" }));
    const tableBox = make("div", { class: "team-table-box" });
    tableBox.append(table);
    const form = make("form", { id: "teamAddForm", class: "team-add" });
    form.append(make("h3", {}, "Add a user"));
    FIELDS.forEach(([id, label, name]) => {
      const field = make("label", { class: "field" }, label);
      const input = make("input", { id, name, type: "text", autocomplete: "off", maxlength: name === "username" ? "40" : "120" });
      if (name === "username") input.required = true;
      field.append(input);
      form.append(field);
    });
    form.append(make("button", { id: "teamAddBtn", type: "submit", class: "primary" }, "Add user"));
    const people = make("div", { id: "teamPeople", class: "team-tab-body" });   // a plain wrapper; an admin's tab strip makes it a tab panel
    people.append(secret, tableBox);
    if (t.admin) people.append(form);                // the add-user form, like Disable and Reset, is built for admins only (the server also says 403)
    const box = make("div", { class: "team-body" });
    box.append(make("div", { id: "teamError", class: "team-error", role: "alert", hidden: true }), people);
    d.append(head, box);
    return d;
  }

  // "Clinic medicines": the names this clinic learned from confirmed prescriptions. Built and inserted for clinic admins
  // only (showMedsTab), so a doctor's page has no such element at all; the server answers 403 to them as well.
  function buildTabs() {
    const tabs = make("div", { class: "team-tabs", role: "tablist", "aria-label": "Team sections" });
    tabs.append(make("button", { id: "teamTabPeople", type: "button", class: "team-tab", role: "tab", "aria-selected": "true", "aria-controls": "teamPeople" }, "People"),
      make("button", { id: "teamTabMeds", type: "button", class: "team-tab", role: "tab", "aria-selected": "false", "aria-controls": "teamMeds" }, "Clinic medicines"));
    return tabs;
  }
  function buildMeds() {
    const hrow = make("tr");
    ["Medicine", "Confirmed on", "Last seen", "Added by", "Actions"].forEach((h) => hrow.append(make("th", { scope: "col" }, h)));
    const thead = make("thead");
    thead.append(hrow);
    const table = make("table", { class: "team-table team-meds-table" });      // stacked per row on a phone (team.css)
    table.append(thead, make("tbody", { id: "teamMedRows" }));
    const tableBox = make("div", { class: "team-table-box" });
    tableBox.append(table);
    const panel = make("div", { id: "teamMeds", class: "team-tab-body", role: "tabpanel", "aria-labelledby": "teamTabMeds", hidden: true });
    panel.append(make("p", { class: "team-hint" }, "Medicines your doctors confirmed on saved documents. Your clinic recognises them when dictating, " +
      "and a row shows them as known to your clinic. Removing a name is not permanent: it comes back only after two new documents confirm it again."),
      make("p", { id: "teamMedLive", class: "team-live", role: "status" }),
      make("p", { id: "teamMedEmpty", class: "team-hint", hidden: true }, "Nothing learned yet."), tableBox);
    return panel;
  }
  function selectTab(meds) {
    el("teamPeople").hidden = meds;
    el("teamMeds").hidden = !meds;
    el("teamTabPeople").setAttribute("aria-selected", String(!meds));
    el("teamTabMeds").setAttribute("aria-selected", String(meds));
    showErr("");
    setLive("");
    if (meds) loadMeds(true);
  }
  function setLive(m) { el("teamMedLive").textContent = m || ""; }
  function renderMeds(items) {
    const rows = el("teamMedRows");
    rows.replaceChildren();
    el("teamMedEmpty").hidden = items.length > 0;
    items.forEach((m, index) => {
      const tr = make("tr");
      const added = m.added_by === null || m.added_by === undefined ? undefined : t.names[m.added_by];
      tr.append(make("td", {}, m.name), make("td", { "data-label": "Confirmed on" }, m.confirm_count + (m.confirm_count === 1 ? " document" : " documents")),
        make("td", { "data-label": "Last seen" }, when(m.last_seen_at)),
        make("td", { "data-label": "Added by" }, added || "Unknown"));   // null: learned in single mode or before sign-in
      const cell = make("td", { class: "team-row-actions" });
      const remove = make("button", { type: "button", class: "team-med-remove" }, "Remove");
      remove.setAttribute("aria-label", "Remove " + m.name + " from your clinic's medicines");
      remove.addEventListener("click", () => removeMed(m, index));
      cell.append(remove);
      tr.append(cell);
      rows.append(tr);
    });
  }
  async function loadNames() {                    // added_by is a user id: name it from the team list; Unknown if that cannot be read
    try {
      const r = await fetch(API);
      const b = r.ok ? await r.json() : {};
      t.names = {};
      (b.users || []).forEach((u) => { t.names[u.id] = u.display_name || u.username; });
    } catch (e) { /* the list still shows, with Unknown */ }
  }
  async function loadMeds(withNames) {
    const mine = ++t.seq;                          // only the newest load may draw: an older answer arriving late is dropped
    el("teamMedRows").replaceChildren();           // never show old rows as current while (or after failing) to reload
    el("teamMedEmpty").hidden = true;
    setLive("Loading…");
    if (withNames) await loadNames();
    const b = await send(MEDS);
    if (mine !== t.seq) return;
    setLive("");
    if (b) renderMeds(b.items || []);              // on a failure the table stays empty and the error box says why
  }
  function focusAfterRemoval(index) {              // next row's Remove, else the previous row's, else the tab
    const rows = el("teamMedRows").children;
    const row = rows[index] || rows[rows.length - 1];
    (row ? row.children[row.children.length - 1].children[0] : el("teamTabMeds")).focus();
  }
  async function removeMed(m, index) {
    if (!window.confirm("Remove " + m.name + " from your clinic's medicines? Doctors will be asked about it again, " +
      "and it comes back only after two new documents confirm it.")) return;
    setLive("");
    const b = await send(MEDS + "/" + Number(m.id), { method: "DELETE" }, "That medicine was already removed. The list has been refreshed.");
    const msg = b ? "" : el("teamError").textContent;     // the row on screen may be stale: reload it, keep the error visible
    await loadMeds(false);
    showErr(msg);
    if (b) setLive("Removed " + m.name + ". It comes back only after two new documents confirm it.");
    if (b) focusAfterRemoval(index); else el("teamTabMeds").focus();
  }
  async function isAdmin() {                       // the signed-in user's role, from /api/v1/auth/me; anything unclear is "not an admin"
    try {
      const r = await fetch("/api/v1/auth/me");
      const me = r.ok ? await r.json() : {};
      return me.role === "admin";
    } catch (e) { return false; }
  }
  function showMedsTab() {
    if (!t.admin) return;
    const people = el("teamPeople");
    people.setAttribute("role", "tabpanel");
    people.setAttribute("aria-labelledby", "teamTabPeople");
    t.tabs = buildTabs();
    people.parentNode.insertBefore(t.tabs, people);
    people.parentNode.append(buildMeds());
    el("teamTabPeople").addEventListener("click", () => selectTab(false));
    el("teamTabMeds").addEventListener("click", () => selectTab(true));
  }

  function errorText(b, status) {                 // our routes answer {"error"}; FastAPI's 422 answers {"detail": text | [{msg}]}
    if (b && typeof b.error === "string" && b.error) return b.error;
    const d = b && b.detail;
    if (typeof d === "string" && d) return d;
    if (Array.isArray(d) && d[0] && typeof d[0].msg === "string" && d[0].msg) return d[0].msg;
    return "Something went wrong (code " + status + "). Try again.";
  }

  function showErr(m) { const e = el("teamError"); e.textContent = m || ""; e.hidden = !m; }
  function when(iso) {
    if (!iso) return "Never";
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  }
  function showSecret(username, password) {
    el("teamSecretFor").textContent = "Temporary password for " + username + ":";
    el("teamSecretValue").textContent = password;
    el("teamSecretReady").textContent = "Password ready";
    el("teamCopyStatus").textContent = "";
    el("teamSecret").hidden = false;
    el("teamCopyBtn").focus();
  }
  function clearSecret() {
    el("teamSecretValue").textContent = "";
    el("teamSecretReady").textContent = "";
    el("teamSecret").hidden = true;
  }
  function doneSecret() {
    clearSecret();
    el("teamNewUsername").focus();                // the Done button just vanished: park focus on the Add form
  }
  async function copySecret() {
    const value = el("teamSecretValue").textContent;
    try {
      await navigator.clipboard.writeText(value);
      el("teamCopyStatus").textContent = "Copied.";
    } catch (e) {                                 // no clipboard access (plain http, old browser): select it instead
      const range = document.createRange();
      range.selectNodeContents(el("teamSecretValue"));
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      el("teamCopyStatus").textContent = "Copy is blocked here. The password is selected: press Ctrl+C (Cmd+C on a Mac).";
    }
  }

  function busy(on) {
    t.dialog.setAttribute("aria-busy", on ? "true" : "false");
    t.dialog.querySelectorAll(".team-row-actions button, #teamAddBtn").forEach((b) => { b.disabled = on; });
  }
  async function send(url, opts, notFound) {      // notFound: the wording for a 404 where it means "already gone"
    busy(true);
    showErr("");
    try {
      const r = await fetch(url, opts);
      let b = {};
      try { b = await r.json(); } catch (e) { /* not JSON */ }
      if (r.ok) return b;
      showErr(r.status === 503 ? "The server is busy. Try again in a moment."
        : r.status === 404 && notFound ? notFound : errorText(b, r.status));
    } catch (e) {
      showErr("Could not reach the server. Check your connection and try again.");
    } finally {
      busy(false);
    }
    return null;
  }

  function rowActions(u) {                          // Disable/Enable and Reset password: admins only; a doctor sees the list read-only
    if (!t.admin) return [];
    const who = u.display_name || u.username;
    const toggle = make("button", { type: "button" }, u.is_active ? "Disable" : "Enable");
    toggle.setAttribute("aria-label", (u.is_active ? "Disable " : "Enable ") + who);
    toggle.addEventListener("click", () => setActive(u, !u.is_active));
    const reset = make("button", { type: "button" }, "Reset password");
    reset.setAttribute("aria-label", "Reset password for " + who);
    reset.addEventListener("click", () => resetPassword(u));
    return [toggle, reset];
  }
  function render(users) {
    const rows = el("teamRows");
    rows.replaceChildren();
    users.forEach((u) => {
      const you = u.id === t.me;
      const tr = make("tr", { class: u.is_active ? "team-on" : "team-off" });
      tr.append(make("td", {}, u.display_name + (you ? " (you)" : "")), make("td", {}, u.username),
        make("td", {}, u.is_active ? "Active" : "Disabled"), make("td", {}, when(u.last_login_at)));
      const cell = make("td", { class: "team-row-actions" });
      if (!you) cell.append(...rowActions(u));
      tr.append(cell);
      rows.append(tr);
    });
  }
  async function refresh() {
    const b = await send(API);
    if (b) { t.me = b.me; render(b.users); }
  }

  async function failedThenRefresh() {           // the row on screen may be stale: reload it, keep the error visible
    const msg = el("teamError").textContent;
    await refresh();
    showErr(msg);
  }
  async function setActive(u, active) {
    if (!active && !window.confirm("Disable " + u.display_name + "? They are signed out at once and cannot sign in " +
      "until someone enables them again. Their prescriptions are kept.")) return;
    const b = await send(API + "/" + Number(u.id) + (active ? "/enable" : "/disable"), { method: "POST" });
    if (!b) return failedThenRefresh();
    await refresh();
    el("teamTitle").focus();
  }
  async function resetPassword(u) {
    if (!window.confirm("Reset the password for " + u.display_name + "? They are signed out at once and must sign in " +
      "with the new temporary password.")) return;
    const b = await send(API + "/" + Number(u.id) + "/reset-password", { method: "POST" });
    if (!b) return failedThenRefresh();
    if (!b.temporary_password) { showErr("The server did not return a temporary password. Try the reset again."); return; }
    await refresh();                              // rebuilds the rows first, so the Copy button keeps the focus
    showSecret(u.username, b.temporary_password);
  }
  async function addUser(ev) {
    ev.preventDefault();
    const payload = {};
    FIELDS.forEach(([id, , name]) => { payload[name] = el(id).value.trim(); });
    const b = await send(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (!b) return failedThenRefresh();
    if (!b.user || !b.temporary_password) { showErr("The server did not return a temporary password. Check the list, then reset it."); await refresh(); return; }
    el("teamAddForm").reset();
    await refresh();
    showSecret(b.user.username, b.temporary_password);
  }

  function openPanel() {
    clearSecret();
    showErr("");
    if (t.tabs) selectTab(false);                 // always start on People
    t.dialog.showModal();
    refresh();
  }

  document.addEventListener("DOMContentLoaded", async () => {
    const btn = el("teamOpenBtn");
    if (!btn) return;
    try {
      const r = await fetch(API);
      if (r.status !== 200) return;               // single mode (404) or not signed in: no Team button
    } catch (e) { return; }
    t.admin = await isAdmin();                    // decided before the dialog is built: a doctor's page never has the admin controls
    t.dialog = build();
    document.body.append(t.dialog);
    el("teamCloseBtn").addEventListener("click", () => t.dialog.close());
    window.addEventListener("pagehide", clearSecret);   // leaving the page (or bfcache): never keep it around
    t.dialog.addEventListener("close", clearSecret);   // Close or Escape: the temporary password is never shown twice
    el("teamCopyBtn").addEventListener("click", copySecret);
    el("teamSecretDoneBtn").addEventListener("click", doneSecret);
    if (t.admin) el("teamAddForm").addEventListener("submit", addUser);
    btn.addEventListener("click", openPanel);
    btn.hidden = false;
    showMedsTab();
  });
})();
