import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { KEPT, MENU } from "./menu.js";

const read = (f) => readFileSync(new URL(f, import.meta.url), "utf8");

test("a kept screen is never in the menu, and the dock links come only from MENU", () => {
  for (const [to] of MENU) assert.ok(!KEPT.includes(to), `${to} is kept and still in the menu`);
  const dock = read("./DemoDock.jsx");
  assert.match(dock, /MENU\.map\(/);
  assert.doesNotMatch(dock, /to="\/older"/);
});

test("the old routes are gone from App.jsx and nothing imports the archived screens", () => {
  const app = read("../App.jsx");
  for (const old of ["/steps", "/older", "/count", "/morning", "/opd", "/ot", "/ward", "/case/", "/journey", "/doctor", "/nurse", "/patient", "/audit"]) {
    if (!KEPT.includes(old)) assert.ok(!app.includes(`path="${old}"`) && !app.includes(`path="${old.replace(/\/$/, "")}/`), old);
  }
  assert.doesNotMatch(app, /from "\.\/screens\//);
});
