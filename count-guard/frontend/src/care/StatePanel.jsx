import DoctorActions from "./DoctorActions";
import NurseActions from "./NurseActions";
import { nextCard } from "./journey";

// Actions for the open chart: one branch per role. Each branch opens with the next-step card.
export default function StatePanel({ state, role, view, act, upload, ask, busy, nowMs, episodeId, replaced }) {
  const card = nextCard(view, role);
  switch (role) {
    case "doctor":
      return <DoctorActions key={state} state={state} card={card} view={view} act={act} upload={upload} ask={ask} busy={busy} />;
    case "nurse":
      return <NurseActions state={state} card={card} view={view} act={act} upload={upload} ask={ask} busy={busy} nowMs={nowMs} episodeId={episodeId} replaced={replaced} />;
    default:
      return <p className="note" role="status">Your actions are in Today and My care.</p>;
  }
}
