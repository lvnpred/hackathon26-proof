import { canInspect, findingFor } from "./moments.js";
import { sourceWords } from "./source.js";
import Source from "./Source.jsx";
import { findingPill } from "./finding.js";
import StatusPill from "./StatusPill.jsx";
import { useInspector } from "./Inspector.jsx";

// One AI result as one line: source words, finding, status, Inspect (C6).
export default function AiMoment({ moment, role, lens = "staff", episodeId, thumb = null, quiet = false }) {
  const { openInspector } = useInspector();
  const finding = findingFor(moment, lens);
  const words = lens !== "patient" ? sourceWords(moment) : null;
  return (
    <div className="ai-moment" data-moment={moment.id}>
      {thumb}
      <Source words={words} />
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
