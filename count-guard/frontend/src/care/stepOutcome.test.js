import test from "node:test";
import assert from "node:assert/strict";
import { createStepRunner, stepText } from "./modelStep.js";
import { UNKNOWN, latestVideo, newMoment, outcomeOf, own, viewOutcome } from "./stepOutcome.js";
import { fakeClock } from "./fakeClock.test.js";

const staff = { lens: "staff" };
const patient = { lens: "patient" };
const ev = (returned, extra = {}) => ({ evidence: { returned, used: {}, calls: [], ...extra } });

test("outcomeOf reads the evidence's returned mode and model", () => {
  assert.deepEqual(outcomeOf(ev({ model: "SAM 3.1", mode: "live", ms: 2100 })), { mode: "live", model: "SAM 3.1" });
  assert.deepEqual(outcomeOf(ev({ model: "Spark 1.3", mode: "prepared" })), { mode: "prepared", model: "Spark 1.3" });
  assert.deepEqual(outcomeOf(ev({ model: "rules", mode: "none" })), { mode: "none" });
  assert.deepEqual(
    outcomeOf(ev({ model: "Spark 1.3", mode: "failed" }, { used: { fallback: "template" }, calls: [{ model: "spark", source: "rules (model reply not usable)" }] })),
    { mode: "fallback", model: "Spark 1.3", fallback: "template" },
  );
  assert.deepEqual(
    outcomeOf(ev({ model: "Muse Voice", mode: "failed" }, { calls: [{ model: "voice", source: "prepared (live call failed)" }] })),
    { mode: "fallback", model: "Muse Voice", fallback: "prepared result" },
  );
  assert.deepEqual(outcomeOf(ev({ model: "SAM 3.1", mode: "failed" }, { calls: [{ model: "sam", source: "unavailable" }] })), { mode: "failed", model: "SAM 3.1" });
});

test("outcomeOf reads calls, then a bare source word; nothing known is null", () => {
  assert.deepEqual(outcomeOf({ calls: [{ model: "sam", source: "sam-3.1" }] }), { mode: "live", model: "SAM 3.1" });
  assert.deepEqual(outcomeOf({ calls: [{ model: "spark", source: "prepared" }] }), { mode: "prepared", model: "Spark 1.3" });
  assert.deepEqual(outcomeOf({ calls: [{ model: "spark", source: "rules (model reply not usable)" }] }), { mode: "fallback", model: "Spark 1.3", fallback: "rules" });
  assert.deepEqual(outcomeOf({ calls: [], source: "rules" }), { mode: "none" });
  assert.deepEqual(outcomeOf({ calls: [], source: "prepared" }), { mode: "prepared", model: null });
  assert.deepEqual(outcomeOf({ source: "sam-3.1" }), { mode: "live", model: null });
  assert.deepEqual(outcomeOf({ source: "prepared" }), { mode: "prepared", model: null });
  assert.equal(outcomeOf({ id: "x" }), null);
  assert.equal(outcomeOf(null), null);
});

test("newMoment finds the moment the call added; viewOutcome falls back to UNKNOWN", () => {
  const before = { ai_moments: [{ id: "a", capability: "strips", calls: [] }] };
  const after = { ai_moments: [{ id: "b", capability: "strips", calls: [{ model: "spark", source: "muse-spark-1.3" }] }, ...before.ai_moments] };
  assert.equal(newMoment(before, after, ["strips"]).id, "b");
  assert.equal(newMoment(before, after, ["tray"]), null);
  assert.deepEqual(viewOutcome(before, ["strips"])(after), { mode: "live", model: "Spark 1.3" });
  assert.equal(viewOutcome(before, ["tray"])(after), UNKNOWN);
});

test("latestVideo picks the newest check of one kind", () => {
  const v = { video_checks: [{ id: 1, check: "tray", source: "prepared" }, { id: 2, check: "swabs" }, { id: 3, check: "tray", source: "sam-3.1" }] };
  assert.equal(latestVideo(v, "tray").id, 3);
  assert.equal(latestVideo(v, "setup"), null);
});

test("own() hands the error to the card's step", () => {
  const signal = new AbortController().signal;
  assert.deepEqual(own({ signal, timeoutMs: 5 }), { signal, timeoutMs: 5, ownFault: true });
  assert.deepEqual(own(), { ownFault: true });
});

test("stepText: rules only, an unusable reply and an unknown result", () => {
  assert.equal(stepText({ stage: "done", mode: "none", model: "Spark 1.3" }, staff), "Done · No model used — drafted by rules");
  assert.equal(stepText({ stage: "done", mode: "none" }, patient), "Done");
  assert.equal(stepText({ stage: "done", mode: "fallback", model: "Spark 1.3", fallback: "rules" }, staff), "Done · Spark 1.3 reply not usable — rules used");
  assert.equal(stepText({ stage: "done", mode: "fallback", model: "Spark 1.3", fallback: "template" }, patient), "Done");
  assert.equal(stepText({ stage: "done", mode: "unknown", model: "SAM 3.1" }, staff), "Done");
});

test("run's outcome sets the done line from the result, with the model the evidence names", async () => {
  const r = createStepRunner({ capability: "orders", clock: fakeClock() });
  await r.run(() => Promise.resolve({ ok: 1 }), { outcome: () => ({ mode: "fallback", model: "Spark 1.3", fallback: "rules" }) });
  assert.equal(stepText(r.step, staff), "Done · Spark 1.3 reply not usable — rules used");
  await r.run(() => Promise.resolve(ev({ model: "Muse Voice", mode: "live" })));
  assert.equal(stepText(r.step, staff), "Done · live (Muse Voice, 0.0 s)");
  await r.run(() => Promise.resolve({ view: 1 }), { outcome: () => UNKNOWN });
  assert.equal(stepText(r.step, staff), "Done");
  await r.retry();
  assert.equal(stepText(r.step, staff), "Done", "retry keeps the outcome");
});

test("two uploads at once: two steps fail and succeed on their own", async () => {
  const clock = fakeClock();
  const a = createStepRunner({ capability: "tray", clock });
  const b = createStepRunner({ capability: "photo", clock });
  let failA;
  let passB;
  let progressB;
  const doneA = a.run(() => new Promise((_, reject) => { failA = reject; }), { what: "video" });
  const doneB = b.run((o) => { progressB = o.onProgress; return new Promise((res) => { passB = res; }); }, { what: "photo" });
  progressB(100);
  clock.advance(2000);
  assert.equal(stepText(a.step, staff), "Uploading video… 0%");
  assert.equal(stepText(b.step, staff), "Checking with Spark 1.3… 2 s");
  failA(new Error("clip too short"));
  assert.equal(await doneA, null);
  assert.equal(stepText(a.step, staff), "Didn't work: clip too short");
  assert.equal(b.step.stage, "checking", "b keeps going after a fails");
  passB({ source: "prepared" });
  await doneB;
  assert.equal(stepText(b.step, staff), "Done · Prepared (no live model)");
  assert.equal(a.step.stage, "failed", "a keeps its own failure");
});

test("P9: the record bot's patient line is Looking in your record, with no model name", () => {
  assert.equal(stepText({ stage: "checking", model: "Spark 1.3", what: "question", seconds: 3 }, patient), "Looking in your record… 3 s");
  assert.equal(stepText({ stage: "checking", model: "Spark 1.3", what: "question", seconds: 3 }, staff), "Checking with Spark 1.3… 3 s");
});

test("rules only: a photo or camera check says rules check; a draft says drafted by rules", async () => {
  assert.equal(stepText({ stage: "done", mode: "none", rules: "check" }, staff), "Done · No model used — rules check");
  assert.equal(stepText({ stage: "done", mode: "none", rules: "check" }, patient), "Done");
  for (const [capability, line] of [["tray", "rules check"], ["verdict", "rules check"], ["strips", "rules check"], ["handover", "drafted by rules"], ["orders", "drafted by rules"], ["voice", "drafted by rules"]]) {
    const r = createStepRunner({ capability, clock: fakeClock() });
    await r.run(() => Promise.resolve({}), { outcome: () => ({ mode: "none" }) });
    assert.equal(stepText(r.step, staff), `Done · No model used — ${line}`, capability);
  }
});

test("the default outcome never claims live without proof", async () => {
  const r = createStepRunner({ capability: "tray", clock: fakeClock() });
  await r.run(() => Promise.resolve({ id: 3, view: {} }));
  assert.equal(stepText(r.step, staff), "Done");
  await r.run(() => Promise.resolve({ text: "ok", heard_by: "prepared" }));
  assert.equal(stepText(r.step, staff), "Done · Prepared (no live model)");
  await r.run(() => Promise.resolve({ source: "sam-3.1" }));
  assert.equal(stepText(r.step, staff), "Done · live (SAM 3.1, 0.0 s)");
});

test("busyOf: a card is busy while its step uploads or checks", async () => {
  const { busyOf } = await import("./modelStep.js");
  assert.equal(busyOf({ stage: "uploading" }), true);
  assert.equal(busyOf({ stage: "checking" }), true);
  for (const stage of ["idle", "recording", "done", "failed"]) assert.equal(busyOf({ stage }), false, stage);
});

test("the AI page's sample tries name their models", async () => {
  const { modelOf } = await import("./modelStep.js");
  assert.deepEqual(["sam", "spark", "spark-open", "voice"].map(modelOf), ["SAM 3.1", "Spark 1.3", "Spark Open", "Muse Voice"]);
});

test("P10: the card step runs only when the server says a card is due, and names Spark only when Spark words it", async () => {
  const { cardStep } = await import("./stepOutcome.js");
  assert.equal(cardStep(null), null, "tier on, no drop due: no step line at all");
  assert.equal(cardStep(undefined), null);
  assert.equal(cardStep("spark"), "card");
  assert.equal(cardStep("rules"), "rules");
  const clock = fakeClock();
  const spark = createStepRunner({ capability: "card", clock });
  let finish;
  const done = spark.run(() => new Promise((res) => { finish = res; }), { outcome: (r) => outcomeOf(r.card) || UNKNOWN });
  clock.advance(2000);
  assert.equal(stepText(spark.step, staff), "Checking with Spark 1.3… 2 s");
  finish({ card: ev({ model: "Spark 1.3", mode: "failed" }, { used: { fallback: "template" }, calls: [{ model: "spark", source: "template (model reply not used)" }] }) });
  await done;
  assert.equal(stepText(spark.step, staff), "Done · Spark 1.3 reply not usable — template used");
  const rules = createStepRunner({ capability: undefined, clock });
  const ruled = rules.run(() => new Promise((res) => { finish = res; }), { outcome: (r) => outcomeOf(r.card) || UNKNOWN });
  assert.equal(stepText(rules.step, staff), "Checking… 0 s", "no model named when none is asked");
  finish({ card: ev({ model: "rules", mode: "none" }) });
  await ruled;
  assert.equal(stepText(rules.step, staff), "Done · No model used — drafted by rules");
});
