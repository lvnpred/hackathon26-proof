import { findingPill } from "./finding.js";
import { SIGNED_IN } from "./people.js";
// Open alerts: which ones are safety alerts, who may answer, and how the strip and header name them.
export const SAFETY = ["obs_past_limit", "count_open"];

// "R. Kumar, 58 M (synthetic)" -> "Kumar"
export function surname(name) {
  return name.split(",")[0].trim().split(/\s+/).pop();
}

const ROLE_ORDER = ["nurse", "doctor", "patient"];

// On a chart keep that patient's pills; elsewhere each pill leads with the patient's surname.
// On a chart the banner owns every alert (a pill with nudgeKind), so the strip drops those.
// The role's own pills come first (mine); the rest fold into one group per other role.
// A pill with a role we do not know still shows, in a group named by that role.
export function stripPills(pills, episodeId, role) {
  const arrow = (p) => `${p.who} → ${p.what}`;
  const shown = episodeId
    ? pills.filter((p) => p.episodeId === episodeId && !p.nudgeKind).map((p) => ({ ...p, text: arrow(p) }))
    : pills.map((p) => ({ ...p, text: p.name ? `${surname(p.name)} · ${arrow(p)}` : arrow(p) }));
  const unknown = [...new Set(shown.map((p) => p.role))].filter((r) => !ROLE_ORDER.includes(r));
  const others = [...ROLE_ORDER, ...unknown].filter((r) => r !== role)
    .map((r) => ({ role: r, pills: shown.filter((p) => p.role === r) }))
    .filter((g) => g.pills.length)
    .map((g) => ({ ...g, text: `+${g.pills.length} for ${g.role}` }));
  return { mine: shown.filter((p) => p.role === role), others };
}

// A nudge reads in the patient's words for the patient and in staff words for staff; an older nudge has one wording.
export const nudgeText = (nudge, role) => (role === "patient" ? nudge.says : nudge.says_staff || nudge.says);

// Every open nudge: danger (safety kinds) before late, oldest first within each. The nurse, the addressee and the deep-linked line may answer. The patient sees only nudges addressed to the patient (R16).
export function bannerAlerts(view, role, line) {
  const items = (view?.nudges || []).filter((nudge) => role !== "patient" || nudge.to === "patient").map((nudge) => ({
    nudge,
    safety: SAFETY.includes(nudge.kind),
    canAnswer: role === "nurse" || nudge.to === role || nudge.id === line,
  }));
  const oldest = (a, b) => (a.nudge.at_ms ?? 0) - (b.nudge.at_ms ?? 0);
  return [...items.filter((i) => i.safety).sort(oldest), ...items.filter((i) => !i.safety).sort(oldest)];
}

const LIMIT_SENTENCE = /^(.+?) is (?:below|above) the limit of (\S+) set by (.+?)\.?$/;

// "Systolic BP 82 is below the limit of 90 set by Dr. A. Rao." -> headline "Systolic BP 82", limit "90", by "Dr. A. Rao".
// A nudge with another wording keeps its whole sentence as the headline and has no limit.
export function alertParts(text) {
  const m = LIMIT_SENTENCE.exec(text || "");
  return m ? { headline: m[1], limit: m[2], by: m[3] } : { headline: text || "", limit: null, by: null };
}

// The banner frame is red only while a safety alert is open; otherwise a neutral card.
export const bannerClass = (alerts) => `alert-banner${alerts.some((a) => a.safety) ? "" : " alert-calm"}`;

const OVERDUE = ["dose_overdue", "obs_overdue"];

// The pill of one alert, from its kind (spec 5.2): past a limit and swab missing are danger, overdue is "Late",
// anything else (a strip that differs, a sign ticked) is a check. The AI moment's own finding wins when the backend built one.
export function alertPill(nudge, moment, role) {
  if (moment) {
    const pill = findingPill(moment, role);
    if (pill.role === "danger" || pill.role === "check") return pill;
  }
  if (nudge.kind === "obs_past_limit") return { role: "danger", text: /\bbelow\b/.test(nudge.says_staff || nudge.says) ? "Below limit" : "Above limit" };
  if (nudge.kind === "count_open") return { role: "danger", text: "Swab unaccounted" };
  if (OVERDUE.includes(nudge.kind)) return { role: "check", text: "Late" };
  return { role: "check", text: "Check this" };
}

// Who signs a response: the viewer's signed-in person. The patient signs with their own name.
// The server takes any text of 1 to 80 characters here (SeenIn.by).
export function responder(role, patientName) {
  if (role === "patient") return (patientName || "Patient").slice(0, 80);
  const person = SIGNED_IN[role] || SIGNED_IN.nurse;
  return `${person.name} (synthetic)`;
}

// The footer line: staff see who it is assigned to; the patient sees plain words.
export function assignedText(nudge, role) {
  if (role === "patient") return nudge.to === "patient" ? "For you" : "With your care team";
  return `Assigned to ${SIGNED_IN[nudge.to]?.name || (nudge.to === "patient" ? "the patient" : nudge.to)}`;
}
