import { label } from "./clock";
import { taskDue } from "./derive";
import { MATCH_LABEL, proofOf, sourceLabel } from "./drafts";
import { orderFoldTitle, orderLines, orderStatus, taskStatusText } from "./tasklist";
import { taskVideoLabel } from "./video";

function Lines({ order, tasks, photos, nowMs, state }) {
  return (
    <ul className="task-list">
      {orderLines(order, tasks).map(({ key, text, task }) => {
        if (!task) return <li key={key}><span>{text}</span></li>;
        const due = taskDue(task, nowMs, state);
        return (
          <li key={key}>
            <span>{task.title}</span> <span className={`pill ${due === "overdue" ? "sun" : due === "done" ? "ready" : "info"}`}>{taskStatusText(task, nowMs, state)}</span>
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
  );
}

// The "Orders and tasks" card: one line per order item, with its task's state when it has one.
// The nurse sees each signed order folded; the nurse's own task list is above (NurseTasks).
export default function OrderTasks({ orders, tasks, photos, nowMs, state, role }) {
  const lines = (order) => <Lines order={order} tasks={tasks} photos={photos} nowMs={nowMs} state={state} />;
  if (role === "nurse" && orders.length > 0) {
    return orders.map((order) => (
      <details className="card order-fold" key={order.id} data-order={order.id}>
        <summary>{orderFoldTitle(order)}</summary>
        {lines(order)}
      </details>
    ));
  }
  return (
    <section className="card">
      <p className="label">Orders and tasks</p>
      {orders.length === 0 && <p className="empty small">No orders or tasks yet.</p>}
      {orders.map((order) => (
        <div key={order.id} data-order={order.id}>
          <p className="small">
            Signed by {order.by} at {label(order.at_ms)} · {orderStatus(order, state)}
          </p>
          {lines(order)}
        </div>
      ))}
    </section>
  );
}
