// Selectors named in the beat table. No playwright-core import, so tests can load this.
import { resolve } from "node:path";

const collapse = (s) => s.replace(/\s+/g, " ");

// root: the element whose text counts. Count Guard's is .app; Doctor Dictation has no app root, so its is body.
export async function waitText(page, s, ms = 10000, root = ".app") {
  await page.waitForFunction(
    ([want, sel]) => (document.querySelector(sel)?.innerText || "").replace(/\s+/g, " ").includes(want),
    [s, root],
    { timeout: ms },
  ).catch(() => { throw new Error(`Text never appeared: "${s}"`); });
}

export async function waitGone(page, regexSource, ms = 3000, root = ".app") {
  await page.waitForFunction(
    ([src, sel]) => !new RegExp(src).test((document.querySelector(sel)?.innerText || "").replace(/\s+/g, " ")),
    [regexSource, root],
    { timeout: ms },
  ).catch(() => { throw new Error(`Text that must be absent is on screen: /${regexSource}/`); });
}

export function helpers(page, root) {
  const nav = page.getByRole("navigation", { name: "Main" });
  const region = (scope) => page.getByRole("region", { name: scope, exact: true });
  return {
    page,
    root,
    role: (name) => page.getByRole("group", { name: "Role" }).getByRole("button", { name, exact: true }).click(),
    // Staff open a chart through the Patients tab ("My patients" for the doctor).
    async chart(who) {
      await nav.getByRole("link", { name: /^(My )?patients$/i }).click();
      await page.locator(".patient-list a").filter({ hasText: who }).first().click();
      await page.locator("h1", { hasText: who }).waitFor();
    },
    async pick(prefix) {
      const value = await page.getByLabel("Patient", { exact: true }).locator("option").filter({ hasText: prefix }).first().getAttribute("value");
      await page.getByLabel("Patient", { exact: true }).selectOption(value);
      await page.locator("h1", { hasText: prefix }).waitFor();
    },
    dockLink: (name) => page.getByRole("region", { name: "Demo" }).getByRole("link", { name, exact: true }).click(),
    tab: (name) => nav.getByRole("link", { name, exact: true }).click(),
    click: (name, scope) => (scope ? region(scope) : page).getByRole("button", { name, exact: true }).first().click(),
    // Open a quiet-row or card panel; leaves it open if it already is.
    async open(name) {
      const button = page.getByRole("button", { name, exact: true }).first();
      if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
    },
    // Open a closed Fold by its label; leaves it open if it already is.
    async unfold(label) {
      const button = page.getByRole("button", { name: `Show ${label}`, exact: true });
      if (await button.count()) await button.first().click();
    },
    clock: (name) => page.getByRole("group", { name: "Demo clock" }).getByRole("button", { name, exact: true }).click(),
    tick: async (...labels) => { for (const l of labels) await page.getByLabel(l, { exact: true }).check(); },
    fill: (label, value, scope) => (scope ? region(scope) : page).getByLabel(label).first().fill(value),
    // scope is a section name, else a field label.
    async file(scope, relPath) {
      const abs = resolve(root, relPath);
      const box = region(scope);
      const isSection = await box.first().waitFor({ timeout: 4000 }).then(() => true, () => false);
      if (isSection) await box.locator("input[type=file]").first().setInputFiles(abs);
      else await page.getByLabel(scope, { exact: true }).setInputFiles(abs);
    },
    // A task row's mic, its audio upload and its text box. rowText picks the row.
    say: (rowText) => page.locator("li.task-row").filter({ hasText: rowText }).getByRole("button", { name: /^Say it: / }).click(),
    sayFile: (rowText, rel) => page.locator("li.task-row").filter({ hasText: rowText }).locator('input[type=file][accept="audio/*"]').setInputFiles(resolve(root, rel)),
    sayText: (rowText, text) => page.locator("li.task-row").filter({ hasText: rowText }).getByLabel("What was said").fill(text),
    text: async () => collapse(await page.locator(".app").innerText()),
    waitText: (s, ms, on = page, textRoot = ".app") => waitText(on, s, ms, textRoot),
  };
}
