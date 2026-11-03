import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { STATE_LABEL } from "./derive.js";
import { PHOTO_CLOSED } from "./askText.js";
import { CARDS, cardsFor, gate } from "./visibility.js";
import { doctorBlocks, quietActions } from "./journey.js";

const read = (f) => fs.readFileSync(new URL(`./${f}`, import.meta.url), "utf8");
const STATES = Object.keys(STATE_LABEL);
const OPENS = /^Opens when the patient is \S/;

// Every feature card renders in every state, enabled or with the reason it cannot run now (clarity §4.4, C5).
for (const role of ["doctor", "nurse", "patient"]) {
  for (const state of STATES) {
    test(`${role} in ${state}: every card renders, open or with its reason`, () => {
      const cards = cardsFor(role, state);
      assert.deepEqual(cards.map((c) => c.key), CARDS[role]);
      for (const card of cards) {
        if (card.open) assert.equal(card.reason, "", `${card.key} is open and says no reason`);
        else assert.ok(OPENS.test(card.reason) || card.reason === PHOTO_CLOSED, `${card.key} in ${state}: "${card.reason}"`);
      }
    });
  }
}

test("the reasons name the state words", () => {
  assert.deepEqual(gate("theatreRoom", "ward"), { open: false, reason: "Opens when the patient is in theatre" });
  assert.deepEqual(gate("tasks", "clinic"), { open: false, reason: "Opens when the patient is admitted" });
  assert.deepEqual(gate("theatre", "clinic"), { open: false, reason: "Opens when the patient is on the ward" });
  assert.deepEqual(gate("admit", "ward"), { open: false, reason: "Opens when the patient is in clinic" });
  assert.equal(gate("orders", "theatre").reason, "Opens when the patient is in clinic, being admitted or on the ward");
  assert.equal(gate("healingPhoto", "ward").reason, PHOTO_CLOSED);
});

test("open states match the server's rules", () => {
  const openIn = (key) => STATES.filter((s) => gate(key, s).open);
  for (const key of ["prescription", "homeMedicines", "photo", "checkin", "help"]) assert.deepEqual(openIn(key), STATES, key);
  assert.deepEqual(openIn("orders"), ["clinic", "admitting", "ward"]); // tasks.ORDER_STATES
  assert.deepEqual(openIn("dischargeDictate"), ["admitting", "ward", "theatre", "discharging"]); // media_api /dictate/discharge
  assert.deepEqual(openIn("dischargeDraft"), ["ward"]);
  assert.deepEqual(openIn("dischargeSign"), ["ward"]);
  for (const key of ["tasks", "dose", "handover"]) assert.deepEqual(openIn(key), ["admitting", "ward", "theatre", "discharging"], key);
  assert.deepEqual(openIn("healingPhoto"), ["clinic_done", "home"]); // ask.PHOTO_STATES
});

test("the doctor's quiet row and blocks are there in every state", () => {
  for (const state of STATES) {
    assert.deepEqual(quietActions(state, "doctor").map(([id]) => id), ["orders", "photo"], state);
    const { inside, below } = doctorBlocks(state, { mine: false, actions: [] });
    assert.deepEqual([...inside, ...below].sort(), ["admit", "discharge", "theatre"], state);
  }
  assert.deepEqual(doctorBlocks("ward", { mine: true, actions: ["theatre", "discharge"] }), { inside: ["theatre", "discharge"], below: ["admit"] });
  assert.deepEqual(quietActions("ward", "nurse"), []);
});

test("no card is hidden behind a state check in the role screens", () => {
  const doctor = read("DoctorActions.jsx");
  assert.doesNotMatch(doctor, /state === "(clinic|theatre|ward)" &&/);
  assert.match(doctor, /<Clinic /);
  for (const key of ["admit", "theatre", "dischargeDraft", "dischargeDictate", "dischargeSign", "theatreRoom", "orders"]) assert.match(doctor, new RegExp(`gate\\("${key}"`), key);
  const nurse = read("NurseActions.jsx");
  assert.doesNotMatch(nurse, /state === "ward" &&|state === "theatre"\) &&|Nothing for the nurse/);
  for (const key of ["tasks", "dose", "handover"]) assert.match(nurse, new RegExp(`gate\\("${key}"`), key);
  for (const f of ["NurseTasks.jsx", "DoseGiven.jsx", "Handover.jsx"]) assert.match(read(f), /<Opens reason=\{reason\} \/>/, f);
  const today = read("Today.jsx");
  assert.doesNotMatch(today, /\{home \?|open once you are home/);
  const asks = read("AskCards.jsx");
  assert.doesNotMatch(asks, /photoAskOpen\(view\.state\) \?/);
  assert.match(read("CareShell.jsx"), /demoRx=\{doctorChart \?/);
});

test("Sign orders is disabled with the reason wherever the order draft shows", () => {
  const src = read("DoctorActions.jsx");
  const body = src.slice(src.indexOf("function OrderDraft"), src.indexOf("function OrdersDictation"));
  assert.match(body, /const shut = gate\("orders", view\.state\)\.reason;/);
  assert.match(body, /<OrderForm busy=\{busy \|\| Boolean\(shut\)\}/);
  assert.match(body, /<Opens reason=\{shut\} \/>/);
});

test("a nurse checklist card shows only with its reason; no vague fallback", () => {
  const src = read("NurseActions.jsx");
  assert.doesNotMatch(src, /Not the next step yet/);
  assert.match(src, /\.filter\(\(\[, gateKey\]\) => gate\(gateKey, state\)\.reason\)/);
});

test("data-gated cards say they are empty instead of vanishing", () => {
  assert.doesNotMatch(read("CameraAdvice.jsx"), /if \(!camera\) return null/);
  assert.doesNotMatch(read("DischargeDraft.jsx"), /if \(!draft\?\.timeline\) return null/);
  const panels = read("TheatrePanels.jsx");
  assert.doesNotMatch(panels, /problem \? <p[^>]*>\{problem\}<\/p> : null/);
  // Once the first read answers (or there is no episode), a missing panel says so instead of loading forever.
  assert.match(panels, /finally \{\s*if \(live\) setRead\(true\);/);
  assert.match(panels, /\{read \|\| !episodeId \? NO_PANEL : "Reading the theatre record…"\}/);
});
