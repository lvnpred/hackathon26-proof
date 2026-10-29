export const VIDEO_TYPES = ["video/mp4", "video/quicktime", "video/webm"];
export const MAX_VIDEO_MB = 50;

export const CHECK_LABEL = {
  tray: {
    ok: "Tray matches the plan",
    mismatch: "Flagged: not everything planned was seen. The surgeon decides.",
    none: "Clip kept, not checked",
  },
  setup: {
    ok: "Set-up matches the list",
    mismatch: "Flagged: not everything on the list was seen. The nurse decides.",
    none: "Clip kept, not checked",
  },
};

// "" when the clip can be sent, else the plain reason it cannot.
export function videoProblem(file) {
  if (!file || !VIDEO_TYPES.includes(file.type)) return "Choose an MP4, MOV or WebM clip.";
  if (file.size > MAX_VIDEO_MB * 1024 * 1024) return `The clip is larger than ${MAX_VIDEO_MB} MB.`;
  return "";
}

// An unknown match reads as "kept, not checked".
export function checkLabel(check) {
  if (!check) return "";
  const labels = CHECK_LABEL[check.check] || CHECK_LABEL.tray;
  return labels[check.match] || labels.none;
}

export function latestCheck(view, kind, taskId = null) {
  const found = (view?.video_checks || []).filter((c) => c.check === kind && (kind !== "setup" || c.task_id === taskId));
  return found.length ? found[found.length - 1] : null;
}

// The surgeon's flag: only a mismatch on the latest tray check. It never blocks anything.
export function trayFlag(view) {
  const latest = view?.tray?.latest;
  if (latest?.match !== "mismatch") return null;
  return `${CHECK_LABEL.tray.mismatch} ${latest.why || ""}`.trim();
}

export function swabTotal(view) {
  const total = view?.tray?.planned?.swab_total;
  return Number.isInteger(total) && total > 0 ? total : null;
}

export function taskVideoLabel(task) {
  return task?.video ? checkLabel({ check: "setup", match: task.video.match }) : "";
}
