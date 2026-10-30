import assert from "node:assert/strict";
import test from "node:test";
import { CHECK_LABEL, checkLabel, latestCheck, patientCheckLine, shownChecks, swabTotal, taskVideoLabel, toUpload, trayFlag, videoProblem } from "./video.js";

const ADVICE = /\b(give|take|stop|increase|reduce|start|administer|consider)\b/i;
const file = (type, mb) => ({ type, size: mb * 1024 * 1024 });

test("videoProblem accepts MP4, MOV and WebM within 50 MB", () => {
  assert.equal(videoProblem(file("video/quicktime", 10)), "");
  assert.equal(videoProblem(file("video/mp4", 50)), "");
  assert.equal(videoProblem(file("video/webm", 1)), "");
});

test("videoProblem refuses a GIF and a 60 MB MP4", () => {
  assert.match(videoProblem(file("image/gif", 1)), /^Choose an MP4, MOV or WebM clip/);
  assert.equal(videoProblem(file("video/mp4", 60)), "The clip is larger than 50 MB.");
});

test("videoProblem accepts one video or 1 to 6 photos", () => {
  assert.equal(videoProblem([file("video/mp4", 5)]), "");
  assert.equal(videoProblem([file("image/png", 1)]), "");
  assert.equal(videoProblem(Array.from({ length: 6 }, () => file("image/jpeg", 8))), "");
  assert.equal(videoProblem(file("image/webp", 1)), "");
});

test("videoProblem refuses mixes, 7 photos, two videos, none and a 9 MB photo", () => {
  const sendOne = "Send one video or 1 to 6 photos.";
  assert.equal(videoProblem([file("video/mp4", 1), file("image/png", 1)]), sendOne);
  assert.equal(videoProblem([file("video/mp4", 1), file("video/mp4", 1)]), sendOne);
  assert.equal(videoProblem(Array.from({ length: 7 }, () => file("image/png", 1))), sendOne);
  assert.match(videoProblem([]), /^Choose an MP4/);
  assert.equal(videoProblem([file("image/png", 9)]), "A photo is larger than 8 MB.");
  assert.ok(![sendOne, "Choose an MP4"].some((m) => ADVICE.test(m)));
});

test("toUpload sends one video as itself and photos as a list", () => {
  const video = file("video/mp4", 1);
  const photos = [file("image/png", 1), file("image/png", 1)];
  assert.equal(toUpload([video]), video);
  assert.equal(toUpload(photos), photos);
  assert.deepEqual(toUpload([photos[0]]), [photos[0]]);
});

test("checkLabel says photos when a photo check was not read", () => {
  assert.equal(checkLabel({ check: "tray", match: "none", media: "photos" }), "Photos kept, not checked");
  assert.equal(checkLabel({ check: "tray", match: "none", media: "video" }), CHECK_LABEL.tray.none);
  assert.equal(checkLabel({ check: "tray", match: "ok", media: "photos" }), CHECK_LABEL.tray.ok);
});

test("checkLabel reads an unknown match as none", () => {
  assert.equal(checkLabel({ check: "tray", match: "ok" }), CHECK_LABEL.tray.ok);
  assert.equal(checkLabel({ check: "setup", match: "mismatch" }), CHECK_LABEL.setup.mismatch);
  assert.equal(checkLabel({ check: "tray", match: "weird" }), CHECK_LABEL.tray.none);
  assert.equal(checkLabel(null), "");
});

test("latestCheck picks the last check of that kind and task", () => {
  const view = {
    video_checks: [
      { id: "a", check: "tray", task_id: null },
      { id: "b", check: "setup", task_id: "t1" },
      { id: "c", check: "tray", task_id: null },
      { id: "d", check: "setup", task_id: "t2" },
      { id: "e", check: "setup", task_id: "t1" },
    ],
  };
  assert.equal(latestCheck(view, "tray").id, "c");
  assert.equal(latestCheck(view, "setup", "t1").id, "e");
  assert.equal(latestCheck(view, "setup", "t3"), null);
  assert.equal(latestCheck({}, "tray"), null);
});

test("trayFlag is null unless the latest tray check is a mismatch", () => {
  assert.equal(trayFlag({}), null);
  assert.equal(trayFlag({ tray: { planned: {}, latest: null } }), null);
  assert.equal(trayFlag({ tray: { latest: { match: "ok", why: "x" } } }), null);
  assert.equal(trayFlag({ tray: { latest: { match: "none", why: "x" } } }), null);
  const text = trayFlag({ tray: { latest: { match: "mismatch", why: "Seen 1 of 2 forceps." } } });
  assert.equal(text, `${CHECK_LABEL.tray.mismatch} Seen 1 of 2 forceps.`);
  assert.doesNotMatch(text, ADVICE);
});

test("swabTotal follows the plan, else null", () => {
  assert.equal(swabTotal({}), null);
  assert.equal(swabTotal({ tray: { planned: null } }), null);
  assert.equal(swabTotal({ tray: { planned: { swab_total: 15 } } }), 15);
  assert.equal(swabTotal({ tray: { planned: { swab_total: 0 } } }), null);
});

test("taskVideoLabel is empty without a video", () => {
  assert.equal(taskVideoLabel({ video: null }), "");
  assert.equal(taskVideoLabel({}), "");
  assert.equal(taskVideoLabel({ video: { match: "ok" } }), CHECK_LABEL.setup.ok);
});

test("no UI string reads as advice", () => {
  const all = [...Object.values(CHECK_LABEL.tray), ...Object.values(CHECK_LABEL.setup), videoProblem(file("image/png", 1)), videoProblem(file("video/mp4", 60))];
  for (const s of all) assert.doesNotMatch(s, ADVICE, s);
});

test("shownChecks hides tray checks from the patient and from the nurse's theatre screen", () => {
  const checks = [{ id: "a", check: "tray" }, { id: "b", check: "setup" }];
  assert.deepEqual(shownChecks(checks, {}).map((c) => c.id), ["a", "b"]);
  assert.deepEqual(shownChecks(checks, { patient: true }).map((c) => c.id), ["b"]);
  assert.deepEqual(shownChecks(checks, { hideTray: true }).map((c) => c.id), ["b"]);
});
test("patientCheckLine", () => {
  assert.equal(patientCheckLine({ check: "setup", match: "ok" }), "Checked from a video: everything planned was seen.");
  assert.equal(patientCheckLine({ check: "setup", match: "mismatch" }), "Checked from a video: something planned was not seen; the nurse was told.");
  assert.equal(patientCheckLine({ check: "setup", match: "ok", media: "photos" }), "Checked from photos: everything planned was seen.");
  assert.equal(patientCheckLine({ check: "setup", match: null }), "A video was kept; it was not checked.");
});
