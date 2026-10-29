import DoctorActions from "./DoctorActions";
import NurseActions from "./NurseActions";

// Actions for the open chart: one branch per role.
export default function StatePanel({ state, role, view, act, upload, ask, busy, nowMs, episodeId, replaced }) {
  switch (role) {
    case "doctor":
      return <DoctorActions state={state} view={view} act={act} upload={upload} busy={busy} />;
    case "nurse":
      return <NurseActions state={state} view={view} act={act} upload={upload} ask={ask} busy={busy} nowMs={nowMs} episodeId={episodeId} replaced={replaced} />;
    default:
      return <p className="note" role="status">Your actions are in Today and My care.</p>;
  }
}
