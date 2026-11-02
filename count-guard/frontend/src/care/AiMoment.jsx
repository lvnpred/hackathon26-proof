import { canInspect, findingFor } from "./moments.js";
import { isPrepared, sourceWords } from "./source.js";
import Source from "./Source.jsx";
import { findingPill } from "./finding.js";
import { hhmm } from "./clock.js";
import StatusPill from "./StatusPill.jsx";
import { useInspector } from "./Inspector.jsx";

// One AI result as a two-line row: the finding, then status, time and source words. Inspectable rows are one
// button that opens the Inspector; the "Details" word stays in the accessible name on a phone (visually hidden).
export default function AiMoment({ moment, role, lens = "staff", episodeId, thumb = null, quiet = false }) {
  const { openInspector } = useInspector();
  const finding = findingFor(moment, lens);
  const words = lens !== "patient" ? sourceWords(moment) : null;
  const inspect = canInspect(moment, lens);
  const body = (
    <>
      {thumb}
      <span className="moment-main">
        {!quiet && finding && <span className="ai-moment-text">{finding}</span>}
        <span className="moment-meta">
          <StatusPill {...findingPill(moment, role)} />
          {moment.at_ms != null && <span className="moment-time">{hhmm(moment.at_ms)}</span>}
          <Source words={words} prepared={isPrepared(moment)} />
        </span>
      </span>
      {inspect && <span className="moment-more"><span className="moment-more-word">Details</span> <span aria-hidden="true">›</span></span>}
    </>
  );
  if (!inspect) return <div className="ai-moment moment-row" data-moment={moment.id}>{body}</div>;
  return (
    <button type="button" className="ai-moment moment-row" data-moment={moment.id} onClick={() => openInspector(moment.id, { episodeId })}>
      {body}
    </button>
  );
}
