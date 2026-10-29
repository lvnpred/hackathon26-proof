// Order form rows (strings, as typed) to the items POST /orders/sign takes.
export const KINDS = [["dose", "Dose"], ["obs", "Observation"], ["procedure", "Procedure"], ["check", "Check"], ["other", "Other"]];

export function blankRow(kind = "other") {
  return { kind, text: "", name: "", amount: "", every_h: "", mode: "tick", proof: "none", sbp_min: "", sbp_max: "" };
}

export const PREFILL = {
  dose: () => ({ ...blankRow("dose"), text: "Paracetamol 1 g every 6 h", name: "paracetamol", amount: "1 g", every_h: "6" }),
  obs: () => ({ ...blankRow("obs"), text: "BP and pulse", every_h: "1", sbp_min: "90" }),
  procedure: () => ({ ...blankRow("procedure"), text: "Saline 1 L over 2 h", mode: "start_end" }),
};

const blank = (value) => String(value).trim() === "";
const number = (value) => (blank(value) ? null : Number(value));

// Rows with no text are dropped. Blank optional fields are left out; limits go on observations only.
// Returns { items, errors }; errors maps a row's index to its plain message. A typed value that is
// not a number, or a dose with no medicine name, is an error, never a silent drop.
export function orderRowsToItems(rows) {
  const items = [];
  const errors = {};
  rows.forEach((row, index) => {
    if (!row.text.trim()) return;
    const fields = [["Every h", row.every_h]];
    if (row.kind === "obs") fields.push(["Systolic BP min", row.sbp_min], ["Systolic BP max", row.sbp_max]);
    const bad = fields.find(([, value]) => !blank(value) && !Number.isFinite(number(value)));
    if (bad) errors[index] = `${bad[0]} must be a number.`;
    else if (row.kind === "dose" && blank(row.name)) errors[index] = "Medicine name is needed for a dose.";
    const item = { kind: row.kind, text: row.text.trim(), mode: row.mode, proof: row.proof };
    const everyH = number(row.every_h);
    if (everyH !== null) item.every_h = everyH;
    if (row.kind === "dose") {
      if (row.name.trim()) item.name = row.name.trim();
      if (row.amount.trim()) item.amount = row.amount.trim();
    }
    if (row.kind === "obs") {
      const limits = {};
      const min = number(row.sbp_min);
      const max = number(row.sbp_max);
      if (min !== null) limits.sbp_min = min;
      if (max !== null) limits.sbp_max = max;
      if (Object.keys(limits).length) item.limits = limits;
    }
    items.push(item);
  });
  return { items, errors };
}
