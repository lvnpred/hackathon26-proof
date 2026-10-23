"use strict";
// Team panel (spec 8.2): the clinic's users, add one, disable/enable, reset a password.
// Builds its own dialog, so index.html carries only the #teamOpenBtn button. Loaded after auth.js,
// whose fetch wrapper adds the X-DD-Client header and sends a 401 to the login page.
(function () {
  const API = "/api/v1/users";
  const t = { me: null, dialog: null, tabs: null, admin: false, owner: false };
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

  // Medicines and Investigations tabs (clinlists.js): built and inserted for clinic admins only (showListTabs), so a
  // doctor's page has no such element at all; the server answers 403 to them on the learned-name Remove as well.
  const TABS = [["teamTabMeds", "teamMeds", "Medicines", "medicine"], ["teamTabTests", "teamTests", "Investigations", "investigation"]];
  const OWNER_TAB = ["teamTabShared", "teamShared", "Shared lists", "shared"];   // the app owner's tab (ownerlists.js)
  function buildTabs() {
    const tabs = make("div", { class: "team-tabs", role: "tablist", "aria-label": "Team sections" });
    tabs.append(make("button", { id: "teamTabPeople", type: "button", class: "team-tab", role: "tab", "aria-selected": "true", "aria-controls": "teamPeople" }, "People"));
    shownTabs().forEach(([tab, panel, label]) => tabs.append(make("button", { id: tab, type: "button", class: "team-tab", role: "tab", "aria-selected": "false", "aria-controls": panel }, label)));
    return tabs;
  }
  function shownTabs() {                           // the tabs this user gets: clinic lists for admins, Shared lists for the owner
    return (t.admin && window.ClinicLists ? TABS : []).concat(t.owner && window.OwnerLists ? [OWNER_TAB] : []);
  }
  function selectTab(kind) {                       // kind: "medicine" | "investigation" | "shared" | null for People
    el("teamPeople").hidden = Boolean(kind);
    el("teamTabPeople").setAttribute("aria-selected", String(!kind));
    t.dialog.setAttribute("data-wide", String(Boolean(kind)));   // a list tab's table gets the wide dialog (team.css)
    shownTabs().forEach(([tab, panel, , k]) => {
      el(panel).hidden = k !== kind;
      el(tab).setAttribute("aria-selected", String(k === kind));
    });
    showErr("");
    if (t.admin && window.ClinicLists) window.ClinicLists.clearLive();
    if (t.owner && window.OwnerLists) window.OwnerLists.clearLive();
    if (window.Mishearings && el("teamMishear")) window.Mishearings.clearLive();
    if (kind === "shared") window.OwnerLists.load();
    else if (kind) { window.ClinicLists.load(kind); if (kind === "medicine" && window.Mishearings && el("teamMishear")) window.Mishearings.load(); }
  }
  async function whoami() {                        // the signed-in user, from /api/v1/auth/me; anything unclear is "not an admin, not the owner"
    try {
      const r = await fetch("/api/v1/auth/me");
      return r.ok ? await r.json() : {};
    } catch (e) { return {}; }
  }
  function showListTabs() {
    const tabs = shownTabs();
    if (!tabs.length) return;
    const people = el("teamPeople");
    people.setAttribute("role", "tabpanel");
    people.setAttribute("aria-labelledby", "teamTabPeople");
    const host = { send, showErr, errText: () => el("teamError").textContent };
    t.tabs = buildTabs();
    people.parentNode.insertBefore(t.tabs, people);
    if (t.admin && window.ClinicLists) {
      window.ClinicLists.init(host);
      TABS.forEach(([, , , kind]) => people.parentNode.append(window.ClinicLists.buildPanel(kind)));
      if (window.Mishearings) { window.Mishearings.init(host); el("teamMeds").append(window.Mishearings.buildSection()); }   // plan SH-H2
    }
    if (t.owner && window.OwnerLists) {
      window.OwnerLists.init(host);
      people.parentNode.append(window.OwnerLists.buildPanel());
    }
    el("teamTabPeople").addEventListener("click", () => selectTab(null));
    tabs.forEach(([tab, , , kind]) => el(tab).addEventListener("click", () => selectTab(kind)));
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
    return isNaN(d.getTime()) ? iso : (window.Dates && window.Dates.dateTime(iso)) || iso;   // clinic zone, "17 Oct 2026, 3:05 pm"
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
    if (t.tabs) selectTab(null);                 // always start on People
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
    const me = await whoami();                    // decided before the dialog is built: a doctor's page never has the admin controls
    t.admin = me.role === "admin";
    t.owner = me.is_owner === true;
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
    showListTabs();
  });
})();
