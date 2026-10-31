import { useState } from "react";
import { citedLine, OPS_SCOPE, STAFF_BY } from "./handling.js";
import { displayName } from "./names.js";
import { useInspector } from "./Inspector.jsx";

// One thing the AI will not do alone: the sentence, the draft, what it cites, and four buttons.
// act(path, body, scope) is already tied to the patient's episode by the caller.
export default function ProposalCard({ p, act, busy, role, episodeId }) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(p.draft || "");
  const { openInspector } = useInspector();
  const by = STAFF_BY[role];
  const base = `/ops/work/${p.work_id}`;
  const cited = citedLine(p.cited);
  const blank = editing && !text.trim();
  const cancel = () => { setEditing(false); setText(p.draft || ""); };
  const approve = () => act(`${base}/approve`, editing ? { by, text } : { by }, `${OPS_SCOPE}approve`);
  const reject = () => act(`${base}/reject`, { by }, `${OPS_SCOPE}reject`);
  return (
    <article className="proposal-card" aria-label="AI proposal">
      <p className="next-text">{displayName(p.sentence)}</p>
      {editing ? (
        <label className="field">
          Answer to send
          <textarea rows={4} value={text} disabled={busy} onChange={(e) => setText(e.target.value)} />
        </label>
      ) : p.draft && <p className="quote">{displayName(p.draft)}</p>}
      {cited && <p className="small muted">{displayName(cited)}</p>}
      <div className="row">
        <button type="button" className="primary" disabled={busy || blank} onClick={approve}>Approve</button>
        {p.editable && !editing && <button type="button" disabled={busy} onClick={() => setEditing(true)}>Edit</button>}
        {editing && <button type="button" disabled={busy} onClick={cancel}>Cancel</button>}
        <button type="button" disabled={busy} onClick={reject}>Reject</button>
        <button type="button" className="linklike" onClick={() => openInspector(p.work_id, { episodeId })}>Why</button>
      </div>
    </article>
  );
}
