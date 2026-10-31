import { hhmm } from "./clock.js";
import { waitedText } from "./derive.js";
import { displayName } from "./names.js";

// The patient's thread: one item per thing the patient sent, with its status and answer. Pure.
const KIND_ORDER = ["checkin", "medicines", "photo", "doctor", "record"];
const OPENED_KEY = "cg-ask-opened:";

const signsText = (signs) => (signs?.length ? `; ${signs.join(", ")}` : "");

export function threadItems(view) {
  const ask = view?.ask || {};
  const questions = (ask.questions || []).map((q) => ({
    kind: q.to === "bot" ? "record" : "doctor", id: q.id, atMs: q.at_ms, said: q.text, answer: q.answer, raw: q,
    title: q.to === "bot" ? "Question to your record" : "Question to Dr. Rao",
  }));
  const photos = (ask.reviews || []).map((r) => ({ kind: "photo", id: r.id, atMs: r.at_ms, title: "Healing photo", said: r.note, answer: r.answer, raw: r }));
  const medicines = (ask.medicines || []).map((m) => ({ kind: "medicines", id: m.id, atMs: m.at_ms, title: "Medicines photo", said: "", answer: null, raw: m }));
  const checkins = (ask.checkins || []).map((c) => ({
    kind: "checkin", id: c.id, atMs: c.at_ms, title: `Check-in day ${c.day}`, said: `${c.feels}${signsText(c.signs)}`, answer: null, raw: c,
  }));
  return [...questions, ...photos, ...medicines, ...checkins]
    .sort((a, b) => b.atMs - a.atMs || KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind));
}

export function threadStatus(item, nowMs) {
  switch (item.kind) {
    case "doctor":
    case "photo":
      return item.answer ? `Answered ${hhmm(item.answer.at_ms)}` : `Waiting for Dr. Rao · ${waitedText(nowMs - item.atMs)}`;
    case "record":
      return item.answer?.found ? "Answered from your record" : "Not in your record";
    case "medicines":
      return "Checked against your prescription";
    default: {
      const seen = item.raw.seen || [];
      return seen.length ? `Seen by ${displayName(seen[0].by)}` : `Sent ${hhmm(item.atMs)} · not seen yet`;
    }
  }
}

// Today's confirmation of the newest check-in, derived from the record so it outlives the closed form.
export function checkinStatusLine(view, nowMs) {
  const newest = threadItems(view).find((i) => i.kind === "checkin");
  return newest ? `Day ${newest.raw.day} check-in recorded · ${threadStatus(newest, nowMs)}` : "";
}

const unreadDoctor = (view, since) =>
  (view?.ask?.questions || []).filter((q) => q.answer?.source === "doctor" && (since == null || q.answer.at_ms > since));
const unreadReviews = (view, since) =>
  (view?.ask?.reviews || []).filter((r) => r.answer && (since == null || r.answer.at_ms > since));

const unreadMarks = (view, since) =>
  (view?.ask?.medicines || []).flatMap((m) => m.marks || []).filter((k) => since == null || k.at_ms > since);

export const unreadCount = (view, since) => unreadDoctor(view, since).length + unreadReviews(view, since).length + unreadMarks(view, since).length;

export function unreadLine(view, since) {
  if (unreadDoctor(view, since).length) return "Dr. Rao answered your question";
  if (unreadReviews(view, since).length) return "Dr. Rao reviewed your healing photo";
  if (unreadMarks(view, since).length) return "Dr. Rao marked your medicines photo";
  return "";
}

export const unseenCheckins = (view, by) =>
  (view?.ask?.checkins || []).filter((c) => !(c.seen || []).some((s) => displayName(s.by) === displayName(by))).map((c) => c.id);

export function readOpened(episodeId) {
  try {
    const raw = localStorage.getItem(OPENED_KEY + episodeId);
    const ms = raw == null ? NaN : Number(raw);
    return Number.isFinite(ms) ? ms : null;
  } catch {
    return null;
  }
}

export function markOpened(episodeId, ms) {
  try {
    localStorage.setItem(OPENED_KEY + episodeId, String(ms));
  } catch {
    // Storage may be blocked; the unread dot then stays until the next open.
  }
}

// Where the AI sent the patient's question, read from view.ops.routes.
export function routedLine(view, questionId) {
  const to = view?.ops?.routes?.[questionId];
  return to ? `Your question went to ${displayName(to)}` : "";
}
