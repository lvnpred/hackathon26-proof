import { canInspect, chipFor, findingFor } from "./moments.js";
import { findingPill } from "./finding.js";
import StatusPill from "./StatusPill.jsx";
import { useInspector } from "./Inspector.jsx";

// One AI result as one line: chip, finding, status, Inspect (C6).
export default function AiMoment({ moment, role, lens = "staff", episodeId, thumb = null, quiet = false }) {
  const { openInspector } = useInspector();
  const finding = findingFor(moment, lens);
  return (
    <div className="ai-moment" data-moment={moment.id}>
      {thumb}
      {lens !== "patient" && <span className="chip">{chipFor(moment)}</span>}
      {!quiet && finding && <span className="ai-moment-text">{finding}</span>}
      <StatusPill {...findingPill(moment, role)} />
      {canInspect(moment, lens) && (
        <button type="button" className="quiet" onClick={() => openInspector(moment.id, { episodeId })}>
          Inspect <span aria-hidden="true">›</span>
        </button>
      )}
    </div>
  );
}
