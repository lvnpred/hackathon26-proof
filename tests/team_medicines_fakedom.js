// A tiny fake DOM and fake server so frontend/team.js can run under node (no jsdom): open({role, ...}) loads team.js,
// fires DOMContentLoaded and returns the page. Elements are found by walking what is attached to <body>, so an element
// team.js never inserted (the Clinic medicines tab for a doctor) is simply not there.
"use strict";
const fs = require("fs");
const tick = () => new Promise((r) => setTimeout(r, 5));

class Node {
  constructor(tag) {
    Object.assign(this, { tag, children: [], attrs: {}, listeners: {}, hidden: false, disabled: false, checked: false, value: "", _text: "", parentNode: null });
  }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get id() { return this.attrs.id; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  append(...kids) { kids.forEach((k) => { k.parentNode = this; this.children.push(k); }); }
  insertBefore(kid, ref) { kid.parentNode = this; this.children.splice(this.children.indexOf(ref), 0, kid); }
  replaceChildren(...kids) { this.children = []; this._text = ""; this.append(...kids); }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  async fire(type) { for (const fn of this.listeners[type] || []) await fn({ preventDefault() {}, target: this }); }
  click() { return this.fire("click"); }
  focus() { global.document.activeElement = this; }
  showModal() { this.open = true; }
  close() { this.open = false; this.fire("close"); }
  reset() {}
  descendants() { return this.children.flatMap((c) => [c, ...c.descendants()]); }
  // comma lists of descendant chains of simple selectors: ".cls", "#id", "tag" (what team.js uses), matched for real
  matches(simple) { return simple.split(/(?=[.#])/).every((p) => p[0] === "." ? (this.attrs.class || "").split(/\s+/).includes(p.slice(1)) : p[0] === "#" ? this.attrs.id === p.slice(1) : this.tag === p); }
  matchesChain(chain) {
    const parts = chain.trim().split(/\s+/);
    if (!this.matches(parts.pop())) return false;
    let up = this.parentNode;
    while (parts.length && up) { if (up.matches && up.matches(parts[parts.length - 1])) parts.pop(); up = up.parentNode; }
    return parts.length === 0;
  }
  querySelectorAll(sel) { const chains = sel.split(","); return this.descendants().filter((n) => chains.some((c) => n.matchesChain(c))); }
}

// A formulary row as the list screen shows it: a learned item (Task 6's item shape) that keeps its id for Remove.
const learned = (m) => ({ entry_key: m.name.toLowerCase(), badge: "learned", flag: "", entry: { canonical: m.generic || "", brands: [m.name] }, shipped: null, base_sha_now: "", formulary_id: m.id, pending: null });
// opts: role (the /auth/me role; null = /auth/me answers 404), items, users, me, delete: [status, body] or a function,
//       lists: {medicine, investigation} item arrays for GET /api/v1/lists/{kind} (default: items shown as learned names),
//       change: [status, body] or a function(body) for POST /api/v1/lists/{kind}/changes (default 200 {item: null}); the bodies land in posts,
//       list: [status, body] for GET /api/v1/lists/medicine, answers: confirm() replies in order (default: always true),
//       mishearings: items for GET /api/v1/spoken/mishearings, mishearDelete: [status, body] for DELETE /api/v1/spoken/mishearings/{id}
async function open(opts = {}) {
  let items = (opts.items || []).slice();
  let mishear = (opts.mishearings || []).slice();
  const gate = { hold: null }, calls = [], posts = [], confirms = [], ownerPosts = [], downloads = [], blobs = [], answers = (opts.answers || []).slice();
  const body = new Node("body");
  const ids = new Proxy({}, { get: (_t, id) => body.descendants().find((n) => n.attrs.id === id) });
  const openBtn = new Node("button");
  openBtn.setAttribute("id", "teamOpenBtn");
  body.append(openBtn);
  let boot;
  global.document = { createElement: (tag) => { const n = new Node(tag); if (tag === "a") n.addEventListener("click", () => downloads.push({ download: n.attrs.download, href: n.attrs.href })); return n; }, getElementById: (id) => ids[id] || null, body, activeElement: null,
                      addEventListener: (type, fn) => { if (type === "DOMContentLoaded") boot = fn; } };
  global.window = { confirm: (m) => { confirms.push(m); return answers.length ? answers.shift() : true; }, addEventListener() {} };
  const reply = (status, b, headers = {}) => ({ ok: status < 300, status, json: async () => { if (b === undefined) throw new Error("not json"); return b; },
    headers: { get: (k) => headers[k] || null }, blob: async () => new Blob([JSON.stringify(b)]) });
  global.URL = { createObjectURL: (blob) => { blobs.push(blob); return "blob:fake-" + blobs.length; }, revokeObjectURL() {} };
  global.fetch = async (url, init = {}) => {
    const method = init.method || "GET";
    calls.push(method + " " + url);
    if (gate.hold) { const held = await gate.hold(method, url); if (held) return reply(...held); }   // a test can park a request and answer it later
    if (url === "/api/v1/auth/me") return opts.role ? reply(200, { role: opts.role, is_owner: opts.is_owner === true }) : reply(404, { error: "off" });
    if (url.startsWith("/api/v1/owner/lists/")) {      // opts.owner: {medicine: {items, pending}, ...}; opts.ownerChange / opts.ownerExport: [status, body, headers]
      const [kind, tail] = url.slice("/api/v1/owner/lists/".length).split("/");
      if (method === "GET" && tail === undefined) return reply(200, { kind, ...((opts.owner || {})[kind] || { items: [], pending: [] }) });
      if (method === "GET" && tail === "export") return reply(...(opts.ownerExport || [200, { kind, changes: [] }, { "Content-Disposition": 'attachment; filename="list-changes-' + kind + '-2026-10-20.json"' }]));
      if (method === "POST" && tail === "changes") {
        const sent = JSON.parse(init.body);
        ownerPosts.push({ kind, ...sent });
        return reply(...(typeof opts.ownerChange === "function" ? opts.ownerChange(sent) : opts.ownerChange || [200, { change: null }]));
      }
    }
    if (url === "/api/v1/users") return reply(200, { users: opts.users || [], me: opts.me || 0 });
    if (url.startsWith("/api/v1/lists/") && method === "GET") {
      const kind = url.slice("/api/v1/lists/".length);
      if (kind === "medicine" && opts.list) return reply(...opts.list);
      const shown = (opts.lists || {})[kind] || (kind === "medicine" ? items.map(learned) : []);   // learned names come from the formulary-shaped items
      return reply(200, { kind, items: shown, flags: shown.filter((i) => i.flag).length, pending: shown.filter((i) => i.pending).length });
    }
    if (method === "POST" && /^\/api\/v1\/lists\/[a-z]+\/changes$/.test(url)) {
      const sent = JSON.parse(init.body);
      posts.push(sent);
      return reply(...(typeof opts.change === "function" ? opts.change(sent) : opts.change || [200, { item: null }]));
    }
    if (url === "/api/v1/spoken/mishearings" && method === "GET") return reply(200, { items: mishear });
    if (method === "DELETE" && url.startsWith("/api/v1/spoken/mishearings/")) {        // opts.mishearDelete: [status, body]
      const r = opts.mishearDelete || [200, {}];
      if (r[0] < 300) mishear = mishear.filter((m) => url !== "/api/v1/spoken/mishearings/" + m.id);
      return reply(r[0], r[1]);
    }
    if (method === "DELETE") {
      const r = typeof opts.delete === "function" ? opts.delete(url) : opts.delete || [200, {}];
      if (r[0] < 300) items = items.filter((i) => url !== "/api/v1/formulary/" + i.id);       // a real removal leaves the list
      return reply(r[0], r[1]);
    }
    throw new Error("unexpected " + method + " " + url);
  };
  if (opts.dates) { require(require("path").join(__dirname, "..", "frontend", "dates.js")); global.window.Dates.init(opts.dates); }   // the page's date formatter, as index.html loads it before team.js
  (0, eval)(fs.readFileSync(require("path").join(__dirname, "..", "frontend", "listedit.js"), "utf8"));    // before clinlists.js, as in index.html
  (0, eval)(fs.readFileSync(require("path").join(__dirname, "..", "frontend", "clinlists.js"), "utf8"));   // loaded before team.js, as in index.html
  (0, eval)(fs.readFileSync(require("path").join(__dirname, "..", "frontend", "mishear.js"), "utf8"));      // after clinlists.js, before team.js, as in index.html
  (0, eval)(fs.readFileSync(require("path").join(__dirname, "..", "frontend", "ownerlists.js"), "utf8"));
  (0, eval)(fs.readFileSync(process.argv[2], "utf8"));
  await boot();
  await tick();
  return { ids, calls, confirms, posts, ownerPosts, downloads, blobs, body, tick, gate,
    openTeam: async () => { await ids.teamOpenBtn.click(); await tick(); },
    openMeds: async () => { await ids.teamTabMeds.click(); await tick(); },
    openShared: async () => { await ids.teamTabShared.click(); await tick(); },
    openTests: async () => { await ids.teamTabTests.click(); await tick(); },
    rows: () => ids.teamMedRows.children.map((tr) => tr.children.map((td) => td.textContent)),
    testRows: () => ids.teamTestRows.children.map((tr) => tr.children.map((td) => td.textContent)),
    type: async (id, v) => { ids[id].value = v; await ids[id].fire("input"); },
    tick2: tick,
    removeButton: (i) => ids.teamMedRows.children[i].children.slice(-1)[0].children.find((b) => b.textContent === "Remove"),
    labels: (rowsId, i) => ids[rowsId].children[i].children.slice(-1)[0].children.map((b) => b.textContent),
    press: async (rowsId, i, label) => { ids[rowsId].children[i].children.slice(-1)[0].children.find((b) => b.textContent === label).click(); await tick(); await tick(); },   // not awaited: Edit waits on the dialog
    fill: async (values) => { Object.entries(values).forEach(([id, v]) => { ids[id].value = v; }); await ids.listEditDialog.querySelectorAll("form")[0].fire("submit"); await tick(); } };
}

const ITEMS = [
  { id: 7, name: "Zorbexin", generic: "", confirm_count: 2, first_seen_at: "2026-10-01T10:00:00Z", last_seen_at: "2026-10-02T10:00:00Z", added_by: 5 },
  { id: 9, name: "Quelvarin", generic: "", confirm_count: 3, first_seen_at: "2026-10-01T10:00:00Z", last_seen_at: "2026-10-03T10:00:00Z", added_by: null },
  { id: 11, name: "Mystara", generic: "", confirm_count: 2, first_seen_at: "2026-10-01T10:00:00Z", last_seen_at: "2026-10-04T10:00:00Z", added_by: 99 },
];
const USERS = [{ id: 5, username: "dr.rao", display_name: "Dr. Rao", is_active: true }, { id: 6, username: "dr.nodisplay", display_name: "", is_active: true }];
module.exports = { open, learned, ITEMS, USERS, tick, sample: { items: ITEMS, users: USERS } };
