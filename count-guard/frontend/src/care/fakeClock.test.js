// A fake clock for step tests: timers fire only when the test moves time on. Named .test.js because only tests use it
// (the archive walk counts no test as an entry point); its own test below checks it.
import test from "node:test";
import assert from "node:assert/strict";

export function fakeClock() {
  let now = 0;
  let next = 1;
  const timers = new Map();
  return {
    now: () => now,
    setTimeout: (fn, ms) => { const id = next++; timers.set(id, { fn, at: now + ms }); return id; },
    clearTimeout: (id) => timers.delete(id),
    setInterval: (fn, ms) => { const id = next++; timers.set(id, { fn, at: now + ms, every: ms }); return id; },
    clearInterval: (id) => timers.delete(id),
    advance(ms) {
      const end = now + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        const [id, t] = due;
        now = t.at;
        if (t.every) t.at += t.every; else timers.delete(id);
        t.fn();
      }
      now = end;
    },
  };
}

export const flush = () => new Promise((r) => setImmediate(r));

test("fakeClock fires timers only when moved on", () => {
  const clock = fakeClock();
  let ticks = 0;
  clock.setInterval(() => { ticks += 1; }, 1000);
  assert.equal(ticks, 0);
  clock.advance(3000);
  assert.equal(ticks, 3);
  assert.equal(clock.now(), 3000);
});
