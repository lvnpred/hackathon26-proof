"use strict";
// Team panel (spec 8.2): the clinic's users, add one, disable/enable, reset a password.
// Builds its own dialog, so index.html carries only the #teamOpenBtn button. Loaded after auth.js,
// whose fetch wrapper adds the X-DD-Client header and sends a 401 to the login page.
(function () {
  const API = "/api/v1/users";
  const t = { me: null, dialog: null };
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
    const box = make("div", { class: "team-body" });
    box.append(make("div", { id: "teamError", class: "team-error", role: "alert", hidden: true }), secret, tableBox, form);
    d.append(head, box);
    return d;
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
  async function send(url, opts) {
    busy(true);
    showErr("");
    try {
      const r = await fetch(url, opts);
      let b = {};
      try { b = await r.json(); } catch (e) { /* not JSON */ }
      if (r.ok) return b;
      showErr(r.status === 503 ? "The server is busy. Try again in a moment."
        : (b && b.error) || "Something went wrong (code " + r.status + "). Try again.");
    } catch (e) {
      showErr("Could not reach the server. Check your connection and try again.");
    } finally {
      busy(false);
    }
    return null;
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
      if (!you) {
        const who = u.display_name || u.username;
        const toggle = make("button", { type: "button" }, u.is_active ? "Disable" : "Enable");
        toggle.setAttribute("aria-label", (u.is_active ? "Disable " : "Enable ") + who);
        toggle.addEventListener("click", () => setActive(u, !u.is_active));
        const reset = make("button", { type: "button" }, "Reset password");
        reset.setAttribute("aria-label", "Reset password for " + who);
        reset.addEventListener("click", () => resetPassword(u));
        cell.append(toggle, reset);
      }
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
    t.dialog = build();
    document.body.append(t.dialog);
    el("teamCloseBtn").addEventListener("click", () => t.dialog.close());
    window.addEventListener("pagehide", clearSecret);   // leaving the page (or bfcache): never keep it around
    t.dialog.addEventListener("close", clearSecret);   // Close or Escape: the temporary password is never shown twice
    el("teamCopyBtn").addEventListener("click", copySecret);
    el("teamSecretDoneBtn").addEventListener("click", doneSecret);
    el("teamAddForm").addEventListener("submit", addUser);
    btn.addEventListener("click", openPanel);
    btn.hidden = false;
  });
})();
