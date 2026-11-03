import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("./CameraAdvice.jsx", import.meta.url), "utf8");

test("camera advice shows plain words and a frame, never a rule id, and says it is advice only", () => {
  assert.match(src, /\{row\.text\}/);
  assert.doesNotMatch(src, /row\.rule/);
  assert.match(src, /row\.frame_url && <img/);
  assert.match(src, /Advice only\. The count a person saves decides\./);
});

test("a prepared camera result says Prepared beside its source words", () => {
  assert.match(src, /<Source words=\{FROM_CAMERA\} prepared=\{camera\.source === "prepared"\} \/>/);
});

test("acknowledging posts to the advice route with the person and an optional reason; nothing saves a count", () => {
  assert.match(src, /act\(`\/camera\/advice\/\$\{row\.id\}\/ack`, \{ by, reason: reason\.trim\(\) \}\)/);
  assert.doesNotMatch(src, /"\/count"/);
  const panel = readFileSync(new URL("./CountPanel.jsx", import.meta.url), "utf8");
  assert.match(panel, /<CameraAdvice episodeId=\{episodeId\}/);
});

test("resolve needs a typed reason and posts it with the person; it is shown once resolved", () => {
  assert.match(src, /disabled=\{busy \|\| !why\}/);
  assert.match(src, /act\(`\/camera\/advice\/\$\{row\.id\}\/resolve`, \{ by, reason: why \}\)/);
  assert.match(src, /<Provenance item=\{\{ id: row\.id, ai: adviceByModel\(row\) \}\} events=\{acts\} \/>/); // "Overridden by {name} {HH:MM}" (provenance.js)
  assert.match(src, /\(row\.resolved \|\| row\.acked\)\.reason/);
});

test("the replay is labelled Prepared and the closed case shows its explanation and the count sheet", () => {
  assert.match(src, /act\("\/camera\/replay", \{ by \}\)/);
  assert.match(src, /<Source words=\{FROM_REPLAY\} prepared=\{camera\.replay\.source === "prepared"\} \/>/);
  assert.match(src, /act\("\/camera\/close", \{ by \}\)/);
  assert.match(src, /<Source words=\{DRAFTED_FROM_CAMERA\} prepared=\{camera\.closed\.source === "prepared"\} \/>/);
  assert.match(src, /\{camera\.closed\.text\}/);
  assert.match(src, /href=\{camera\.closed\.count_sheet_url\}/);
  assert.doesNotMatch(src, /camera\.closed\.model|camera\.closed\.narrative/); // model names and evidence ids stay off staff screens
});
