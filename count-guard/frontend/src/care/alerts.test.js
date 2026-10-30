import assert from "node:assert/strict";
import test from "node:test";
import { showTrayFlag } from "./derive.js";
import { SAFETY, alertNow, bannerAlerts, bannerClass, stripPills, surname } from "./alerts.js";

const n = (id, kind, to, at_ms, says = `says ${id}`) => ({ id, kind, to, at_ms, says, when: "Day 0 10:00" });
const pill = (episodeId, name, who, what) => ({ key: `${episodeId}:${what}`, episodeId, name, who, what });

test("surname", () => assert.equal(surname("R. Kumar, 58 M (synthetic)"), "Kumar"));
test("SAFETY lists the two safety kinds", () => assert.deepEqual(SAFETY, ["obs_past_limit", "count_open"]));
test("stripPills off a chart names each patient", () => {
  const out = stripPills([pill("e9", "A. Das, 47 M (synthetic)", "Patient", "This strip reads …")], undefined);
  assert.equal(out[0].text, "Das · Patient → This strip reads …");
});
test("stripPills on a chart keeps that patient's pills only", () => {
  const pills = [pill("e9", "A. Das", "Patient", "x"), pill("e4", "R. Kumar", "Nurse", "y")];
  assert.deepEqual(stripPills(pills, "e4").map((p) => p.text), ["Nurse → y"]);
  assert.deepEqual(stripPills(pills, "e7"), []);
});
test("alertNow picks the newest safety nudge", () => {
  const view = { nudges: [n("a", "obs_past_limit", "nurse", 1, "BP low."), n("b", "count_open", "nurse", 2, "Count open."), n("c", "obs_overdue", "nurse", 3)] };
  assert.equal(alertNow(view), "Waiting for the nurse's answer: Count open.");
  assert.equal(alertNow({ nudges: [n("c", "obs_overdue", "nurse", 3)] }), null);
});
test("bannerAlerts gives the form to the nurse, to the addressee and to the deep link", () => {
  const view = { nudges: [n("o", "obs_overdue", "nurse", 1), n("a", "obs_past_limit", "nurse", 2)] };
  assert.deepEqual(bannerAlerts(view, "nurse", null).map((x) => [x.nudge.id, x.safety, x.canAnswer]), [["a", true, true], ["o", false, true]]);
  assert.deepEqual(bannerAlerts(view, "doctor", null).map((x) => x.canAnswer), [false, false]);
  assert.deepEqual(bannerAlerts(view, "doctor", "a").map((x) => x.canAnswer), [true, false]);
});
test("showTrayFlag shows the flag only while in theatre, and not to the nurse (her theatre card shows it)", () => {
  assert.equal(showTrayFlag("nurse", "theatre"), false);
  assert.equal(showTrayFlag("doctor", "theatre"), true);
  assert.equal(showTrayFlag("doctor", "ward"), false);
  assert.equal(showTrayFlag("nurse", "ward"), false);
  assert.equal(showTrayFlag("doctor", "home"), false);
});

test("on a chart the strip drops pills the banner already shows", () => {
  const pills = [{ ...pill("e4", "R. Kumar", "Nurse", "BP low"), nudgeKind: "obs_past_limit" }, pill("e4", "R. Kumar", "Nurse", "Handover waiting")];
  assert.deepEqual(stripPills(pills, "e4").map((p) => p.text), ["Nurse → Handover waiting"]);
  assert.equal(stripPills(pills, undefined).length, 2);
});
test("stripPills with no name leaves no stray separator", () => {
  assert.equal(stripPills([pill("e4", "", "Nurse", "y")], undefined)[0].text, "Nurse → y");
});
test("the banner frame is red only while a safety alert is open", () => {
  const view = (...ns) => ({ nudges: ns });
  assert.equal(bannerClass(bannerAlerts(view(n("a", "obs_past_limit", "nurse", 1)), "nurse")), "alert-banner");
  assert.equal(bannerClass(bannerAlerts(view(n("o", "obs_overdue", "nurse", 1)), "nurse")), "alert-banner alert-calm");
  assert.equal(bannerClass([]), "alert-banner alert-calm");
});
