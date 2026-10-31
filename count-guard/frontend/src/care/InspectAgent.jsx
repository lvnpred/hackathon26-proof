import Fault from "./Fault";
import { OPS_SCOPE, STAFF_BY, levelWords, undoLabel } from "./handling.js";


// What the AI read: each input as label · when.
export function AgentInput({ moment }) {
  const inputs = moment.refs?.inputs || [];
  if (!inputs.length) return <div className="inspector-input"><p>No inputs were recorded.</p></div>;
  return (
    <div className="inspector-input">
      <ul className="plan-list">{inputs.map((i, n) => <li key={i.id || n}>{i.label} · {i.when}</li>)}</ul>
    </div>
  );
}

// Why the AI did it, how far it went, and Undo while the window is open.
export function AgentFound({ moment, role, nowMs = 0, act, busy, fault, episodeId }) {
  const refs = moment.refs || {};
  const open = moment.status === "recorded" ? undoLabel(refs.undoUntilMs, nowMs) : "";
  const undo = () => act(`/ops/work/${refs.workId}/undo`, { by: STAFF_BY[role] }, `${OPS_SCOPE}undo`);
  return (
    <div className="inspector-found">
      <p>{refs.reason || moment.finding}</p>
      <p className="small muted">{levelWords(refs.level)}</p>
      {open && act && <button type="button" disabled={busy} onClick={undo}>{open}</button>}
      <Fault fault={fault} episodeId={episodeId} only={[OPS_SCOPE]} />
    </div>
  );
}
