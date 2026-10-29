import { useState } from "react";
import { Nudge } from "../screens/WardPanel";
import Checklist from "./Checklist";
import TheatrePanel from "./TheatrePanel";
import { taskDue } from "./derive";
import { OBS_FIELDS, obsValues, sortTasks, surgeryNow } from "./tasklist";

const WARD_NURSE = "Nurse Meena (synthetic)";
const THEATRE_NURSE = "Nurse Asha (synthetic)";

const ADMISSION = [
  ["band", "Wristband on"],
  ["allergies", "Allergies checked"],
  ["baseline_obs", "Baseline observations taken"],
  ["consent", "Consent on file"],
];
const DISCHARGE = [
  ["card_given", "Discharge card given"],
  ["medicines_handed", "Medicines handed over"],
  ["reminders_set", "Reminders set"],
];

function Orders({ orders, by, busy, act }) {
  const fresh = orders.filter((order) => !order.acknowledged_by);
  if (!fresh.length) return null;
  return (
    <section className="card">
      <p className="label">New orders</p>
      {fresh.map((order) => (
        <div key={order.id}>
          <p className="small">From {order.by}</p>
          <ul>{(order.items || []).map((item, i) => <li key={i}>{item.text}</li>)}</ul>
          <button type="button" className="primary" disabled={busy} onClick={() => act(`/orders/${order.id}/ack`, { by })}>Acknowledge</button>
        </div>
      ))}
    </section>
  );
}

function ObsForm({ busy, onSave }) {
  const [form, setForm] = useState({});
  const [error, setError] = useState("");
  function save() {
    const out = obsValues(form);
    if (out.error) return setError(out.error);
    setError("");
    Promise.resolve(onSave(out.values)).then((next) => next && setForm({}));
  }
  return (
    <div className="row">
      {OBS_FIELDS.map(([key, label]) => (
        <label className="field" key={key} style={{ flex: "1 1 70px" }}>
          {label}
          <input inputMode="decimal" value={form[key] || ""} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
        </label>
      ))}
      <button type="button" className="primary" disabled={busy} onClick={save}>Mark done</button>
      {error && <p className="error small" role="alert">{error}</p>}
    </div>
  );
}

function TaskRow({ task, due, by, busy, act }) {
  const done = (body = {}) => act(`/tasks/${task.id}/done`, { by, via: "tap", note: "", ...body });
  return (
    <li>
      <div className="row between">
        <span>{task.title}</span>
        <span className={`pill ${due === "overdue" ? "sun" : due === "done" ? "ready" : "info"}`}>{due}</span>
      </div>
      {due !== "done" && task.kind === "obs" && <ObsForm busy={busy} onSave={(values) => done({ values })} />}
      {due !== "done" && task.kind !== "obs" && task.mode === "start_end" && (
        task.status === "running"
          ? <button type="button" className="primary" disabled={busy} onClick={() => done()}>End</button>
          : <button type="button" disabled={busy} onClick={() => act(`/tasks/${task.id}/begin`, { by })}>Begin</button>
      )}
      {due !== "done" && task.kind !== "obs" && task.mode !== "start_end" && (
        <button type="button" className="primary" disabled={busy} onClick={() => done()}>Mark done</button>
      )}
    </li>
  );
}

function Ward({ view, nowMs, by, busy, act }) {
  const tasks = sortTasks(view.tasks || [], nowMs).filter((task) => task.status !== "done");
  return (
    <>
      <section className="card">
        <p className="label">Tasks</p>
        {tasks.length === 0 && <p className="empty small">No open tasks.</p>}
        <ul className="task-list">
          {tasks.map((task) => <TaskRow key={task.id} task={task} due={taskDue(task, nowMs)} by={by} busy={busy} act={act} />)}
        </ul>
      </section>
      {(view.nudges || []).map((nudge) => <Nudge key={nudge.id} nudge={nudge} busy={busy} act={act} />)}
    </>
  );
}

function Theatre({ episodeId, view, busy, act, replaced }) {
  const move = (view.allowed || []).find((m) => m.to === "ward");
  const surgeonMoves = move?.role === "doctor";
  const { began, ended } = surgeryNow(view.timeline);
  return (
    <>
      <TheatrePanel episodeId={episodeId} view={view} busy={busy} act={act} replaced={replaced} />
      <section className="card">
        <p className="label">Surgery</p>
        <div className="row">
          <button type="button" disabled={busy || began} onClick={() => act("/surgery", { step: "began", by: THEATRE_NURSE })}>Surgery began</button>
          <button type="button" disabled={busy || !began || ended} onClick={() => act("/surgery", { step: "ended", by: THEATRE_NURSE })}>Surgery ended</button>
        </div>
        {surgeonMoves ? (
          <p className="note" role="status">The count is open: the surgeon records the reason before the patient leaves theatre.</p>
        ) : (
          <>
            {move && (move.needs || []).length > 0 && <p className="small muted">Needs: {move.needs.join(", ")}</p>}
            <button
              type="button"
              className="primary"
              disabled={busy || !ended}
              onClick={() => act("/state", { to: "ward", by: THEATRE_NURSE, reason: "", checklist: {} })}
            >
              Back to ward
            </button>
          </>
        )}
      </section>
    </>
  );
}

// The nurse's actions for the patient's current state: orders first, then one branch per state.
export default function NurseActions({ state, view, act, busy, nowMs, episodeId, replaced }) {
  const by = state === "theatre" ? THEATRE_NURSE : WARD_NURSE;
  const move = (to, checklist) => act("/state", { to, by, reason: "", checklist });
  return (
    <>
      <Orders orders={["clinic", "admitting", "ward"].includes(state) ? view.order_list || [] : []} by={by} busy={busy} act={act} />
      {state === "admitting" && (
        <section className="card">
          <p className="label">Admission checklist</p>
          <Checklist items={ADMISSION} busy={busy} button="Complete admission" onDone={(c) => move("ward", c)} />
        </section>
      )}
      {state === "ward" && <Ward view={view} nowMs={nowMs} by={by} busy={busy} act={act} />}
      {state === "theatre" && <Theatre episodeId={episodeId} view={view} busy={busy} act={act} replaced={replaced} />}
      {state === "discharging" && (
        <section className="card">
          <p className="label">Discharge checklist</p>
          <Checklist items={DISCHARGE} busy={busy} button="Complete discharge" onDone={(c) => move("home", c)} />
        </section>
      )}
      {!["admitting", "ward", "theatre", "discharging"].includes(state) && <p className="empty small">Nothing for the nurse to do from this state.</p>}
    </>
  );
}
