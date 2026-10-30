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
export function journeySteps(state, visited = []) {
  const at = JOURNEY.findIndex((step) => step.states.includes(state));
  return JOURNEY.map((step, i) => {
    const seen = step.states.some((s) => visited.includes(s));
    if (i === at) {
      return { key: step.key, label: state === "clinic_done" ? "Visit closed" : step.label, status: "current", detail: STATE_LABEL[state] };
    }
    let status;
    if (i < at) status = step.key === "theatre" && !visited.includes("theatre") ? "skipped" : "done";
    else status = seen ? "done" : "later";
    return { key: step.key, label: step.label, status, detail: "" };
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

// Where the doctor's primary blocks render. The card holds them only while the doctor owns the step;
// on the ward they stay reachable below the quiet row when the nurse owns it (a dictated draft is never hidden).
export function doctorBlocks(state, card) {
  if (card.mine) return { inside: card.actions, below: [] };
  return { inside: [], below: state === "ward" ? ["theatre", "discharge"] : [] };
}

const QUIET = {
  clinic: [["orders", "Dictate orders"], ["photo", "Reference photo"]],
  ward: [["orders", "Dictate orders"], ["photo", "Wound photo"]],
  admitting: [["orders", "Dictate orders"]],
};

// Secondary doctor actions that sit in a quiet bar, never on the card.
export const quietActions = (state, role) => (role === "doctor" ? QUIET[state] || [] : []);

export function nextCard(view, role, { you = false } = {}) {
  const nn = view.now_next || {};
  const owner = nn.next_role ?? null;
  const mine = owner !== null && owner === role;
  return {
    owner,
    mine,
    eyebrow: mine ? "Next · for you" : owner ? `Next · for the ${owner}` : "Next",
    text: (you ? nn.you_next || nn.next : nn.next) || "Nothing queued",
    waiting: !owner || mine ? "" : `Waiting for the ${owner}.`,
    last: `Last: ${(you ? nn.you_now : nn.now) || "Nothing recorded"}`,
    actions: mine && !you ? cardActions(view.state, role, view) : [],
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
