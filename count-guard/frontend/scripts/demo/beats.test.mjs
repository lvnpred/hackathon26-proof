import test from "node:test";
import assert from "node:assert/strict";
import { ADVICE, BEATS, GENERATOR, MEDIA, ROLES, filmSeconds, missingMedia, roleSeconds } from "./beats.mjs";

test("ids are unique and every beat has a known role and path", () => {
  const ids = BEATS.map((b) => b.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(BEATS.length, 31);
  for (const b of BEATS) {
    assert.ok([...ROLES, "none"].includes(b.role), b.id);
    assert.ok(["intro", "das", "kumar", "iyer", "close"].includes(b.path), b.id);
  }
});

test("paths run das, then kumar, then iyer (intro first, close last)", () => {
  const order = BEATS.map((b) => b.path);
  assert.equal(order[0], "intro");
  assert.equal(order.at(-1), "close");
  const middle = order.slice(1, -1);
  const rank = { das: 0, kumar: 1, iyer: 2 };
  assert.ok(middle.every((p) => p in rank));
  assert.deepEqual(middle.map((p) => rank[p]), [...middle.map((p) => rank[p])].sort());
});

test("each role is filmed 54 to 62 s and the film is at most 180 s", () => {
  const sums = roleSeconds(BEATS);
  for (const r of ROLES) assert.ok(sums[r] >= 54 && sums[r] <= 62, `${r} ${sums[r]}`);
  assert.ok(filmSeconds(BEATS) <= 180, String(filmSeconds(BEATS)));
});

test("roleSeconds counts filmed beats only", () => {
  const beats = [
    { role: "doctor", seconds: 5, film: true },
    { role: "doctor", seconds: 0, film: false },
    { role: "none", seconds: 3, film: true },
  ];
  assert.deepEqual(roleSeconds(beats), { doctor: 5, nurse: 0, patient: 0, none: 3 });
  assert.equal(filmSeconds(beats), 8);
});

test("check-only beats are 0 s and not filmed", () => {
  for (const b of BEATS) assert.equal(b.film === false, b.seconds === 0, b.id);
  assert.deepEqual(BEATS.filter((b) => !b.film).map((b) => b.id), ["kumar-free-soon"]);
});

test("every filmed beat has narration, at least one click and one expected text", () => {
  for (const b of BEATS.filter((x) => x.film)) {
    assert.ok(b.say.length > 0, b.id);
    assert.ok(b.clicks.length >= 1, b.id);
    assert.ok(b.expect.length >= 1, b.id);
    assert.ok(b.keyed.length > 0, b.id);
  }
  for (const b of BEATS) assert.ok(b.expect.length >= 1, b.id);
});

test("narration passes the no-advice regex", () => {
  for (const b of BEATS) assert.doesNotMatch(b.say, ADVICE, b.id);
});

test("every file a beat uses is in MEDIA, and each folder has a generator", () => {
  for (const b of BEATS) for (const f of b.files ?? []) assert.ok(f in MEDIA, `${b.id} ${f}`);
  for (const folder of new Set(Object.values(MEDIA))) assert.ok(GENERATOR[folder], folder);
});

test("missingMedia names the first missing file and its generator", () => {
  assert.equal(missingMedia("/r", () => true), "");
  assert.equal(
    missingMedia("/r", (p) => !p.endsWith("wound-day0.png")),
    "Missing eval/p4/wound-day0.png. Run: .venv/bin/python eval/p4/make_photos.py (or make demo-check).",
  );
});

test("expected strings follow the accepted rulings", () => {
  const by = Object.fromEntries(BEATS.map((b) => [b.id, b]));
  assert.ok(by["kumar-orders"].expect.includes("Draft from dictation · Rules (no model)"));
  assert.ok(by["kumar-orders"].expect.includes("Heard by: Prepared demo result"));
  assert.ok(by["iyer-meds"].expect.includes("Pantoprazole 40 mg:"));
  const title = "Saline 1 litre over 2 hours, video check of the set-up";
  assert.ok(by["iyer-setup"].expect.includes(`${title} running`));
  assert.ok(by["iyer-end"].expect.includes(`finished ${title} at`));
  assert.ok(by["kumar-count"].before.includes("Closing count: 14 of 15 back, 1 unaccounted."));
  const NEXT_ADMIT = "Nurse acknowledges the new orders from Dr. A. Rao, then completes the admission.";
  // kumar-review: the "Heard by" line goes once the answer is sent, so it is checked before and not in expect.
  // kumar-admission: the NEXT card sentence goes once the orders are acknowledged.
  for (const b of BEATS) for (const s of b.before ?? []) assert.ok(b.expect.includes(s) || b.id === "kumar-review" || (b.id === "kumar-admission" && s === NEXT_ADMIT), `${b.id} ${s}`);
});
