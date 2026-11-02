// Staff source words: how a reading was made, in plain words. Never a model name (those live in the Inspector and on the AI page).
export const FROM_CAMERA = "Read by camera";
export const FROM_REPLAY = "Replayed camera recording";
export const DRAFTED_FROM_CAMERA = "Drafted from the camera case";
export const FROM_PHOTO = "Read from photo";
export const FROM_ORDER = "Checked against the order";
export const DRAFTED_FROM_VOICE = "Drafted from voice";
export const FROM_VOICE = "From voice";

const VOICE = { orders: DRAFTED_FROM_VOICE, discharge: DRAFTED_FROM_VOICE, task_voice: FROM_VOICE, answer_voice: FROM_VOICE };

// One AI moment (or { kind, capability }) -> its source words, or null when only rules built it.
export function sourceWords(moment) {
  switch (moment?.kind) {
    case "visual": return FROM_CAMERA;
    case "photo_read": return moment.capability === "dose_strip" ? FROM_ORDER : FROM_PHOTO;
    case "voice": return VOICE[moment.capability] || FROM_VOICE;
    default: return null;
  }
}

// Spec §6.7: a prepared (fixture) result never passes for live. It says "Prepared" beside its source words.
export const PREPARED = "Prepared";

// A moment, check, or heard result -> true when a prepared result stands behind it.
export function isPrepared(x) {
  if (!x) return false;
  if (x.source === "prepared" || x.heard_by === "prepared") return true;
  return (x.calls || []).some((c) => c.source === "prepared");
}

// The words a staff screen shows: "Read by camera · Prepared", "Prepared" alone, or the words as they are.
export function sourceLine(words, prepared) {
  if (!prepared) return words || null;
  return words ? `${words} · ${PREPARED}` : PREPARED;
}
