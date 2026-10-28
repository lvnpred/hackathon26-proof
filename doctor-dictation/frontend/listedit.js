"use strict";
// The edit dialog for one list entry (plan PQ-f): ListEdit.open(kind, item | null, {owner}) resolves to
// {op, entry_key, data} for the change route, or null on Cancel / Escape. clinlists.js (the clinic's tabs) uses it
// now; the owner screen reuses it with {owner: true}, which adds the Safety checkbox. Text only: no HTML is built.
(function () {
  const LABEL = { name: "Name", generic: "Generic", aliases: "Aliases", brands: "Brands", category: "Category", print: "Print" };
  const FIELDS = { medicine: ["name", "generic", "aliases", "brands"], investigation: ["name", "aliases", "category", "print"] };
  const LISTY = { aliases: true, brands: true };
  let dlg = null, settle = null;

  function make(tag, attrs, text) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, v));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  const split = (s) => String(s || "").split(",").map((x) => x.trim()).filter(Boolean);
  const squash = (s) => String(s || "").split(/\s+/).filter(Boolean).join(" ");

  // What the form starts with. A pending doctor suggestion's values win over the live entry: an admin edit replaces them.
  function initial(kind, item) {
    const out = { name: "", generic: "", aliases: [], brands: [], category: "", print: "", safety: false };
    if (!item) return out;
    const e = item.entry || {};
    const p = (item.pending && item.pending.data) || {};
    const brands = Array.isArray(e.brands) ? e.brands : [];
    if (kind === "investigation") {
      out.name = e.canonical || item.entry_key;
      Object.assign(out, { aliases: e.aliases || [], category: e.category || "", print: e.print || "" });
    } else if (item.shipped) {
      Object.assign(out, { name: e.canonical || item.entry_key, generic: e.canonical || "", aliases: e.aliases || [], brands });
    } else {
      out.name = p.name || brands[0] || e.canonical || item.entry_key;
      const own = squash(out.name).toLowerCase();
      Object.assign(out, { generic: e.canonical || "", aliases: e.aliases || [], brands: brands.filter((b) => squash(b).toLowerCase() !== own) });
    }
    ["generic", "category", "print"].forEach((f) => { if (typeof p[f] === "string" && p[f]) out[f] = p[f]; });
    ["aliases", "brands"].forEach((f) => { if (Array.isArray(p[f])) out[f] = p[f]; });
    out.safety = e.safety === true;
    return out;
  }

  function ensureDialog() {
    if (dlg) return dlg;
    dlg = make("dialog", { id: "listEditDialog", class: "panel team-panel team-edit no-print", "aria-labelledby": "listEditTitle" });
    dlg.addEventListener("close", () => finish(null));            // Escape, or close() after a result was already given
    document.body.append(dlg);
    return dlg;
  }
  function finish(result) {
    const done = settle;
    settle = null;
    if (done) done(result);
  }

  function open(kind, item, opts) {
    const owner = Boolean(opts && opts.owner);
    if (!FIELDS[kind]) return Promise.resolve(null);
    finish(null);                                                 // a second open() closes the first as cancelled
    return new Promise((resolve) => {
      settle = resolve;
      const editing = Boolean(item);
      const start = initial(kind, item);
      const basedOnShared = editing && Boolean(item.shipped);     // a shared entry's name never changes; a clinic's own entry sends its name again
      const sendGeneric = !(owner && basedOnShared);              // an owner edit never changes the generic
      const form = make("form", { class: "team-edit-form", method: "dialog" });
      const noun = kind === "medicine" ? "medicine" : "test";
      form.append(make("h3", { id: "listEditTitle" }, editing ? "Edit " + start.name : "Add a " + noun));
      const inputs = {};
      FIELDS[kind].forEach((f) => {
        const input = make("input", { id: "listEdit" + f[0].toUpperCase() + f.slice(1), type: "text", autocomplete: "off" });
        input.value = LISTY[f] ? start[f].join(", ") : start[f];
        if (f === "name" && editing) { input.setAttribute("readonly", "readonly"); input.readOnly = true; }
        if (f === "generic" && !sendGeneric) { input.setAttribute("readonly", "readonly"); input.readOnly = true; }
        if (f === "name") input.setAttribute("required", "required");
        const label = make("label", { class: "field" }, LABEL[f] + (LISTY[f] ? " (separate with commas)" : ""));
        label.append(input);
        form.append(label);
        inputs[f] = input;
      });
      let safety = null;
      if (owner) {
        safety = make("input", { id: "listEditSafety", type: "checkbox" });
        safety.checked = start.safety;
        const l = make("label", { class: "team-only" });
        l.append(safety, make("span", {}, "Safety entry"));
        form.append(l);
      }
      const err = make("p", { id: "listEditError", class: "team-error", role: "alert" });
      err.hidden = true;
      const cancel = make("button", { id: "listEditCancel", type: "button" }, "Cancel");
      const save = make("button", { id: "listEditSave", type: "submit", class: "primary" }, "Save");
      const bar = make("div", { class: "team-edit-actions" });
      bar.append(save, cancel);
      form.append(err, bar);
      cancel.addEventListener("click", () => dlg.close());
      form.addEventListener("submit", (ev) => {
        if (ev && ev.preventDefault) ev.preventDefault();
        const name = squash(inputs.name.value);
        if (!name) { err.textContent = "Enter a name."; err.hidden = false; inputs.name.focus(); return; }
        if (kind === "medicine" && sendGeneric && !squash(inputs.generic.value)) {     // stay open: nothing typed is lost
          err.textContent = "Enter the generic name.";
          err.hidden = false;
          inputs.generic.focus();
          return;
        }
        err.hidden = true;
        const data = {};
        FIELDS[kind].forEach((f) => {
          if (f === "name") { if (!basedOnShared) data.name = name; return; }
          if (f === "generic" && !sendGeneric) return;
          data[f] = LISTY[f] ? split(inputs[f].value) : squash(inputs[f].value);
        });
        if (safety) data.safety = Boolean(safety.checked);
        const learnedName = editing && !item.shipped && item.formulary_id !== null && item.formulary_id !== undefined;
        const op = !editing || learnedName ? "add" : "edit";          // a learned name has no stored row yet: saving it adds one
        const entry_key = op === "add" ? name.toLowerCase() : item.entry_key;
        finish({ op, entry_key, data });
        dlg.close();
      });
      ensureDialog().replaceChildren(form);
      if (!dlg.open) dlg.showModal();
      (editing ? inputs[FIELDS[kind][1]] : inputs.name).focus();
    });
  }

  window.ListEdit = { open };
})();
