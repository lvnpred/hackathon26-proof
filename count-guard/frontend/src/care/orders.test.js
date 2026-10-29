import test from "node:test";
import assert from "node:assert/strict";
import { blankRow, orderRowsToItems, PREFILL } from "./orders.js";

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
