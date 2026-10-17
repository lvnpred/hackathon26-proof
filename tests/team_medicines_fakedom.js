// A tiny fake DOM and fake server so frontend/team.js can run under node (no jsdom): open({role, ...}) loads team.js,
// fires DOMContentLoaded and returns the page. Elements are found by walking what is attached to <body>, so an element
// team.js never inserted (the Clinic medicines tab for a doctor) is simply not there.
"use strict";
const fs = require("fs");
const tick = () => new Promise((r) => setTimeout(r, 5));

class Node {
  constructor(tag) {
    Object.assign(this, { tag, children: [], attrs: {}, listeners: {}, hidden: false, disabled: false, value: "", _text: "", parentNode: null });
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

// opts: role (the /auth/me role; null = /auth/me answers 404), items, users, me, delete: [status, body] or a function,
//       list: [status, body] for GET /api/v1/formulary, answers: confirm() replies in order (default: always true)
async function open(opts = {}) {
  let items = (opts.items || []).slice();
  const gate = { hold: null }, calls = [], confirms = [], answers = (opts.answers || []).slice();
  const body = new Node("body");
  const ids = new Proxy({}, { get: (_t, id) => body.descendants().find((n) => n.attrs.id === id) });
  const openBtn = new Node("button");
  openBtn.setAttribute("id", "teamOpenBtn");
  body.append(openBtn);
  let boot;
  global.document = { createElement: (tag) => new Node(tag), getElementById: (id) => ids[id] || null, body, activeElement: null,
                      addEventListener: (type, fn) => { if (type === "DOMContentLoaded") boot = fn; } };
  global.window = { confirm: (m) => { confirms.push(m); return answers.length ? answers.shift() : true; }, addEventListener() {} };
  const reply = (status, b) => ({ ok: status < 300, status, json: async () => { if (b === undefined) throw new Error("not json"); return b; } });
  global.fetch = async (url, init = {}) => {
    const method = init.method || "GET";
    calls.push(method + " " + url);
    if (gate.hold) { const held = await gate.hold(method, url); if (held) return reply(...held); }   // a test can park a request and answer it later
    if (url === "/api/v1/auth/me") return opts.role ? reply(200, { role: opts.role }) : reply(404, { error: "off" });
    if (url === "/api/v1/users") return reply(200, { users: opts.users || [], me: opts.me || 0 });
    if (url === "/api/v1/formulary" && method === "GET") return opts.list ? reply(...opts.list) : reply(200, { items });
    if (method === "DELETE") {
      const r = typeof opts.delete === "function" ? opts.delete(url) : opts.delete || [200, {}];
      if (r[0] < 300) items = items.filter((i) => url !== "/api/v1/formulary/" + i.id);       // a real removal leaves the list
      return reply(r[0], r[1]);
    }
    throw new Error("unexpected " + method + " " + url);
  };
  (0, eval)(fs.readFileSync(process.argv[2], "utf8"));
  await boot();
  await tick();
  return { ids, calls, confirms, body, tick, gate,
    openTeam: async () => { await ids.teamOpenBtn.click(); await tick(); },
    openMeds: async () => { await ids.teamTabMeds.click(); await tick(); },
    rows: () => ids.teamMedRows.children.map((tr) => tr.children.map((td) => td.textContent)),
    removeButton: (i) => ids.teamMedRows.children[i].children.slice(-1)[0].children[0] };
}

const ITEMS = [
  { id: 7, name: "Zorbexin", generic: "", confirm_count: 2, first_seen_at: "2026-10-01T10:00:00Z", last_seen_at: "2026-10-02T10:00:00Z", added_by: 5 },
  { id: 9, name: "Quelvarin", generic: "", confirm_count: 3, first_seen_at: "2026-10-01T10:00:00Z", last_seen_at: "2026-10-03T10:00:00Z", added_by: null },
  { id: 11, name: "Mystara", generic: "", confirm_count: 2, first_seen_at: "2026-10-01T10:00:00Z", last_seen_at: "2026-10-04T10:00:00Z", added_by: 99 },
];
const USERS = [{ id: 5, username: "dr.rao", display_name: "Dr. Rao", is_active: true }, { id: 6, username: "dr.nodisplay", display_name: "", is_active: true }];
module.exports = { open, ITEMS, USERS, tick, sample: { items: ITEMS, users: USERS } };
