import Checklist from "./Checklist";
import NextCard from "./NextCard";
import NurseTasks from "./NurseTasks";
import TheatrePanel from "./TheatrePanel";
import { surgeryNow } from "./tasklist";
import VideoCheck from "./VideoCheck";

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
  return fresh.map((order) => (
    <div key={order.id}>
      <p className="label">New orders from {order.by}</p>
      <ul>{(order.items || []).map((item, i) => <li key={i}>{item.text}</li>)}</ul>
      <button type="button" className="primary" disabled={busy} onClick={() => act(`/orders/${order.id}/ack`, { by })}>Acknowledge</button>
    </div>
  ));
}

function Theatre({ episodeId, view, busy, act, upload, replaced }) {
  const move = (view.allowed || []).find((m) => m.to === "ward");
  const surgeonMoves = move?.role === "doctor";
  const { began, ended } = surgeryNow(view.timeline);
  return (
    <>
      {view.tray?.planned && (
        <VideoCheck
          title="Tray check"
          step="Step 1 of 4 ·"
          kind="tray"
          check={view.tray.latest}
          busy={busy}
          hideUpload={began}
          onFile={(file) => upload("/video", file, { check: "tray", by: THEATRE_NURSE })}
        />
      )}
      <section className="card">
        <p className="label">Step 2 of 4 · Surgery began</p>
        <div className="row">
          <button type="button" disabled={busy || began} onClick={() => act("/surgery", { step: "began", by: THEATRE_NURSE })}>Surgery began</button>
          {began && <span className="small muted">Began {began}</span>}
        </div>
      </section>
      <TheatrePanel episodeId={episodeId} view={view} busy={busy} act={act} replaced={replaced} step="Step 3 of 4 ·" />
      <section className="card">
        <p className="label">Step 4 of 4 · Surgery ended</p>
        <div className="row">
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

// The nurse's actions for the patient's current state: the card holds the step, the ward tasks follow.
export default function NurseActions({ state, card, view, act, upload, ask, busy, nowMs, episodeId, replaced }) {
  const by = state === "theatre" ? THEATRE_NURSE : WARD_NURSE;
  const move = (to, checklist) => act("/state", { to, by, reason: "", checklist });
  const primary = {
    ack: <Orders key="ack" orders={view.order_list || []} by={by} busy={busy} act={act} />,
    admission: (
      <div key="admission">
        <p className="label">Admission checklist</p>
        <Checklist items={ADMISSION} busy={busy} button="Complete admission" onDone={(c) => move("ward", c)} />
      </div>
    ),
    theatre: <Theatre key="theatre" episodeId={episodeId} view={view} busy={busy} act={act} upload={upload} replaced={replaced} />,
    discharge: (
      <div key="discharge">
        <p className="label">Discharge checklist</p>
        <Checklist items={DISCHARGE} busy={busy} button="Complete discharge" onDone={(c) => move("home", c)} />
      </div>
    ),
  };
  return (
    <>
      <NextCard card={card}>{card.actions.map((key) => primary[key])}</NextCard>
      {(state === "ward" || state === "theatre") && <NurseTasks view={view} nowMs={nowMs} state={state} by={by} busy={busy} act={act} upload={upload} ask={ask} />}
      {!["admitting", "ward", "theatre", "discharging"].includes(state) && <p className="empty small">Nothing for the nurse to do from this state.</p>}
    </>
  );
}
