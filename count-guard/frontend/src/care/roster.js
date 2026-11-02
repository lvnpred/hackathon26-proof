// The ward list as the server keeps it (GET /journey/ward). Pure helpers, so node --test can load them.

const bedNumber = (bed) => {
  const n = Number(bed);
  return Number.isFinite(n) ? n : Infinity;
};

// { now_ms, patients, board } -> { nowMs, board, patients } with patients in bed order (4 before 10).
export function rosterFrom(ward) {
  const patients = [...(ward?.patients || [])].sort(
    (a, b) => bedNumber(a.bed) - bedNumber(b.bed) || String(a.bed).localeCompare(String(b.bed)),
  );
  return { nowMs: Number(ward?.now_ms) || 0, board: ward?.board || "", patients };
}

// The ward list follows this stream for changes (spec §8): any patient's record, a new patient, the clock.
export const WARD_STREAM = "/journey/ward/stream";

// The fallback: how often the ward list is read again while the page is visible, stream or not.
export const wardPollIntervalMs = () => 3000;
