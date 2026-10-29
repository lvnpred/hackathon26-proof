import test from "node:test";
import assert from "node:assert/strict";
import { photoPurposeLabel, doneBody, proofOf, draftChanged, itemsToRows, MATCH_LABEL, photoCheckLabel, sourceLabel, newestPhoto, proposalChoices, sectionsToSummary, SOURCE_LABEL } from "./drafts.js";
import { orderRowsToItems } from "./orders.js";

// The Task 2 Kumar draft, in the shape orderRowsToItems emits (P2-R9).
const KUMAR = [
  { kind: "dose", text: "Paracetamol 1 g every 6 hours", mode: "tick", proof: "photo", every_h: 6, name: "paracetamol", amount: "1 g" },
  { kind: "obs", text: "BP and pulse every 1 hour", mode: "tick", proof: "none", every_h: 1, limits: { sbp_min: 90 } },
];

test("itemsToRows inverts orderRowsToItems for the Kumar draft", () => {
  const rows = itemsToRows(KUMAR);
  assert.equal(rows[0].every_h, "6");
  assert.equal(rows[1].sbp_min, "90");
  assert.equal(rows[1].sbp_max, "");
  assert.equal(rows[0].proof, "photo");
  const { items, errors } = orderRowsToItems(rows);
  assert.deepEqual(items, KUMAR);
  assert.deepEqual(errors, {});
});

test("itemsToRows fills defaults for missing fields", () => {
  const [row] = itemsToRows([{ kind: "check", text: "Consent signed" }]);
  assert.deepEqual(row, { kind: "check", text: "Consent signed", name: "", amount: "", every_h: "", mode: "tick", proof: "none", sbp_min: "", sbp_max: "" });
});

test("sectionsToSummary joins heading and text lines", () => {
  const out = sectionsToSummary([{ heading: "Diagnosis", text: "Hernia" }, { heading: "Follow up", text: "Review in a week" }]);
  assert.equal(out, "Diagnosis: Hernia\nFollow up: Review in a week");
  assert.equal(sectionsToSummary([]), "");
});

test("proposalChoices for 0, 1 and 2 candidates", () => {
  const tasks = [
    { id: "a", status: "open" }, { id: "b", status: "running" }, { id: "c", status: "done" }, { id: "d", status: "closed" },
  ];
  const none = proposalChoices({ candidates: [] }, tasks);
  assert.deepEqual(none.choices.map((t) => t.id), ["a", "b"]);
  assert.equal(none.pick, true);
  const one = proposalChoices({ candidates: [tasks[0]] }, tasks);
  assert.deepEqual(one, { choices: [tasks[0]], pick: false });
  const two = proposalChoices({ candidates: [tasks[0], tasks[1]] }, tasks);
  assert.equal(two.choices.length, 2);
  assert.equal(two.pick, true);
});

test("newestPhoto is the last match, any purpose when taskId is null", () => {
  const view = { photos: [{ id: 1, task_id: "a" }, { id: 2, task_id: "b" }, { id: 3, task_id: "a" }] };
  assert.equal(newestPhoto(view, "a").id, 3);
  assert.equal(newestPhoto(view, "b").id, 2);
  assert.equal(newestPhoto(view, "z"), null);
  assert.equal(newestPhoto(view, null).id, 3);
  assert.equal(newestPhoto({}, "a"), null);
});

test("labels are the specified strings", () => {
  assert.equal(MATCH_LABEL.ok, "Photo matches the task");
  assert.equal(SOURCE_LABEL["muse-spark-1.3"], "Muse Spark");
  assert.equal(SOURCE_LABEL["muse-voice-transcribe"], "Muse Voice");
});

test("draftChanged is true only when a draft with a new id appears", () => {
  assert.equal(draftChanged(null, null), false);
  assert.equal(draftChanged(null, undefined), false);
  assert.equal(draftChanged(null, { id: "a" }), true);
  assert.equal(draftChanged("a", { id: "a" }), false);
  assert.equal(draftChanged("a", { id: "b" }), true);
  assert.equal(draftChanged("a", null), false);
});

test("photoCheckLabel gives every backend match a plain label", () => {
  assert.equal(photoCheckLabel(null), "");
  assert.equal(photoCheckLabel({ match: "ok" }), MATCH_LABEL.ok);
  assert.equal(photoCheckLabel({ match: "none" }), MATCH_LABEL.none);
  assert.equal(photoCheckLabel({ match: "weird" }), MATCH_LABEL.none);
});

test("sourceLabel falls back to the raw source, never a blank", () => {
  assert.equal(sourceLabel("typed"), "Typed");
  assert.equal(sourceLabel("none"), "Not read");
  assert.equal(sourceLabel("odd-model"), "odd-model");
  assert.equal(sourceLabel(undefined), "Not read");
});

const OBS = { kind: "obs", mode: "tick" };
const DOSE = { kind: "dose", mode: "tick" };
const GOOD = { sbp: "120", dbp: "80", hr: "70" };

test("doneBody for an obs task needs valid values", () => {
  assert.ok(doneBody({ task: OBS, via: "tap", transcript: "", form: {}, photo: null }).error);
  assert.ok(doneBody({ task: OBS, via: "tap", transcript: "", form: { ...GOOD, hr: "900" }, photo: null }).error);
  const { body, error } = doneBody({ task: OBS, via: "tap", transcript: "", form: GOOD, photo: null });
  assert.equal(error, undefined);
  assert.deepEqual(body, { via: "tap", transcript: "", note: "", values: { sbp: 120, dbp: 80, hr: 70 } });
});

test("doneBody carries proof_id only when there is a photo", () => {
  const plain = doneBody({ task: DOSE, via: "tap", transcript: "", form: {}, photo: null }).body;
  assert.deepEqual(plain, { via: "tap", transcript: "", note: "" });
  assert.equal("proof_id" in plain, false);
  const proved = doneBody({ task: DOSE, via: "tap", transcript: "", form: {}, photo: { id: "p1", check: { match: "mismatch" } } }).body;
  assert.equal(proved.proof_id, "p1");
});

test("doneBody by voice needs a transcript and keeps it", () => {
  assert.ok(doneBody({ task: DOSE, via: "voice", transcript: "   ", form: {}, photo: null }).error);
  const { body } = doneBody({ task: DOSE, via: "voice", transcript: " dose given ", form: {}, photo: null });
  assert.equal(body.via, "voice");
  assert.equal(body.transcript, "dose given");
});

test("doneBody errors carry no advice words", () => {
  const errors = [
    doneBody({ task: OBS, via: "tap", transcript: "", form: {}, photo: null }).error,
    doneBody({ task: OBS, via: "tap", transcript: "", form: { ...GOOD, sbp: "1" }, photo: null }).error,
    doneBody({ task: DOSE, via: "voice", transcript: "", form: {}, photo: null }).error,
  ];
  for (const e of errors) assert.doesNotMatch(e, /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i);
});

test("proofOf finds the photo, the voice flag and the mismatch flag", () => {
  const photos = [{ id: "p1", url: "/u/p1", check: { match: "mismatch" } }];
  const a = proofOf({ via: "voice", proof_id: "p1", match: "mismatch" }, photos);
  assert.deepEqual([a.voice, a.photo.url, a.flagged], [true, "/u/p1", true]);
  const b = proofOf({ via: "tap", proof_id: null, match: null }, photos);
  assert.deepEqual([b.voice, b.photo, b.flagged], [false, null, false]);
  assert.equal(proofOf({ via: "tap", proof_id: "gone", match: "ok" }, photos).photo, null);
});

test("sourceLabel names a failed or fallback read", () => {
  assert.equal(sourceLabel("failed"), "Not read (the model call failed)");
  assert.equal(sourceLabel("prepared (live call failed)"), "Prepared demo result (the live call failed)");
  assert.equal(sourceLabel("none"), "Not read");
  assert.equal(sourceLabel("muse-spark-1.3"), "Muse Spark");
});

test("photoPurposeLabel names each purpose, and unknown ones plainly", () => {
  assert.equal(photoPurposeLabel("proof"), "Proof");
  assert.equal(photoPurposeLabel("reference"), "Reference");
  assert.equal(photoPurposeLabel("healing"), "Healing photo");
  assert.equal(photoPurposeLabel("medicines"), "Medicines photo");
  assert.equal(photoPurposeLabel("other"), "Photo");
});
