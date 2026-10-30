import { Nudge } from "../screens/WardPanel";
import { bannerAlerts } from "./alerts";
import { showTrayFlag } from "./derive";
import { trayFlag } from "./video";

// Every open alert at the top of the chart, answered here and nowhere else.
export default function AlertBanner({ view, role, line, busy, act }) {
  const alerts = bannerAlerts(view, role, line);
  const flag = showTrayFlag(role, view.state) ? trayFlag(view) : null;
  if (!alerts.length && !flag) return null;
  return (
    <section className="alert-banner" aria-label="Open alerts">
      {alerts.map(({ nudge, safety, canAnswer }) => (
        <div key={nudge.id} data-line={nudge.id} className={`alert-item${safety ? " alert-safety" : ""}`}>
          {canAnswer ? (
            <Nudge nudge={nudge} busy={busy} act={act} />
          ) : (
            <p><span className="tag">{nudge.when}</span> <b>{nudge.says}</b></p>
          )}
        </div>
      ))}
      {flag && <p className="note" role="status"><span className="pill sun">Tray flag</span> {flag}</p>}
    </section>
  );
}
