// One step per beat id: the clicks of the beat table, as browser actions. Expected strings are checked by run.mjs.
import { BEATS } from "./beats.mjs";
export { helpers, waitGone, waitText } from "./helpers.mjs";

const URL = "http://127.0.0.1:5273/";
const ADMISSION = ["Wristband on", "Allergies checked", "Baseline observations taken", "Consent on file"];
const DISCHARGE = ["Discharge card given", "Medicines handed over", "Reminders set"];
const KUMAR = "R. Kumar";
const IYER = "S. Iyer";
// A beat's "seen before" strings, asserted before the click that would change them.
const before = async (H, id) => { for (const s of BEATS.find((b) => b.id === id).before) await H.waitText(s); };
const VOICE = "Complete a task by voice";

export const STEPS = {
  async intro(H) {
    await H.page.goto(URL);
    await H.role("Doctor");
  },
  async "das-rx"(H) {
    await H.chart("A. Das");
    await H.click("Use the demo prescription");
  },
  async "das-strip"(H) {
    await H.fill("One strip per line: name then strength", "Amlodipine 10 mg");
    await H.click("Check these strips");
  },
  async "das-close"(H) {
    await H.click("Close visit");
  },
  async "das-ask"(H) {
    await H.role("Patient");
    await H.pick("A. Das");
    await H.tab("Ask");
    await H.fill("Your question", "When do I take amlodipine?", "Ask the record");
    await H.click("Ask the record");
  },
  async "das-mycare"(H) {
    await H.tab("My care");
  },
  async "kumar-orders"(H) {
    await H.role("Doctor");
    await H.chart(KUMAR);
    await H.click("Use the demo prescription");
    await H.file("Dictate orders", "eval/p2/kumar-orders.wav");
  },
  async "kumar-admit"(H) {
    await H.click("Sign orders");
    await H.click("Admit");
  },
  async "kumar-admission"(H) {
    await H.role("Nurse");
    await H.tab("My queue");
    await H.chart(KUMAR);
    await before(H, "kumar-admission");
    await H.tick(...ADMISSION);
    await H.click("Complete admission");
    await H.click("Acknowledge");
  },
  async "kumar-theatre"(H) {
    await H.role("Doctor");
    await H.page.locator("label.field", { hasText: "Procedure" }).locator("select").selectOption("hernia-repair");
    await before(H, "kumar-theatre");
    await H.click("Send to theatre");
  },
  async "kumar-chip"(H) {
    await H.role("Patient");
    await H.pick(KUMAR);
    await H.tab("Today");
  },
  async "kumar-free-soon"(H) {
    await H.role("Nurse");
    await H.chart(KUMAR);
    await H.clock("+1 h");
  },
  async "kumar-tray"(H) {
    await H.file("Tray check", "eval/p3/tray-hernia.mp4");
  },
  async "kumar-count"(H) {
    await H.click("Surgery began");
    await H.click("Record pack opened");
    await H.fill("Closing count (returned)", "14");
    await H.click("Record closing count");
    await before(H, "kumar-count");
    await H.fill("Closing count (returned)", "15");
    await H.click("Correct the count");
  },
  async "kumar-back"(H) {
    await H.click("Surgery ended");
    await H.click("Back to ward");
  },
  async "kumar-paracetamol"(H) {
    await H.file(VOICE, "eval/p2/kumar-paracetamol.wav");
    await before(H, "kumar-paracetamol");
    await H.file(VOICE, "eval/p2/strip-paracetamol.png");
    await H.click("Confirm");
  },
  async "kumar-mycare"(H) {
    await H.role("Patient");
    await H.pick(KUMAR);
    await H.tab("My care");
  },
  async "kumar-discharge"(H) {
    await H.role("Doctor");
    await H.chart(KUMAR);
    await H.file("Add reference photo", "eval/p4/wound-day0.png");
    await H.file("Dictate discharge", "eval/p2/kumar-discharge.wav");
    await before(H, "kumar-discharge");
    await H.click("Sign discharge");
  },
  async "kumar-home"(H) {
    await H.role("Nurse");
    await H.chart(KUMAR);
    await H.tick(...DISCHARGE);
    await H.click("Complete discharge");
  },
  async "kumar-ask"(H) {
    await H.role("Patient");
    await H.pick(KUMAR);
    await H.tab("Ask");
    await H.fill("Your question", "Is the swelling normal on day 3?", "Ask the doctor");
    await H.click("Send to Dr. Rao");
    await H.fill("Note for the doctor (optional)", "Day 3", "Healing photo");
    await H.file("Healing photo", "eval/p4/wound-day3.png");
  },
  async "kumar-review"(H) {
    await H.role("Doctor");
    await H.tab("My queue");
    await H.page.locator("tr").filter({ hasText: "Healing photo to review" }).getByRole("link", { name: /Open/ }).click();
    await H.file("Answer by voice", "eval/p2/rao-answer.wav");
    await before(H, "kumar-review");
    await H.click("Send answer");
    await H.click("No visit needed");
  },
  async "kumar-answers"(H) {
    await H.role("Patient");
    await H.pick(KUMAR);
    await H.tab("Ask");
  },
  async "iyer-bp"(H) {
    await H.role("Nurse");
    await H.chart(IYER);
    await H.file(VOICE, "eval/p2/iyer-bp.wav");
    await before(H, "iyer-bp");
    await H.click("Confirm");
  },
  async "iyer-orders"(H) {
    await H.role("Doctor");
    await H.tab("My queue");
    await H.chart(IYER);
    await H.file("Dictate orders", "eval/p2/iyer-saline.wav");
    await H.click("Sign orders");
  },
  async "iyer-setup"(H) {
    await H.role("Nurse");
    await H.chart(IYER);
    await H.click("Acknowledge");
    await H.file("Set-up check", "eval/p3/saline-setup.mp4");
    await H.waitText("Set-up matches the list");
    await H.click("Begin");
  },
  async "iyer-end"(H) {
    await H.clock("+1 h");
    await H.clock("+1 h");
    await H.click("End");
  },
  async "iyer-discharge"(H) {
    await H.role("Doctor");
    await H.fill("Summary", "Recovered on the ward after saline. BP back above the limit.");
    await H.click("Sign discharge");
  },
  async "iyer-home"(H) {
    await H.role("Nurse");
    await H.chart(IYER);
    await H.tick(...DISCHARGE);
    await H.click("Complete discharge");
  },
  async "iyer-meds"(H) {
    await H.role("Patient");
    await H.pick(IYER);
    await H.tab("Ask");
    await H.file("Medicine photo", "eval/p4/meds-iyer.png");
  },
  async close(H) {
    await H.role("Doctor");
    await H.tab("My queue");
  },
};
