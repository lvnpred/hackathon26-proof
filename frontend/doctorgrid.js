"use strict";
// Several doctors edited side by side (the sheet's two-column layout): one cell per doctor with name, qualifications
// and registration no. The three joined strings ("A; B", "qualsA; qualsB", "regA; regB", doctor i = part i of each)
// stay in three hidden inputs, so the forms that own them read, save and dirty-check them exactly as before.
// Parsing mirrors the backend's pdf/doctors_text.py: empty parts are KEPT so index pairing holds, and a doctor is
// skipped only when all three of its parts are empty. DOM is built with createElement/textContent only.
window.DoctorGrid = (function () {
  const MAX = 12;                                   // MAX_DOCTORS on the server
  const KEYS = ["name", "quals", "reg"];
  const LABELS = ["Doctor name", "Qualifications", "Registration no."];
  const grids = {};                                 // container id -> { box, hidden, cells }

  const split = (v) => (typeof v === "string" && v.trim() ? v.split(";").map((t) => t.trim()) : []);

  // The three joined strings -> [{name, quals, reg}], at least one (empty) cell.
  function parse(name, quals, reg) {
    const cols = [split(name), split(quals), split(reg)];
    const cells = [];
    for (let i = 0; i < Math.max(cols[0].length, cols[1].length, cols[2].length); i++) {
      const c = { name: cols[0][i] || "", quals: cols[1][i] || "", reg: cols[2][i] || "" };
      if (c.name || c.quals || c.reg) cells.push(c);
    }
    return cells.length ? cells : [{ name: "", quals: "", reg: "" }];
  }

  // [{name, quals, reg}] -> the three joined strings: empty positions kept, trailing empties dropped.
  function serialise(cells) {
    return KEYS.map((k) => {
      const vals = cells.map((c) => String(c[k] || "").replace(/;/g, ",").trim());
      while (vals.length && !vals[vals.length - 1]) vals.pop();
      return vals.join("; ");
    });
  }

  function sync(g) {
    const out = serialise(g.cells);
    g.hidden.forEach((h, i) => {
      if (h.value === out[i]) return;
      h.value = out[i];
      h.dispatchEvent(new Event("input", { bubbles: true }));   // dirty checks and listeners see the edit
    });
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function render(g, id, focus) {
    g.box.textContent = "";
    const grid = el("div", "dg-grid");
    g.cells.forEach((cell, i) => {
      const card = el("div", "dg-cell");
      const head = el("div", "dg-head");
      head.appendChild(el("h4", "dg-title", "Doctor " + (i + 1)));
      if (g.cells.length > 1) {
        const rm = el("button", "dg-remove", "Remove");
        rm.type = "button";
        rm.setAttribute("aria-label", "Remove Doctor " + (i + 1));
        rm.addEventListener("click", () => {
          g.cells.splice(i, 1);
          sync(g);
          render(g, id, { cell: Math.min(i, g.cells.length - 1) });
        });
        head.appendChild(rm);
      }
      card.appendChild(head);
      KEYS.forEach((k, j) => {
        const fid = id + "_" + i + "_" + k;
        const w = el("label", "field");
        w.setAttribute("for", fid);
        w.textContent = LABELS[j];
        const inp = document.createElement("input");
        inp.id = fid; inp.type = "text"; inp.value = cell[k];
        if (k === "name") inp.autocomplete = "off";
        inp.addEventListener("input", () => { cell[k] = inp.value; sync(g); });
        w.appendChild(inp);
        card.appendChild(w);
      });
      grid.appendChild(card);
    });
    g.box.appendChild(grid);
    const add = el("button", "dg-add", "+ Add doctor");
    add.type = "button";
    add.setAttribute("aria-label", "Add another doctor");
    add.disabled = g.cells.length >= MAX;
    add.hidden = g.cells.length >= MAX;
    add.addEventListener("click", () => {
      g.cells.push({ name: "", quals: "", reg: "" });
      render(g, id, { cell: g.cells.length - 1 });
    });
    g.box.appendChild(add);
    if (focus) {
      const t = document.getElementById(id + "_" + focus.cell + "_name");
      if (t) t.focus();
    }
  }

  // box: the container; hidden: the three inputs [doctor name, qualifications, registration no.]. Safe to call again.
  function mount(box, hidden) {
    if (!box || !box.id || hidden.length !== 3 || hidden.some((h) => !h)) return;
    box.classList.add("dg-wrap");
    grids[box.id] = { box: box, hidden: hidden, cells: [] };
    refresh(box.id);
  }

  // Re-read the hidden inputs (after the form was filled from the server) and redraw.
  function refresh(id) {
    const g = grids[id];
    if (!g) return;
    g.cells = parse(g.hidden[0].value, g.hidden[1].value, g.hidden[2].value);
    render(g, id, null);
  }

  const profile = ["profDoctor", "profQual", "profReg"].map((i) => document.getElementById(i));
  mount(document.getElementById("profDoctorGrid"), profile);

  return { parse, serialise, mount, refresh, MAX };
})();
