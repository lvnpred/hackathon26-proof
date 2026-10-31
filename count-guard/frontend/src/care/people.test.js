import test from "node:test";
import assert from "node:assert/strict";
import { SIGNED_IN, initials } from "./people.js";

test("initials skip the Dr. title and use the first and last word", () => {
  assert.equal(initials("Dr. A. Rao"), "AR");
  assert.equal(initials("Nurse Meena"), "NM");
  assert.equal(initials("Meena"), "M");
  assert.equal(initials(""), "");
});

test("each signed-in person has a name that the backend accepts as a person", () => {
  assert.deepEqual(Object.keys(SIGNED_IN), ["doctor", "nurse"]);
  for (const person of Object.values(SIGNED_IN)) assert.doesNotMatch(person.name, /^AI/);
  assert.equal(initials(SIGNED_IN.doctor.name), "AR");
  assert.equal(initials(SIGNED_IN.nurse.name), "NM");
});
