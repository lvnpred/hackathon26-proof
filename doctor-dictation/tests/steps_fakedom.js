// A tiny fake DOM so frontend/steps.js can run under node: elements by id, text, attributes, hidden flags, listeners, and a
// MutationObserver that records what it watches and runs on demand (D.fire()). Only what steps.js touches is implemented.
"use strict";
class El {
  constructor(tag) { this.tag = tag; this.children = []; this._text = ""; this.attrs = {}; this.dataset = {}; this.hidden = false; this.className = ""; this.listeners = {}; this.value = ""; this.disabled = false; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get firstChild() { return this.children[0]; }
  get lastChild() { return this.children[this.children.length - 1]; }
  appendChild(c) { this.children.push(c); return c; }
  append(...n) { n.forEach((x) => (typeof x === "string" ? (this._text += x) : this.appendChild(x))); }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  click() { this.clicks = (this.clicks || 0) + 1; (this.listeners.click || []).forEach((f) => f({ target: this })); }
  closest() { return null; }
  focus() {}
}
const IDS = ["steps", "agentChip", "profilePanel", "profSteps", "profClinic", "profDoctor", "profLhStatus", "profLhMine", "profLhHint", "profLhTitle",
  "lhPanel", "lhSteps", "lhProgress", "lhProgressText", "lhUpload", "lhReview", "lhDone", "lhError", "lhCloseBtn", "lhStatus"];
const els = {};
IDS.forEach((id) => { els[id] = new El("x"); els[id].id = id; });
["profLhMine", "profLhHint", "lhReview", "lhDone", "lhError", "lhProgress"].forEach((id) => { els[id].hidden = true; });
els.profLhStatus._text = "Checking your letterhead…";
const watchers = [], observed = [];
globalThis.MutationObserver = class { constructor(fn) { this.fn = fn; watchers.push(fn); } observe(n) { observed.push(n.id); } };
globalThis.document = { getElementById: (id) => els[id] || null, createElement: (t) => new El(t), createElementNS: (ns, t) => new El(t) };
globalThis.window = globalThis;
const lis = (id) => els[id].children;
module.exports = { els, observed, fire: () => watchers.forEach((f) => f()),
  status: (id) => lis(id).map((li) => li.className.replace(/^stp /, "")),
  subs: (id) => lis(id).map((li) => li.lastChild.children[1].textContent),
  current: (id) => lis(id).map((li) => li.attrs["aria-current"] || null) };
