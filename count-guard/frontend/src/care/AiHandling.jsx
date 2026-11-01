import Fault from "./Fault";
import ProposalCard from "./ProposalCard.jsx";
import { OPS_SCOPE, PAUSED_TITLE, handlingRows, liveCount, needsTitle, pausedRows, proposalsFor, staffBy, stripTitle } from "./handling.js";
import { useInspector } from "./Inspector.jsx";

// What the AI is handling on this chart, and what it hands to the role. Staff only: the patient sees one routed line in Messages.
export default function AiHandling({ view, role, nowMs, act, episodeId, busy, fault, movedWork = null }) {
  const { openInspector } = useInspector();
  if (role === "patient" || !view?.ops) return null;
  const rows = handlingRows(view.ops, nowMs).filter((r) => r.workId !== movedWork);
  const proposals = proposalsFor(view.ops, role);
  const paused = pausedRows(view.ops, role);
  const undo = (id) => act(`/ops/work/${id}/undo`, { by: staffBy(role, view) }, `${OPS_SCOPE}undo`);
  return (
    <section className="ai-handling" aria-label="AI is handling">
      <p className="label">{stripTitle(liveCount(view.ops))}</p>
      {rows.length === 0 ? <p className="empty small">Nothing handled yet.</p> : (
        <ul className="ai-handling-list">
          {rows.map((r) => (
            <li key={r.workId}>
              <span className="ai-handling-text">{r.text} · {r.when}</span>
              {r.undone && <span className="pill tone-grey">Undone</span>}
              {r.undo && <button type="button" disabled={busy} onClick={() => undo(r.workId)}>{r.undo}</button>}
              <button type="button" className="linklike" onClick={() => openInspector(r.workId, { episodeId })}>Why</button>
            </li>
          ))}
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
