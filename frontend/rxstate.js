"use strict";
// Pure row-state logic for the medication rows (no DOM, no network): the page, the tests (node) and the
// summary bar all read the same rules. One predicate matters most: a row "needs you" exactly when the
// server's save gate (core/safety.py screen_unverified) would block it, i.e. status is not "verified"
// and the doctor has not confirmed it. Everything else here is wording and icon choice.
(function (root) {
  // Strings pass; numbers stringify; objects, arrays, booleans and null are "" (never "[object Object]").
  const str = (v) => (typeof v === "string" ? v : typeof v === "number" && Number.isFinite(v) ? String(v) : "");
  const optsOf = (l) => (Array.isArray(l) ? l.map(str).map((o) => o.trim()).filter(Boolean) : []);
  const same = (a, b) => str(a).trim().toLowerCase() === str(b).trim().toLowerCase();
  const DOSE_STATUS = ["unverified-strength", "dose-check"];
  const NEEDS = ["dose", "confirm"];
  const ICON = { ok: "check-circle", dose: "capsule", confirm: "triangle", you: "shield-check", known: "book" };
  const LABEL = { ok: "Matched", dose: "Check dose", confirm: "Confirm medicine", you: "Confirmed by you", known: "Known to your clinic" };
  const META_KEYS = ["heard", "lookalike", "generic", "usual_strength", "dose_note", "source"];
  const MAX_CHIPS = 8;
  // The extra row fields the server sends (contract 4.1), with safe defaults.
  function metaOf(r) {
    r = r || {};
    const m = {};
    META_KEYS.forEach((k) => { m[k] = str(r[k]); });
    m.strength_options = optsOf(r.strength_options);
    return m;
  }
  function chipsFor(row) {
    row = row || {};
    const usual = str(row.usual_strength).trim();
    const opts = optsOf(row.strength_options);
    const seen = new Set();
    const list = [];
    opts.forEach((o) => { const k = o.toLowerCase(); if (!seen.has(k)) { seen.add(k); list.push(o); } });
    list.sort((a, b) => (same(b, usual) ? 1 : 0) - (same(a, usual) ? 1 : 0));   // stable: usual first, rest keep order
    return list.slice(0, MAX_CHIPS).map((label) => ({ label, usual: usual !== "" && same(label, usual) }));
  }
  function reasonFor(row, state, ctx) {
    const status = str(row.status);
    const name = str(row.name).trim();
    const heard = str(row.heard).trim();
    const strength = str(ctx.strength != null ? ctx.strength : row.strength).trim();
    const note = str(row.dose_note).trim();
    const options = optsOf(row.strength_options);
    if (state === "ok") {                           // the server marks a blank strength "verified": do not claim a strength match
      if (!strength) return "Name matches the medicine list. No strength was given.";
      return options.length ? "Name and strength match the medicine list." : "Name matches the medicine list.";
    }
    if (state === "known") return "Known to your clinic from earlier prescriptions. There is no dose reference for it yet.";
    if (state === "you") {
      const how = str(ctx.how);
      const base = how === "spell" ? "You chose this name." : how === "chip" ? (strength ? "You chose the strength " + strength + "." : "You chose a strength.") : "You accepted this row as written.";
      return note ? base + " Note: " + note : base;
    }
    if (state === "dose") {
      if (status === "dose-check") {
        if (str(ctx.how) === "chip-open" && strength) return "You changed the strength to " + strength + ". Check the dose again.";
        return note || "The daily total looks higher than usual. Check the dose.";
      }
      if (strength && options.some((o) => same(o, strength))) return strength + " is one of its strengths. Confirm it or tap another.";
      const tap = options.length ? " Tap one below." : "";
      return (strength ? "Strength " + strength + " is not one this medicine usually comes in." : "No strength was dictated.") + tap;
    }
    if (status === "lookalike-check") {
      const twin = str(row.lookalike).trim();
      return (heard ? 'Heard "' + heard + '". ' : "") + (twin ? "It looks like " + twin + ". They are different medicines." : "Another medicine has a very similar name.");
    }
    if (status === "unknown-medicine") return (heard || name) ? '"' + (heard || name) + '" is not in the medicine list.' : "This medicine is not in the medicine list.";
    if (status === "unverified-name") return (heard ? 'Heard "' + heard + '". ' : "") + "The name was not clearly dictated.";
    if (status === "") return "You changed this row. Confirm it before saving.";
    return "This row needs a check (status: " + status + ").";
  }
  // row: the Rx row fields (status, source, heard, lookalike, dose_note, strength_options, usual_strength, ...).
  // ctx: { confirmed: bool, strength: current strength text, how: "confirm" | "spell" | "chip" }.
  function rowState(row, ctx) {
    row = row || {};
    ctx = ctx || {};
    // The status is compared on the RAW value, like the server (status == "verified"): only the exact string
    // "verified" is verified. A non-string status (array, number, object, boolean) is unreadable: a safe confirm.
    const raw = row.status;
    const status = typeof raw === "string" ? raw : raw == null ? "" : "unreadable";
    let state;
    if (ctx.confirmed) state = "you";
    else if (status === "verified") state = row.source === "clinic" ? "known" : "ok";
    else if (DOSE_STATUS.indexOf(status) >= 0) state = "dose";
    else state = "confirm";                       // name statuses, "" (edited) and any future status: the safe side
    const edited = state === "confirm" && status === "";
    return {
      state,
      icon: ICON[state],
      label: edited ? "Confirm row" : LABEL[state],
      reason: reasonFor(Object.assign({}, row, { status }), state, ctx),
      needsYou: NEEDS.indexOf(state) >= 0,
      canConfirm: NEEDS.indexOf(state) >= 0,
      canSpell: state === "confirm",
      canReopen: state === "you",
      chips: state === "dose" ? chipsFor(row) : [],
    };
  }
  // After an edit by hand the old reasons are stale: drop them (a name edit also drops what belonged to the old name).
  function afterEdit(meta, col) {
    const m = Object.assign({}, meta);
    m.heard = ""; m.lookalike = ""; m.dose_note = "";
    if (col === "name") { m.generic = ""; m.source = ""; m.usual_strength = ""; m.strength_options = []; }
    return m;
  }
  // counts: {total, needs, checking} -> the summary bar words and the Save button.
  function summary(counts) {
    counts = counts || {};
    const n = (x) => { const v = Math.floor(Number(x)); return Number.isFinite(v) && v > 0 ? v : 0; };
    const total = n(counts.total), checking = n(counts.checking), needs = Math.min(n(counts.needs), total);
    return {
      title: total + (total === 1 ? " medicine" : " medicines"),
      ready: (total - needs) + " ready",
      needs: needs + (needs === 1 ? " needs you" : " need you"),
      saveLabel: checking ? "Checking..." : needs ? "Resolve " + needs + " to save" : "Save prescription",
      saveDisabled: checking > 0 || needs > 0,
    };
  }
  root.RxState = { rowState, metaOf, chipsFor, afterEdit, summary, NEEDS };
})(typeof window !== "undefined" ? window : globalThis);
