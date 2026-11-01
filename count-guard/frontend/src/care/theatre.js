import { hhmm } from "./clock.js";
import { displayName } from "./names.js";
import { checkLabel } from "./video.js";

// The five theatre steps as the doctor sees them: one line each, read from this theatre stay only.
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
      open: (view.count?.missing ?? 0) > 0,
    },
    { key: "ended", title: "Surgery ended", done: Boolean(ended), says: ended ? `Ended ${ended.when}` : "Not yet", at: clock(ended), open: false },
    { key: "ward", title: "Back to ward", done: false, says: "Not yet", at: "", open: false },
  ];
}

// A step that cannot start yet just says "Locked"; what unlocks it is stated beside the control.
const WAIT = { began: "Locked", count: "Locked", ended: "Locked", ward: "Locked" };

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

// What the camera read, before or after the save: the live camera count, else the figure the saved closing read.
export function cameraRead(count) {
  if (count?.camera) return count.camera.count;
  if (count?.read?.returned != null) return count.read.returned;
  return count?.closed_via === "camera" ? count.returned : null;
}

// The server's reason rule at save: unaccounted is not 0, or Back is not the camera read. A correction has no live
// camera, but the server still checks against the superseded closing's read, so this uses cameraRead too.
export function reasonNeeded(count, back) {
  const camera = count?.camera?.count ?? cameraRead(count);
  const unaccounted = count?.opened != null ? count.opened - back : null;
  return (unaccounted !== null && unaccounted !== 0) || (camera != null && back !== camera);
}

// The saved line: who saved the count, when, what the camera read and what the team did.
export function savedLine(count) {
  if (!count?.closed_by) return "";
  const read = count.camera ? null : cameraRead(count);
  return ["Saved by " + displayName(count.closed_by), count.closed_at_ms != null && hhmm(count.closed_at_ms),
    read != null && `camera read ${read}`, (count.closed_detail || "").trim()].filter(Boolean).join(" · ");
}

// The server's swab-count rule (states.count_gate), read from this stay's count in the view: a closing a person
// saved (not the AI) after surgery began, with the stay's opened sum - returned recomputed to 0 or a non-empty
// reason. The server stays the authority.
export function countReconciled(view) {
  const count = view?.count;
  const by = String(count?.closed_by || "").trim();
  if (!by || by.startsWith("AI (on behalf of") || count.closed_after_began !== true) return false;
  const { opened, returned } = count;
  const addsUp = Number.isInteger(opened) && Number.isInteger(returned) && opened - returned === 0;
  return addsUp || Boolean(String(count.closed_detail || "").trim());
}

// Which controls a step offers, by the backend's rules and not by list order: the tray can be
// (re)checked until surgery begins, surgery ends once it began, the count is taken once surgery began.
export function canRecord(view, key) {
  const done = Object.fromEntries(checklistState(theatreSteps(view)).map((step) => [step.key, step]));
  switch (key) {
    case "tray": return Boolean(view.tray?.planned) && !done.began.done;
    case "began": return !done.began.done;
    case "count": return done.began.done && (!done.count.done || done.count.open);
    case "ended": return done.began.done && !done.ended.done && countReconciled(view);
    case "ward": return done.ended.done;
    default: return false;
  }
}
