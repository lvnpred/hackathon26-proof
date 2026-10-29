import { label } from "./clock";
import { PageLead } from "../App";
import { useCareWard } from "./CareShell";
import StateHeader from "./StateHeader";
import { findKumar } from "./Patients";
import Timeline from "./Timeline";

// The same record as Today, read-only: no forms, no actions.
export default function MyCare() {
  const ward = useCareWard();
  const patient = findKumar(ward.patients);
  if (!patient) return <p className="empty">{ward.error || "Loading your care…"}</p>;
  const { view } = patient;
  return (
    <>
      <PageLead kicker={patient.name} title="My care" body="Where you are and what has been recorded. You can read it here." />
      <StateHeader patient={patient} view={view} />
      <section className="card">
        <p className="label">Orders and tasks</p>
        {(view.order_list || []).length === 0 && <p className="empty small">No orders yet.</p>}
        {(view.order_list || []).map((order) => (
          <div key={order.id}>
            <p className="small">Ordered by {order.by}{order.acknowledged_by ? `, acknowledged by ${order.acknowledged_by}` : ""}</p>
            <ul className="task-list">
              {(view.tasks || []).filter((task) => task.order_id === order.id).map((task) => (
                <li key={task.id}>
                  <span>{task.title}</span> <span className="pill info">{task.status}</span>
                  {(task.done || []).map((d) => (
                    <p className="small muted" key={d.at_ms}>Done by {d.by} at {label(d.at_ms)}</p>
                  ))}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>
      <section className="card">
        <p className="label">Timeline</p>
        <Timeline lines={view.timeline} nudges={view.nudges} replaced={new Set()} lens="patient" role="patient" readOnly />
      </section>
    </>
  );
}
