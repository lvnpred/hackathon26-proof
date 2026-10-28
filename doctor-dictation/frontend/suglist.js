"use strict";
// One suggestion, built the same way inline ("Did you mean X?") and in the Spell it list (I2-c). Text only.
window.SugList = (function () {
  const REASON = { matched: "in the medicine list", clinic: "your clinic uses it", sounds: "sounds like", lookalike: "looks alike: a different medicine" };
  let seq = 0;
  const same = (a, b) => String(a || "").trim().toLowerCase() === String(b || "").trim().toLowerCase();
  function el(tag, cls, t) { const n = document.createElement(tag); if (cls) n.className = cls; if (t != null) n.textContent = t; return n; }
  const reasonText = (code) => REASON[code] || "";
  // sug: {name, generic, reason}; o: {action, prefix ("Did you mean " inline, "" in the list), reason: bool}
  function item(sug, o) {
    const b = el("button", "rx-act sug " + (o.cls || "")); b.type = "button"; b.dataset.action = o.action; b.dataset.value = sug.name;
    const uid = "sug" + (++seq), why = [];
    b.append(el("span", "sug-name", (o.prefix || "") + sug.name + (o.prefix ? "?" : "")));
    if (sug.generic && !same(sug.generic, sug.name)) { const g = el("span", "sug-gen", "generic: " + sug.generic); g.id = uid + "g"; why.push(g.id); b.append(g); }
    if (o.reason && reasonText(sug.reason)) { const r = el("span", "sug-why", reasonText(sug.reason)); r.id = uid + "r"; why.push(r.id); b.append(r); }
    b.setAttribute("aria-label", o.prefix ? o.prefix + sug.name + "? Use it for this row" : sug.name + ": use for this row");   // starts with the visible name; the generic and the warning are read as the description
    if (why.length) b.setAttribute("aria-describedby", why.join(" "));
    return b;
  }
  const PAGE = 8;
  // items: the options in server order; index: the page asked for (clamped); total: names the server found (may exceed items)
  function page(items, index, total) {
    const n = items.length, pages = Math.max(1, Math.ceil(n / PAGE)), i = Math.min(Math.max(0, Math.floor(+index) || 0), pages - 1);
    const from = n ? i * PAGE + 1 : 0, to = Math.min(n, (i + 1) * PAGE), more = +total > n ? +total : 0;
    const label = !n ? "No close names found. Type the name." : "Showing " + from + "-" + to + " of " + n + (more ? " (" + more + " found: type more letters to narrow them)" : "");
    return { items: items.slice(from ? from - 1 : 0, to), index: i, pages, from, to, label, hasPrev: i > 0, hasNext: i < pages - 1 };
  }
  function list(box, items, o) {
    box.textContent = "";
    items.forEach((s) => box.appendChild(item(s, Object.assign({ action: "pick", reason: true, cls: "spell-item" }, o))));
    return box;
  }
  // ---- the context group below the list (SH-B2): what the server found for the diagnosis and this patient; never the first button ----
  const CTX_KINDS = ["diagnosis", "patient"];
  function groupsOf(res) {                          // keep known kinds, string names only, at most 2 groups of 3
    const raw = res && Array.isArray(res.context) ? res.context : [];
    return raw.filter((g) => g && CTX_KINDS.includes(g.kind) && Array.isArray(g.items)).slice(0, 2).map((g) => ({
      kind: g.kind, for: typeof g.for === "string" ? g.for : "",
      items: g.items.filter((i) => i && typeof i.name === "string" && i.name).slice(0, 3).map((i) => ({ name: i.name, generic: typeof i.generic === "string" ? i.generic : "" })),
    })).filter((g) => g.items.length);
  }
  function groupLabel(g) {
    if (g.kind === "patient") return "This patient's earlier medicines";
    const f = String(g.for || "").trim();
    return f ? "Used for " + (f.length > 40 ? f.slice(0, 40) + "\u2026" : f) : "Used for this diagnosis";
  }
  function groups(box, gs, shown) {                 // shown: the names already in the list; they are not repeated here
    box.textContent = ""; const btns = [];
    (gs || []).forEach((g, n) => {
      const items = g.items.filter((i) => !(shown || []).some((s) => same(s.name, i.name)));
      if (!items.length) return;
      const wrap = el("div", "spell-ctx-group"), id = "spellCtxL" + n; wrap.setAttribute("role", "group"); wrap.setAttribute("aria-labelledby", id);
      const lab = el("p", "spell-ctx-label", groupLabel(g)); lab.id = id; wrap.appendChild(lab);
      items.forEach((i) => { const b = item(i, { action: "pick", reason: false, cls: "spell-item" }); wrap.appendChild(b); btns.push(b); });
      box.appendChild(wrap);
    });
    box.hidden = !btns.length;
    return btns;
  }
  return { item, reasonText, same, PAGE, page, list, groupsOf, groupLabel, groups };
})();
