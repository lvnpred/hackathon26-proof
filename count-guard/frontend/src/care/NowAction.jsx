import AlertCard from "./AlertCard.jsx";
import { OPS_SCOPE, handlingRows, staffBy } from "./handling.js";
import { useInspector } from "./Inspector.jsx";

// Scrolls to a region of the chart and puts the cursor in its first field or button.
function focusIn(selector) {
  const target = document.querySelector(selector);
  target?.scrollIntoView({ block: "start" });
  target?.querySelector("input, textarea, select, button")?.focus();
}

// The control the Now winner owns. It is moved here from further down the chart, never copied, so each name exists once.
// An alert renders its own card; a review item gets that AI item's Undo and Why; the rest get one primary button.
export default function NowAction({ item, view, role, busy, act, nowMs, episodeId, patientName }) {
  const { openInspector } = useInspector();
  const action = item.action;
  if (!action) return null;
  if (action.kind === "alert") {
    const nudge = (view.nudges || []).find((n) => n.id === action.nudgeId);
    if (!nudge) return null;
    return (
      <div data-line={nudge.id}>
        <AlertCard view={view} role={role} nudge={nudge} primary busy={busy} act={act} nowMs={nowMs} episodeId={episodeId} patientName={patientName} />
      </div>
    );
  }
  if (action.kind === "review") {
    const row = handlingRows(view.ops, nowMs).find((r) => r.workId === action.workId);
    if (!row) return null;
    return (
      <div className="row">
        {row.undo && <button type="button" className="primary" disabled={busy} onClick={() => act(`/ops/work/${row.workId}/undo`, { by: staffBy(role, view) }, `${OPS_SCOPE}undo`)}>{row.undo}</button>}
        <button type="button" className="linklike" onClick={() => openInspector(row.workId, { episodeId })}>Why</button>
      </div>
    );
  }
  if (action.kind === "task") {
    return <button type="button" className="primary" onClick={() => focusIn(`[data-task="${CSS.escape(action.taskId)}"]`)}>{`Open task: ${item.title}`}</button>;
  }
  if (action.kind === "focus") {
    return <button type="button" className="primary" onClick={() => focusIn(action.selector)}>{action.label}</button>;
  }
  return null;
}
