import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageLead } from "../App";
import { call } from "../journey";
import { BAD_ANSWER, EMPTY_MODELS, PIPELINES, callsText, isSummary, isTry, latencyText, modeLabel, recentText } from "./ai.js";
import { displayName } from "./names.js";
import { useCareWard } from "./CareShell";
import { Evidence, EvidenceThumb } from "./Evidence.jsx";

const faultOf = (e) => (e && e.message) || "That did not work. Try again.";

function ModelCard({ model, busy, text, onTry }) {
  const last = model.last;
  return (
    <section className="card model-card" aria-label={model.name}>
      <h3>{model.name}</h3>
      <p className="small">{model.role}</p>
      <p className="row"><span className="pill">{modeLabel(model.mode)}</span> <span className="small">{callsText(model.calls)} · {latencyText(model.median_ms)}</span></p>
      {last && <p className="small">{displayName(last.text)}</p>}
      {last?.evidence_id && <EvidenceThumb episodeId={last.episode_id} evidenceId={last.evidence_id} model={model.key} />}
      {text && <p className="small"><span className="pill">{modeLabel(text.mode)}</span> {text.text}</p>}
      <button type="button" disabled={busy} onClick={onTry}>Try sample</button>
    </section>
  );
}

function RecentRow({ row, open, toggle }) {
  const text = recentText(row);
  if (!row.evidence_id) return <li><Link to={`/chart/${row.episode_id}?line=${row.event_id}`}>{text}</Link></li>;
  return (
    <li>
      <button type="button" className="linklike" aria-expanded={open} onClick={toggle}>{text}</button>
      {open && <Evidence episodeId={row.episode_id} evidenceId={row.evidence_id} linkLines model={row.model} />}
    </li>
  );
}

// The showcase page: which Muse models run this ward, what they did, and a sample run of each.
export default function AiDashboard() {
  const ward = useCareWard();
  const ids = ward.patients.map((p) => p.id).join(",");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sample, setSample] = useState(null);
  const [texts, setTexts] = useState({});
  const [open, setOpen] = useState({});
  const load = useCallback(() => {
    if (!ids) return Promise.resolve();
    return call(`/journey/ai/summary?ids=${ids}`)
      .then((out) => { if (!isSummary(out)) throw new Error(BAD_ANSWER); setData(out); })
      .catch((e) => setError(faultOf(e)));
  }, [ids]);
  useEffect(() => { load(); }, [load]);
  const tryIt = async (key) => {
    setBusy(true);
    setError(null);
    try {
      const out = await call(`/journey/ai/try/${key}`, { method: "POST" });
      if (!isTry(out)) throw new Error(BAD_ANSWER);
      if (out.evidence) setSample({ key, evidence: out.evidence });
      else setTexts((t) => ({ ...t, [key]: { text: out.text, mode: out.mode } }));
      await load();
    } catch (e) {
      setError(faultOf(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageLead kicker="Demo" title="AI at work" body="Which Muse models run this ward, and what they just did." />
      {data && <p className="small ai-live" aria-label="Models">{data.live ? "Live ●" : "Prepared ○"}</p>}
      <ol className="pipelines small" aria-label="Pipelines">
        {PIPELINES.map((steps) => <li key={steps[0]}>{steps.join(" → ")}</li>)}
      </ol>
      {error && <p className="error small" role="alert">{error}</p>}
      <div className="model-cards">
        {(data?.models || EMPTY_MODELS).map((m) => <ModelCard key={m.key} model={m} busy={busy} text={texts[m.key]} onTry={() => tryIt(m.key)} />)}
      </div>
      {sample && <Evidence sample={sample.evidence} check={{ rows: sample.evidence.rows }} model={sample.key} />}
      <section aria-label="Recent AI events">
        <h3>Recent AI events</h3>
        {data && data.recent.length === 0 && <p className="empty small">No model results yet. Run a flow and they appear here.</p>}
        <ul className="recent-ai">
          {(data?.recent || []).map((r, i) => <RecentRow key={i} row={r} open={Boolean(open[i])} toggle={() => setOpen((o) => ({ ...o, [i]: !o[i] }))} />)}
        </ul>
      </section>
    </>
  );
}
