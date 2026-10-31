import test from "node:test";
import assert from "node:assert/strict";
import { H, M } from "./clock.js";
import { whenText, DAY0 } from "./when.js";

const ms = (day, h = 9, m = 0) => day * 24 * H + (h - 9) * H + m * M;

test("DAY0 is the demo's first day", () => assert.equal(DAY0, "2026-11-02"));

test("the same demo day is just the time", () => assert.equal(whenText(ms(0, 9, 0), ms(0, 10, 0)), "09:00"));

test("the day before says Yesterday", () => assert.equal(whenText(ms(0, 22, 10), ms(1, 9, 0)), "Yesterday 22:10"));

test("older times carry the date", () => assert.equal(whenText(ms(2, 9, 14), ms(5, 9)), "Wed 4 Nov, 09:14"));

test("no clock gives the full date", () => assert.equal(whenText(ms(0, 9, 14), null), "Mon 2 Nov, 09:14"));

test("past midnight rolls the day and never says Day", () => {
  assert.equal(whenText(ms(0, 9, 0) + 16 * H, undefined), "Tue 3 Nov, 01:00");
  assert.doesNotMatch(whenText(ms(3, 9, 0), ms(3, 9, 0)), /Day /);
});

test("only the demo dock prints Day N: no other care file imports label from clock", async () => {
  const { readdirSync, readFileSync } = await import("node:fs");
  const users = readdirSync(new URL(".", import.meta.url))
    .filter((f) => /\.(js|jsx)$/.test(f) && !f.endsWith(".test.js") && f !== "clock.js")
    .filter((f) => /import\s*\{[^}]*\blabel\b[^}]*\}\s*from\s*"\.\/clock/.test(readFileSync(new URL(f, import.meta.url), "utf8")));
  assert.deepEqual(users, ["DemoDock.jsx"]);
});
