import assert from "node:assert/strict";
import { test } from "node:test";
import { CLOCK, INBOX_SCOPES, faultText, makeFault } from "./faults.js";

const f = makeFault("e9", "/ask/medicines", "No prescription");

test("a fault shows only on its own episode", () => {
  assert.equal(faultText(f, "e4"), "");
  assert.equal(faultText(f, "e9"), "No prescription");
  assert.equal(faultText(null, "e9"), "");
});

test("only and except pick the action", () => {
  assert.equal(faultText(f, "e9", { only: ["/ask/review"] }), "");
  assert.equal(faultText(f, "e9", { only: ["/ask/medicines"] }), "No prescription");
  const q = makeFault("e4", "/questions/q1/answer", "x");
  assert.equal(faultText(q, "e4", { except: INBOX_SCOPES }), "");
  assert.equal(faultText(q, "e4", { only: INBOX_SCOPES }), "x");
});

test("ward-wide faults have no episode", () => {
  assert.equal(faultText(makeFault(null, CLOCK, "m"), null, { only: [CLOCK] }), "m");
  assert.equal(faultText(makeFault(null, CLOCK, "m"), "e4"), "");
});

test("a fault with a non-string scope never throws and does not match", () => {
  assert.equal(faultText(makeFault("e4", undefined, "m"), "e4", { only: ["/ask/"] }), "");
  assert.equal(faultText(makeFault("e4", 7, "m"), "e4"), "");
});

test("a strip photo failure shows in the strips card only", () => {
  const photo = makeFault("e4", "/strips/photo", "No Meta Model API key.");
  assert.equal(faultText(photo, "e4", { only: ["/strips"] }), "No Meta Model API key.");
  assert.equal(faultText(photo, "e4", { only: ["/reminders"] }), "");
  assert.equal(faultText(photo, "e4", { only: ["/help"] }), "");
  assert.equal(faultText(photo, "e4", { only: ["/checkin"] }), "");
  assert.equal(faultText(photo, "e4", { only: ["/nudges/"] }), "");
});
