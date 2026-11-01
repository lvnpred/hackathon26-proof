import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { showTrayFlag } from "./derive.js";
import { SAFETY, alertParts, bannerAlerts, bannerClass, nudgeText, stripPills, surname } from "./alerts.js";

const n = (id, kind, to, at_ms, says = `says ${id}`) => ({ id, kind, to, at_ms, says, when: "10:00" });
const pill = (episodeId, name, who, what, role = "nurse") => ({ key: `${episodeId}:${what}`, episodeId, name, who, what, role });

test("surname", () => assert.equal(surname("R. Kumar, 58 M (synthetic)"), "Kumar"));
test("SAFETY lists the two safety kinds", () => assert.deepEqual(SAFETY, ["obs_past_limit", "count_open"]));
test("stripPills off a chart names each patient", () => {
  const out = stripPills([pill("e9", "A. Das, 47 M (synthetic)", "Patient", "This strip reads …", "nurse")], undefined, "nurse").mine;
  assert.equal(out[0].text, "Das · Patient → This strip reads …");
});
test("stripPills on a chart keeps that patient's pills only", () => {
  const pills = [pill("e9", "A. Das", "Patient", "x"), pill("e4", "R. Kumar", "Nurse", "y")];
  assert.deepEqual(stripPills(pills, "e4", "nurse").mine.map((p) => p.text), ["Nurse → y"]);
  assert.deepEqual(stripPills(pills, "e7", "nurse").mine, []);
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
  assert.deepEqual(stripPills(pills, "e4", "nurse").mine.map((p) => p.text), ["Nurse → Handover waiting"]);
  assert.equal(stripPills(pills, undefined, "nurse").mine.length, 2);
});
test("stripPills with no name leaves no stray separator", () => {
  assert.equal(stripPills([pill("e4", "", "Nurse", "y")], undefined, "nurse").mine[0].text, "Nurse → y");
});
test("the banner frame is red only while a safety alert is open", () => {
  const view = (...ns) => ({ nudges: ns });
  assert.equal(bannerClass(bannerAlerts(view(n("a", "obs_past_limit", "nurse", 1)), "nurse")), "alert-banner");
  assert.equal(bannerClass(bannerAlerts(view(n("o", "obs_overdue", "nurse", 1)), "nurse")), "alert-banner alert-calm");
  assert.equal(bannerClass([]), "alert-banner alert-calm");
});
test("stripPills puts the role's own pills first and folds the rest", () => {
  const pills = [pill("e4", "R. Kumar", "Nurse", "a", "nurse"), pill("e7", "S. Iyer", "Dr. A. Rao", "b", "doctor"), pill("e7", "S. Iyer", "Nurse", "c", "nurse")];
  const out = stripPills(pills, undefined, "doctor");
  assert.deepEqual(out.mine.map((p) => p.what), ["b"]);
  assert.deepEqual(out.others.map((g) => g.text), ["+2 for nurse"]);
  assert.deepEqual(out.others[0].pills.map((p) => p.what), ["a", "c"]);
});
test("stripPills with no own pills still shows the folded ones", () => {
  const out = stripPills([pill("e4", "R. Kumar", "Nurse", "a", "nurse")], undefined, "doctor");
  assert.equal(out.mine.length, 0);
  assert.equal(out.others[0].text, "+1 for nurse");
});
test("folded groups follow the order nurse, doctor, patient", () => {
  const pills = [pill("e4", "R", "x", "p", "patient"), pill("e4", "R", "x", "d", "doctor"), pill("e4", "R", "x", "n", "nurse")];
  assert.deepEqual(stripPills(pills, undefined, "nurse").others.map((g) => g.role), ["doctor", "patient"]);
  assert.deepEqual(stripPills(pills, undefined, "patient").others.map((g) => g.role), ["nurse", "doctor"]);
});

test("stripPills keeps a pill with an unknown role, in a group named by that role", () => {
  const pills = [pill("e4", "R. Kumar", "Lab", "z", "pharmacist"), pill("e4", "R. Kumar", "Nurse", "y", "nurse"), pill("e4", "R. Kumar", "Lab", "w", "pharmacist")];
  const out = stripPills(pills, "e4", "nurse");
  assert.deepEqual(out.mine.map((p) => p.text), ["Nurse → y"]);
  assert.deepEqual(out.others.map((g) => g.text), ["+2 for pharmacist"]);
  assert.equal(out.others[0].pills.length, 2);
  const viewer = stripPills(pills, "e4", "pharmacist");
  assert.equal(viewer.mine.length, 2);
  assert.deepEqual(viewer.others.map((g) => g.text), ["+1 for nurse"]);
});

test("nudgeText gives staff the staff wording and the patient the patient wording", () => {
  assert.equal(nudgeText({ says: "a", says_staff: "b" }, "doctor"), "b");
  assert.equal(nudgeText({ says: "a", says_staff: "b" }, "nurse"), "b");
  assert.equal(nudgeText({ says: "a", says_staff: "b" }, "patient"), "a");
  for (const role of ["doctor", "nurse", "patient"]) assert.equal(nudgeText({ says: "a" }, role), "a");
});
test("bannerAlerts shows the patient only nudges addressed to the patient", () => {
  const view = { nudges: [n("a", "obs_overdue", "nurse", 1), n("p", "strip_strength_differs", "patient", 2)] };
  assert.deepEqual(bannerAlerts(view, "patient", null).map((x) => x.nudge.id), ["p"]);
  assert.deepEqual(bannerAlerts(view, "nurse", null).map((x) => x.nudge.id), ["a", "p"]);
});

test("bannerAlerts sorts danger before late, then oldest first", () => {
  const view = { nudges: [n("l1", "obs_overdue", "nurse", 5), n("d2", "obs_past_limit", "nurse", 9), n("l0", "dose_overdue", "nurse", 1), n("d1", "count_open", "nurse", 3)] };
  assert.deepEqual(bannerAlerts(view, "nurse", null).map((x) => x.nudge.id), ["d1", "d2", "l0", "l1"]);
});
test("alertParts splits the reading from the limit and who set it", () => {
  assert.deepEqual(alertParts("Systolic BP 82 is below the limit of 90 set by Dr. A. Rao."), { headline: "Systolic BP 82", limit: "90", by: "Dr. A. Rao" });
  assert.deepEqual(alertParts("Closing count: 14 of 15 back."), { headline: "Closing count: 14 of 15 back.", limit: null, by: null });
});
test("AlertCard asks 'What did you do?', saves a response and names the assignee", () => {
  const src = fs.readFileSync(new URL("./AlertCard.jsx", import.meta.url), "utf8");
  assert.ok(src.includes("Save response"));
  assert.ok(!src.includes("Answer"));
  assert.ok(src.includes("What did you do?"));
  assert.ok(src.includes("Details") && src.includes("Take observations now") && src.includes("Assigned to"));
  assert.ok(src.includes("aria-label={`Alert: ${headline}`}"));
  assert.ok(!src.includes('placeholder="Called the patient back"'));
  assert.ok(src.includes("/seen"));
});
