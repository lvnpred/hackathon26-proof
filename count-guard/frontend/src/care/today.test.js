import test from "node:test";
import assert from "node:assert/strict";
import { H, M } from "./clock.js";
import { greeting, nextWords, todayFolds, whereWords } from "./today.js";

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

test("next item: the review when nothing else is next", () => {
  assert.equal(nextWords(home()), "Next: wound check in the surgical clinic on day 7");
  assert.equal(nextWords(home({ now_next: { you_next: "The doctor reviews your healing photo." } })), "Next: the doctor reviews your healing photo.");
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
