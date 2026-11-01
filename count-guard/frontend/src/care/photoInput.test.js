import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const dir = new URL("./", import.meta.url);
const read = (name) => fs.readFileSync(new URL(name, dir), "utf8");
const jsx = fs.readdirSync(dir).filter((name) => name.endsWith(".jsx"));

test("only PhotoInput and Dictate's audio input use a native file input in care/", () => {
  for (const name of jsx) {
    if (name === "PhotoInput.jsx") continue;
    const src = read(name);
    if (name === "Dictate.jsx") assert.match(src, /type="file" accept="audio\/\*"/);
    else assert.doesNotMatch(src, /type="file"/, `${name} has its own file input`);
  }
});

test("PhotoInput hides the real input, shows a camera button and the upload hint", () => {
  const src = read("PhotoInput.jsx");
  assert.match(src, /className="visually-hidden" type="file"/);
  assert.match(src, /className=\{`photo-input/);
  assert.match(src, /<IconCamera \/>/);
  assert.match(src, /<span className="small">or upload a file<\/span>/);
  assert.match(src, /label = "Take photo"/);
});

test("the tray and clip checks say what they add", () => {
  assert.match(read("VideoCheck.jsx"), /label="Add video or photos"/);
  assert.match(read("TheatreChecklist.jsx"), /label="Check the tray again"/);
});

test("the only .primary buttons outside the Now card are Now-owned blocks", () => {
  const allowed = new Set(["NowAction.jsx"]);
  for (const name of jsx) {
    if (/className="primary"/.test(read(name))) assert.ok(allowed.has(name), `${name} has a stray primary button`);
  }
  assert.doesNotMatch(read("AlertBanner.jsx"), /primary/);
  assert.doesNotMatch(read("Queue.jsx"), /primary/);
  assert.match(read("DoctorActions.jsx"), /Close visit/);
  assert.doesNotMatch(read("DoctorActions.jsx"), /className="primary"[^>]*>Close visit/);
});

test("styles.css has the four button kinds", () => {
  const css = fs.readFileSync(new URL("../styles.css", import.meta.url), "utf8");
  for (const kind of ["primary", "quiet", "danger"]) assert.match(css, new RegExp(`button\\.${kind}\\b`));
});
