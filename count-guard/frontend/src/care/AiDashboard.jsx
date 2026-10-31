import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PageLead } from "../App";
import { PIPELINES, PIPELINE_KIND, STAFF_ONLY, activityRows, canSeeAi, emptyLine, storyCounts, storyLine } from "./ai.js";
import { shortName } from "./names.js";
import { useCareWard } from "./CareShell";
import ActivityList from "./ActivityList.jsx";
import ModelCards from "./ModelCards.jsx";

// The AI activity page: what the AI did today by patient and pipeline, then the Muse models.
export default function AiDashboard() {
  const ward = useCareWard();
  const staff = canSeeAi(ward.role);
  const [filter, setFilter] = useState(null);
  const rows = useMemo(() => activityRows(ward.patients), [ward.patients]);
  if (!staff) return <PageLead kicker="Staff" title="AI activity" body={STAFF_ONLY} />;
  const story = storyLine(storyCounts(rows));
  const shown = filter ? rows.filter((r) => r.moment.kind === filter) : rows;
  const first = ward.patients[0];
  const empty = first ? <Link to={`/chart/${first.id}`}>{emptyLine(shortName(first.name))}</Link> : "Nothing yet today.";
  return (
    <>
      <PageLead kicker="Staff" title="AI activity" body={story || "What the AI did on this ward, by patient and pipeline."} />
      <ol className="pipelines small" aria-label="Pipelines">
        {PIPELINES.map((steps) => {
          const kind = PIPELINE_KIND[steps[0]];
          return (
            <li key={steps[0]}>
              <button type="button" className="linklike" aria-label={steps.join(", ")} aria-pressed={filter === kind} onClick={() => setFilter(filter === kind ? null : kind)}>
                {steps.map((step, i) => <span key={step}>{i > 0 && <span className="step-arrow" aria-hidden="true">→</span>}<span className="step-chip">{step}</span></span>)}
              </button>
            </li>
          );
        })}
      </ol>
      <ActivityList rows={shown} role={ward.role} empty={rows.length === 0 ? empty : "Nothing here for this filter."} />
      <ModelCards ids={ward.patients.map((p) => p.id).join(",")} />
    </>
  );
}
