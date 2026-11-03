// AI proposed vs person accepted (clarity spec §4.3): one mark for every item the AI proposes and a person answers.
// Pure, so node --test reads it. <Provenance> renders it; the Expand view (Task 4) reuses provenanceOf.
import { hhmm } from "./clock.js";
import { fieldDiffs, isAiBy } from "./inspect.js";
import { displayName } from "./names.js";

export const PROPOSED = "Proposed by AI";
const VERB = { accepted: "Accepted", changed: "Changed", overridden: "Overridden", seen: "Seen" };

// The person acts (view.acts types) that answer a proposal: these accept it, the OVERRIDE_ACTS set it aside.
export const ACCEPTED_ACTS = ["order.signed", "discharge.signed", "handover.accepted", "drug.given", "count.pack_opened", "camera.ack", "task.done"];
export const OVERRIDE_ACTS = ["check.override", "camera.resolved"];

// Model calls that did not produce the result (ai_moments.py FAILED_SOURCES); a "rules…" source is not a model.
const NOT_MADE = ["failed", "unreadable", "prepared (live call failed)", "unavailable"];

// True when a model produced it (live, or a prepared stand-in labelled Prepared): only then is it "Proposed by AI".
export const madeByModel = (x) => (x?.calls || []).some((c) => c?.source && !NOT_MADE.includes(c.source) && !String(c.source).startsWith("rules"));

// Spoken values (a /dictate reply) are the AI's only when a model structured them: not a rules fallback, not a failed
// hearing. The hearing alone does not make the values the model's.
export const proposalByModel = (p) => madeByModel(p) && !String(p?.source || "").startsWith("rules")
  && !NOT_MADE.includes(p?.heard_by) && !NOT_MADE.includes(p?.source);

// Camera advice the camera's model made (R6, "the camera count does not add up", is the count rule, not the model).
export const adviceByModel = (row) => row?.rule !== "R6" && madeByModel({ calls: [{ source: row?.source }] });

// Content equality: object keys in any order, text compared without outer spaces.
function same(a, b) {
  if (typeof a === "string" && typeof b === "string") return a.trim() === b.trim();
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a);
  return ka.length === Object.keys(b).length && ka.every((k) => same(a[k], b[k]));
}

// Orders compare by the fields a doctor signs (inspect.js fieldDiffs), so a draft-only field is not a change.
export const sameOrders = (drafted, signed) => fieldDiffs(drafted, signed).length === 0;

// item: { id, at_ms?, value?, same?, ai? } — the AI proposal, what it proposed, how to compare it, and whether a model
// made it (ai: false hides "Proposed by AI"). events: { type, ref, by, at_ms, value?, proposed?, reason? } rows (view.acts).
// The newest person act on item.id decides. An act that carries `proposed` compares it with its own `value`.
// -> { kind: "proposed"|"accepted"|"changed"|"overridden"|"seen", by, at_ms, before, after }
export function provenanceOf(item, events) {
  const acts = (events || []).filter((e) => e && e.ref === item?.id && e.by && !isAiBy(e.by)
    && (ACCEPTED_ACTS.includes(e.type) || OVERRIDE_ACTS.includes(e.type)));
  const last = acts[acts.length - 1];
  if (!last) return { kind: "proposed", by: "AI", at_ms: item?.at_ms ?? null, before: null, after: null };
  const by = displayName(last.by);
  const plain = (kind) => ({ kind, by, at_ms: last.at_ms, before: null, after: null });
  if (OVERRIDE_ACTS.includes(last.type)) return plain("overridden");
  if (last.type === "camera.ack") return plain(String(last.reason || "").trim() ? "overridden" : "seen"); // a reason disagrees
  const compare = item.same || same;
  const before = last.proposed !== undefined ? last.proposed : item.value;
  const changed = before !== undefined && last.value !== undefined && !compare(before, last.value);
  return changed
    ? { kind: "changed", by, at_ms: last.at_ms, before, after: last.value }
    : { kind: "accepted", by, at_ms: last.at_ms, before: null, after: null };
}

// "Proposed by AI", "Accepted by Nurse Meena 09:14", "Changed by …", "Overridden by …", "Seen by …".
export function provenanceText(p) {
  if (!p || p.kind === "proposed") return PROPOSED;
  return `${VERB[p.kind]} by ${p.by} ${hhmm(p.at_ms)}`;
}

// A draft is dashed (.prov-proposed); anything a person did is solid with a person icon (.prov-accepted).
export const provClass = (kind) => (kind === "proposed" ? "prov prov-proposed" : kind === "accepted" ? "prov prov-accepted" : `prov prov-accepted prov-${kind}`);

// The newest act of one type (acts arrive oldest first), or null.
export const lastActOf = (acts, type) => [...(acts || [])].reverse().find((a) => a.type === type) || null;
