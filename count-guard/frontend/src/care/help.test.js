import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { AUDIENCES, PATIENT_RULE, helpSections } from "./help.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;

test("help has sections with a title and what it does", () => {
  const rows = helpSections();
  assert.ok(rows.length > 0);
  rows.forEach((s) => assert.ok(s.id && s.title && s.does && s.who));
  assert.equal(new Set(rows.map((s) => s.id)).size, rows.length);
});

test("help copy has no event names, model names or advice", () => {
  const text = helpSections().map((s) => `${s.title} ${s.does} ${s.where}`).join(" ");
  assert.doesNotMatch(text, /\b[a-z]+\.[a-z_]+\b/);
  assert.doesNotMatch(text, /Spark|SAM|Whisper|Llama|model/i);
  assert.doesNotMatch(text, ADVICE);
});

test("help is a care route and a nav tab", () => {
  const app = fs.readFileSync(new URL("../App.jsx", import.meta.url), "utf8");
  assert.match(app, /path="\/help"/);
  const shell = fs.readFileSync(new URL("./CareShell.jsx", import.meta.url), "utf8");
  assert.equal((shell.match(/"\/help", "Help"/g) || []).length, 3);
});

test("help keeps the behaviour notes and the who-starts-where block", () => {
  const text = helpSections().map((s) => s.does).join(" ");
  assert.match(text, /counts as back only after it stays in the bucket/);
  assert.match(text, /fact card stays off unless you turn it on/);
  assert.match(text, /stays as read; it is not guessed/);
  assert.match(PATIENT_RULE, /not mixed/);
  assert.deepEqual(AUDIENCES.map((a) => a.start), ["/patients", "/queue", "/today"]);
  assert.doesNotMatch(AUDIENCES.map((a) => a.does).join(" "), ADVICE);
});

test("/guide shows Help and the old Guide screen is archived, not deleted", () => {
  const app = fs.readFileSync(new URL("../App.jsx", import.meta.url), "utf8");
  assert.match(app, /path="\/guide" element=\{<Help \/>\}/);
  assert.ok(!fs.existsSync(new URL("../screens/Guide.jsx", import.meta.url)));
  assert.ok(fs.existsSync(new URL("../../../archive/frontend/src/screens/Guide.jsx", import.meta.url)));
});
