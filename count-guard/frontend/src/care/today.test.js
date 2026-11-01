import test from "node:test";
import assert from "node:assert/strict";
import { H, M } from "./clock.js";
import { greeting, todayFolds, whereWords } from "./today.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const home = (extra = {}) => ({ state: "home", schedule: [{}], card: { review: "Wound check in the surgical clinic on day 7 (synthetic)" }, ask: { questions: [] },
  now_next: { you_now: "Dr. A. Rao completed your discharge at 10:50.", you_next: "You are home. No further steps." }, ...extra });

test("greeting and where", () => {
  assert.equal(greeting("R. Kumar, 58 M (synthetic)"), "Hi, R. Kumar");
  assert.equal(whereWords("home", 3 * 24 * H + 5 * M), "You are home · day 3");
  assert.equal(whereWords("home", 5 * M), "You are home");
  assert.equal(whereWords("theatre", 0), "You are in theatre");
  assert.equal(whereWords("discharging", 0), "You are getting ready to go home");
});

test("folds: an empty My medicines never comes first, and the answered count shows", () => {
  assert.deepEqual(todayFolds(home()).map((f) => f.key), ["card", "medicines", "strips", "ask"]);
  const empty = home({ schedule: [], ask: { questions: [{ to: "doctor", answer: { text: "ok" } }, { to: "doctor", answer: null }] } });
  assert.deepEqual(todayFolds(empty).map((f) => f.key), ["card", "strips", "ask", "medicines"]);
  assert.equal(todayFolds(empty).find((f) => f.key === "ask").title, "Ask Dr. Rao (1 answered)");
});

test("M6 copy has no advice words", () => {
  for (const s of ["Open check-in", "Feeling worse?", "Need help now", "You are getting ready to go home", "Ask a question →"]) assert.doesNotMatch(s, ADVICE);
});

test("Today keeps its panel state per patient and closes check-in after a save", async () => {
  const fs = await import("node:fs");
  const today = fs.readFileSync(new URL("./Today.jsx", import.meta.url), "utf8");
  assert.match(today, /<TodayBody key=\{patient\.id\}/);
  assert.match(today, /onDone=\{\(\) => setCheckingIn\(false\)\}/);
  const card = fs.readFileSync(new URL("../screens/PatientCard.jsx", import.meta.url), "utf8");
  assert.match(card, /onDone\?\.\(\)/);
  // The form unmounts on save, so Today shows the check-in's status line from the record (PF-2).
  assert.match(today, /checkinStatusLine\(view, ward\.nowMs\)/);
  assert.match(today, /\{sent && <p className="note" role="status">\{sent\}<\/p>\}/);
});
