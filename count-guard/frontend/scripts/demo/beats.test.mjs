import test from "node:test";
import assert from "node:assert/strict";
import { ADVICE, BEATS, GENERATOR, MEDIA, ROLES, filmSeconds, missingMedia, roleSeconds } from "./beats.mjs";

test("ids are unique and every beat has a known role and path", () => {
  const ids = BEATS.map((b) => b.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(BEATS.length, 32);
  for (const b of BEATS) {
    assert.ok([...ROLES, "none"].includes(b.role), b.id);
    assert.ok(["intro", "das", "kumar", "iyer", "close"].includes(b.path), b.id);
  }
});

test("paths run intro twice, then das, kumar, iyer, and close last", () => {
  const order = BEATS.map((b) => b.path);
  assert.deepEqual(order.slice(0, 2), ["intro", "intro"]);
  assert.equal(order.at(-1), "close");
  const middle = order.slice(2, -1);
  const rank = { das: 0, kumar: 1, iyer: 2 };
  assert.ok(middle.every((p) => p in rank));
  assert.deepEqual(middle.map((p) => rank[p]), [...middle.map((p) => rank[p])].sort());
});

test("each role is filmed 54 to 62 s, the opening and close take 26 s and the film is at most 200 s", () => {
  const sums = roleSeconds(BEATS);
  for (const r of ROLES) assert.ok(sums[r] >= 54 && sums[r] <= 62, `${r} ${sums[r]}`);
  assert.equal(sums.none, 26);
  assert.ok(filmSeconds(BEATS) <= 200, String(filmSeconds(BEATS)));
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
  assert.ok(by["kumar-orders"].expect.includes("Draft from dictation"));
  assert.ok(by["kumar-orders"].expect.includes("Drafted from voice"));
  assert.ok(by["kumar-orders"].expect.includes("2 orders drafted from 25 words."));
  assert.deepEqual(by["kumar-review"].before, ["From voice"]);
  assert.ok(by["kumar-review"].expect.includes("From voice"));
  assert.equal(BEATS[1].id, "ai");
  assert.ok(by.ai.expect.includes("Saw 2 of 3 needle holders."));
  assert.ok(by["iyer-meds"].expect.includes("Pantoprazole 40 mg:"));
  const title = "Saline 1 litre over 2 hours, video check of the set-up";
  const ACK = "Acknowledged Dr. A. Rao's orders";
  assert.ok(by["kumar-admit"].expect.includes(ACK));
  assert.ok(by["kumar-admission"].before.includes(ACK) && by["kumar-admission"].expect.includes(ACK));
  assert.ok(by["iyer-orders"].expect.includes(ACK));
  assert.ok(!by["kumar-admission"].clicks.includes('Button "Acknowledge"'));
  assert.ok(!by["iyer-setup"].clicks.includes('Button "Acknowledge"'));
  assert.ok(by["kumar-ask"].expect.includes("Your question went to Dr. A. Rao"));
  assert.ok(by["iyer-setup"].expect.includes(`${title} running`));
  assert.ok(by["iyer-end"].expect.includes(`finished ${title} at`));
  assert.ok(by["kumar-count"].before.includes("Saw 14 of 15 gauze swabs."));
  assert.ok(by["kumar-discharge"].clicks.indexOf('Button "Draft discharge"') < by["kumar-discharge"].clicks.indexOf('Button "Update draft"'));
  const GONE_AFTER_SIGN = ["Drafted from voice", "5 sections drafted from 40 words.", "swab count closed 15 of 15", "Drafted from the record", "opened 15 / returned 15"];
  // kumar-review: the Dictate chip goes once the answer is sent, so it is checked before and not in expect.
  // kumar-discharge: the chip, the finding and the Inspector's swab count are gone once the discharge is signed, so they are checked before only.
  // kumar-count: the swab viewer goes once the count is saved, because the count step folds.
  for (const b of BEATS) for (const s of b.before ?? []) assert.ok(b.expect.includes(s) || b.id === "kumar-review" || (b.id === "kumar-discharge" && GONE_AFTER_SIGN.includes(s)) || (b.id === "kumar-count" && s === "Saw 14 of 15 gauze swabs."), `${b.id} ${s}`);
});
