import { useState } from "react";
import AiMoment from "./AiMoment.jsx";
import { FILTERS, filterMoments } from "./moments.js";

// The one list of every AI result and kept record on a chart (R17). The patient lens drops the chips.
export default function RecordEvidence({ view, role, lens = "staff", episodeId }) {
  const [filter, setFilter] = useState("all");
  const patient = lens === "patient";
  const rows = filterMoments(view.ai_moments, patient ? "all" : filter, role, lens);
  return (
    <section className="card" aria-label="Record and evidence">
      <p className="label">Record &amp; evidence</p>
      {!patient && (
        <div className="row" role="group" aria-label="Filter">
          {FILTERS.map(([key, text]) => (
            <button type="button" key={key} className="quiet" aria-pressed={filter === key} onClick={() => setFilter(key)}>{text}</button>
          ))}
        </div>
      )}
      {rows.length === 0 && <p className="empty small">Nothing here for this filter.</p>}
      <ul className="task-list">
        {rows.map((moment) => (
          <li key={moment.id}>
            <AiMoment
              moment={moment}
              role={role}
              lens={lens}
              episodeId={episodeId}
              thumb={moment.photo_id ? <img src={`/journey/episodes/${episodeId}/photos/${moment.photo_id}`} alt="" width={40} height={40} style={{ objectFit: "cover", borderRadius: 6 }} /> : null}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}
