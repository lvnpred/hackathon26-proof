import { SAFETY, alertParts, alertPill, bannerAlerts, nudgeText } from "./alerts.js";
import { taskDue } from "./derive.js";
import { nextCard } from "./journey.js";
import { momentFor } from "./moments.js";
import { displayName } from "./names.js";
import { pausedRows } from "./handling.js";
import { countReconciled } from "./theatre.js";
import { whenText } from "./when.js";

// The Now rule (spec 5.1): one thing is Now. The rank decides, never the list order.
// 1 danger (an open safety alert), 2 blocked (a step waits on the viewer), 3 late, 4 due now, 5 review (AI work in its undo window), 6 nothing.
export const RANK = { danger: 1, blocked: 2, late: 3, due: 4, review: 5, nothing: 6 };

const OVERDUE = ["dose_overdue", "obs_overdue"];
const WARD_STAY = ["ward", "admitting"];
const NEEDS_YOU = { role: "wait", text: "Needs you" };

const item = (rank, kind, fields) => ({ rank, kind, since: null, detail: "", ...fields });

const dangerItems = (view, { role }) =>
  bannerAlerts(view, role, null)
    .filter((a) => a.safety && (a.canAnswer || (role === "doctor" && a.nudge.kind === "obs_past_limit")))
    .map(({ nudge }) => {
      const text = nudgeText(nudge, role);
      return item(RANK.danger, "alert", {
        title: alertParts(text).headline, detail: text, since: nudge.at_ms ?? null,
        pill: alertPill(nudge, momentFor(view, nudge.id), role), action: { kind: "alert", nudgeId: nudge.id },
      });
    });

// Other open nudges addressed to the viewer: an overdue one is late for staff; the patient never reads "late".
function nudgeItems(view, { role }) {
  return (view.nudges || []).filter((n) => n.to === role && !SAFETY.includes(n.kind)).map((nudge) => {
    const late = role !== "patient" && OVERDUE.includes(nudge.kind);
    const pill = role === "patient" ? { role: "check", text: "For you" } : alertPill(nudge, null, role);
    return item(late ? RANK.late : RANK.due, "alert", {
      title: nudgeText(nudge, role), since: nudge.at_ms ?? null, pill, action: { kind: "alert", nudgeId: nudge.id },
    });
  });
}

function blockedItems(view, { role }, nowMs) {
  const nn = view.now_next || {};
  const items = [];
  if (nn.next_role && nn.next_role === role) {
    const card = nextCard(view, role);
    items.push(item(RANK.blocked, "step", {
      title: role === "patient" ? displayName(nn.you_next) : card.text, since: -Infinity, pill: NEEDS_YOU,
      action: { kind: "step", keys: role === "patient" ? [] : card.actions },
    }));
  }
  if (role !== "nurse") return items;
  const count = view.count;
  if (view.state === "theatre" && count?.opened != null && !countReconciled(view)) {
    const saved = Boolean(String(count.closed_by || "").trim());
    items.push(item(RANK.blocked, "count", {
      title: saved ? "Swab count does not add up" : "Swab count not saved",
      detail: saved ? "Add the reason or correct the count." : `${count.opened} swabs opened. Save the closing count.`,
      since: count.opened_at_ms ?? null, pill: { role: "check", text: "Count open" }, action: { kind: "step", keys: ["theatre"] },
    }));
  }
  const fresh = WARD_STAY.includes(view.state) ? (view.order_list || []).filter((o) => !o.acknowledged_by) : [];
  if (fresh.length && pausedRows(view.ops, role).length) {
    items.push(item(RANK.blocked, "orders", {
      title: `New orders from ${displayName(fresh[0].by)}`, detail: "The AI is paused, so acknowledge them yourself.",
      since: fresh[0].at_ms ?? null, pill: NEEDS_YOU, action: { kind: "step", keys: ["ack"] },
    }));
  }
  return items;
}

function taskItems(view, { role }, nowMs) {
  if (role !== "nurse" || !WARD_STAY.includes(view.state)) return [];
  return (view.tasks || []).flatMap((task) => {
    const due = taskDue(task, nowMs, view.state);
    if (due !== "overdue" && due !== "due") return [];
    return [item(due === "overdue" ? RANK.late : RANK.due, "task", {
      title: task.title, detail: `Due ${whenText(task.due_ms, nowMs)}`, since: task.due_ms,
      pill: { role: "check", text: due === "overdue" ? "Late" : "Due now" }, action: { kind: "task", taskId: task.id },
    })];
  });
}

// Questions and photos waiting for the doctor; a handover waiting for a nurse.
function waitingItems(view, { role }) {
  if (role === "doctor") {
    const { questions = [], reviews = [] } = view.ask || {};
    return [
      ...questions.filter((q) => q.to === "doctor" && !q.answer).map((q) => ["Question from the patient", q.at_ms]),
      ...reviews.filter((r) => !r.answer).map((r) => ["Healing photo to review", r.at_ms]),
    ].map(([title, at]) => item(RANK.due, "ask", { title, since: at ?? null, pill: NEEDS_YOU }));
  }
  const { handover } = view;
  if (role !== "nurse" || !handover || handover.accepted_by) return [];
  return [item(RANK.due, "handover", { title: `Handover to ${displayName(handover.to_nurse)} not accepted`, pill: NEEDS_YOU })];
}

// AI work a person can still undo. Staff only.
function reviewItems(view, { role }, nowMs) {
  if (role === "patient") return [];
  return (view.ops?.handling || [])
    .filter((r) => r.status !== "undone" && r.undo_until_ms != null && r.undo_until_ms > nowMs)
    .map((r) => item(RANK.review, "review", {
      title: displayName(r.summary), detail: `You can undo this until ${whenText(r.undo_until_ms, nowMs)}.`,
      since: r.at_ms ?? null, pill: { role: "wait", text: "Review" }, action: { kind: "review", workId: r.work_id },
    }));
}

// Nothing waits on the viewer: say what comes next, from the backend's own text.
function nothingItem(view, { role }) {
  const nn = view.now_next || {};
  const owner = nn.next_role ?? null;
  const next = displayName(role === "patient" ? nn.you_next : nn.next) || "Nothing queued";
  return item(RANK.nothing, "nothing", {
    title: "Nothing needs you.", detail: `Next: ${next}`, owner,
    pill: owner && owner !== role ? { role: "wait", text: `Waiting for the ${owner}` } : { role: "fine", text: "All clear" },
  });
}

const age = (i) => (i.since == null ? Infinity : i.since);
const byRank = (a, b) => a.rank - b.rank || age(a) - age(b);

export function nowItems(view, viewer, nowMs) {
  if (!view) return [];
  return [
    ...dangerItems(view, viewer), ...blockedItems(view, viewer, nowMs), ...nudgeItems(view, viewer), ...taskItems(view, viewer, nowMs),
    ...waitingItems(view, viewer), ...reviewItems(view, viewer, nowMs),
  ].sort(byRank);
}

function shape(items, nothing) {
  return { now: items[0] || nothing, next: items.slice(1, 3), more: items.slice(3), rest: Math.max(0, items.length - 3) };
}

// view: one patient's journey view. viewer: { role, name }. Returns the one Now, the two after it, and how many more.
export function pickNow(view, viewer, nowMs) {
  return shape(nowItems(view, viewer, nowMs), nothingItem(view || {}, viewer));
}

// The nurse queue's Now across patients: same ranks, then the oldest first. patients: [{ id, bed, name, view }].
export function pickNowAcross(patients, viewer, nowMs) {
  const items = patients.flatMap((p) => nowItems(p.view, viewer, nowMs).map((i) => ({ ...i, patient: { episodeId: p.id, bed: p.bed, name: p.name } })));
  return shape(items.sort(byRank), nothingItem(patients[0]?.view || {}, viewer));
}

const lowerFirst = (text) => text.charAt(0).toLowerCase() + text.slice(1);

// What each staff step is, in the patient's words, after "{who} will".
const STEP_WORDS = {
  clinic: ["The doctor", "admit you or close the visit"],
  admitting: ["The nurse", "complete your admission"],
  ward: ["The doctor", "send you to theatre or sign your discharge"],
  theatre: ["The nurse", "record the surgery and the count, then return you to the ward"],
  discharging: ["The nurse", "complete your discharge"],
};

// The patient's one line (Today, My care): what they must do, who acts next, or that nothing is needed.
export function nextUp(view) {
  const nn = view?.now_next || {};
  const owner = nn.next_role ?? null;
  const said = displayName(nn.you_next);
  if (owner === "patient") return { kind: "you", text: `You need to: ${lowerFirst(said)}` };
  const wait = /^The doctor (reviews|answers) (.+?)\.?$/.exec(said);
  if (wait) return { kind: "who", text: `The doctor will ${wait[1].slice(0, -1)} ${wait[2]}.` };
  const seen = /^Dr\. Rao has not seen your (.+?)\.?$/.exec(said);
  if (seen) return { kind: "who", text: `Dr. Rao will look at your ${seen[1].replace(/ yet$/, "")}.` };
  const step = owner && STEP_WORDS[view.state];
  if (step) return { kind: "who", text: `${step[0]} will ${step[1]}.` };
  return { kind: "none", text: "You don't need to do anything now." };
}
