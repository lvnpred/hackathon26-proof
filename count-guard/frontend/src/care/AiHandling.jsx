import { useState } from "react";
import AiMark from "./AiMark.jsx";
import Fault from "./Fault";
import Fold from "./Fold.jsx";
import ProposalCard from "./ProposalCard.jsx";
import { OPS_SCOPE, PAUSED_TITLE, adminTitle, foldTitle, handlingState, needsTitle, staffBy } from "./handling.js";
import { useInspector } from "./Inspector.jsx";

// The AI's admin on this chart. Rows with a live Undo stay open; once every window has closed they fold into one line.
// Staff only: the patient sees one routed line in Messages.
export default function AiHandling({ view, role, nowMs, act, episodeId, busy, fault, movedWork = null }) {
  const { openInspector } = useInspector();
  const [reviewing, setReviewing] = useState(false);
  if (role === "patient" || !view?.ops) return null;
  const { open, done, paused, proposals } = handlingState(view.ops, nowMs, role, movedWork);
  const undo = (id) => act(`/ops/work/${id}/undo`, { by: staffBy(role, view) }, `${OPS_SCOPE}undo`);
  const why = (r) => <button type="button" className="quiet" onClick={() => openInspector(r.workId, { episodeId })}>Why</button>;
  const line = (r) => <span className="ai-handling-text"><AiMark /> {r.text} · {r.when}</span>;
  const total = open.length + done.length;
  return (
    <section className="ai-handling" aria-label="AI admin">
      <p className="label">{adminTitle(total)}</p>
      {total === 0 && <p className="empty small">Nothing handled yet.</p>}
      {open.length > 0 && (
        <ul className="ai-handling-list">
          {open.map((r) => (
            <li key={r.workId}>
              {line(r)}
              <button type="button" disabled={busy} onClick={() => undo(r.workId)}>{r.undo}</button>
              {why(r)}
            </li>
          ))}
        </ul>
      )}
      {done.length > 0 && open.length === 0 && (
        <Fold label={foldTitle(done)} open={reviewing} onToggle={() => setReviewing(!reviewing)}>
          <ul className="ai-handling-list">
            {done.map((r) => <li key={r.workId}>{line(r)}{r.undone && <span className="pill tone-grey">Undone</span>}{why(r)}</li>)}
          </ul>
        </Fold>
      )}
      {done.length > 0 && open.length > 0 && (
        <ul className="ai-handling-list">
          {done.map((r) => <li key={r.workId}>{line(r)}{r.undone && <span className="pill tone-grey">Undone</span>}{why(r)}</li>)}
        </ul>
      )}
      {paused.length > 0 && (
        <>
          <p className="label">{PAUSED_TITLE}</p>
          <ul className="ai-handling-list">
            {paused.map((r) => <li key={r.workId}><span className="ai-handling-text">{r.text}</span></li>)}
          </ul>
        </>
      )}
      {proposals.length > 0 && (
        <>
          <p className="label">{needsTitle(proposals.length)}</p>
          {proposals.map((p) => <ProposalCard key={p.work_id} p={p} act={act} busy={busy} role={role} view={view} episodeId={episodeId} />)}
        </>
      )}
      <Fault fault={fault} episodeId={episodeId} only={[OPS_SCOPE]} />
    </section>
  );
}
