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

export const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];
export const MAX_PHOTO_MB = 8;
export const MAX_PHOTOS = 6;
const ONE_OR_PHOTOS = "Send one video or 1 to 6 photos.";

// "" when what was picked can be sent, else the plain reason it cannot. One video, or 1 to 6 photos.
export function videoProblem(picked) {
  const files = Array.isArray(picked) ? picked : [picked];
  if (!files.length || files.some((f) => !f || ![...VIDEO_TYPES, ...PHOTO_TYPES].includes(f.type))) {
    return "Choose an MP4, MOV or WebM clip, or 1 to 6 JPEG, PNG or WebP photos.";
  }
  const videos = files.filter((f) => VIDEO_TYPES.includes(f.type));
  if (videos.length) {
    if (files.length > 1) return ONE_OR_PHOTOS;
    return videos[0].size > MAX_VIDEO_MB * 1024 * 1024 ? `The clip is larger than ${MAX_VIDEO_MB} MB.` : "";
  }
  if (files.length > MAX_PHOTOS) return ONE_OR_PHOTOS;
  return files.some((f) => f.size > MAX_PHOTO_MB * 1024 * 1024) ? `A photo is larger than ${MAX_PHOTO_MB} MB.` : "";
}

// What to hand to the upload: the video itself, or the list of photos.
export function toUpload(files) {
  return files.length === 1 && VIDEO_TYPES.includes(files[0].type) ? files[0] : files;
}

// An unknown match reads as "kept, not checked".
export function checkLabel(check) {
  if (!check) return "";
  const labels = CHECK_LABEL[check.check] || CHECK_LABEL.tray;
  if (check.match !== "ok" && check.match !== "mismatch" && check.media === "photos") return "Photos kept, not checked";
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

// Checks to list on a chart. The tray result stays off the patient's page and off the nurse's theatre
// screen, where her Tray check card already shows it.
// `onTaskLines` ids are checks already shown on a task line, so the list skips them.
export function shownChecks(checks, { hideTray = false, patient = false, onTaskLines = [] } = {}) {
  const noTray = hideTray || patient ? checks.filter((c) => c.check !== "tray") : checks;
  return noTray.filter((c) => !onTaskLines.includes(c.id));
}

// The ids of the set-up checks that the patient's task lines already show.
export function taskLineCheckIds(view) {
  return (view?.tasks || []).map((t) => t.video?.id).filter(Boolean);
}

// The patient's line for a task's set-up clip; the media (video or photos) comes from the check.
export function taskCheckLine(view, task) {
  if (!task?.video) return "";
  const media = (view?.video_checks || []).find((c) => c.id === task.video.id)?.media;
  return patientCheckLine({ check: "setup", match: task.video.match, media });
}

// The patient's line for a clip: what was seen, in plain words.
export function patientCheckLine(check) {
  const photos = check?.media === "photos";
  if (check?.match === "ok") return `Checked from ${photos ? "photos" : "a video"}: everything planned was seen.`;
  if (check?.match === "mismatch") return `Checked from ${photos ? "photos" : "a video"}: something planned was not seen; the nurse was told.`;
  return photos ? "Photos were kept; they were not checked." : "A video was kept; it was not checked.";
}
