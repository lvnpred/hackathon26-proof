import DoctorActions from "./DoctorActions";
import NurseActions from "./NurseActions";
import AiHandling from "./AiHandling.jsx";
import { nextCard } from "./journey";
import NowAction from "./NowAction.jsx";

// Actions for the open chart: one branch per role. Each branch opens with the Now card.
export default function StatePanel({ state, role, pick, view, act, upload, ask, busy, nowMs, episodeId, replaced, fault }) {
  const card = nextCard(view, role);
  const control = <NowAction item={pick.now} view={view} role={role} busy={busy} act={act} nowMs={nowMs} episodeId={episodeId} />;
  const footer = <AiHandling view={view} role={role} nowMs={nowMs} act={act} episodeId={episodeId} busy={busy} fault={fault} movedWork={pick.now.action?.workId} />;
  switch (role) {
    case "doctor":
      return <DoctorActions key={state} state={state} card={card} pick={pick} control={control} view={view} act={act} upload={upload} ask={ask} busy={busy} footer={footer} />;
    case "nurse":
      return <NurseActions state={state} card={card} pick={pick} control={control} view={view} act={act} upload={upload} ask={ask} busy={busy} nowMs={nowMs} episodeId={episodeId} replaced={replaced} footer={footer} />;
    default:
      return <p className="note" role="status">Your actions are in Today and My care.</p>;
  }
}
