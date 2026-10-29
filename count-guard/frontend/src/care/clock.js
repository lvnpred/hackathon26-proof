// The demo clock. ts_ms 0 is Day 0, 09:00, the same zero the backend uses.
export const H = 3_600_000;
export const M = 60_000;

const DAY = 24 * H;
const START_MINUTES = 9 * 60;

// Stage times match backend/app/journey/play.py, so the live demo and /play agree.
export const STAGES = [
  { id: "clinic", label: "Clinic", atMs: 0 },
  { id: "strips", label: "Strips (evening)", atMs: 10 * H },
  { id: "admission", label: "Admission", atMs: 22 * H },
  { id: "theatre", label: "Theatre", atMs: 24 * H },
  { id: "ward", label: "Ward", atMs: 26 * H },
  { id: "ward-check", label: "Ward 18:30 check", atMs: 33 * H + 30 * M },
  { id: "home", label: "Home", atMs: 48 * H },
];

// Same text as backend clock() in app/journey/stories.py.
export function label(ms) {
  let day = Math.floor(ms / DAY);
  let minutes = START_MINUTES + Math.floor((ms - day * DAY) / M);
  day += Math.floor(minutes / (24 * 60));
  minutes %= 24 * 60;
  const pad = (n) => String(n).padStart(2, "0");
  return `Day ${day} ${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
}

export function stageOf(ms) {
  if (ms >= 48 * H) return "home";
  if (ms >= 26 * H) return "ward";
  if (ms >= 24 * H) return "theatre";
  return "clinic";
}

// A button only jumps forward: enabled when its time is after now.
export function jumpTargets(nowMs) {
  return STAGES.map((stage) => ({ ...stage, enabled: stage.atMs > nowMs }));
}

export function plusHour(ms) {
  return ms + H;
}

// Skip-ahead buttons. "Next due" is the earliest open task still in the future.
export function skipTargets(nowMs, patients) {
  const targets = [
    { id: "plus15", label: "+15 min", atMs: nowMs + 15 * M },
    { id: "plus60", label: "+1 h", atMs: nowMs + H },
  ];
  const dues = patients
    .flatMap((patient) => patient.view?.tasks || [])
    .filter((task) => task.status === "open" && task.due_ms != null && task.due_ms > nowMs)
    .map((task) => task.due_ms);
  if (dues.length) targets.push({ id: "next-due", label: "Next due", atMs: Math.min(...dues) });
  return targets;
}
