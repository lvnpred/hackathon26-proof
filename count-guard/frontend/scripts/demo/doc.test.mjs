import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { ADVICE, BEATS } from "./beats.mjs";

// The two-app video script (spec §12) is written by plan Task 17; until then these checks are skipped, not passed.
const DOC_URL = new URL("../../../../docs/demo/dd-cg-flow-video-script.md", import.meta.url);
const skip = fs.existsSync(DOC_URL) ? false : "docs/demo/dd-cg-flow-video-script.md is not written yet (plan Task 17)";
const doc = () => fs.readFileSync(DOC_URL, "utf8");

test("every beat id appears in backticks", { skip }, () => {
  const text = doc();
  for (const b of BEATS) assert.ok(text.includes("`" + b.id + "`"), b.id);
});

test("the labels synthetic data and research demo appear", { skip }, () => {
  assert.match(doc(), /synthetic data/i);
  assert.match(doc(), /research demo/i);
});

test("narration passes the no-advice regex", { skip }, () => {
  for (const q of doc().split("\n").filter((l) => l.startsWith("> "))) assert.ok(!ADVICE.test(q), q);
});

test("no key value is written", { skip }, () => {
  assert.doesNotMatch(doc(), /(MODEL_API_KEY|BASETEN_API_KEY|META_API_KEY)=\S/);
});
