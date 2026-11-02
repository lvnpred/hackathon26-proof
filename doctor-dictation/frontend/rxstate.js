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
  const META_KEYS = ["heard", "lookalike", "generic", "usual_strength", "dose_note", "source", "did_you_mean", "did_you_mean_generic", "schedule", "generic_source", "combo_base", "generic_suggestion", "generic_listed", "spelled_heard", "typed_heard"];
  const MAX_CHIPS = 8;
  // The extra row fields the server sends (contract 4.1), with safe defaults.
  function metaOf(r) {
    r = r || {};
    const m = {};
    META_KEYS.forEach((k) => { m[k] = str(r[k]); });
    m.said = str(r.said) || str(r.name);                              // the name the server last gave: page only, never sent
    m.strength_options = optsOf(r.strength_options);
    m.generic_pending = r.generic_pending === true;                  // older cached results lack these keys: default them
    m.generic_suggestion_unknown = optsOf(r.generic_suggestion_unknown);
    return m;
  }
  // The Drugs and Cosmetics Rules mark a screen badge may show: only H, H1 or X (the server sends nothing else); information only.
  const scheduleOf = (meta) => { const s = str((meta || {}).schedule); return s === "H" || s === "H1" || s === "X" ? s : ""; };
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
    if (status === "unknown-medicine" && str(row.combo_base).trim()) return '"' + (heard || name) + '" is a combination of ' + str(row.combo_base).trim() + ". Its generic is not in the medicine list.";
    if (status === "unknown-medicine") return (heard || name) ? '"' + (heard || name) + '" is not in the medicine list.' : "This medicine is not in the medicine list.";
    if (status === "unverified-name") return (heard ? 'Heard "' + heard + '". ' : "") + "The name was not clearly dictated.";
    if (status === "") return "You changed this row. Confirm it before saving.";
    return "This row needs a check (status: " + status + ").";
  }
  // A row that needs you for another reason AND has a pending doctor generic: confirming it confirms the generic too, so say so.
  function pendingNote(row, state, ctx) {
    const g = str(row.generic).trim();
    return !ctx.confirmed && row.generic_pending === true && g && NEEDS.indexOf(state) >= 0 ? " The generic " + g + " was entered for it." : "";
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
    // A generic the doctor typed stays pending until the doctor confirms the row: a matched row becomes "Confirm generic".
    const pendingGeneric = !ctx.confirmed && row.generic_pending === true && (state === "ok" || state === "known");
    if (pendingGeneric) state = "confirm";
    return {
      state,
      icon: ICON[state],
      label: pendingGeneric ? "Confirm generic" : edited ? "Confirm row" : LABEL[state],
      reason: pendingGeneric ? "You entered the generic " + str(row.generic).trim() + ". Confirm the row before saving."
        : reasonFor(Object.assign({}, row, { status }), state, ctx) + pendingNote(row, state, ctx),
      needsYou: NEEDS.indexOf(state) >= 0,
      canConfirm: NEEDS.indexOf(state) >= 0,
      canSpell: true,                               // every row that reaches here: a matched name can be changed too
      spellLabel: state === "confirm" && !pendingGeneric ? "Spell it" : "Change name",
      canReopen: state === "you",
      chips: state === "dose" ? chipsFor(row) : [],
      didYouMean: state === "confirm" && status === "unknown-medicine" && str(row.did_you_mean).trim() && !same(row.did_you_mean, row.name)
        ? { name: str(row.did_you_mean).trim(), generic: str(row.did_you_mean_generic).trim() } : null,
      // The doctor spelled this name over words that only sounded like it: the row offers those words back (core/spelled.py).
      spelledUndo: str(row.spelled_heard).trim() && !same(row.spelled_heard, row.name) ? { heard: str(row.spelled_heard).trim() } : null,
    };
  }
  // After an edit by hand the old reasons are stale: drop them (a name edit also drops what belonged to the old name).
  // typedFrom: the words a hand edit replaces, for the save to learn from (first non-blank wins, so the first keystroke decides).
  const typedFrom = (meta, priorName) => {
    meta = meta || {};
    const hit = [meta.typed_heard, meta.spelled_heard, meta.heard, priorName].map((v) => str(v).trim()).find(Boolean);
    return hit || "";
  };
  function afterEdit(meta, col) {
    const m = Object.assign({}, meta);
    m.typed_heard = typedFrom(meta, col === "name" ? (meta || {}).said : "");   // BEFORE heard and spelled_heard are cleared
    m.heard = ""; m.lookalike = ""; m.dose_note = "";
    if (col === "name") { m.generic = ""; m.source = ""; m.usual_strength = ""; m.strength_options = []; m.did_you_mean = ""; m.did_you_mean_generic = ""; m.schedule = ""; m.generic_source = ""; m.combo_base = ""; m.generic_suggestion = ""; m.generic_suggestion_unknown = []; m.generic_pending = false; m.generic_listed = ""; m.remember_generic = false; m.spelled_heard = ""; }
    return m;
  }
  // After "Use this": the doctor chose the NAME, so name questions are answered; dose questions and a name the
  // list still does not know stay open. Returns "you" (mark confirmed) or "stay" (leave to the row's state).
  function afterSpell(status) {
    return ["verified", "unverified-name", "lookalike-check"].indexOf(str(status)) >= 0 ? "you" : "stay";
  }

  // Letters said one by one ("p r e d n i s o l o n e") are joined; anything else only has its spaces tidied.
  function cleanTyped(s) {
    const t = str(s).replace(/\s+/g, " ").trim();
    return /^[A-Za-z]( [A-Za-z])+$/.test(t) ? t.replace(/ /g, "") : t;
  }
  // "" when fine, else the sentence to show (limits are the server's: 60 characters, 8 words).
  // Names are 2-60 characters of letters, digits, space . - / ( ) ' ,
  function typedProblem(s) {
    if (!s) return "Type a medicine name first.";
    if (s.length < 2) return "That is too short for a medicine name.";
    if (s.length > 60) return "That is too long for a medicine name (60 characters at most).";
    if (s.split(" ").length > 8) return "That is too many words for a medicine name (8 at most).";
    if (!/^[A-Za-z0-9][A-Za-z0-9 .\-\/()',]*$/.test(s)) return "Use letters and digits only.";
    return "";
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
      saveLabel: checking ? "Checking..." : needs ? "Resolve " + needs + " to save" : "Save & send home",
      saveDisabled: checking > 0 || needs > 0,
    };
  }
  // One sentence for a failed check-row call. err is what postJson throws. postJson's own fallback text
  // ("Request failed (422)") is dropped: the status is already in the sentence.
  function errorText(err) {
    if (err && err.aborted) return "The check took too long and was stopped.";
    if (err && err.status >= 500) return "The medicine check is not available right now.";     // no raw status or server text for a server fault
    if (err && err.status) {
      const m = str(err.message).trim();
      return "The server answered " + err.status + (m && m.indexOf("Request failed") !== 0 ? " (" + m + ")" : "") + ".";
    }
    return "Could not reach the server.";
  }

  // One sentence for a failed voice capture; phase "mic" (getUserMedia, the recorder, the clip) or "upload" (the transcribe call).
  function voiceError(e, phase) {
    const n = str(e && e.name), k = str(e && e.kind);
    if (n === "NotAllowedError" || n === "SecurityError") return "The microphone is blocked. Allow it in the browser, or type the name.";
    if (n === "NotFoundError" || n === "OverconstrainedError") return "No microphone was found. Type the name.";
    if (k === "no-recorder") return "Voice input is not supported in this browser. Type the name.";
    if (k === "no-audio") return "No sound was recorded. Try again, or type the name.";
    if (k === "no-speech") return "No name was heard. Try again, or type the name.";
    if (e && e.aborted) return "Reading the name took too long. Type the name instead.";
    if (phase === "upload") return e && e.status ? "Could not read that. Try again or type the name." : errorText(e).replace(/\.$/, "") + ". Type the name instead.";
    return "The microphone could not start. Type the name.";
  }

  // Which prior row id each row of a correction keeps: name + occurrence, the server's pairing
  // (core/correction.py `_paired_prior`); changed rows and an untrusted `changed_rows` get none.
  function carryRowids(priorRowids, priorRows, nextRows, changed) {
    if (!Array.isArray(nextRows)) return [];
    const n = nextRows.length;
    const out = nextRows.map(() => null);
    if (!Array.isArray(changed) || changed.some((i) => !Number.isInteger(i) || i < 0 || i >= n)) return out;
    const key = (r) => (typeof r.name === "string" ? r.name.trim().toLowerCase() : "");
    const isRow = (r) => r !== null && typeof r === "object" && !Array.isArray(r);
    const queues = new Map();
    (Array.isArray(priorRows) ? priorRows : []).forEach((r, i) => {
      if (!isRow(r)) return;
      if (!queues.has(key(r))) queues.set(key(r), []);
      queues.get(key(r)).push(i);
    });
    const ids = Array.isArray(priorRowids) ? priorRowids : [];
    const gone = new Set(changed);
    const used = new Set();
    nextRows.forEach((r, j) => {
      if (!isRow(r)) return;
      const q = queues.get(key(r));
      const at = q && q.length ? q.shift() : -1;
      const id = at >= 0 ? ids[at] : null;
      if (gone.has(j) || typeof id !== "string" || id === "" || used.has(id)) return;
      used.add(id);
      out[j] = id;
    });
    return out;
  }

  // The "[unverified: confirm with doctor]" and "[unverified strength: confirm with doctor]" texts check-row adds to Instructions; the doctor's
  // own confirmation removes exactly them (and one space before each). Other words, however similar, stay.
  function stripMarker(text) {
    return str(text).replace(/ ?\[unverified(?: strength)?: confirm with doctor\]/g, "").trim();
  }

  root.RxState = { scheduleOf, rowState, metaOf, typedFrom, chipsFor, afterEdit, afterSpell, cleanTyped, typedProblem, summary, errorText, voiceError, stripMarker, carryRowids, sameName: same, NEEDS };
})(typeof window !== "undefined" ? window : globalThis);
