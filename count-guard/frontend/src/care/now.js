import { WARD_NAME } from "./dock.js";
import { SAFETY, alertParts, alertPill, bannerAlerts, nudgeText } from "./alerts.js";
import { taskDue } from "./derive.js";
import { nextCard } from "./journey.js";
import { momentFor } from "./moments.js";
import { displayName } from "./names.js";
import { pausedRows } from "./handling.js";
import { RANK } from "./rank.js";
import { countReconciled } from "./theatre.js";
import { whenText } from "./when.js";

// The Now rule (spec 5.1): one thing is Now. The rank decides, never the list order. Ranks live in rank.js.
export { RANK };

const OVERDUE = ["dose_overdue", "obs_overdue"];
const WARD_STAY = ["ward", "admitting"];
const NEEDS_YOU = { role: "wait", text: "Needs you" };

const item = (rank, kind, fields) => ({ rank, kind, since: null, detail: "", ...fields });

const dangerItems = (view, { role }) =>
  bannerAlerts(view, role, null)
    .filter((a) => a.safety && (a.canAnswer || (role === "doctor" && a.nudge.kind === "obs_past_limit")))
    .map(({ nudge, canAnswer }) => {
      const text = nudgeText(nudge, role);
      return item(RANK.danger, "alert", {
        title: alertParts(text).headline, detail: text, since: nudge.at_ms ?? null,
        pill: alertPill(nudge, momentFor(view, nudge.id), role), action: canAnswer ? { kind: "alert", nudgeId: nudge.id } : null,
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

function blockedItems(view, { role }) {
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
    ].map(([title, at]) => item(RANK.due, "ask", { title, since: at ?? null, pill: NEEDS_YOU, action: { kind: "focus", label: "Open ask inbox", selector: '[aria-label="Ask inbox"]' } }));
  }
  const { handover } = view;
  if (role !== "nurse" || !handover || handover.accepted_by) return [];
  return [item(RANK.due, "handover", { title: `Handover to ${displayName(handover.to_nurse)} not accepted`, pill: NEEDS_YOU, action: { kind: "focus", label: "Open handover", selector: '[aria-label="Shift handover"]' } })];
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
    ...dangerItems(view, viewer), ...blockedItems(view, viewer), ...nudgeItems(view, viewer), ...taskItems(view, viewer, nowMs),
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
  const none = item(RANK.nothing, "nothing", { title: "Nothing needs you.", pill: { role: "fine", text: "All clear" } });
  return shape(items.sort(byRank), none);
}

const lowerFirst = (text) => text.charAt(0).toLowerCase() + text.slice(1);

// The patient's one line (Today, My care): what they must do, who acts next, or that nothing is needed.
// One rule: the backend's next owner and its second-person sentence ("The nurse acknowledges the new orders.")
// read as "The nurse will acknowledge the new orders." The backend owns who and what; this only changes the tense.
export function nextUp(view) {
  const nn = view?.now_next || {};
  const owner = nn.next_role ?? null;
  const said = displayName(nn.you_next);
  if (owner === "patient" && said) return { kind: "you", text: `You need to: ${lowerFirst(said)}` };
  const staff = /^(The doctor|The nurse) (\w+?)s (.+?)\.?$/.exec(said);
  if (owner && owner !== "patient" && staff) {
    const rest = staff[3].replace(/ (or|then) (\w+?)s /g, " $1 $2 ");
    return { kind: "who", text: `${staff[1]} will ${staff[2]} ${rest}.` };
  }
  const seen = /^Dr\. Rao has not seen your (.+?)\.?$/.exec(said);
  if (owner && seen) return { kind: "who", text: `Dr. Rao will look at your ${seen[1].replace(/ yet$/, "")}.` };
  return { kind: "none", text: "You don't need to do anything now." };
}

// The alert that Now holds. The chart's alert list leaves it out, so its controls exist once on the screen.
export const movedAlertId = (pick, role) => (role !== "patient" && pick.now.action?.kind === "alert" ? pick.now.action.nudgeId : null);

// The doctor's clinic step names the patient and the ward in its heading; the buttons keep their short names.
export function withAdmitHeading(pick, view, role, patientName) {
  if (role !== "doctor" || view?.state !== "clinic" || pick.now.action?.kind !== "step" || !patientName) return pick;
  return { ...pick, now: { ...pick.now, title: `Admit ${patientName} to ${WARD_NAME}, or close the visit` } };
}
