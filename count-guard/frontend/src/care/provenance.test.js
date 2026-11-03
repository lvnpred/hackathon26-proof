import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { H, M } from "./clock.js";
import { ACCEPTED_ACTS, PROPOSED, madeByModel, provClass, provenanceOf, provenanceText, sameOrders } from "./provenance.js";
import { heardHow } from "./askText.js";
import { doneBody } from "./drafts.js";

const RAO = "Dr. A. Rao (synthetic)";
const ASHA = "Nurse Asha (synthetic)";
const DOSE = { kind: "dose", name: "Paracetamol", amount: "1 g", every_h: 6, text: "Paracetamol 1 g every 6 h", mode: "tick", proof: "none" };
const act = (type, ref, by, at_ms, extra = {}) => ({ id: `${type}:${ref}:${at_ms}`, type, ref, by, at_ms, ...extra });
const read = (name) => fs.readFileSync(new URL(`./${name}`, import.meta.url), "utf8");

test("nothing a person did yet: the item is proposed by the AI", () => {
  const p = provenanceOf({ id: "d1", at_ms: 5 * M }, []);
  assert.equal(p.kind, "proposed");
  assert.equal(p.at_ms, 5 * M);
  assert.equal(provenanceText(p), "Proposed by AI");
  assert.equal(PROPOSED, "Proposed by AI");
  assert.equal(provenanceOf({ id: "d1" }, undefined).kind, "proposed");
});

test("a person's act on this item accepts it: name without the synthetic tag, demo clock HH:MM", () => {
  const p = provenanceOf({ id: "h1" }, [act("handover.accepted", "h1", "Nurse Kavya (synthetic)", H + 14 * M)]);
  assert.deepEqual({ kind: p.kind, by: p.by, at_ms: p.at_ms }, { kind: "accepted", by: "Nurse Kavya", at_ms: H + 14 * M });
  assert.equal(provenanceText(p), "Accepted by Nurse Kavya 10:14");
});

test("acts on other items, and acts written by the AI, never accept it", () => {
  const acts = [act("handover.accepted", "h2", ASHA, H), act("camera.ack", "h1", "AI (on behalf of Ward 4)", H)];
  assert.equal(provenanceOf({ id: "h1" }, acts).kind, "proposed");
});

test("a signed order whose items differ from the draft is changed, with before and after", () => {
  const signed = [{ ...DOSE, amount: "500 mg" }];
  const p = provenanceOf({ id: "d1", value: [DOSE], same: sameOrders }, [act("order.signed", "d1", RAO, 14 * M, { value: signed })]);
  assert.equal(p.kind, "changed");
  assert.deepEqual(p.before, [DOSE]);
  assert.deepEqual(p.after, signed);
  assert.equal(provenanceText(p), "Changed by Dr. A. Rao 09:14");
});

test("a signed order equal to the draft is accepted; extra draft-only fields do not count as a change", () => {
  const drafted = [{ ...DOSE, grounded: true }];
  const p = provenanceOf({ id: "d1", value: drafted, same: sameOrders }, [act("order.signed", "d1", RAO, 14 * M, { value: [DOSE] })]);
  assert.equal(p.kind, "accepted");
  assert.equal(p.before, null);
  assert.equal(p.after, null);
});

test("without a compare function, values compare by their content", () => {
  const item = { id: "t1", value: { sbp: 120, hr: 72 } };
  assert.equal(provenanceOf(item, [act("task.done", "t1", ASHA, 0, { value: { hr: 72, sbp: 120 } })]).kind, "accepted");
  assert.equal(provenanceOf(item, [act("task.done", "t1", ASHA, 0, { value: { sbp: 118, hr: 72 } })]).kind, "changed");
  assert.equal(provenanceOf({ id: "t1" }, [act("task.done", "t1", ASHA, 0, { value: { sbp: 1 } })]).kind, "accepted");
});

test("a photo verdict override and a camera advice resolve are overridden; the newest act wins", () => {
  const over = provenanceOf({ id: "task:t1" }, [act("check.override", "task:t1", ASHA, 30 * M)]);
  assert.equal(over.kind, "overridden");
  assert.equal(provenanceText(over), "Overridden by Nurse Asha 09:30");
  const advice = [act("camera.ack", "a1", ASHA, H, { reason: "" }), act("camera.resolved", "a1", RAO, 2 * H, { reason: "Counted" })];
  const p = provenanceOf({ id: "a1" }, advice);
  assert.equal(p.kind, "overridden");
  assert.equal(provenanceText(p), "Overridden by Dr. A. Rao 11:00");
  assert.ok(ACCEPTED_ACTS.includes("camera.ack"));
});

test("camera advice: an ack with no reason is Seen by, an ack that says why is Overridden by", () => {
  const seen = provenanceOf({ id: "a1" }, [act("camera.ack", "a1", ASHA, H, { reason: "" })]);
  assert.equal(seen.kind, "seen");
  assert.equal(provenanceText(seen), "Seen by Nurse Asha 10:00");
  const why = provenanceOf({ id: "a1" }, [act("camera.ack", "a1", ASHA, H, { reason: "Found under the drape" })]);
  assert.equal(provenanceText(why), "Overridden by Nurse Asha 10:00");
});

test("an act that carries the AI's proposal is changed when the saved value differs (obs, discharge, drug)", () => {
  const obs = act("task.done", "t1", ASHA, 30 * M, {
    proposed: { values: { sbp: 118, dbp: 80 }, said: "one eighteen over eighty" },
    value: { values: { sbp: 120, dbp: 80 }, said: "one twenty over eighty" },
  });
  const p = provenanceOf({ id: "t1" }, [obs]);
  assert.equal(p.kind, "changed");
  assert.deepEqual(p.before.values, { sbp: 118, dbp: 80 });
  assert.deepEqual(p.after.values, { sbp: 120, dbp: 80 });
  assert.equal(provenanceText(p), "Changed by Nurse Asha 09:30");
  const summary = provenanceOf({ id: "d2" }, [act("discharge.signed", "d2", RAO, H, { proposed: "Recovered.", value: "Recovered. Day 7 check." })]);
  assert.equal(summary.kind, "changed");
  assert.equal(provenanceOf({ id: "d2" }, [act("discharge.signed", "d2", RAO, H, { proposed: "Recovered.\n", value: "Recovered." })]).kind, "accepted");
  const drug = provenanceOf({ id: "g1" }, [act("drug.given", "g1", ASHA, H, { proposed: { said: "five ml", amount: 5 }, value: { said: "eight ml", amount: 8 } })]);
  assert.deepEqual([drug.kind, drug.before.amount, drug.after.amount], ["changed", 5, 8]);
  const same = provenanceOf({ id: "g1" }, [act("drug.given", "g1", ASHA, H, { proposed: { said: "five ml", amount: 5 }, value: { said: "five ml", amount: 5 } })]);
  assert.equal(same.kind, "accepted");
});

test("Proposed by AI only where a model produced the proposal", () => {
  assert.equal(madeByModel({ calls: [{ model: "voice", source: "prepared" }] }), true);
  assert.equal(madeByModel({ calls: [{ model: "spark", source: "live" }] }), true);
  assert.equal(madeByModel({ calls: [{ model: "sam", source: "unavailable" }] }), false);
  assert.equal(madeByModel({ calls: [{ model: "spark", source: "failed" }] }), false);
  assert.equal(madeByModel({ calls: [{ model: "spark", source: "rules (model reply not usable)" }] }), false);
  assert.equal(madeByModel({ calls: [] }), false);
  assert.equal(madeByModel(null), false);
  const src = read("Provenance.jsx");
  assert.match(src, /p\.kind === "proposed" && item\?\.ai === false/);
  assert.match(read("ProofItem.jsx"), /ai: \["accepted", "not_accepted"\]\.includes\(check\.state\)/);
});

test("heard words the person edited stay voice, marked edited, with the heard words kept", () => {
  assert.deepEqual(heardHow("one eighteen", "one eighteen", "prepared"), { via: "voice", heard_by: "prepared" });
  assert.deepEqual(heardHow("one eighteen", "one twenty", "prepared"), { via: "voice", heard_by: "prepared", edited: true, heard_text: "one eighteen" });
  assert.deepEqual(heardHow("", "typed it", ""), { via: "text", heard_by: "" });
  assert.deepEqual(heardHow("x", "y", "typed"), { via: "text", heard_by: "" });
});

test("a task saved from heard values sends the AI's proposal beside the values", () => {
  const task = { kind: "obs" };
  const form = { sbp: "120", dbp: "80", hr: "70" };
  const { body } = doneBody({ task, via: "voice", transcript: "one twenty", form, heardBy: "prepared", proposed: { sbp: 118, dbp: 80, hr: 70, rr: 16 }, edited: true, heardText: "one eighteen" });
  assert.deepEqual(body.proposed_values, { sbp: 118, dbp: 80, hr: 70 }); // only the fields the server takes
  assert.equal(body.edited, true);
  assert.equal(body.heard_text, "one eighteen");
  const typed = doneBody({ task, via: "text", transcript: "", form, proposed: { sbp: 118 } }).body;
  assert.equal("proposed_values" in typed, false);
});

test("the mark's classes: a draft is dashed, a person's act is solid", () => {
  assert.equal(provClass("proposed"), "prov prov-proposed");
  assert.equal(provClass("accepted"), "prov prov-accepted");
  assert.equal(provClass("changed"), "prov prov-accepted prov-changed");
  assert.equal(provClass("overridden"), "prov prov-accepted prov-overridden");
  assert.equal(provClass("seen"), "prov prov-accepted prov-seen");
});

test("the CSS: .prov-proposed is dashed, .prov-accepted is solid, both from tokens only", () => {
  const css = read("provenance.css");
  assert.doesNotMatch(read("care.css"), /\.prov-/); // care.css does not grow
  assert.match(read("Provenance.jsx"), /import "\.\/provenance\.css";/);
  const rule = (sel) => css.match(new RegExp(`\\n\\${sel} \\{[^}]*\\}`))?.[0] || "";
  assert.match(rule(".prov-proposed"), /border-style:\s*dashed/);
  assert.match(rule(".prov-accepted"), /border-style:\s*solid/);
  for (const sel of [".prov", ".prov-proposed", ".prov-accepted"]) assert.doesNotMatch(rule(sel), /#[0-9a-f]{3,6}|rgb\(/i);
});

test("the Provenance mark: the AI mark when proposed, a person icon when a person acted", () => {
  const src = read("Provenance.jsx");
  assert.match(src, /provenanceOf\(item, events\)/);
  assert.match(src, /<AiMark \/>/);
  assert.match(src, /<IconPerson \/>/);
  assert.match(src, /provClass\(p\.kind\)/);
  assert.match(read("icons.jsx"), /export function IconPerson/);
});

test("every item in §4.3 carries the mark", () => {
  assert.match(read("OrderForm.jsx"), /<Provenance /); // order draft
  assert.match(read("DoctorActions.jsx"), /<Provenance [^>]*sameOrders/); // order signed: changed shows
  assert.match(read("DoctorActions.jsx"), /discharge\.signed/); // discharge signed
  assert.match(read("DischargeDraft.jsx"), /<Provenance /); // discharge draft
  assert.match(read("Handover.jsx"), /<Provenance item=\{\{ id: handover\.id/);
  assert.match(read("TheatreDrugs.jsx"), /<Provenance item=\{\{ id: row\.id/);
  assert.match(read("TheatreDrugs.jsx"), /<Provenance item=\{\{ id: pack\.id/);
  assert.match(read("ProofItem.jsx"), /<Provenance item=\{\{ id: check\.item/);
  assert.match(read("CameraAdvice.jsx"), /<Provenance item=\{\{ id: row\.id/);
  assert.match(read("NurseTasks.jsx"), /<Provenance item=\{\{ id: task\.id/); // dictated values saved
  assert.match(read("TaskProof.jsx"), /<Provenance /); // dictated values before Confirm
});

test("callers pass the chart's acts to every mark", () => {
  for (const name of ["NurseActions.jsx", "TheatreChecklist.jsx", "TaskProof.jsx"]) assert.match(read(name), /<ProofItem [^>]*acts=\{view\.acts\}/s, name);
  assert.match(read("CountPanel.jsx"), /<CameraAdvice [^>]*acts=\{view\.acts\}/);
  assert.match(read("TheatrePanels.jsx"), /<TheatreDrugs [^>]*acts=/);
  assert.match(read("DoctorActions.jsx"), /proposed_summary: draftSummary\(draft\)/);
  assert.match(read("TheatreDrugs.jsx"), /heardHow\(/);
  assert.match(read("NurseTasks.jsx"), /heardHow\(/);
  assert.match(read("NurseTasks.jsx"), /a\.type === "task\.done" && a\.ref === task\.id/); // same predicate as acts.py

});

test("heard text the person edits keeps the From voice mark until it is sent", () => {
  const src = read("Dictate.jsx");
  assert.doesNotMatch(src, /heard\.text === text/);
  assert.match(src, /\{heard && text\.trim\(\) && <p className="small"><Source /);
});

test("camera advice is the AI's only when the camera's model made it", async () => {
  const { adviceByModel } = await import("./provenance.js");
  assert.equal(adviceByModel({ rule: "R1", source: "prepared" }), true);
  assert.equal(adviceByModel({ rule: "R6", source: "prepared" }), false);
  assert.equal(adviceByModel({ rule: "R1", source: "unavailable" }), false);
});

test("a spoken task's values are the AI's only when a model read them, never a rules fallback or a failed hearing", async () => {
  const { proposalByModel } = await import("./provenance.js");
  const { rowSession } = await import("./drafts.js");
  const task = { id: "t1", kind: "obs" };
  const spark = { heard_by: "prepared", source: "prepared", calls: [{ model: "voice", source: "prepared" }, { model: "spark", source: "prepared" }], values: { sbp: 118 } };
  const rules = { heard_by: "prepared", source: "rules", calls: [{ model: "voice", source: "prepared" }], values: { sbp: 118 } };
  const failed = { heard_by: "prepared (live call failed)", source: "prepared", calls: [{ model: "spark", source: "prepared" }], values: {} };
  assert.equal(proposalByModel(spark), true);
  assert.equal(proposalByModel(rules), false);
  assert.equal(proposalByModel({ ...rules, source: "rules (model reply not usable)" }), false);
  assert.equal(proposalByModel(failed), false);
  assert.equal(rowSession(spark, task).ai, true);
  assert.equal(rowSession(rules, task).ai, false); // a rules-only session shows no "Proposed by AI"
  assert.match(read("TaskProof.jsx"), /<Provenance item=\{\{ id: task\.id, ai: session\.ai === true \}\} events=\{\[\]\} \/>/);
});

test("a confirmed typed drug or pack still shows who confirmed it, with no AI frame", () => {
  const src = read("TheatreDrugs.jsx");
  assert.doesNotMatch(src, /source !== "typed" && <Provenance/);
  assert.match(src, /<Provenance item=\{\{ id: row\.id, at_ms: row\.at_ms, ai: row\.source !== "typed" && madeByModel\(row\) \}\} events=\{acts\} \/>/);
  assert.match(src, /<Provenance item=\{\{ id: pack\.id, at_ms: pack\.at_ms, ai: pack\.source !== "typed" && madeByModel\(pack\) \}\} events=\{acts\} \/>/);
  const typed = provenanceOf({ id: "g1", ai: false }, [act("drug.given", "g1", ASHA, 12 * M, { proposed: { said: "x", amount: 5 }, value: { said: "x", amount: 5 } })]);
  assert.equal(provenanceText(typed), "Accepted by Nurse Asha 09:12");
});
