import { Nudge } from "../screens/WardPanel";
import { bannerAlerts, bannerClass, nudgeText } from "./alerts";
import { showTrayFlag } from "./derive";
import { trayFlag } from "./video";

// Every open alert at the top of the chart, answered here and nowhere else.
export default function AlertBanner({ view, role, line, busy, act }) {
  const alerts = bannerAlerts(view, role, line);
  const flag = showTrayFlag(role, view.state) ? trayFlag(view) : null;
  if (!alerts.length && !flag) return null;
  return (
    <section className={bannerClass(alerts)} aria-label="Open alerts">
      {alerts.map(({ nudge, safety, canAnswer }) => (
        <div key={nudge.id} data-line={nudge.id} className={`alert-item${safety ? " alert-safety" : ""}${nudge.id === line ? " line-hit" : ""}`}>
          {canAnswer ? (
            <Nudge nudge={{ ...nudge, says: nudgeText(nudge, role) }} busy={busy} act={act} />
          ) : (
            <p><span className="tag">{nudge.when}</span> <b>{nudgeText(nudge, role)}</b></p>
          )}
        </div>
      ))}
      {flag && <p className="note" role="status"><span className="pill sun">Tray flag</span> {flag}</p>}
    </section>
  );
}
