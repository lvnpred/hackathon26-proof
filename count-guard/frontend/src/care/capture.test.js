import assert from "node:assert/strict";
import test from "node:test";
import * as capture from "./capture.js";
import { closingBody, correctionLine, prefillObs } from "./capture.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;

test("prefillObs fills only empty fields", () => {
  const regions = [{ label: "SBP", value: "88" }, { label: "DBP", value: "54" }, { label: "HR", value: null }, { label: null, value: null }];
  assert.deepEqual(prefillObs(regions, {}), { sbp: "88", dbp: "54" });
  assert.deepEqual(prefillObs(regions, { sbp: "90" }), { sbp: "90", dbp: "54" });
  assert.deepEqual(prefillObs(regions, { sbp: "" }), { sbp: "88", dbp: "54" });
  assert.deepEqual(prefillObs(null, { hr: "70" }), { hr: "70" });
});

test("prefillObs returns a new object", () => {
  const form = { sbp: "90" };
  assert.notEqual(prefillObs([], form), form);
});

test("the camera count never fills the closing count; it only names its evidence", () => {
  assert.equal(capture.cameraPrefill, undefined);
  const count = { opened: 15, camera: { count: 14, evidence_id: "a".repeat(32) } };
  assert.deepEqual(closingBody(count, 14, ""), { step: "closing", returned: 14, detail: "", evidence_id: "a".repeat(32), via: "camera" });
  assert.deepEqual(closingBody({ opened: 15 }, 14, ""), { step: "closing", returned: 14, detail: "" });
});

test("correctionLine", () => {
  assert.equal(correctionLine({ sbp: 118 }, { sbp: 120 }, "Nurse Meena (synthetic)"), "Read 118, saved 120 by Nurse Meena");
  assert.equal(correctionLine({ returned: 14 }, { returned: 15 }, "Nurse Asha (synthetic)"), "Read 14, saved 15 by Nurse Asha");
  assert.equal(correctionLine({ sbp: 88, dbp: 54, hr: 112 }, { sbp: 90, dbp: 54, hr: 110 }, "Nurse Asha"), "Read 88/112, saved 90/110 by Nurse Asha");
  assert.equal(correctionLine({ sbp: 88 }, { sbp: 88 }, "x"), "");
  assert.equal(correctionLine(null, null, "x"), "");
  assert.equal(correctionLine({ sbp: 88 }, null, "x"), "");
});

test("capture copy has no advice words", () => {
  for (const s of ["Read from monitor photo", "Swab camera count", "Upload a clip or photos of the returned swabs", "Camera count: 14", "Swab count matches the pack", "Flagged: fewer swabs seen than opened. The nurse decides.", "Clip kept, not counted"]) assert.doesNotMatch(s, ADVICE);
});
