import test from "node:test";
import assert from "node:assert/strict";
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
