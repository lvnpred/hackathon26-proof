// Words for the demo dock and the alerts pill. Pure, so node can test them.
export const ROLE_NAME = { doctor: "Doctor", nurse: "Nurse", patient: "Patient" };

// live: true (a key is set), false (prepared results), null (the server has not answered).
export function modelsText(live) {
  if (live === null) return "";
  return `models: ${live ? "live" : "offline (prepared)"}`;
}

export const alertsLabel = (n) => (n === 0 ? "" : n === 1 ? "1 alert" : `${n} alerts`);

// Open alerts the bar counts: the role's own pills plus every grouped pill. The patient has none.
export const alertCount = ({ mine, others }, role) =>
  role === "patient" ? 0 : mine.length + others.reduce((n, g) => n + g.pills.length, 0);

// The dock's AI chip. paused: true, false, or null (the server has not answered).
// Same words in the header and the dock.
export const aiChip = (paused) => (paused == null ? "" : `AI admin: ${paused ? "paused" : "on"}`);
export const pauseLabel = (paused) => (paused ? "Resume" : "Pause");
// The dock's copy of the control gets its own name, so the header's Pause/Resume stays the one button by that name.
export const dockPauseLabel = (paused) => `${pauseLabel(paused)} AI (demo shortcut)`;

export const WARD_NAME = "Ward 4";

// The ward-wide banner. A missing time or name leaves that part out.
export function pausedText(by, atPhrase) {
  return `AI admin is paused for ${WARD_NAME}. Paused by ${by || "a person"}${atPhrase ? ` ${atPhrase}` : ""}. New orders and tasks wait for a person.`;
}
