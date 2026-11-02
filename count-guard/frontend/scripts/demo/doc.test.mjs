import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { ADVICE, BEATS } from "./beats.mjs";

// The two-app video script (spec §12, plan Task 17) must match the beat table: every filmed beat, in order, with its
// seconds and time range, its narration free of advice words, and the two labels on screen in every row.
const DOC_URL = new URL("../../../../docs/demo/dd-cg-flow-video-script.md", import.meta.url);
const doc = () => fs.readFileSync(DOC_URL, "utf8");
const FILMED = BEATS.filter((b) => b.film);

// The script table: | Time | Scene | Beat | s | On-screen action | Narration | Labels on screen |
const COL = { time: 0, scene: 1, beat: 2, seconds: 3, action: 4, say: 5, labels: 6 };
function rows(text) {
  return text.split("\n")
    .filter((l) => l.startsWith("|"))
    .map((l) => l.split("|").slice(1, -1).map((c) => c.trim()))
    .filter((c) => c.length === 7 && /^`[a-z-]+`$/.test(c[COL.beat]))
    .map((c) => ({ ...Object.fromEntries(Object.entries(COL).map(([k, i]) => [k, c[i]])), id: c[COL.beat].slice(1, -1) }));
}
const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

test("the script exists", () => {
  assert.ok(fs.existsSync(DOC_URL), "docs/demo/dd-cg-flow-video-script.md");
});

test("rows parses the script table and skips other tables", () => {
  const text = [
    "| Time | Scene | Beat | s | On-screen action | Narration | Labels on screen |",
    "|---|---|---|---|---|---|---|",
    "| 0:00–0:10 | Title | `title` | 10 | Open both apps | Two apps. | Research demo · Synthetic data |",
    "| A | B | C |",
  ].join("\n");
  assert.deepEqual(rows(text).map((r) => [r.id, r.seconds, r.time]), [["title", "10", "0:00–0:10"]]);
});

test("every filmed beat is a row, in beat order, and nothing else is", () => {
  assert.deepEqual(rows(doc()).map((r) => r.id), FILMED.map((b) => b.id));
});

test("each row's seconds and time range match the beat table, ending at 3:00", () => {
  let at = 0;
  const got = rows(doc());
  FILMED.forEach((b, i) => {
    assert.equal(got[i].seconds, String(b.seconds), b.id);
    assert.equal(got[i].time, `${clock(at)}–${clock(at + b.seconds)}`, b.id);
    at += b.seconds;
  });
  assert.equal(clock(at), "3:00");
});

test("every row shows the labels synthetic data and research demo", () => {
  for (const r of rows(doc())) {
    assert.match(r.labels, /synthetic data/i, r.id);
    assert.match(r.labels, /research demo/i, r.id);
  }
});

test("narration is written for every row and passes the no-advice regex", () => {
  for (const r of rows(doc())) {
    assert.ok(r.say.length > 0, r.id);
    assert.doesNotMatch(r.say, ADVICE, r.id);
  }
  for (const q of doc().split("\n").filter((l) => l.startsWith("> "))) assert.doesNotMatch(q, ADVICE, q);
});

test("the three judging criteria are each tied to the beat that proves them", () => {
  const lines = doc().split("\n");
  for (const [mark, id] of [["(a)", "theatre-card"], ["(b)", "theatre-missing"], ["(c)", "discharge-draft"]]) {
    assert.ok(lines.some((l) => l.includes(mark) && l.includes("`" + id + "`")), `${mark} ${id}`);
  }
});

test("no key value is written", () => {
  assert.doesNotMatch(doc(), /(MODEL_API_KEY|BASETEN_API_KEY|META_API_KEY)=\S/);
});
