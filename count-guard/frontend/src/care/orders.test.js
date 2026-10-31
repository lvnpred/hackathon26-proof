import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { blankRow, chipEdit, missingChips, numberProblem, CHIP_INPUT, obsLabel, orderRowsToItems, orderSentence, PREFILL, rowItem, sentenceText } from "./orders.js";

test("empty rows are dropped", () => {
  assert.deepEqual(orderRowsToItems([blankRow("other"), { ...blankRow("dose"), text: "  " }]).items, []);
});

test("every_h becomes a number and blank stays out", () => {
  const { items } = orderRowsToItems([
    { ...blankRow("dose"), text: "Paracetamol 1 g", name: "paracetamol", amount: "1 g", every_h: "6" },
    { ...blankRow("procedure"), text: "Saline 1 L over 2 h", every_h: "" },
  ]);
  assert.equal(items[0].every_h, 6);
  assert.equal(items[0].name, "paracetamol");
  assert.equal("every_h" in items[1], false);
  assert.equal("name" in items[1], false);
  assert.equal("limits" in items[0], false);
});

test("limits only on observations, blanks omitted", () => {
  const rows = [
    { ...blankRow("obs"), text: "BP and pulse", every_h: "1", sbp_min: "90", sbp_max: "" },
    { ...blankRow("dose"), text: "x", name: "x", sbp_min: "90" },
  ];
  const [obs, dose] = orderRowsToItems(rows).items;
  assert.deepEqual(obs.limits, { sbp_min: 90 });
  assert.equal("limits" in dose, false);
});

test("prefilled rows carry the brief's values", () => {
  assert.equal(PREFILL.dose().every_h, "6");
  assert.equal(PREFILL.obs().sbp_min, "90");
  assert.equal(PREFILL.procedure().mode, "start_end");
});

test("a non-numeric number field is an error on its row, not a silent drop", () => {
  const rows = [
    { ...blankRow("dose"), text: "Paracetamol", name: "paracetamol", every_h: "abc" },
    { ...blankRow("obs"), text: "BP", sbp_min: "9o" },
    { ...blankRow("obs"), text: "BP", sbp_max: "140" },
  ];
  const { errors, items } = orderRowsToItems(rows);
  assert.deepEqual(Object.keys(errors), ["0", "1"]);
  assert.match(errors[0], /Every h/);
  assert.match(errors[1], /Systolic BP min/);
  assert.equal(items.length, 3);
});

test("a dose row needs a medicine name", () => {
  const { errors } = orderRowsToItems([{ ...blankRow("dose"), text: "Paracetamol 1 g", every_h: "6" }]);
  assert.match(errors[0], /Medicine/);
  const ok = orderRowsToItems([{ ...blankRow("dose"), text: "Paracetamol 1 g", name: "paracetamol" }]);
  assert.deepEqual(ok.errors, {});
});

test("a video proof survives the round trip", () => {
  const { items } = orderRowsToItems([{ ...blankRow("procedure"), text: "Saline 1 L over 2 h", mode: "start_end", proof: "video" }]);
  assert.equal(items[0].proof, "video");
});

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const DOSE = { kind: "dose", text: "Paracetamol 1 g every 6 hours, strip photo as proof", name: "paracetamol", amount: "1 g", every_h: 6, proof: "photo", mode: "tick" };
const OBS = { kind: "obs", text: "BP and pulse every 1 hour, lower systolic limit 90", every_h: 1, proof: "none", limits: { sbp_min: 90 }, mode: "tick" };

test("sentenceText renders the demo orders as sentences", () => {
  assert.equal(sentenceText(DOSE), "Paracetamol · 1 g · every 6 h · proof: strip photo");
  assert.equal(sentenceText(OBS), "BP and pulse · every 1 h · alert if systolic < 90");
});

test("orderSentence names the fields, skips absent ones and words each proof", () => {
  assert.deepEqual(orderSentence(DOSE).map((c) => c.field), ["name", "amount", "every_h", "proof"]);
  assert.deepEqual(orderSentence(OBS).map((c) => c.field), ["text", "every_h", "limits.sbp_min"]);
  assert.equal(sentenceText({ kind: "obs", text: "BP", proof: "photo", limits: { sbp_min: 90, sbp_max: 160 } }), "BP · alert if systolic < 90 · alert if systolic > 160 · proof: monitor photo");
  assert.equal(sentenceText({ kind: "dose", name: "x", proof: "video" }), "X · proof: video");
  assert.equal(sentenceText({ kind: "procedure", text: "Saline 1 L over 2 h", proof: "none" }), "Saline 1 L over 2 h");
  assert.doesNotMatch(sentenceText(DOSE) + sentenceText(OBS), ADVICE);
});

test("obsLabel cuts before a comma or every; rowItem falls back for an empty row", () => {
  assert.equal(obsLabel("BP and pulse every 1 hour, lower"), "BP and pulse");
  assert.equal(obsLabel("BP, pulse"), "BP");
  assert.deepEqual(rowItem(blankRow("dose")), { kind: "dose", text: "" });
  assert.equal(rowItem({ ...blankRow("other"), text: "Wound check" }).text, "Wound check");
});

test("chipEdit sets one field and limits map to the row", () => {
  const dose = PREFILL.dose();
  assert.equal(chipEdit(dose, "amount", "2 g").amount, "2 g");
  assert.equal(chipEdit(dose, "every_h", "8").every_h, "8");
  const obs = chipEdit(PREFILL.obs(), "limits.sbp_min", "100");
  assert.equal(obs.sbp_min, "100");
  assert.equal(chipEdit(obs, "limits.sbp_max", "160").sbp_max, "160");
  assert.equal(dose.amount, "1 g");
  assert.deepEqual(CHIP_INPUT, { proof: "select" });
});

test("one rule words a bad number for the chip and the form", () => {
  const msg = numberProblem("every_h", "abc");
  assert.equal(msg, "Every h must be a number.");
  assert.equal(orderRowsToItems([{ ...PREFILL.dose(), every_h: "abc" }]).errors[0], msg);
  assert.equal(numberProblem("limits.sbp_min", "9x"), "Systolic BP min must be a number.");
  assert.equal(numberProblem("every_h", "6"), "");
  assert.equal(numberProblem("amount", "a lot"), "");
});

test("a dose with no medicine name gets a tappable placeholder chip", () => {
  assert.deepEqual(missingChips({ ...PREFILL.dose(), name: " " }), [{ field: "name", text: "Add medicine" }]);
  assert.deepEqual(missingChips(PREFILL.dose()), []);
  assert.deepEqual(missingChips(PREFILL.obs()), []);
});

test("new Task 7 copy gives no advice", () => {
  const copy = ["Add order text", "Add medicine", "Edit all fields", "Open the full form", numberProblem("every_h", "x"), numberProblem("limits.sbp_max", "x")];
  for (const text of copy) assert.doesNotMatch(text, /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i);
  const form = readFileSync(new URL("./OrderForm.jsx", import.meta.url), "utf8");
  assert.match(form, /Open the full form/);
});

test("a prefilled dose reads as a sentence", () => {
  assert.equal(sentenceText(rowItem(PREFILL.dose())), "Paracetamol · 1 g · every 6 h");
});

test("the form has Edit all fields and the nurse list uses sentenceText", () => {
  assert.match(readFileSync(new URL("./OrderForm.jsx", import.meta.url), "utf8"), /Edit all fields/);
  assert.match(readFileSync(new URL("./NurseActions.jsx", import.meta.url), "utf8"), /sentenceText\(/);
});

test("editing a dose or observation chip rebuilds the order text", () => {
  const dose = PREFILL.dose();
  const every8 = chipEdit(dose, "every_h", "8");
  assert.equal(every8.text, "Paracetamol 1 g every 8 h");
  assert.equal(orderRowsToItems([every8]).items[0].text, "Paracetamol 1 g every 8 h");
  assert.equal(chipEdit(dose, "amount", "500 mg").text, "Paracetamol 500 mg every 6 h");
  assert.equal(chipEdit(dose, "name", "ibuprofen").text, "Ibuprofen 1 g every 6 h");
  assert.equal(chipEdit(dose, "every_h", "").text, "Paracetamol 1 g");
  assert.equal(chipEdit({ ...PREFILL.obs(), text: "BP and pulse every 1 h" }, "every_h", "2").text, "BP and pulse every 2 h");
  const proc = PREFILL.procedure();
  assert.equal(chipEdit(proc, "proof", "photo").text, proc.text);
});
