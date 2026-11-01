// Staff source words: how a reading was made, in plain words. Never a model name (those live in the Inspector and on the AI page).
export const FROM_CAMERA = "Read by camera";
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
