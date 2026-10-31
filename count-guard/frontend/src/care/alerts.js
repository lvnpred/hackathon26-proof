// Open alerts: which ones are safety alerts, who may answer, and how the strip and header name them.
export const SAFETY = ["obs_past_limit", "count_open"];
const WHO = { nurse: "the nurse", doctor: "the doctor", patient: "the patient" };

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

// The newest open safety nudge, as the NOW line.
export function alertNow(view) {
  const safety = (view?.nudges || []).filter((n) => SAFETY.includes(n.kind));
  if (!safety.length) return null;
  const latest = safety.reduce((a, b) => (b.at_ms >= a.at_ms ? b : a));
  return `Waiting for ${WHO[latest.to] || latest.to}'s answer: ${latest.says}`;
}

// Every open nudge, safety first. The nurse, the addressee and the deep-linked line may answer.
export function bannerAlerts(view, role, line) {
  const items = (view?.nudges || []).map((nudge) => ({
    nudge,
    safety: SAFETY.includes(nudge.kind),
    canAnswer: role === "nurse" || nudge.to === role || nudge.id === line,
  }));
  return [...items.filter((i) => i.safety), ...items.filter((i) => !i.safety)];
}

// The banner frame is red only while a safety alert is open; otherwise a neutral card.
export const bannerClass = (alerts) => `alert-banner${alerts.some((a) => a.safety) ? "" : " alert-calm"}`;
