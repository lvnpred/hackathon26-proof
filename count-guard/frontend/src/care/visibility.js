import { PHOTO_CLOSED, PHOTO_STATES } from "./askText.js";

// Every feature card renders in every state (clarity §4.4, C5). Where its action cannot run now the card stays and
// says why, with its buttons disabled. The server still refuses the same writes; this only words the reason first.
export const ADMITTED = ["admitting", "ward", "theatre", "discharging"];
const EVERY = null;

// key: [states where the action runs (null: every state), the state words of its reason].
const OPENS = {
  admit: [["clinic"], "in clinic"],
  prescription: [EVERY],
  homeMedicines: [EVERY],
  orders: [["clinic", "admitting", "ward"], "in clinic, being admitted or on the ward"], // tasks.ORDER_STATES
  photo: [EVERY],
  theatre: [["ward"], "on the ward"],
  dischargeDraft: [["ward"], "on the ward"],
  dischargeDictate: [ADMITTED, "admitted"], // media_api.ADMITTED
  dischargeSign: [["ward"], "on the ward"],
  theatreRoom: [["theatre"], "in theatre"],
  admission: [["admitting"], "being admitted"],
  tasks: [ADMITTED, "admitted"],
  dose: [ADMITTED, "admitted"],
  handover: [ADMITTED, "admitted"],
  theatreChecklist: [["theatre"], "in theatre"],
  dischargeChecklist: [["discharging"], "being discharged"],
  checkin: [EVERY],
  help: [EVERY],
  healingPhoto: [PHOTO_STATES, null, PHOTO_CLOSED], // the patient reads their own words, not "the patient is"
  medicinesPhoto: [PHOTO_STATES, null, PHOTO_CLOSED],
};

// The cards each role's screens show, in every state.
export const CARDS = {
  doctor: ["admit", "prescription", "homeMedicines", "orders", "photo", "theatre", "dischargeDraft", "dischargeDictate", "dischargeSign", "theatreRoom"],
  nurse: ["admission", "tasks", "dose", "handover", "theatreChecklist", "dischargeChecklist"],
  patient: ["checkin", "help", "healingPhoto", "medicinesPhoto"],
};

export const opensWhen = (words) => `Opens when the patient is ${words}`;

// Whether a card's action runs in this state, and if not, why: { open, reason }.
export function gate(key, state) {
  const [states, words, said] = OPENS[key];
  const open = states === EVERY || states.includes(state);
  return { open, reason: open ? "" : said || opensWhen(words) };
}

export const cardsFor = (role, state) => CARDS[role].map((key) => ({ key, ...gate(key, state) }));
