import { label } from "./clock";
import { dueLabel, taskDue } from "./derive";
import { MATCH_LABEL, proofOf, sourceLabel } from "./drafts";
import { orderLines, orderStatus } from "./tasklist";
import { taskVideoLabel } from "./video";

// The staff "Orders and tasks" card: one line per order item, with its task's state when it has one.
export default function OrderTasks({ orders, tasks, photos, nowMs, state }) {
  return (
    <section className="card">
      <p className="label">Orders and tasks</p>
      {orders.length === 0 && <p className="empty small">No orders or tasks yet.</p>}
      {orders.map((order) => (
        <div key={order.id} data-order={order.id}>
          <p className="small">
            Signed by {order.by} at {label(order.at_ms)} · {orderStatus(order, state)}
          </p>
          <ul className="task-list">
            {orderLines(order, tasks).map(({ key, text, task }) => {
              if (!task) return <li key={key}><span>{text}</span></li>;
              const due = taskDue(task, nowMs, state);
              return (
                <li key={key}>
                  <span>{task.title}</span> <span className={`pill ${due === "overdue" ? "sun" : due === "done" ? "ready" : "info"}`}>{dueLabel(due)}</span>
                  {taskVideoLabel(task) && <span className="small muted"> · {taskVideoLabel(task)}</span>}
                  {(task.done || []).slice(-1).map((d) => {
                    const proof = proofOf(d, photos);
                    return (
                      <span className="small muted" key={d.at_ms}>
                        {" "}· Done by {d.by}, {proof.voice ? "by voice" : proof.typed ? "typed" : "by tap"}
                        {d.match && <> · <span className={`pill ${proof.flagged ? "sun" : "info"}`}>{MATCH_LABEL[d.match] || MATCH_LABEL.none}</span> <span className="muted">({sourceLabel(d.source || proof.photo?.check?.source)})</span></>}
                      </span>
                    );
                  })}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </section>
  );
}
