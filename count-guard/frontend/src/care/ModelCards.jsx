import { useCallback, useEffect, useState } from "react";
import { call } from "../journey";
import { BAD_ANSWER, EMPTY_MODELS, cardLine, isSummary, isTry, modeLabel, modelsPill } from "./ai.js";
import { displayName } from "./names.js";
import { Evidence, EvidenceThumb } from "./Evidence.jsx";
import ModelStep from "./ModelStep.jsx";
import { useModelStep } from "./useModelStep.js";
import { busyOf } from "./modelStep.js";
import { UNKNOWN } from "./stepOutcome.js";

// A sample try's mode -> the step's outcome. "Sample" (a bundled text, no model call) proves nothing: plain Done.
const TRIED = { live: { mode: "live" }, prepared: { mode: "prepared" }, failed: { mode: "fallback", fallback: "prepared result" } };
const tried = (out) => TRIED[out?.mode] || UNKNOWN;

const faultOf = (e) => (e && e.message) || "That did not work. Try again.";

// onTry(opts) runs the sample through this card's step (by model key): its checking line and any failure show here.
export function ModelCard({ model, busy, text, onTry }) {
  const last = model.last;
  const step = useModelStep({ capability: model.key });
  return (
    <section className="card model-card" aria-label={model.name} aria-busy={busyOf(step.step)}>
      <h3>{model.name}</h3>
      <p className="small">{model.role}</p>
      <p className="row"><span className="pill">{modeLabel(model.mode)}</span> <span className="small">{cardLine(model)}</span></p>
      {last && <p className="small">{displayName(last.text)}</p>}
      {last?.evidence_id && <EvidenceThumb episodeId={last.episode_id} evidenceId={last.evidence_id} model={model.key} />}
      {text && <p className="small"><span className="pill">{modeLabel(text.mode)}</span> {text.text}</p>}
      <button type="button" className="quiet" disabled={busy} onClick={() => step.run((o) => onTry(o), { outcome: tried })}>Try sample</button>
      <ModelStep busy={busy} step={step.step} onRetry={step.retry} />
    </section>
  );
}

// The four Muse model cards with their last real result, and the Try-sample flow.
export default function ModelCards({ ids }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sample, setSample] = useState(null);
  const [texts, setTexts] = useState({});
  const load = useCallback(() => {
    if (!ids) return Promise.resolve();
    return call(`/journey/ai/summary?ids=${ids}`)
      .then((out) => { if (!isSummary(out)) throw new Error(BAD_ANSWER); setData(out); })
      .catch((e) => setError(faultOf(e)));
  }, [ids]);
  useEffect(() => { load(); }, [load]);
  // A failed try throws to the card's step (Didn't work + Retry); the page's error line is for the summary.
  const tryIt = async (key, opts = {}) => {
    setBusy(true);
    setError(null);
    try {
      const out = await call(`/journey/ai/try/${key}`, { method: "POST" }, { signal: opts.signal, timeoutMs: opts.timeoutMs });
      if (!isTry(out)) throw new Error(BAD_ANSWER);
      if (out.evidence) setSample({ key, evidence: out.evidence });
      else setTexts((t) => ({ ...t, [key]: { text: out.text, mode: out.mode } }));
      await load();
      return out;
    } finally {
      setBusy(false);
    }
  };
  return (
    <section aria-label="Models">
      <h3>Models {data && <span className="pill">{modelsPill(data.live)}</span>}</h3>
      {error && <p className="error small" role="alert">{error}</p>}
      <div className="model-cards">
        {(data?.models || EMPTY_MODELS).map((m) => <ModelCard key={m.key} model={m} busy={busy} text={texts[m.key]} onTry={(opts) => tryIt(m.key, opts)} />)}
      </div>
      {sample && <Evidence sample={sample.evidence} check={{ rows: sample.evidence.rows }} model={sample.key} />}
    </section>
  );
}
