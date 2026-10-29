// The demo clock. ts_ms 0 is Day 0, 09:00, the same zero the backend uses.
export const H = 3_600_000;
export const M = 60_000;

const DAY = 24 * H;
const START_MINUTES = 9 * 60;

// Same text as backend clock() in app/journey/stories.py.
export function label(ms) {
  let day = Math.floor(ms / DAY);
  let minutes = START_MINUTES + Math.floor((ms - day * DAY) / M);
  day += Math.floor(minutes / (24 * 60));
  minutes %= 24 * 60;
  const pad = (n) => String(n).padStart(2, "0");
  return `Day ${day} ${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
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
