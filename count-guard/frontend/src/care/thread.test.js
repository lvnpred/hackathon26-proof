import test from "node:test";
import assert from "node:assert/strict";
import { checkinStatusLine, readOpened, markOpened, threadItems, threadStatus, unreadCount, unreadLine, unseenCheckins } from "./thread.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const M = 60_000;
const ok = { text: "Here is what your record says.", found: true, source: "rules", sources: [{ id: "L1", text: "Prescription from Dr. A. Rao: Tab. Amlodipine 5 mg — 1 in the morning." }], at_ms: M, by: "Record bot" };
const view = { ask: {
  questions: [
    { id: "b1", to: "bot", text: "When do I take amlodipine?", at_ms: M, answer: ok },
    { id: "d1", to: "doctor", text: "Is the swelling normal?", at_ms: 2 * M, answer: null },
    { id: "d0", to: "doctor", text: "Old", at_ms: 0, answer: { text: "Yes.", by: "Dr. A. Rao", via: "voice", source: "doctor", at_ms: 64 * M } },
  ],
  reviews: [{ id: "r1", at_ms: 3 * M, note: "Day 3", photo: { url: "/p" }, answer: null }],
  medicines: [],
  checkins: [
    { id: "c1", at_ms: 4 * M, day: 3, feels: "Better", signs: [], seen: [{ by: "Nurse Meena (synthetic)", at_ms: 5 * M }] },
    { id: "c2", at_ms: 6 * M, day: 4, feels: "Same", signs: ["Redness"], seen: [] },
  ],
} };
const at = (id) => threadItems(view).find((i) => i.id === id);

test("one row per thing sent, newest first", () => {
  assert.deepEqual(threadItems(view).map((i) => i.id), ["c2", "c1", "r1", "d1", "b1", "d0"]);
  assert.deepEqual(threadItems({}), []);
});

test("status wording", () => {
  assert.equal(threadStatus(at("d1"), 8 * M), "Waiting for Dr. Rao · 6 min");
  assert.equal(threadStatus(at("r1"), 8 * M), "Waiting for Dr. Rao · 5 min");
  assert.equal(threadStatus(at("d0"), 8 * M), "Answered 10:04");
  assert.equal(threadStatus(at("b1"), 8 * M), "Answered from your record");
  assert.equal(threadStatus({ ...at("b1"), answer: { ...ok, found: false } }, 8 * M), "Not in your record");
  assert.equal(threadStatus(at("c1"), 8 * M), "Seen by Nurse Meena");
  assert.equal(threadStatus(at("c2"), 8 * M), "Sent 09:06 · not seen yet");
  assert.equal(at("c2").said, "Same; Redness");
});

test("unread counts answers after the last open", () => {
  assert.equal(unreadCount(view, null), 1);
  assert.equal(unreadCount(view, 64 * M), 0);
  assert.equal(unreadLine(view, 63 * M), "Dr. Rao answered your question");
  assert.equal(unreadLine(view, 64 * M), "");
});

test("unseenCheckins is per nurse", () => {
  assert.deepEqual(unseenCheckins(view, "Nurse Meena (synthetic)"), ["c2"]);
  assert.deepEqual(unseenCheckins(view, "Nurse Asha (synthetic)"), ["c1", "c2"]);
  assert.deepEqual(unseenCheckins(view, "Nurse Meena"), ["c2"]);
});

test("a saved check-in stays confirmed on Today after the form closes (PF-2)", () => {
  assert.equal(checkinStatusLine(view), "Day 4 check-in recorded · Sent 09:06 · not seen yet");
  const seen = { ask: { checkins: [view.ask.checkins[0]] } };
  assert.equal(checkinStatusLine(seen), "Day 3 check-in recorded · Seen by Nurse Meena");
  assert.equal(checkinStatusLine({}), "");
  assert.doesNotMatch(checkinStatusLine(view), ADVICE);
});

test("opened time survives and failures read as null", () => {
  const store = {};
  globalThis.localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } };
  assert.equal(readOpened("e1"), null);
  markOpened("e1", 123);
  assert.equal(readOpened("e1"), 123);
  globalThis.localStorage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  assert.equal(readOpened("e1"), null);
  assert.doesNotThrow(() => markOpened("e1", 1));
  delete globalThis.localStorage;
});

test("thread copy has no advice words", () => {
  for (const s of ["My messages", "Question to your record", "Question to Dr. Rao", "Checked against your prescription", "Not in your record", "Sent 09:06 · not seen yet", "Nothing sent yet. Ask your record or Dr. Rao above.", "Dr. Rao reviewed your healing photo", "Dr. Rao marked your medicines photo", "Answered (2)"]) assert.doesNotMatch(s, ADVICE);
});

test("a brown-bag mark is unread until Ask is opened", () => {
  const marked = { ask: { ...view.ask, questions: [], reviews: [], medicines: [{ id: "m1", at_ms: M, marks: [{ row: 3, mark: "noted", by: "Dr. A. Rao", at_ms: 70 * M }] }] } };
  assert.equal(unreadCount(marked, 69 * M), 1);
  assert.equal(unreadCount(marked, 70 * M), 0);
  assert.equal(unreadLine(marked, null), "Dr. Rao marked your medicines photo");
  assert.doesNotMatch(unreadLine(marked, null), ADVICE);
});
