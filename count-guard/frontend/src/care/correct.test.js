import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { canCorrect, correctionBody, correctorFor, fieldsFor } from "./correct.js";

test("a typed observation set and a theatre drug line get a Correct button; nothing else", () => {
  for (const type of ["obs.recorded", "drug.given", "druglog.given", "druglog.parsed"]) assert.equal(canCorrect({ type }), true, type);
  for (const type of ["count.closing", "surgery.began", "patient.state", "check.photo", "check.override", "dose.given", "camera.advice", "rx.ordered"]) {
    assert.equal(canCorrect({ type }), false, type);
  }
  assert.equal(canCorrect(null), false);
});

test("the form sends only the values typed, as numbers, with a person's name", () => {
  const got = correctionBody({ event_id: "e1", type: "obs.recorded" }, { sbp: "118", dbp: "", hr: " 72 ", temp: "37.5" }, "Nurse Meena (synthetic)");
  assert.deepEqual(got, { body: { event_id: "e1", payload: { sbp: 118, hr: 72, temp: 37.5 }, by: "Nurse Meena (synthetic)" } });
});

test("a reading that must be whole says so before the server is asked", () => {
  assert.deepEqual(correctionBody({ event_id: "e1", type: "obs.recorded" }, { sbp: "118.5" }, "N"), { error: "Systolic BP must be a whole number." });
  assert.deepEqual(correctionBody({ event_id: "e1", type: "obs.recorded" }, { hr: "fast" }, "N"), { error: "Heart rate must be a whole number." });
  assert.deepEqual(correctionBody({ event_id: "e1", type: "obs.recorded" }, { temp: "warm" }, "N"), { error: "Temperature must be a number." });
  assert.deepEqual(correctionBody({ event_id: "e1", type: "obs.recorded" }, {}, "N"), { error: "Type the value to correct." });
});

test("a drug line corrects its dose and route only, never the name or who gave it", () => {
  assert.deepEqual(fieldsFor("drug.given").map(([key]) => key), ["strength", "amount", "unit", "route"]);
  const got = correctionBody({ event_id: "d1", type: "drug.given" }, { amount: "8", unit: "ml", route: "" }, "Dr. A. Rao (synthetic)");
  assert.deepEqual(got.body.payload, { amount: 8, unit: "ml" });
  assert.deepEqual(correctionBody({ event_id: "d1", type: "drug.given" }, { amount: "0" }, "N"), { error: "Amount must be more than 0." });
});

test("the corrector is the person in the role, never the AI", () => {
  assert.equal(correctorFor("doctor"), "Dr. A. Rao (synthetic)");
  assert.equal(correctorFor("nurse"), "Nurse Meena (synthetic)");
  for (const type of ["obs.recorded", "drug.given"]) assert.ok(fieldsFor(type).every(([key, label]) => key && label && !label.includes("_")));
});

test("Inspector History shows Correct only for a correctable line, and never in the patient lens", () => {
  const src = fs.readFileSync(new URL("./Inspector.jsx", import.meta.url), "utf8");
  assert.match(src, /lens !== "patient" && role !== "patient" && canCorrect\(w\) && <Correct /);
  assert.match(src, /<HistoryTab [^>]*lens=\{lens\}/);
  const form = fs.readFileSync(new URL("./Correct.jsx", import.meta.url), "utf8");
  assert.match(form, /correctorFor\(role\)/); // the person in the role, never a typed or AI name
});

test("the theatre drug row offers Correct on the heard line, then on the drug given", () => {
  const src = fs.readFileSync(new URL("./TheatreDrugs.jsx", import.meta.url), "utf8");
  assert.match(src, /row\.given \? \{ event_id: row\.given\.id, type: "drug\.given" \} : \{ event_id: row\.id, type: "druglog\.parsed" \}/);
});
