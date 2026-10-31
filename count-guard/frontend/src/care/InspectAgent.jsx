import { OPS_SCOPE, STAFF_BY, undoLabel } from "./handling.js";

const LEVELS = {
  act: "The AI did this on its own, and you can undo it.",
  propose: "The AI proposed this and waited for a person to approve it.",
  inform: "The AI only told someone about this.",
};
export const levelWords = (level) => LEVELS[level] || "The AI handled this by its rules.";

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
export function AgentFound({ moment, role, nowMs = 0, act, busy }) {
  const refs = moment.refs || {};
  const open = moment.status === "recorded" ? undoLabel(refs.undoUntilMs, nowMs) : "";
  const undo = () => act(`/ops/work/${refs.workId}/undo`, { by: STAFF_BY[role] }, `${OPS_SCOPE}undo`);
  return (
    <div className="inspector-found">
      <p>{refs.reason || moment.finding}</p>
      <p className="small muted">{levelWords(refs.level)}</p>
      {open && act && <button type="button" disabled={busy} onClick={undo}>{open}</button>}
    </div>
  );
}
