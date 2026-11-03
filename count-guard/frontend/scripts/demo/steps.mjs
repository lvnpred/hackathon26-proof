// One step per beat id: the clicks of the beat table, as browser actions. Expected strings are checked by run.mjs.
// H is the Count Guard helper set (helpers.mjs) plus H.dd (the Doctor Dictation tab), H.cgApi (the API origin)
// and H.marks (what one step leaves for a later one).
import { resolve } from "node:path";
import { BEATS, PATIENT } from "./beats.mjs";
import { pdfText } from "./pdftext.mjs";
export { helpers, waitGone, waitText } from "./helpers.mjs";

const CG = "http://127.0.0.1:5273/";
const DD = "http://127.0.0.1:8300/";
const FULL_NAME = "M. Fernandes, 52 F (synthetic)";
const NURSE_THEATRE = "Nurse Asha (synthetic)";
const ADMISSION = ["Wristband on", "Allergies checked", "Baseline observations taken", "Consent on file"];
const DISCHARGE = ["Discharge card given", "Medicines handed over", "Reminders set"];
const MISSING = "One lap sponge was not seen back.";
const FOUND = "Found under the drape, counted by hand";

// A beat's "seen before" strings, asserted before the click that would change them.
const before = async (H, id, page = H.page, root = ".app") => {
  for (const s of BEATS.find((b) => b.id === id).before) await H.waitText(s, 10000, page, root);
};
const photo = async (H, label, file, seen) => {
  await H.file(`Photo check: ${label}`, file);
  await H.waitText(seen);
};
const episodeId = (H) => new URL(H.page.url()).pathname.split("/").pop();

// The patient on Count Guard's ward list, read from the same API the list polls. Resolves with the ms since `from`.
async function arrival(api, from, ms = 10000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      const ward = await (await fetch(`${api}/journey/ward`)).json();
      if ((ward.patients || []).some((p) => p.name === FULL_NAME)) return Date.now() - from;
    } catch {
      // the next poll tries again
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  return Infinity;
}

export const STEPS = {
  async title(H) {
    await H.dd.goto(DD, { waitUntil: "domcontentloaded" });
    await H.page.goto(CG, { waitUntil: "domcontentloaded" });
    await H.page.bringToFront();
    await H.role("Doctor");
  },
  async "dd-open"(H) {
    await H.dd.bringToFront();
    await H.dd.locator("#recBtn").waitFor();
  },
  async "dd-dictate"(H) {
    await H.dd.click("#recBtn");
    await H.dd.waitForTimeout(3000); // the fake microphone records about 3 s
    await H.dd.click("#recBtn");
    await H.dd.locator("#admitBtn").waitFor({ state: "visible", timeout: 60000 });
  },
  async "dd-admit"(H) {
    await H.dd.click("#admitBtn"); // the first press asks for the reason
    await H.dd.fill("#admitReason", "Right inguinal hernia repair");
    const saved = H.dd.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/v1/documents");
    await H.dd.click("#admitBtn");
    const reply = await saved;
    if (!reply.ok()) throw new Error(`The DD save answered ${reply.status()}`);
    H.marks.arrived = arrival(H.cgApi, Date.now());
    const first = BEATS.find((b) => b.id === "dd-admit").firstOf;
    await H.dd.waitForFunction((lines) => lines.some((l) => document.getElementById("status")?.innerText.includes(l)), first, { timeout: 10000 })
      .catch(() => { throw new Error(`No save status: none of ${first.join(" / ")}`); });
  },
  async "ward-arrival"(H) {
    const ms = await H.marks.arrived;
    const limit = BEATS.find((b) => b.id === "ward-arrival").arrivalMs;
    if (!(ms <= limit)) throw new Error(`The patient reached the Count Guard ward ${ms} ms after the DD save (limit ${limit} ms)`);
    await H.page.bringToFront();
    await H.role("Nurse");
    await H.tab("Patients");
  },
  async "ward-photo-ok"(H) {
    await H.chart(PATIENT);
    await H.file("Photo check: Wristband on", "eval/media/wristband/wristband-synthetic.png");
  },
  async "ward-photo-wrong"(H) {
    await H.file("Photo check: Consent on file", "eval/media/wrong-photo/wrong-photo-bed-rail-synthetic.png");
  },
  async "ward-retake"(H) {
    await photo(H, "Consent on file", "eval/media/consent/consent-form.png", "Photo matches — The photo shows a signed consent form");
    await before(H, "ward-retake");
    await H.tick(...ADMISSION);
    await H.click("Complete admission");
  },
  async "theatre-send"(H) {
    await H.role("Doctor");
    await H.page.locator("label.field", { hasText: "Procedure" }).locator("select").selectOption("hernia-repair");
    await H.click("Send to theatre");
  },
  async "theatre-drug"(H) {
    await H.role("Nurse");
    const drug = H.page.getByRole("region", { name: "Drug given" });
    await drug.locator('input[type=file][accept="audio/*"]').setInputFiles(resolve(H.root, "eval/media/drug-phrases/drug-lignocaine.wav"));
    await H.page.waitForFunction(() => document.querySelector("[aria-label='Drug given'] textarea")?.value.includes("lignocaine"));
    await drug.getByRole("button", { name: "Add heard line", exact: true }).click();
    await before(H, "theatre-drug");
    await drug.getByRole("button", { name: "Confirm given", exact: true }).click();
  },
  async "theatre-card"(H) {
    const strip = H.page.getByRole("region", { name: "Vitals strip" });
    for (let i = 0; i < 4; i++) {
      await strip.getByRole("button", { name: /^Next reading/ }).click();
      await H.page.waitForFunction((n) => document.querySelectorAll("[aria-label='Vitals strip'] li").length === n, i + 1);
    }
    // The tier is turned on after the drop, so the card is written at once (before a drop the server has none).
    await H.page.getByRole("region", { name: "Context card" }).getByLabel("Context card (research tier)").click();
  },
  async "theatre-camera"(H) {
    await H.click("Surgery began");
    await H.click("Record pack opened");
    await H.waitText("Pack opened recorded.");
    await H.click("Start the swab camera");
    await H.click("Play the recorded theatre clip");
  },
  async "theatre-missing"(H) {
    const row = H.page.locator(".alert-card").filter({ hasText: MISSING });
    const frame = row.locator('img[alt="Last frame the camera saw it in"]');
    await frame.scrollIntoViewIfNeeded();
    await H.page.waitForFunction((img) => img.complete && img.naturalWidth > 0, await frame.elementHandle(), { timeout: 10000 })
      .catch(() => { throw new Error("The missing sponge's last frame did not load"); });
  },
  async "theatre-hard-stop"(H) {
    await H.fill("Closing count (returned)", "14");
    // The count gate itself: with no count a person saved, the API refuses to end surgery.
    const refused = await H.page.request.post(`${H.cgApi}/journey/episodes/${episodeId(H)}/surgery`, { data: { step: "ended", by: NURSE_THEATRE } });
    if (refused.status() !== 409) throw new Error(`Ending surgery before the count answered ${refused.status()}, not 409`);
  },
  async "theatre-reconcile"(H) {
    const row = H.page.locator(".alert-card").filter({ hasText: MISSING });
    await row.getByLabel("If you disagree, say why").fill(FOUND);
    await row.getByRole("button", { name: "Acknowledge", exact: true }).click();
    await H.fill("Closing count (returned)", "15");
    await H.click("Save count as Nurse Asha");
    await before(H, "theatre-reconcile");
    await H.click("Surgery ended");
    await H.click("Back to ward");
  },
  async "discharge-draft"(H) {
    await H.role("Doctor");
    await H.click("Draft discharge");
  },
  async "discharge-sign"(H) {
    H.marks.episode = episodeId(H);
    await before(H, "discharge-sign");
    await H.click("Sign discharge");
  },
  // After the signature, as spec §12 reads: the PDF is read back and must hold the drug log and the count.
  async "discharge-pdf"(H) {
    const base = `${CG}journey/episodes/${H.marks.episode}`;
    const got = await H.page.request.get(`${base}/discharge.pdf`);
    const body = await got.body();
    if (!got.ok() || body.subarray(0, 5).toString() !== "%PDF-") throw new Error(`The discharge PDF answered ${got.status()} without a PDF`);
    const text = pdfText(body);
    for (const want of BEATS.find((b) => b.id === "discharge-pdf").pdf) {
      if (!text.includes(want)) throw new Error(`The discharge PDF does not say "${want}"`);
    }
    const cal = await H.page.request.get(`${base}/follow-up.ics`);
    if (!cal.ok() || !(await cal.text()).includes("BEGIN:VCALENDAR")) throw new Error(`The follow-up answered ${cal.status()} without a calendar`);
  },
  async "discharge-home"(H) {
    await H.role("Nurse");
    await H.chart(PATIENT);
    await photo(H, "Discharge card given", "eval/media/discharge/discharge-card.png", "shows the discharge card");
    await photo(H, "Medicines handed over", "eval/media/medicine-bag/medicine-bag-synthetic.png", "shows a medicine bag");
    await before(H, "discharge-home");
    await H.tick(...DISCHARGE);
    await H.click("Complete discharge");
  },
  async close(H) {
    await H.role("Doctor");
    await H.tab("My patients");
  },
};
