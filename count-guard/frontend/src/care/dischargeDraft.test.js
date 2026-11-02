import { test } from "node:test";
import assert from "node:assert/strict";
import { dischargeLinks, draftSections, draftSummary } from "./dischargeDraft.js";

const TIMELINE = {
  prescription: { rows: [{ name: "Paracetamol", strength: "650 mg", dose: "1-0-1", instructions: "After food" }] },
  drugs_given: [{ name: "lignocaine", strength: "2%", amount: 5, unit: "ml", route: "local infiltration", by: "Dr. A. Rao (synthetic)", when: "Mon 2 Nov, 09:20" }],
  count: { text: "opened 20 / returned 20, 0 unaccounted", by: "Nurse Asha (synthetic)" },
  events: [{ when: "Mon 2 Nov, 09:00", text: "Admitted" }],
  follow_up: { text: "Wound check", when: "Mon 9 Nov" },
};

test("draftSections lists the five sections from the record", () => {
  const sections = draftSections(TIMELINE);
  assert.deepEqual(sections.map((s) => s.title), ["Prescription", "Drugs given", "Swab count", "Key events", "Follow-up"]);
  assert.equal(sections[0].lines[0], "Paracetamol 650 mg 1-0-1 · After food");
  assert.equal(sections[1].lines[0], "lignocaine 2% 5 ml local infiltration · by Dr. A. Rao (synthetic), Mon 2 Nov, 09:20");
  assert.equal(sections[2].lines[0], "opened 20 / returned 20, 0 unaccounted · saved by Nurse Asha (synthetic)");
  assert.equal(sections[4].lines[0], "Wound check, Mon 9 Nov");
});

test("draftSections says when nothing was recorded", () => {
  const sections = draftSections({ prescription: null, drugs_given: [], count: null, events: [], follow_up: null });
  assert.deepEqual(sections.map((s) => s.lines[0]), ["No prescription recorded.", "No drug given in theatre.", "No count saved by a person.", "No moves recorded.", "None."]);
  assert.deepEqual(draftSections(null), []);
});

test("draftSummary puts dictated sections under the timeline summary", () => {
  assert.equal(draftSummary(null), "");
  assert.equal(draftSummary({ summary: "From the record." }), "From the record.");
  assert.equal(draftSummary({ sections: [{ heading: "Follow-up", text: "Day 7." }] }), "Follow-up: Day 7.");
  assert.equal(draftSummary({ summary: "A.", sections: [{ heading: "Follow-up", text: "B." }] }), "A.\n\nFollow-up: B.");
});

test("dischargeLinks name the PDF and the calendar file", () => {
  assert.deepEqual(dischargeLinks("e1"), { pdf: "/journey/episodes/e1/discharge.pdf", ics: "/journey/episodes/e1/follow-up.ics" });
});
