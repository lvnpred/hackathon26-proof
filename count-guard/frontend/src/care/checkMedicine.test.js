import test from "node:test";
import assert from "node:assert/strict";

import { ALLOW, CHECK_COPY, checkMatchLine } from "./checkMedicine.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;

test("each match kind reads in the patient's own words", () => {
  assert.equal(checkMatchLine("on_prescription"), "On your prescription");
  assert.equal(checkMatchLine("strength_differs"), "Strength differs from your prescription");
  assert.equal(checkMatchLine("not_on_prescription"), "Not on your prescription — ask your doctor");
  assert.equal(checkMatchLine("no_prescription"), "No prescription yet.");
});

test("an unknown match fails safe, to the doctor", () => {
  assert.equal(checkMatchLine("mismatch"), "Not on your prescription — ask your doctor");
  assert.equal(checkMatchLine(undefined), "Not on your prescription — ask your doctor");
});

test("the ask-your-doctor line is the only allowed advice-shaped copy", () => {
  assert.deepEqual(ALLOW, ["Not on your prescription — ask your doctor"]);
  for (const line of CHECK_COPY) {
    if (ALLOW.includes(line)) continue;
    assert.doesNotMatch(line, ADVICE, line);
  }
});

test("every fixed line of the card is swept", () => {
  for (const line of ["Check a medicine", "Add a photo", "Type instead", "Check this medicine"]) {
    assert.ok(CHECK_COPY.includes(line), line);
  }
});
