// "What a person did" in the Expand view (clarity §4.2 part 4), pure. peopleOf(record, evidence, view) ->
// { kind, text, before, after, reason, note, lines } or null. It reads the person acts of the view (`view.acts`,
// acts.py) through provenanceOf, and knows the results a person answers in their own way:
//   a spoken answer (heard -> confirmed), a camera read (its findings, each Seen or Overridden), a proof or monitor photo
//   read (the task's verdict override or its done act), the camera count read (read -> the count a person saved),
//   and advice-only reads (camera checks, strips, medicines photos) that nobody answers.
import { sentenceText } from "./orders.js";
import { madeByModel, provenanceOf, provenanceText, sameOrders } from "./provenance.js";
import { displayName } from "./names.js";

export const NOT_ACTED = "No one has acted on it yet.";
export const ADVICE_ONLY = "Advice only — nothing for a person to answer";
export const ON_CONFIRM = "Confirmed when the nurse presses Confirm";
export const NOT_SAVED = "Not saved yet — the count a person saves decides";

const ADVICE_TYPES = new Set(["tray.checked", "setup.checked", "swabs.counted", "brownbag.med_found", "medicines.read"]);
const ADVICE_CAPS = new Set(["tray", "setup", "swabs", "strips", "medicines"]);

const words = (key) => String(key).replaceAll("_", " ");
const isOrder = (x) => x && typeof x === "object" && "kind" in x && ("name" in x || "text" in x);

// Any saved value as plain words: an order list as sentences, an object as "key value" pairs, never a snake_case key.
export function plainValue(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(plainValue).filter(Boolean).join("; ");
  if (isOrder(value)) return sentenceText(value);
  if (typeof value === "object") {
    if ("values" in value && Object.keys(value).length <= 2) return [plainValue(value.values), value.said ? `“${value.said}”` : ""].filter(Boolean).join(" · ");
    return Object.entries(value).filter(([, v]) => v !== null && v !== undefined && v !== "")
      .map(([k, v]) => (k === "said" ? `“${v}”` : `${words(k)} ${plainValue(v)}`)).join(" · ");
  }
  return String(value);
}

const part = (kind, text, extra = {}) => ({ kind, text, before: null, after: null, reason: null, note: null, lines: [], ...extra });
const lastAct = (acts, ref) => [...(acts || [])].reverse().find((a) => a.ref === ref && a.by) || null;

// The proposal a person may answer: an order draft compares the signed fields; a photo check is answered by its item.
function itemOf(r, ev) {
  const id = r.ref || (r.type === "check.photo" ? r.item : r.id);
  const calls = ev?.calls || r.calls;
  const base = { id, at_ms: r.at_ms, ai: madeByModel({ calls }) };
  if (r.type === "order.drafted") return { ...base, value: ev?.used?.items ?? r.items, same: sameOrders };
  return base;
}

// A camera read: each finding (advice row) a person saw or overrode. "2 of 3 findings answered".
function findings(r, acts) {
  const ids = r.adviceIds;
  const answered = ids.map((id) => ({ id, p: provenanceOf({ id }, acts), act: lastAct(acts, id) })).filter((x) => x.p.kind !== "proposed");
  if (!ids.length) return part("advice", ADVICE_ONLY);
  const head = `${answered.length} of ${ids.length} finding${ids.length === 1 ? "" : "s"} answered`;
  const lines = answered.map(({ p, act }) => `${provenanceText(p)}${act?.reason ? ` — ${act.reason}` : ""}`);
  return part(answered.length ? "accepted" : "proposed", head, { lines, note: answered.length < ids.length ? "A person acknowledges each finding on the camera card." : null });
}

// A proof or monitor photo read on a task: the verdict override (task:{id}), else the task's done act.
function taskRead(r, acts) {
  const override = lastAct((acts || []).filter((a) => a.type === "check.override"), `task:${r.taskId}`);
  if (override) return part("overridden", provenanceText(provenanceOf({ id: `task:${r.taskId}` }, acts)), { reason: override.reason || null });
  const done = lastAct((acts || []).filter((a) => a.type === "task.done"), r.taskId);
  if (done) {
    const p = provenanceOf({ id: r.taskId }, acts);
    return part(p.kind, provenanceText(p), { before: p.before == null ? null : plainValue(p.before), after: p.after == null ? null : plainValue(p.after) });
  }
  return part("proposed", ON_CONFIRM);
}

// The camera's swab count read, and the count a person saved from it.
function countRead(r) {
  const s = r.savedCount;
  if (!s || s.returned == null) return part("proposed", NOT_SAVED);
  const read = r.count;
  const changed = read != null && read !== s.returned;
  const p = { kind: changed ? "changed" : "accepted", by: displayName(s.by), at_ms: s.at_ms };
  return part(p.kind, provenanceText(p), {
    before: read == null ? null : `Camera read ${read}`, after: `Saved ${s.returned}`,
    note: changed ? null : `Saved ${s.returned}, as the camera read`,
  });
}

export function peopleOf(r, ev, view) {
  const acts = view?.acts || [];
  const c = ev?.captured || {};
  if (typeof c.answer === "string") { // a spoken answer: the person confirmed what was heard, maybe edited
    const edited = Boolean(ev.used?.edited);
    const p = { kind: edited ? "changed" : "accepted", by: displayName(r.by), at_ms: r.at_ms };
    return part(p.kind, provenanceText(p), { by: p.by, at_ms: p.at_ms, before: edited ? c.transcript : null, after: edited ? c.answer : null });
  }
  if (Array.isArray(r.adviceIds)) return findings(r, acts);
  if (r.taskId) return taskRead(r, acts);
  if (r.type === "count.camera") return countRead(r);
  if (ADVICE_TYPES.has(r.type) || ADVICE_CAPS.has(r.capability)) return part("advice", ADVICE_ONLY);
  const item = itemOf(r, ev);
  if (!item.id) return null;
  const p = provenanceOf(item, acts);
  const act = lastAct(acts, item.id);
  if (p.kind === "proposed") return part("proposed", item.ai ? provenanceText(p) : "Not proposed by a model", { note: NOT_ACTED });
  return part(p.kind, provenanceText(p), {
    before: p.before == null ? null : plainValue(p.before), after: p.after == null ? null : plainValue(p.after), reason: act?.reason || null,
  });
}

