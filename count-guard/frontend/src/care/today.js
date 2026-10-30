// Words and fold order for the patient's Today page. Pure, so node can test them.
import { displayName, shortName } from "./names.js";
import { doctorQuestions } from "./askText.js";
import { H } from "./clock.js";

const DAY = 24 * H;

export const greeting = (name) => `Hi, ${shortName(name)}`;

const WHERE = {
  clinic: "You are in clinic",
  clinic_done: "Your clinic visit is closed",
  admitting: "You are being admitted",
  ward: "You are on the ward",
  theatre: "You are in theatre",
  discharging: "You are getting ready to go home",
};

// R18: day N is the demo-clock day; day 0 has no day.
export function whereWords(state, nowMs) {
  if (state !== "home") return WHERE[state] || "";
  const day = Math.floor(nowMs / DAY);
  return day >= 1 ? `You are home · day ${day}` : "You are home";
}

const lowerFirst = (text) => text.charAt(0).toLowerCase() + text.slice(1);

// R19: the discharge review is next when the server has no further step.
export function nextWords(view) {
  const next = view?.now_next?.you_next || "";
  const review = view?.card?.review;
  const text = next.includes("No further steps.") && review ? review : next;
  return `Next: ${lowerFirst(displayName(text))}`;
}

// R17: an empty My medicines goes last.
export function todayFolds(view) {
  const answered = doctorQuestions(view).filter((q) => q.answer).length;
  const medicines = { key: "medicines", title: "My medicines" };
  const rest = [
    { key: "card", title: "My discharge card" },
    { key: "strips", title: "Check my strips" },
    { key: "ask", title: `Ask Dr. Rao (${answered} answered)` },
  ];
  return (view?.schedule || []).length === 0 ? [...rest, medicines] : [rest[0], medicines, ...rest.slice(1)];
}
