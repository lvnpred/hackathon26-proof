import { correctionLine } from "./capture.js";
import { hhmm } from "./clock.js";
import { displayName } from "./names.js";
import { checkLabel } from "./video.js";

// The four theatre steps as the doctor sees them: one line each, read from this theatre stay only.
export function theatreSteps(view) {
  const lines = view.timeline || [];
  let since = 0;
  lines.forEach((line, i) => { if (line.type === "patient.state") since = i + 1; });
  const stay = lines.slice(since);
  const last = (type) => stay.filter((line) => line.type === type).pop() || null;
  const tray = view.tray?.latest || null;
  const began = last("surgery.began");
  const opened = last("count.pack_opened");
  const closing = last("count.closing");
  const ended = last("surgery.ended");
  const clock = (line) => (line ? line.when.slice(-5) : "");
  const noTray = !view.tray?.planned;
  return [
    noTray
      ? { key: "tray", title: "Tray check", done: true, says: "No tray planned", at: "", open: false }
      : { key: "tray", title: "Tray check", done: Boolean(tray), says: tray ? checkLabel(tray) : "Not checked yet", at: tray?.at_ms != null ? hhmm(tray.at_ms) : "", open: false },
    { key: "began", title: "Surgery began", done: Boolean(began), says: began ? `Began ${began.when}` : "Not yet", at: clock(began), open: false },
    {
      key: "count",
      title: "Swab count",
      done: Boolean(closing),
      says: closing ? closing.plain : opened ? "Pack opened; closing count not recorded yet" : "Not started",
      at: clock(closing),
      // "Read 14, saved 15 by Nurse Asha": stays on the folded line so the corrected camera count is still visible.
      correction: closing ? correctionLine(view.count?.read, view.count?.saved, view.count?.closed_by) : "",
      open: (view.count?.missing ?? 0) > 0,
    },
    { key: "ended", title: "Surgery ended", done: Boolean(ended), says: ended ? `Ended ${ended.when}` : "Not yet", at: clock(ended), open: false },
  ];
}

const WAIT = { began: "after the tray check", count: "after surgery began", ended: "after surgery began" };

// Where each step stands: done, open (a count with swabs missing), current (the next to do) or later.
export function checklistState(steps) {
  let current = false;
  return steps.map((step) => {
    if (step.done) return { ...step, status: step.open ? "open" : "done", wait: "" };
    if (!current) {
      current = true;
      return { ...step, status: "current", wait: "" };
    }
    return { ...step, status: "later", wait: WAIT[step.key] || "" };
  });
}

// The three swab numbers; "–" until a figure exists.
export function swabFigures(count) {
  const figure = (value) => (value == null ? "–" : value);
  const missing = count?.missing;
  return {
    opened: figure(count?.opened),
    back: figure(count?.returned),
    missing: figure(missing),
    tone: missing == null ? "" : missing > 0 ? "red" : "green",
  };
}

export function packLine(count) {
  if (count?.opened == null) return "";
  return `Pack opened ${hhmm(count.opened_at_ms)} by ${displayName(count.opened_by)}`;
}

// Which controls a step offers, by the backend's rules and not by list order: the tray can be
// (re)checked until surgery begins, surgery ends once it began, the count needs nothing before it.
export function canRecord(view, key) {
  const done = Object.fromEntries(checklistState(theatreSteps(view)).map((step) => [step.key, step]));
  switch (key) {
    case "tray": return Boolean(view.tray?.planned) && !done.began.done;
    case "began": return !done.began.done;
    case "count": return !done.count.done || done.count.open;
    case "ended": return done.began.done && !done.ended.done;
    default: return false;
  }
}
