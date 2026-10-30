import { EvidenceThumb } from "./Evidence.jsx";
import { LENSES, lensLines } from "./journey";

export { LENSES };

// One line per event in time order. Open alerts are answered in the chart banner, never here.
// A line a lens filters out still shows when the nudge is for the current role or is the deep-linked line.
export default function Timeline({ episodeId, lines, nudges, replaced, lens, role, line }) {
  const shown = lensLines(lines, nudges, lens, role, line);
  if (!shown.length) return <p className="empty small">Nothing recorded for this lens yet.</p>;
  return (
    <ol className="timeline" aria-label="Timeline">
      {shown.map((item) => {
        const hit = item.id === line ? " line-hit" : "";
        const struck = replaced.has(item.id);
        return (
          <li key={item.id} id={item.id} data-line={item.id} className={`${struck ? "struck" : ""}${hit}`.trim() || undefined}>
            <span className="tag">{item.when}</span> <span>{lens === "patient" ? item.patient ?? item.plain : item.plain}</span>
            {struck && <> <span className="tag">corrected</span></>}
            {item.evidence_id && episodeId && lens !== "patient" && (
              <EvidenceThumb episodeId={episodeId} evidenceId={item.evidence_id} linkLines={false} version={lines.length} />
            )}
          </li>
        );
      })}
    </ol>
  );
}
