import { useEffect, useState } from "react";
import { Link, useMatch, useSearchParams } from "react-router-dom";
import { chipFor, findingFor, statusLabel } from "./moments.js";
import { TABS, correctionLine, inspectEpisode, modelRows, readInspect, recordLine, resolveMoment, tabsFor } from "./inspect.js";
import { findPatient } from "./Patients";
import { VoiceFound, VoiceInput } from "./InspectVoice.jsx";
import { PhotoFound, RawOutput, VisualFound, VisualInput } from "./InspectVisual.jsx";

// Registration point: Tasks 3-5 fill each kind with { Input, Found }; the ops agent adds `agent`.
// Both components take { moment, episodeId, view, role, lens, focus, setFocus }.
// An unregistered kind renders the finding only.
export const KIND_VIEWS = {
  visual: { Input: VisualInput, Found: VisualFound },
  photo_read: { Input: VisualInput, Found: PhotoFound },
  voice: { Input: VoiceInput, Found: VoiceFound },
  answer: null,
  rule: null,
  draft: null,
};

const CLEAR = ["inspect", "episode", "focus"];

// The drawer is driven by the URL (R7, R8); every page can open it.
export function useInspector() {
  const [params, setParams] = useSearchParams();
  const read = readInspect(params);
  function openInspector(momentId, { episodeId, focus } = {}) {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("inspect", momentId);
      if (episodeId) next.set("episode", episodeId); else next.delete("episode");
      if (focus) next.set("focus", focus); else next.delete("focus");
      return next;
    }, { replace: true });
  }
  function closeInspector() {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      CLEAR.forEach((k) => next.delete(k));
      return next;
    }, { replace: true });
  }
  return { momentId: read?.momentId ?? null, episodeId: read?.episodeId ?? null, focus: read?.focus ?? null, openInspector, closeInspector };
}

function ModelTab({ moment, episodeId }) {
  const rows = modelRows(moment.calls, moment.handmade);
  return (
    <div className="inspector-model">
      {rows.length ? (
        <table>
          <thead><tr><th>Model</th><th>Id</th><th>Mode</th><th>Time</th></tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i}><td>{r.name}</td><td>{r.id}</td><td>{r.mode}</td><td>{r.ms}</td></tr>)}</tbody>
        </table>
      ) : <p>No model call.</p>}
      {moment.kind === "rule" && moment.refs?.rule && <p>{moment.refs.rule}</p>}
      <RawOutput moment={moment} episodeId={episodeId} />
    </div>
  );
}

function RecordTab({ moment, episodeId, lens }) {
  return (
    <ul className="inspector-record">
      {(moment.written || []).map((w) => {
        const text = recordLine(w, lens);
        const fix = lens === "patient" ? "" : correctionLine(w.read, w.saved, w.by);
        return (
          <li key={w.event_id}>
            {lens === "patient" || !episodeId ? text : <Link to={`/chart/${episodeId}?line=${w.event_id}`}>{text}</Link>}
            {fix && <span className="muted"> · {fix}</span>}
          </li>
        );
      })}
    </ul>
  );
}

function Body({ moment, tab, episodeId, view, role, lens, initialFocus }) {
  const [focus, setFocus] = useState(initialFocus);
  const views = KIND_VIEWS[moment.kind];
  const props = { moment, episodeId, view, role, lens, focus, setFocus };
  const finding = <p>{findingFor(moment, lens)}</p>;
  if (tab === "record") return <RecordTab moment={moment} episodeId={episodeId} lens={lens} />;
  if (tab === "model") return <ModelTab moment={moment} episodeId={episodeId} />;
  const View = views?.[tab === "input" ? "Input" : "Found"];
  return View ? <View {...props} /> : finding;
}

export default function Inspector({ ward }) {
  const { momentId, episodeId: paramEpisode, focus: urlFocus, closeInspector } = useInspector();
  const [tab, setTab] = useState("found");
  const chartId = useMatch("/chart/:episodeId")?.params.episodeId;
  useEffect(() => { setTab("found"); }, [momentId]);
  useEffect(() => {
    if (!momentId) return undefined;
    const onKey = (e) => { if (e.key === "Escape") closeInspector(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  if (!momentId) return null;

  const lens = ward.role === "patient" ? "patient" : "staff";
  const own = ward.role === "patient" ? findPatient(ward.patients, ward.patientBed)?.id : null;
  const episodeId = inspectEpisode({ lens, param: paramEpisode, chartId, own });
  const patient = (ward.patients || []).find((p) => p.id === episodeId);
  const moment = resolveMoment(patient?.view?.ai_moments, momentId, lens);
  const status = moment && statusLabel(moment, ward.role);
  const tabs = tabsFor(lens);

  return (
    <section className="inspector" aria-label="Inspector">
      <header className="inspector-head">
        {moment ? (
          <>
            <h2>{moment.title}</h2>
            <span className="chip">{chipFor(moment)}</span>
            <span className={`pill tone-${status.tone}`}>{status.text}</span>
          </>
        ) : <p>Nothing to inspect with that id.</p>}
        <button type="button" className="quiet" onClick={closeInspector}>Close</button>
      </header>
      {moment && (
        <>
          <div role="tablist" className="inspector-tabs">
            {TABS.filter(([key]) => tabs.includes(key)).map(([key, label]) => (
              <button key={key} type="button" role="tab" aria-selected={tab === key} className="quiet" onClick={() => setTab(key)}>{label}</button>
            ))}
          </div>
          <div role="tabpanel" className="inspector-panel">
            <Body key={moment.id} initialFocus={urlFocus} moment={moment} tab={tab} episodeId={episodeId} view={patient.view} role={ward.role} lens={lens} />
          </div>
        </>
      )}
    </section>
  );
}
