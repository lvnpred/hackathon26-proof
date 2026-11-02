import { PageLead, Pill, Shell } from "../App";
import { subtitle, useJourney } from "../journey";
import { OrdersSummary } from "./DoctorOrders";
import WardPanel from "./WardPanel";

export default function Nurse() {
  const { view, error, busy, act } = useJourney();

  const inbox = (view?.nudges || []).filter((nudge) => nudge.to === "nurse");
  const recent = (view?.timeline || []).slice(-10).reverse();

  return (
    <Shell subtitle={subtitle(view)} status={view ? { tone: inbox.length ? "sun" : "ready", label: `${inbox.length} open for the nurse` } : null}>
      <PageLead
        kicker="Nurse"
        title="Give, log, and answer the nudges."
        body="A nudge sets a logged dose or reading beside the doctor's order. It does not tell you what to give. Answer it with what you did or saw."
      />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split">
        <section className="main">
          <WardPanel view={view} busy={busy} act={act} />
          <section className="card">
            <p className="label">Last entries</p>
            {recent.length === 0 && <p className="empty small">Nothing recorded yet.</p>}
            <div className="timeline">
              {recent.map((line) => (
                <div key={line.id}>
                  <span className="when" style={{ width: 96 }}>{line.when}</span>
                  <span className="what small">{line.plain}</span>
                </div>
              ))}
            </div>
          </section>
        </section>
        <aside className="side">
          <section className="card">
            <div className="row between">
              <p className="label">Ward orders</p>
              <Pill>read only</Pill>
            </div>
            <OrdersSummary orders={view?.orders} />
          </section>
        </aside>
      </div>
    </Shell>
  );
}
