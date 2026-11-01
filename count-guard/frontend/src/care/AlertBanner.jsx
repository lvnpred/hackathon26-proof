import AiMoment from "./AiMoment.jsx";
import AlertCard from "./AlertCard.jsx";
import { bannerAlerts, bannerClass, nudgeText } from "./alerts";
import { showTrayFlag } from "./derive";
import { momentFor } from "./moments.js";
import { trayFlag } from "./video";

// Every open alert at the top of the chart, answered here and nowhere else.
export default function AlertBanner({ view, role, line, busy, act, nowMs, patientName }) {
  const alerts = bannerAlerts(view, role, line);
  const first = alerts.find((a) => a.canAnswer);
  const flag = showTrayFlag(role, view.state) ? trayFlag(view) : null;
  if (!alerts.length && !flag) return null;
  return (
    <section className={bannerClass(alerts)} aria-label="Open alerts">
      {alerts.map(({ nudge, safety, canAnswer }) => {
        const moment = momentFor(view, nudge.id);
        const lens = role === "patient" ? "patient" : "staff";
        return (
          <div key={nudge.id} data-line={nudge.id} className={`alert-item${safety ? " alert-safety" : ""}${nudge.id === line ? " line-hit" : ""}`}>
            {canAnswer ? (
              <AlertCard view={view} role={role} nudge={nudge} primary={first?.nudge.id === nudge.id} busy={busy} act={act} nowMs={nowMs} episodeId={view.episode?.id} patientName={patientName} />
            ) : moment ? (
              <AiMoment moment={moment} role={role} lens={lens} episodeId={view.episode?.id} />
            ) : (
              <p><span className="tag">{nudge.when}</span> <b>{nudgeText(nudge, role)}</b></p>
            )}
          </div>
        );
      })}
      {flag && <p className="note" role="status"><span className="pill sun">Tray flag</span> {flag}</p>}
    </section>
  );
}
