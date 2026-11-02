import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { NO_PHOTO, checkFor, proofLabel, proofTone } from "./verdict.js";

test("the line a photo check shows (spec §6.6)", () => {
  assert.equal(proofLabel({ verdict: "not_accepted", source: "live", why: "No wristband visible" }), "Not accepted — No wristband visible");
  assert.equal(proofLabel({ verdict: "accepted", source: "live", why: "Wristband with a name" }), "Accepted — Wristband with a name");
  assert.equal(proofLabel({ verdict: "not_checked", source: "unavailable", why: "Not checked — model unavailable" }), "Not checked — model unavailable");
});

test("a prepared verdict says so", () => {
  assert.equal(proofLabel({ verdict: "accepted", source: "prepared", why: "The photo shows a signed consent form." }),
    "Accepted — The photo shows a signed consent form. · Prepared");
  assert.equal(proofLabel({ verdict: "not_accepted", source: "prepared", why: "A bed rail" }), "Not accepted — A bed rail · Prepared");
});

test("no photo and an override are visible, never silent", () => {
  assert.equal(proofLabel(null), NO_PHOTO);
  assert.equal(proofLabel({ state: "none" }), "No photo");
  assert.equal(proofLabel({ state: "overridden", verdict: "not_accepted", reason: "Band checked by hand" }), "Overridden — Band checked by hand");
});

test("the tone of each state", () => {
  assert.equal(proofTone({ state: "accepted" }), "fine");
  assert.equal(proofTone({ state: "not_accepted" }), "check");
  assert.equal(proofTone({ state: "not_checked" }), "check");
  assert.equal(proofTone({ state: "overridden" }), "done");
  assert.equal(proofTone({ state: "none" }), "wait");
});

test("checkFor finds the row, else a no-photo row", () => {
  const view = { photo_checks: [{ item: "admission:band", state: "accepted", verdict: "accepted", why: "ok", source: "live" }] };
  assert.equal(checkFor(view, "admission:band").state, "accepted");
  assert.deepEqual(checkFor(view, "admission:consent"), { item: "admission:consent", state: "none", open: false });
  assert.equal(checkFor({}, "task:x").state, "none");
});

test("ProofItem shows the override box only while the item is open, and no snake_case words", () => {
  const src = fs.readFileSync(new URL("./ProofItem.jsx", import.meta.url), "utf8");
  assert.match(src, /check\.open/);
  assert.match(src, /Override/);
  for (const text of src.match(/>[^<>{}]+</g) || []) assert.doesNotMatch(text, /[a-z]_[a-z]/, text);
});
