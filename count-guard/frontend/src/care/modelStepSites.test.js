import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (f) => fs.readFileSync(new URL(`./${f}`, import.meta.url), "utf8");

// Every card that calls a model shows its own step line, with Retry (spec §4.1).
const SITES = [
  "Dictate.jsx", "TaskProof.jsx", "ProofItem.jsx", "HomeMedicines.jsx", "VideoCheck.jsx", "CameraAdvice.jsx",
  "AskCards.jsx", "Handover.jsx", "ContextCard.jsx", "DoctorActions.jsx", "TheatreChecklist.jsx", "VitalsStrip.jsx", "ModelCards.jsx",
];

// Retry waits while another write runs (the global busy), and the card says it is busy while its step works (§4.1).
for (const file of SITES) {
  test(`${file}: Retry respects busy and the card has aria-busy`, () => {
    const src = read(file);
    for (const tag of src.match(/<ModelStep\b[^>]*\/>/g) || []) assert.match(tag, /busy=\{/, `${file}: ${tag}`);
    assert.match(src, /aria-busy=\{/, file);
  });
}

for (const file of SITES) {
  test(`${file} renders <ModelStep> with Retry from useModelStep`, () => {
    const src = read(file);
    assert.match(src, /useModelStep\(/, "uses the hook");
    assert.match(src, /<ModelStep\b[^>]*onRetry=/, "renders the step with Retry");
    assert.match(src, /from "\.\/ModelStep\.jsx"/, "imports the step directly");
  });
}

test("every model call in a site hands its fault to the step (own(opts))", () => {
  for (const file of ["TaskProof.jsx", "HomeMedicines.jsx", "AskCards.jsx", "Handover.jsx", "DoctorActions.jsx", "TheatreChecklist.jsx",
    "NurseTasks.jsx", "NurseActions.jsx", "CountPanel.jsx", "TheatreDrugs.jsx", "AskInbox.jsx", "CameraAdvice.jsx"]) {
    assert.match(read(file), /own\(o\)/, file);
  }
});

test("ward.js no longer re-exports ModelStep; the chart and Ask pass opts through", () => {
  assert.doesNotMatch(read("ward.js"), /export \{ default as ModelStep/);
  const chart = read("Chart.jsx");
  assert.match(chart, /const act = \(path, body, scope, opts\) => ward\.act\(episodeId, path, body, scope, opts\)/);
  assert.match(chart, /const upload = \(path, file, fields, scope, opts\) => ward\.upload\(episodeId, path, file, fields, scope, opts\)/);
  assert.match(chart, /const ask = \(path, file, fields, scope, opts\) => ward\.ask\(episodeId, path, file, fields, scope, opts\)/);
  const ask = read("Ask.jsx");
  assert.match(ask, /act: \(path, body, scope, opts\) => ward\.act\(patient\.id, path, body, scope, opts\)/);
  assert.match(ask, /upload: \(path, file, fields, scope, opts\) => ward\.upload\(patient\.id, path, file, fields, scope, opts\)/);
});

test("TheatreDrugs hears through ward.ask (the Dictate step), not the raw client", () => {
  const src = read("TheatreDrugs.jsx");
  assert.doesNotMatch(src, /uploadJourney/);
  assert.match(src, /ask\("\/ask\/hear", file/);
});

test("doctor dictation keeps heard-then-edited text as voice (ruling P8) and drafts with a Spark step", () => {
  const src = read("DoctorActions.jsx");
  assert.doesNotMatch(src, /answerHow/);
  assert.match(src, /heardHow\(heard\?\.text, text, heard\?\.by\)\.heard_by/);
  assert.match(src, /sendCapability="discharge"/);
});

test("the patient's Ask cards (record bot and both photos) use the patient lens", () => {
  const src = read("AskCards.jsx");
  assert.equal((src.match(/lens: "patient"/g) || []).length, 3);
  assert.match(src, /act\("\/ask\/bot", \{ text: text\.trim\(\) \}, undefined, own\(o\)\)/);
  assert.match(src, /what: "question"/);
});

test("the orders drafting step lives outside the Dictate again fold, so its done line survives the remount", () => {
  const src = read("DoctorActions.jsx");
  assert.match(src, /sendStep=\{drafting\}/);
  assert.match(read("Dictate.jsx"), /const sending = sendStep \|\| ownSend/);
});

test("ModelStep disables Retry while busy", () => {
  assert.match(read("ModelStep.jsx"), /onClick=\{onRetry\} disabled=\{busy\}/);
});

test("the camera read beside Back says Prepared when a prepared read stands behind it", () => {
  const src = read("CountPanel.jsx");
  assert.match(src, /Camera read \{camera\}[^\n]*prepared=\{isPrepared\(count\.camera\)\}/);
});

test("P10: the vitals strip and the context card show a step only when the panel says a card is due", () => {
  const strip = read("VitalsStrip.jsx");
  assert.match(strip, /cardStep\(panel\.card_due\)/);
  assert.match(strip, /if \(!due\) return onNext\(\);/);
  const card = read("ContextCard.jsx");
  assert.match(card, /cardStep\(due\)/);
  assert.match(card, /disabled=\{busy \|\| working\}/);
  assert.match(read("TheatrePanels.jsx"), /due=\{panel\.card_on_tier\}/);
});

test("Dictate sets nothing after it unmounts (the Dictate again box remounts)", () => {
  const src = read("Dictate.jsx");
  assert.match(src, /const mounted = useRef\(true\)/);
  assert.match(src, /if \(!mounted\.current\) return;/);
});
