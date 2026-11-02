import { useEffect, useState } from "react";
import { Link, useMatch, useSearchParams } from "react-router-dom";
import Correct from "./Correct.jsx";
import Fault from "./Fault";
import { canCorrect } from "./correct.js";
import { modelChip, findingFor } from "./moments.js";
import { findingPill } from "./finding.js";
import StatusPill from "./StatusPill.jsx";
import { AI_NOTE, TABS, correctionLine, eventIdLines, historyLine, inspectEpisode, isAiBy, modelRows, readInspect, resolveMoment, tabsFor } from "./inspect.js";
import { findPatient } from "./Patients";
import { VoiceFound, VoiceInput } from "./InspectVoice.jsx";
import { AnswerFound, AnswerInput, DraftFound, DraftInput, RuleFound, RuleInput } from "./InspectText.jsx";
import { AgentFound, AgentInput, AgentUndo } from "./InspectAgent.jsx";
import { OPS_SCOPE, agentMoments } from "./handling.js";
import { PhotoFound, RawOutput, VisualFound, VisualInput } from "./InspectVisual.jsx";

// Registration point: Tasks 3-5 fill each kind with { Input, Found }; the ops agent registers `agent`.
// Both components take { moment, episodeId, view, role, lens, focus, setFocus }.
// An unregistered kind renders the finding only.
export const KIND_VIEWS = {
  visual: { Input: VisualInput, Found: VisualFound },
  photo_read: { Input: VisualInput, Found: PhotoFound },
  voice: { Input: VoiceInput, Found: VoiceFound },
  answer: { Input: AnswerInput, Found: AnswerFound },
  rule: { Input: RuleInput, Found: RuleFound },
  draft: { Input: DraftInput, Found: DraftFound },
  agent: { Input: AgentInput, Found: AgentFound },
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
      {modelChip(moment) && <p><span className="chip">{modelChip(moment)}</span></p>}
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

// A plain audit trail: "09:20 · Nurse Asha logged BP 88/60." with no event names; a line links to the chart only when it can.
function HistoryTab({ moment, episodeId, nowMs, role, lens, act, busy, fault }) {
  const [copied, setCopied] = useState("");
  const written = moment.written || [];
  const copy = () => {
    const text = eventIdLines(written);
    Promise.resolve().then(() => navigator.clipboard.writeText(text)).then(() => setCopied("Copied"), () => setCopied("Could not copy"));
  };
  return (
    <div className="inspector-history">
      {written.some((w) => isAiBy(w.by)) && <p className="small muted">{AI_NOTE}</p>}
      <ul className="inspector-record">
        {written.map((w) => {
          const text = historyLine(w, nowMs);
          const fix = correctionLine(w.read, w.saved, w.by);
          return (
            <li key={w.event_id}>
              {episodeId ? <Link className="history-line" to={`/chart/${episodeId}?line=${w.event_id}`}>{text}</Link> : text}
              {fix && <span className="muted"> · {fix}</span>}
              {episodeId && lens !== "patient" && role !== "patient" && canCorrect(w) && <Correct written={w} role={role} episodeId={episodeId} act={act} busy={busy} fault={fault} />}
            </li>
          );
        })}
      </ul>
      {written.length > 0 && <button type="button" className="quiet" onClick={copy}>Copy event IDs</button>}
      {copied && <span className="small muted" role="status"> {copied}</span>}
    </div>
  );
}

function Body({ moment, tab, episodeId, view, role, lens, initialFocus, act, nowMs, busy, fault }) {
  const [focus, setFocus] = useState(initialFocus);
  const views = KIND_VIEWS[moment.kind];
  const props = { moment, episodeId, view, role, lens, focus, setFocus, act, nowMs, busy, fault };
  const finding = <p>{findingFor(moment, lens)}</p>;
  if (tab === "history") return <HistoryTab moment={moment} episodeId={episodeId} nowMs={nowMs} role={role} lens={lens} act={act} busy={busy} fault={fault} />;
  if (tab === "model") return <ModelTab moment={moment} episodeId={episodeId} />;
  const View = views?.[tab === "evidence" ? "Input" : "Found"];
  return View ? <View {...props} /> : finding;
}

export default function Inspector({ ward }) {
  const { momentId, episodeId: paramEpisode, focus: urlFocus, closeInspector } = useInspector();
  const [tab, setTab] = useState("why");
  const chartId = useMatch("/chart/:episodeId")?.params.episodeId;
  useEffect(() => { setTab("why"); }, [momentId]);
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
  const moment = resolveMoment([...(patient?.view?.ai_moments || []), ...agentMoments(patient?.view?.ops, episodeId)], momentId, lens);
  const tabs = tabsFor(lens);

  return (
    <section className="inspector" aria-label="Inspector">
      <header className="inspector-head">
        {moment ? (
          <>
            <h2>{moment.title}</h2>
            <StatusPill {...findingPill(moment, ward.role)} />
            {lens !== "patient" && moment.kind === "agent" && <AgentUndo moment={moment} role={ward.role} nowMs={ward.nowMs} busy={ward.busy} act={(path, body, scope) => ward.act(episodeId, path, body, scope)} />}
          </>
        ) : <p>Nothing to inspect with that id.</p>}
        <button type="button" className="quiet" onClick={closeInspector}>Close</button>
      </header>
      {moment?.kind === "agent" && lens !== "patient" && <Fault fault={ward.fault} episodeId={episodeId} only={[OPS_SCOPE]} />}
      {moment && (
        <>
          <div role="tablist" className="inspector-tabs">
            {TABS.filter(([key]) => tabs.includes(key)).map(([key, label]) => (
              <button key={key} type="button" role="tab" aria-selected={tab === key} className="quiet" onClick={() => setTab(key)}>{label}</button>
            ))}
          </div>
          <div role="tabpanel" className="inspector-panel">
            <Body key={moment.id} initialFocus={urlFocus} moment={moment} tab={tab} episodeId={episodeId} view={patient.view} role={ward.role} lens={lens} nowMs={ward.nowMs} busy={ward.busy} fault={ward.fault} act={(path, body, scope) => ward.act(episodeId, path, body, scope)} />
          </div>
        </>
      )}
    </section>
  );
}
