import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { ADVICE, BEATS, MEDIA } from "./beats.mjs";

const DOC_URL = new URL("../../../../docs/demo/count-guard-v2-video-script.md", import.meta.url);
const doc = () => fs.readFileSync(DOC_URL, "utf8");

test("the script doc exists", () => {
  assert.ok(fs.existsSync(DOC_URL), "docs/demo/count-guard-v2-video-script.md is missing");
});

test("every beat id appears in backticks", () => {
  const text = doc();
  for (const b of BEATS) assert.ok(text.includes("`" + b.id + "`"), b.id);
});

test("every expected string appears verbatim", () => {
  const text = doc();
  for (const b of BEATS) for (const e of b.expect) assert.ok(text.includes(e), `${b.id}: ${e}`);
});

test("every narration line appears", () => {
  const text = doc();
  for (const b of BEATS) assert.ok(text.includes(b.say), `${b.id}: ${b.say}`);
});

test("every media file name appears", () => {
  const text = doc();
  for (const name of Object.keys(MEDIA)) assert.ok(text.includes(name), name);
});

test("the switches and clip names appear", () => {
  const text = doc();
  for (const word of ["TRAY_LIVE", "SETUP_LIVE", "MEDICINES_LIVE", "tray-hernia.mp4", "saline-setup.mp4", "make demo-check"]) {
    assert.ok(text.includes(word), word);
  }
});

test("the sections exist", () => {
  const headings = doc().split("\n").filter((l) => /^#{1,3} /.test(l));
  for (const word of ["Offline", "Keyed", "Owner handover"]) {
    assert.ok(headings.some((h) => h.includes(word)), word);
  }
});

test("narration passes the no-advice regex", () => {
  const quotes = doc().split("\n").filter((l) => l.startsWith("> "));
  assert.ok(quotes.length >= BEATS.length, "one narration quote per beat");
  for (const q of quotes) assert.ok(!ADVICE.test(q), q);
});

test("no key value is written", () => {
  assert.doesNotMatch(doc(), /(MODEL_API_KEY|BASETEN_API_KEY)=\S/);
});
