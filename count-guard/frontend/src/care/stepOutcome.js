// What a finished model step says about its result (care-app clarity §4.1): live, prepared, rules only ("none"),
// a reply that was not usable so something else stood in ("fallback"), or the model unavailable ("failed").
// It reads the result's `evidence` (Task 3) first, then its `calls`, then a bare `source` word.

// The record's model keys -> display names (the same as evidence_payload.MODEL_NAMES on the server).
const NAMES = { sam: "SAM 3.1", spark: "Spark 1.3", "spark-open": "Spark Open", voice: "Muse Voice" };
// Source words, as live.mode_of reads them on the server.
const LIVE = new Set(["muse-voice-transcribe", "muse-spark-1.3", "sam-3.1", "muse-spark-open", "live"]);
const FAILED = new Set(["prepared (live call failed)", "failed", "unreadable", "rules (model reply not usable)", "unavailable"]);
const UNAVAILABLE = "unavailable";
const STOOD_IN = { rules: "rules", template: "template", prepared: "prepared result" };

// A result the step cannot read: the done line says plain "Done", never a live claim it cannot back.
export const UNKNOWN = Object.freeze({ mode: "unknown" });

// The words for what stood in when the model's reply was not used.
function stoodIn(fallback, source) {
  if (fallback) return STOOD_IN[fallback] || fallback;
  return source === "prepared (live call failed)" ? STOOD_IN.prepared : STOOD_IN.rules;
}

function fromSource(source, model, fallback) {
  if (LIVE.has(source)) return { mode: "live", model };
  if (source === "prepared") return { mode: "prepared", model };
  if (source === UNAVAILABLE) return { mode: "failed", model };
  if (FAILED.has(source)) return { mode: "fallback", model, fallback: stoodIn(fallback, source) };
  return null;
}

function fromEvidence(evidence) {
  const { returned, used, calls = [] } = evidence;
  const last = calls[calls.length - 1];
  const model = returned.model && returned.model !== "rules" ? returned.model : null;
  if (returned.mode === "none") return { mode: "none" };
  if (returned.mode === "failed") {
    if (last?.source === UNAVAILABLE) return { mode: "failed", model };
    return { mode: "fallback", model, fallback: stoodIn(used?.fallback, last?.source) };
  }
  return { mode: returned.mode, model };
}

// outcomeOf(x) -> { mode, model?, fallback? } for an evidence-carrying result, a check, a moment or a draft; null
// when x says nothing about a model.
export function outcomeOf(x) {
  if (!x || typeof x !== "object") return null;
  if (x.evidence?.returned?.mode) return fromEvidence(x.evidence);
  if (Array.isArray(x.calls)) {
    const last = x.calls[x.calls.length - 1];
    if (!last) return fromSource(x.source, null) || { mode: "none" };
    return fromSource(last.source, NAMES[last.model] || null) || { mode: "none" };
  }
  if (typeof x.source === "string") return fromSource(x.source, null);
  if (typeof x.heard_by === "string") return fromSource(x.heard_by, null); // a heard result names its hearer
  return null;
}

// The moment a call added to the view (not in `before`), optionally of one of `caps`.
export function newMoment(before, after, caps) {
  const old = new Set((before?.ai_moments || []).map((m) => m.id));
  return (after?.ai_moments || []).find((m) => !old.has(m.id) && (!caps || caps.includes(m.capability))) || null;
}

// An outcome for a call that returns the whole view: the moment it added says how the model did.
export const viewOutcome = (before, caps) => (after) => outcomeOf(newMoment(before, after, caps)) || UNKNOWN;

// The newest tray, set-up or swab camera check of one kind in a view.
export function latestVideo(view, kind) {
  const found = (view?.video_checks || []).filter((c) => c.check === kind);
  return found.length ? found[found.length - 1] : null;
}

// The step's opts for ward.act/upload/ask, with the error handed back to the card's step (not the chart's fault).
export const own = (opts = {}) => ({ ...opts, ownFault: true });

// Ruling P10: the theatre panel says before a click whether it writes the context card and who words it
// (`card_due` / `card_on_tier`: "spark", "rules" or null). null -> no step line; "card" -> a Spark step; "rules" -> a
// step that names no model.
export const cardStep = (due) => (due === "spark" ? "card" : due === "rules" ? "rules" : null);
