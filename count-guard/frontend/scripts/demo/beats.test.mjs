import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { ADVICE, APPS, BEATS, GENERATOR, MEDIA, ROLES, SCENES, SCENE_SECONDS, filmSeconds, missingMedia, sceneSeconds } from "./beats.mjs";

const by = Object.fromEntries(BEATS.map((b) => [b.id, b]));
const allText = (b) => [...b.expect, ...(b.before ?? [])].join(" | ");

test("ids are unique, the count is pinned, and every beat has a known scene, app and role", () => {
  const ids = BEATS.map((b) => b.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(BEATS.length, 20);
  for (const b of BEATS) {
    assert.ok(SCENES.includes(b.scene), b.id);
    assert.ok(APPS.includes(b.app), b.id);
    assert.ok([...ROLES, "none"].includes(b.role), b.id);
  }
});

test("scenes follow the spec §12 order: title, DD, ward, theatre, discharge, close", () => {
  assert.deepEqual(SCENES, ["title", "dd", "ward", "theatre", "discharge", "close"]);
  const order = BEATS.map((b) => SCENES.indexOf(b.scene));
  assert.deepEqual(order, [...order].sort((a, b) => a - b));
  assert.equal(BEATS[0].scene, "title");
  assert.equal(BEATS.at(-1).scene, "close");
  for (const b of BEATS.filter((x) => x.scene === "dd")) assert.equal(b.app, "dd", b.id);
  for (const b of BEATS.filter((x) => x.scene !== "dd" && x.scene !== "title")) assert.equal(b.app, "cg", b.id);
});

test("scene seconds match spec §12 within 4 s (DD 30, ward 25, theatre 60, discharge 40) and the film is at most 180 s", () => {
  assert.deepEqual(SCENE_SECONDS, { dd: 30, ward: 25, theatre: 60, discharge: 40 });
  const sums = sceneSeconds(BEATS);
  for (const [scene, want] of Object.entries(SCENE_SECONDS)) {
    assert.ok(Math.abs(sums[scene] - want) <= 4, `${scene} ${sums[scene]} s, want ${want} ± 4`);
  }
  assert.ok(filmSeconds(BEATS) <= 180, String(filmSeconds(BEATS)));
});

test("sceneSeconds counts filmed beats only", () => {
  const beats = [
    { scene: "dd", seconds: 5, film: true },
    { scene: "dd", seconds: 0, film: false },
    { scene: "title", seconds: 3, film: true },
  ];
  assert.equal(sceneSeconds(beats).dd, 5);
  assert.equal(sceneSeconds(beats).title, 3);
  assert.equal(filmSeconds(beats), 8);
});

test("check-only beats are 0 s and not filmed", () => {
  for (const b of BEATS) assert.equal(b.film === false, b.seconds === 0, b.id);
});

test("every filmed beat has narration, at least one click and one expected text", () => {
  for (const b of BEATS.filter((x) => x.film)) {
    assert.ok(b.say.length > 0, b.id);
    assert.ok(b.clicks.length >= 1, b.id);
    assert.ok(b.expect.length >= 1, b.id);
    assert.ok(b.keyed.length > 0, b.id);
  }
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
    missingMedia("/r", (p) => !p.endsWith("consent-form.png")),
    "Missing eval/media/consent/consent-form.png. Run: .venv/bin/python eval/make_media.py (or make demo-check).",
  );
});

test("DD: dictate, then Save & admit to ward, and the save reaches Count Guard", () => {
  const dd = BEATS.filter((b) => b.app === "dd");
  assert.ok(dd.some((b) => b.clicks.some((c) => c.includes("Save & admit to ward"))));
  const saved = BEATS.findIndex((b) => b.expect.includes("Saved and in Count Guard."));
  assert.ok(saved >= 0 && BEATS[saved].app === "dd");
  assert.ok(by["dd-dictate"].expect.includes("M. Fernandes (synthetic)"));
});

test("the patient is on the CG ward within 3 s of the DD save (A1)", () => {
  const saved = BEATS.findIndex((b) => b.expect.includes("Saved and in Count Guard."));
  const arrival = BEATS[saved + 1];
  assert.equal(arrival.app, "cg");
  assert.equal(arrival.scene, "ward");
  assert.ok(arrival.arrivalMs > 0 && arrival.arrivalMs <= 3000, String(arrival.arrivalMs));
  assert.ok(arrival.expect.includes("M. Fernandes, 52 F"));
  assert.ok(arrival.expect.includes("Being admitted"));
});

test("\"synthetic data\" and \"Research demo\" are expected on screen in both apps", () => {
  for (const app of ["dd", "cg"]) {
    const text = BEATS.filter((b) => b.app === app).map(allText).join(" | ");
    assert.match(text, /synthetic data/i, app);
    assert.match(text, /research demo/i, app);
  }
});

test("the §12 moments are each expected by a beat", () => {
  const scene = (s) => BEATS.filter((b) => b.scene === s).map(allText).join(" | ");
  assert.match(scene("ward"), /Accepted — The photo shows a patient wristband/);
  assert.match(scene("ward"), /Not accepted — /);
  assert.match(scene("ward"), /On the ward/);
  assert.match(scene("theatre"), /From voice/);
  assert.match(scene("theatre"), /confirmed by Nurse Asha/);
  assert.match(scene("theatre"), /Research demo — not for clinical use/);
  assert.match(scene("theatre"), /BP 86\/50, down 28% in 4 min\./);
  assert.match(scene("theatre"), /Advice only\. The count a person saves decides\./);
  assert.match(scene("theatre"), /One lap sponge was not seen back\./);
  assert.match(scene("theatre"), /Surgery ended unlocks when the count is saved\./);
  assert.match(scene("discharge"), /Drafted from the record/);
  assert.match(scene("discharge"), /Discharge PDF/);
  assert.match(scene("discharge"), /opened 15 \/ returned 15/);
});

test("the wrong photo is retaken in the ward scene", () => {
  const ward = BEATS.filter((b) => b.scene === "ward");
  const wrong = ward.findIndex((b) => b.expect.some((s) => s.startsWith("Not accepted — ")));
  assert.ok(wrong >= 0);
  assert.ok(ward.slice(wrong + 1).some((b) => b.clicks.some((c) => c.includes("again"))));
});

test("every beat with before strings has its step check them through before(H, id)", () => {
  const steps = fs.readFileSync(new URL("./steps.mjs", import.meta.url), "utf8");
  const withBefore = BEATS.filter((b) => (b.before ?? []).length);
  assert.ok(withBefore.length >= 4);
  for (const b of withBefore) {
    const start = steps.indexOf(`async ${/^[a-z]+$/.test(b.id) ? b.id : `"${b.id}"`}(H) {`);
    assert.ok(start >= 0, `no step for ${b.id}`);
    const body = steps.slice(start, steps.indexOf("\n  },", start));
    assert.match(body, new RegExp(`before\\(H, "${b.id}"`), `${b.id}: its step never checks its before strings`);
  }
});

test("the DD save status accepts either first line, so the 1 s Sending line cannot race", () => {
  assert.deepEqual(by["dd-admit"].firstOf, ["Saved. Sending to Count Guard…", "Saved and in Count Guard."]);
  assert.equal(by["dd-admit"].before, undefined);
});

test("the discharge is signed before the PDF opens, and the PDF must hold the drug log and the count", () => {
  const ids = BEATS.map((b) => b.id);
  assert.ok(ids.indexOf("discharge-sign") < ids.indexOf("discharge-pdf"));
  assert.ok(ids.indexOf("discharge-draft") < ids.indexOf("discharge-sign"));
  assert.ok(by["discharge-sign"].before.includes("Discharge PDF"));
  assert.ok(by["discharge-pdf"].pdf.includes("lignocaine 2% 5 ml local infiltration"));
  assert.ok(by["discharge-pdf"].pdf.includes("Opened 15. Returned 15. Unaccounted 0."));
});
