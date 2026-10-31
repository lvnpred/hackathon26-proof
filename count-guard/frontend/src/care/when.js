// Clock times for the product. ts_ms 0 is 09:00 on the demo's first day, Monday 2 Nov 2026.
// Same rules as backend app/journey/clocktext.py when_text. "Day N" belongs only to the demo dock (clock.js label).
import { H, M } from "./clock.js";

export const DAY0 = "2026-11-02";
const DAY = 24 * H;
const START_MINUTES = 9 * 60;
const DAY0_UTC = Date.parse(`${DAY0}T00:00:00Z`);
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function parts(ms) {
  let day = Math.floor(ms / DAY);
  let minutes = START_MINUTES + Math.floor((ms - day * DAY) / M);
  day += Math.floor(minutes / (24 * 60));
  minutes %= 24 * 60;
  return { day, minutes };
}

// "09:14" on the same demo day as nowMs, "Yesterday 09:14" the day before, else "Wed 4 Nov, 09:14".
// A null or undefined nowMs always gives the full date.
export function whenText(tsMs, nowMs) {
  const { day, minutes } = parts(tsMs);
  const pad = (n) => String(n).padStart(2, "0");
  const time = `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
  if (nowMs != null) {
    const today = parts(nowMs).day;
    if (day === today) return time;
    if (day === today - 1) return `Yesterday ${time}`;
  }
  const date = new Date(DAY0_UTC + day * DAY);
  return `${WEEKDAYS[date.getUTCDay()]} ${date.getUTCDate()} ${MONTHS[date.getUTCMonth()]}, ${time}`;
}
