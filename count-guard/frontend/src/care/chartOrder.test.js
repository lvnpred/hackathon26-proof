import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";

const read = (name) => fs.readFileSync(new URL(`./${name}`, import.meta.url), "utf8");

test("chart order: band, Now, attention, AI block, medicines, folded record, folded history", () => {
  const src = read("Chart.jsx");
  const at = (needle) => {
    const i = src.indexOf(needle, src.indexOf("return (\n    <>\n      <StateHeader"));
    assert.ok(i > 0, needle);
    return i;
  };
  const order = ["<StateHeader", "<StatePanel", "<MedicinesFromHome", '<Fold label="Orders and evidence"', "<RecordEvidence", "<History"].map(at);
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  // StatePanel renders the Now card first, then the attention items handed in as afterNow.
  const attention = src.slice(src.indexOf("const attention"), src.indexOf("  return (\n    <>\n      <StateHeader"));
  const inner = ["<AlertBanner", "<AskInbox", "<AiHandling"].map((tag) => attention.indexOf(tag));
  assert.deepEqual([...inner].sort((a, b) => a - b), inner);
  assert.ok(inner.every((i) => i >= 0));
  assert.match(src, /useState\(false\)/);
});

test("Now card comes before the attention items in each role panel", () => {
  for (const name of ["DoctorActions.jsx", "NurseActions.jsx"]) {
    const src = read(name);
    assert.ok(src.indexOf("</NowCard>") < src.indexOf("{afterNow}"), name);
  }
});

test("the folded record and history keep their region names inside a closed Fold", () => {
  assert.match(read("History.jsx"), /<Fold label="History" count=\{view\.timeline\.length\} open=\{open\}/);
  assert.match(read("History.jsx"), /useState\(\(\) => Boolean\(line\)\)/);
  assert.match(read("RecordEvidence.jsx"), /aria-label="Record and evidence"/);
});

test("doctor quiet actions sit in the Now card's action area", () => {
  const src = read("DoctorActions.jsx");
  assert.match(src, /<NowCard[\s\S]*<ActionBar[\s\S]*<\/NowCard>/);
});
