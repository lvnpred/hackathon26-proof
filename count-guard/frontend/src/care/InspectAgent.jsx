import { OPS_SCOPE, STAFF_BY, levelWords, undoLabel } from "./handling.js";
import { modelChip } from "./moments.js";
import { stamp } from "./when.js";

// What the AI read: each input as label · when.
export function AgentInput({ moment, nowMs }) {
  const inputs = moment.refs?.inputs || [];
  if (!inputs.length) return <div className="inspector-input"><p>No inputs were kept.</p></div>;
  return (
    <div className="inspector-input">
      <ul className="plan-list">{inputs.map((i, n) => <li key={i.id || n}>{i.label} · {stamp(i, nowMs)}</li>)}</ul>
    </div>
  );
}

// "Undo · 12 min" while the window is open, in the Inspector header so it shows on every tab.
export function AgentUndo({ moment, role, nowMs = 0, act, busy }) {
  const refs = moment.refs || {};
  const label = moment.status === "recorded" ? undoLabel(refs.undoUntilMs, nowMs) : "";
  if (!label || !act) return null;
  return <button type="button" disabled={busy} onClick={() => act(`/ops/work/${refs.workId}/undo`, { by: STAFF_BY[role] }, `${OPS_SCOPE}undo`)}>{label}</button>;
}

const MADE_BY_RULE = "A fixed rule, not a model";

// Why the AI did it: four labelled lines. Model names appear only on the "Made by" line.
export function AgentFound({ moment }) {
  const refs = moment.refs || {};
  const lines = [
    ["What it did", moment.title],
    ["Because", refs.reason || moment.finding],
    ["How it chose", refs.how || levelWords(refs.level)],
    ["Made by", moment.calls?.length ? modelChip(moment) : MADE_BY_RULE],
  ];
  return (
    <div className="inspector-found">
      <dl className="why-lines">
        {lines.map(([label, text]) => <div key={label}><dt className="t-caption">{label}</dt><dd>{text}</dd></div>)}
      </dl>
      <p className="small muted">{levelWords(refs.level)}</p>
    </div>
  );
}
