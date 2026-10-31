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

// The proof word an order sentence shows: a dose photo is a strip photo, an observation photo a monitor photo.
export const PROOF_WORD = {
  dose: { photo: "strip photo", video: "video" },
  obs: { photo: "monitor photo", video: "video" },
};
const proofWord = (item) => PROOF_WORD[item.kind]?.[item.proof] || (item.proof === "video" ? "video" : "photo");

// An observation's text without its interval: "BP and pulse every 1 h" -> "BP and pulse".
export const obsLabel = (text) => String(text ?? "").split(/,|\s+every\b/i)[0].trim();

const capital = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

// One order as chips: [{ field, text }]. The field names are the ones the word marks use (backend order_spans).
export function orderSentence(item) {
  const chips = [];
  const add = (field, text) => chips.push({ field, text });
  const every = () => item.every_h != null && item.every_h !== "" && add("every_h", `every ${item.every_h} h`);
  if (item.kind === "dose") {
    if (item.name) add("name", capital(item.name));
    if (item.amount) add("amount", item.amount);
    every();
  } else if (item.kind === "obs") {
    add("text", obsLabel(item.text));
    every();
    const { sbp_min: min, sbp_max: max } = item.limits || {};
    if (min != null) add("limits.sbp_min", `alert if systolic < ${min}`);
    if (max != null) add("limits.sbp_max", `alert if systolic > ${max}`);
  } else {
    add("text", item.text);
  }
  if (item.proof && item.proof !== "none") add("proof", `proof: ${proofWord(item)}`);
  return chips;
}

export const sentenceText = (item) => orderSentence(item).map((c) => c.text).join(" · ");

// A form row as the item it would sign; a row with no text still names its kind.
export const rowItem = (row) => orderRowsToItems([row]).items[0] ?? { kind: row.kind, text: row.text };

// Chip fields edited as text unless listed here.
export const CHIP_INPUT = { proof: "select" };

const NUMERIC_CHIP = new Set(["every_h", "limits.sbp_min", "limits.sbp_max"]);
const ROW_FIELD = { "limits.sbp_min": "sbp_min", "limits.sbp_max": "sbp_max" };

// The form row's value behind a chip, as the string an input shows.
export const chipValue = (row, field) => row[ROW_FIELD[field] ?? field] ?? "";

// A chip edit is valid unless a numeric field holds something that is not a number.
export const chipValid = (field, value) => !NUMERIC_CHIP.has(field) || blank(value) || Number.isFinite(Number(value));

// The row with one chip's field replaced; the value is stored as typed, as the form does.
export const chipEdit = (row, field, value) => ({ ...row, [ROW_FIELD[field] ?? field]: value });
