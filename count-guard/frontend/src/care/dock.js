// Words for the demo dock and the alerts pill. Pure, so node can test them.
import { hhmm } from "./clock.js";

export const ROLE_NAME = { doctor: "Doctor", nurse: "Nurse", patient: "Patient" };

// The one line the dock folds to on a phone.
export const dockSummary = (role, nowMs) => `DEMO · ${ROLE_NAME[role]} · ${hhmm(nowMs)}`;

// live: true (a key is set), false (prepared results), null (the server has not answered).
export function modelsText(live) {
  if (live === null) return "Synthetic data";
  return `Synthetic data · models: ${live ? "live" : "offline (prepared)"}`;
}

export const alertsLabel = (n) => (n === 0 ? "" : n === 1 ? "1 alert" : `${n} alerts`);

// Open alerts the bar counts: the role's own pills plus every grouped pill. The patient has none.
export const alertCount = ({ mine, others }, role) =>
  role === "patient" ? 0 : mine.length + others.reduce((n, g) => n + g.pills.length, 0);
