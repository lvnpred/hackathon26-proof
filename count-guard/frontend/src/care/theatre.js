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
  return [
    { title: "Tray check", done: Boolean(tray), says: tray ? checkLabel(tray) : "Not checked yet" },
    { title: "Surgery began", done: Boolean(began), says: began ? `Began ${began.when}` : "Not yet" },
    {
      title: "Swab count",
      done: Boolean(closing),
      says: closing ? closing.plain : opened ? "Pack opened; closing count not recorded yet" : "Not started",
    },
    { title: "Surgery ended", done: Boolean(ended), says: ended ? `Ended ${ended.when}` : "Not yet" },
  ];
}
