import assert from "node:assert/strict";
import { test } from "node:test";
import { bedProblem, headerFacts } from "./header.js";

const DD = {
  bed: "1", source: "doctor-dictation", age_sex: "52 F", op_no: "OP-24-0042",
  diagnosis: ["Left inguinal hernia, for elective repair"], dd_doctor: "Dr. A. Rao",
  dd_pdf: "http://127.0.0.1:8300/api/v1/documents/42/pdf",
};

test("headerFacts lists what Doctor Dictation sent, in plain words", () => {
  assert.deepEqual(headerFacts(DD), [
    { label: "Age/sex", value: "52 F" },
    { label: "OP number", value: "OP-24-0042" },
    { label: "Diagnosis", value: "Left inguinal hernia, for elective repair" },
    { label: "Doctor in Doctor Dictation", value: "Dr. A. Rao" },
  ]);
});

test("headerFacts leaves out what is empty", () => {
  assert.deepEqual(headerFacts({ bed: "4", source: "seed", age_sex: "", op_no: "", diagnosis: [], dd_doctor: "", dd_pdf: null }), []);
  assert.deepEqual(headerFacts(undefined), []);
});

test("bedProblem checks the new bed before it is sent", () => {
  assert.equal(bedProblem("5", "1"), "");
  assert.equal(bedProblem(" 1 ", "1"), "The patient is already in bed 1.");
  assert.equal(bedProblem("", "1"), "Type a bed number.");
  assert.equal(bedProblem("bed 5", "1"), "Use letters, numbers or a dash.");
});
