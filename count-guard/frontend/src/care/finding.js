// The pill of one AI moment: the clinical finding, never "Recorded" (spec 5.2). Pure, so node can test it.
import { hhmm } from "./clock.js";

const WHO = { doctor: "the doctor", nurse: "the nurse", patient: "the patient" };

// Moments the backend does not build (the AI agent's own rows) have no finding fields yet.
function ownFinding({ status, owner, at_ms: at }) {
  if (status === "undone") return { role: "done", text: "Undone" };
  if (status === "open") return { role: "wait", text: owner ? `Waiting for ${WHO[owner]}` : "Waiting" };
  return { role: "done", text: at == null ? "Saved" : `Saved ${hhmm(at)}` };
}

// A waiting moment that is waiting on the viewer reads "Needs you". Danger and check keep their words.
export function findingPill(moment, role) {
  const pill = moment.finding_role && moment.finding_text
    ? { role: moment.finding_role, text: moment.finding_text }
    : ownFinding(moment);
  if (pill.role === "wait" && moment.status === "open" && moment.owner && moment.owner === role) return { role: "wait", text: "Needs you" };
  return pill;
}
