// Open alerts: which ones are safety alerts, who may answer, and how the strip and header name them.
export const SAFETY = ["obs_past_limit", "count_open"];
const WHO = { nurse: "the nurse", doctor: "the doctor", patient: "the patient" };

// "R. Kumar, 58 M (synthetic)" -> "Kumar"
export function surname(name) {
  return name.split(",")[0].trim().split(/\s+/).pop();
}

// On a chart keep that patient's pills; elsewhere each pill leads with the patient's surname.
// On a chart the banner owns every alert (a pill with nudgeKind), so the strip drops those.
export function stripPills(pills, episodeId) {
  const arrow = (p) => `${p.who} → ${p.what}`;
  if (episodeId) return pills.filter((p) => p.episodeId === episodeId && !p.nudgeKind).map((p) => ({ ...p, text: arrow(p) }));
  return pills.map((p) => ({ ...p, text: p.name ? `${surname(p.name)} · ${arrow(p)}` : arrow(p) }));
}

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
