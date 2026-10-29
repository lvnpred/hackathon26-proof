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

const number = (value) => (String(value).trim() === "" ? null : Number(value));

// Rows with no text are dropped. Blank optional fields are left out; limits go on observations only.
export function orderRowsToItems(rows) {
  return rows
    .filter((row) => row.text.trim())
    .map((row) => {
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
      return item;
    });
}
