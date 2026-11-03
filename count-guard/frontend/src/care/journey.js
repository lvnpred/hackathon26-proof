import { STATE_LABEL } from "./derive.js";

// Which timeline types each lens keeps. "everyone" has no entry: the chart shows the audit rows instead.
export const LENSES = {
  nurse: ["count.", "dose.", "obs.", "handover.", "nudge.", "patient.state", "order.", "task.", "surgery.", "discharge."],
  doctor: ["rx.", "ward.orders", "discharge.", "druglog.", "patient.state", "order.", "task.", "surgery."],
  patient: ["brownbag.", "reminders.", "checkin.", "help.", "patient.state", "order.signed", "task.done", "surgery.", "discharge."],
};

export const JOURNEY = [
  { key: "clinic", label: "Clinic", states: ["clinic", "clinic_done"] },
  { key: "admitted", label: "Admitted", states: ["admitting"] },
  { key: "ward", label: "Ward", states: ["ward"] },
  { key: "theatre", label: "Theatre", states: ["theatre"] },
  { key: "discharge", label: "Discharge", states: ["discharging"] },
  { key: "home", label: "Home", states: ["home"] },
];

// Where the patient has been: done, current, later, or skipped (theatre never visited once past it).
// Back on the ward after theatre, the Ward segment says so; Theatre does not tick ahead of the current step.
export function journeySteps(state, visited = []) {
  const at = JOURNEY.findIndex((step) => step.states.includes(state));
  return JOURNEY.map((step, i) => {
    if (i === at) {
      if (state === "ward" && visited.includes("theatre")) return { key: step.key, label: "Ward · back from theatre", status: "current", detail: "" };
      const label = state === "clinic_done" ? "Visit closed" : step.label;
      const detail = STATE_LABEL[state];
      return { key: step.key, label, status: "current", detail: detail === label ? "" : detail };
    }
    if (i > at) return { key: step.key, label: step.label, status: "later", detail: "" };
    if (step.key === "theatre" && !visited.includes("theatre")) return { key: step.key, label: step.label, status: "skipped", detail: "Skipped" };
    return { key: step.key, label: step.label, status: "done", detail: "" };
  });
}

const hasFreshOrders = (view) => (view?.order_list || []).some((order) => !order.acknowledged_by);

// The buttons the next-step card shows to the person who owns the step.
export function cardActions(state, role, view) {
  if (role === "doctor") {
    if (state === "clinic") return ["admit"];
    if (state === "ward") return ["theatre", "discharge"];
  }
  if (role === "nurse") {
    if (state === "admitting") return hasFreshOrders(view) ? ["ack", "admission"] : ["admission"];
    if (state === "ward") return ["ack"];
    if (state === "theatre") return ["theatre"];
    if (state === "discharging") return ["discharge"];
  }
  return [];
}

// Where the doctor's primary blocks render. The card holds them only while the doctor owns the step; every other
// block sits below the quiet row in every state, open or saying when it opens (clarity §4.4).
const DOCTOR_BLOCKS = ["admit", "theatre", "discharge"];
export function doctorBlocks(state, card) {
  const inside = card.mine ? card.actions : [];
  return { inside, below: DOCTOR_BLOCKS.filter((key) => !inside.includes(key)) };
}

// Secondary doctor actions that sit in a quiet bar, never on the card. Both are there in every state; a panel that
// cannot run now says why when opened.
export const quietActions = (state, role) =>
  role === "doctor" ? [["orders", "Dictate orders"], ["photo", state === "ward" ? "Wound photo" : "Reference photo"]] : [];

const titled = (word) => word.charAt(0).toUpperCase() + word.slice(1);

// The step the backend names as next, for one staff role: who owns it and the buttons that do it.
export function nextCard(view, role) {
  const nn = view.now_next || {};
  const owner = nn.next_role ?? null;
  const mine = owner !== null && owner === role;
  return {
    owner,
    mine,
    eyebrow: mine ? "Now · for you" : owner ? `Now · ${titled(owner)}` : "Now",
    text: (mine ? nn.next_mine || nn.next : nn.next) || "Nothing queued",
    last: `Last: ${nn.now || "Nothing recorded"}`,
    actions: mine ? cardActions(view.state, role, view) : [],
  };
}

// A line a lens filters out still shows when the nudge is for the current role or is the deep-linked line.
export function lensLines(lines, nudges, lens, role, line) {
  const open = Object.fromEntries(nudges.map((nudge) => [nudge.id, nudge]));
  const prefixes = LENSES[lens] || [];
  return lines.filter((item) => {
    if (lens === "patient" && item.patient === "") return false; // staff-only wording
    const nudge = open[item.id];
    if (nudge && (nudge.to === role || nudge.id === line)) return true;
    return prefixes.some((prefix) => item.type.startsWith(prefix));
  });
}

export function foldLines(lines, open, keep = 3) {
  if (open) return { lines, more: 0 };
  return { lines: lines.slice(-keep), more: Math.max(0, lines.length - keep) };
}

export const foldOpensFor = (lines, line) => Boolean(line) && !lines.slice(-3).some((item) => item.id === line);
