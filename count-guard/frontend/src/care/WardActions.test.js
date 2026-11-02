import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { newPatientError, syncSummary } from "./wardForm.js";

test("syncSummary reads like a sentence", () => {
  assert.equal(syncSummary({ new: 2, existing: 3, updated: 1 }), "2 new, 3 already here, 1 updated");
  assert.equal(syncSummary({ new: 1, existing: 0, updated: 0, failed: 1 }), "1 new, 0 already here, 0 updated, 1 could not be read");
  assert.equal(syncSummary({ new: 0, existing: 0, updated: 0 }), "0 new, 0 already here, 0 updated");
});

test("newPatientError asks for the synthetic tag and a name", () => {
  assert.equal(newPatientError({ name: "Kiran" }), 'Add "(synthetic)" to the name');
  assert.equal(newPatientError({ name: "  " }), "Enter a name");
  assert.equal(newPatientError({ name: "Kiran (synthetic)" }), "");
});

test("Sync and New patient read the ward again right after they answer (spec §8)", () => {
  const src = fs.readFileSync(new URL("./WardActions.jsx", import.meta.url), "utf8");
  assert.match(src, /await syncWard\(\);[\s\S]*?onChanged\(\);[\s\S]*?catch/);
  assert.match(src, /await newPatient\(form\);[\s\S]*?onChanged\(\);[\s\S]*?catch/);
  const shell = fs.readFileSync(new URL("./CareShell.jsx", import.meta.url), "utf8");
  assert.match(shell, /<WardActions [^>]*onChanged=\{ward\.reload\}/);
});
