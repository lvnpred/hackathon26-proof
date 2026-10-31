import { canInspect, chipFor, findingFor, statusLabel } from "./moments.js";
import { useInspector } from "./Inspector.jsx";

// One AI result as one line: chip, finding, status, Inspect (C6).
export default function AiMoment({ moment, role, lens = "staff", episodeId, thumb = null, quiet = false }) {
  const { openInspector } = useInspector();
  const status = statusLabel(moment, role);
  const finding = findingFor(moment, lens);
  return (
    <div className="ai-moment" data-moment={moment.id}>
      {thumb}
      <span className="chip">{chipFor(moment)}</span>
      {!quiet && finding && <span className="ai-moment-text">{finding}</span>}
      <span className={`pill tone-${status.tone}`}>{status.text}</span>
      {canInspect(moment) && (
        <button type="button" className="quiet" onClick={() => openInspector(moment.id, { episodeId })}>
          Inspect <span aria-hidden="true">›</span>
        </button>
      )}
    </div>
  );
}
