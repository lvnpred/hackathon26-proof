import { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../journey";
import AiMark from "./AiMark.jsx";
import Fault from "./Fault";
import { BAD_ANSWER } from "./ai.js";
import { OPS_SCOPE, STAFF_BY, feedRows, isFeed } from "./handling.js";
import { useInspector } from "./Inspector.jsx";

// Everything the AI did across the roster, newest first, with Why and Undo while the window is open.
export default function AiFeed({ ids, nowMs, ward }) {
  const { openInspector } = useInspector();
  const [feed, setFeed] = useState(null);
  const [error, setError] = useState(null);
  const seq = useRef(0);
  const [failedIn, setFailedIn] = useState(null);
  const load = useCallback(() => {
    if (!ids) return Promise.resolve();
    const mine = ++seq.current;
    return call(`/journey/ops/feed?ids=${ids}`)
      .then((out) => { if (!isFeed(out)) throw new Error(BAD_ANSWER); if (mine === seq.current) { setFeed(out); setError(null); } })
      .catch((e) => mine === seq.current && setError((e && e.message) || "That did not work. Try again."));
  }, [ids]);
  // Reload when the ward changes (a clock jump, an act); load never writes ward.patients.
  useEffect(() => { load(); }, [load, ward.patients]);
  const rows = feedRows(feed, nowMs);
  const undo = async (r) => {
    setFailedIn(r.episodeId);
    await ward.act(r.episodeId, `/ops/work/${r.workId}/undo`, { by: STAFF_BY[ward.role] }, `${OPS_SCOPE}undo`);
    await load();
  };
  return (
    <section aria-label="AI did this">
      <h3>AI did this</h3>
      {error && <p className="error small" role="alert">{error}</p>}
      {rows.length === 0 ? (error && !feed ? null : <p className="empty small">Nothing handled yet.</p>) : (
        <ul className="ai-handling-list">
          {rows.map((r) => (
            <li key={r.workId}>
              <span className="ai-handling-text"><AiMark /> {r.patient} · {r.text} · {r.when}</span>
              {r.undone && <span className="pill tone-grey">Undone</span>}
              {r.undo && <button type="button" disabled={ward.busy} onClick={() => undo(r)}>{r.undo}</button>}
              <button type="button" className="quiet" onClick={() => openInspector(r.workId, { episodeId: r.episodeId })}>Why</button>
            </li>
          ))}
        </ul>
      )}
      <Fault fault={ward.fault} episodeId={failedIn} only={[OPS_SCOPE]} />
    </section>
  );
}
