import { sentenceText } from "./orders.js";
import Checklist from "./Checklist";
import HandoverCard from "./HandoverCard.jsx";
import NowCard from "./NowCard";
import NurseTasks from "./NurseTasks";
import TheatreChecklist from "./TheatreChecklist";

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

function Orders({ orders, by, busy, act, primary }) {
  const fresh = orders.filter((order) => !order.acknowledged_by);
  return fresh.map((order) => (
    <div key={order.id}>
      <p className="label">New orders from {order.by}</p>
      <ul>{(order.items || []).map((item, i) => <li key={i}>{sentenceText(item)}</li>)}</ul>
      <button type="button" className={primary ? "primary" : undefined} disabled={busy} onClick={() => act(`/orders/${order.id}/ack`, { by })}>Acknowledge</button>
    </div>
  ));
}

// The nurse's actions for the patient's current state: the card holds the step, the ward tasks follow.
export default function NurseActions({ state, card, pick, control, view, act, upload, ask, busy, nowMs, episodeId, replaced, afterNow = null }) {
  const by = state === "theatre" ? THEATRE_NURSE : WARD_NURSE;
  const nowStep = pick.now.action?.kind === "step"; // only the Now action is primary
  const move = (to, checklist) => act("/state", { to, by, reason: "", checklist });
  const primary = {
    ack: <Orders key="ack" orders={view.order_list || []} by={by} busy={busy} act={act} primary={nowStep} />,
    admission: (
      <div key="admission">
        <p className="label">Admission checklist</p>
        <Checklist items={ADMISSION} busy={busy} button="Complete admission" primary={nowStep} onDone={(c) => move("ward", c)} />
      </div>
    ),
    theatre: <TheatreChecklist key="theatre" role="nurse" episodeId={episodeId} view={view} busy={busy} act={act} upload={upload} replaced={replaced} primary={nowStep} />,
    discharge: (
      <div key="discharge">
        <p className="label">Discharge checklist</p>
        <Checklist items={DISCHARGE} busy={busy} button="Complete discharge" primary={nowStep} onDone={(c) => move("home", c)} />
      </div>
    ),
  };
  return (
    <>
      <NowCard pick={pick} card={card} control={control}>{card.actions.map((key) => primary[key])}</NowCard>
      {afterNow}
      {(state === "ward" || state === "theatre") && <NurseTasks view={view} nowMs={nowMs} state={state} by={by} busy={busy} act={act} upload={upload} ask={ask} />}
      {state === "ward" && <HandoverCard view={view} busy={busy} act={act} />}
      {!["admitting", "ward", "theatre", "discharging"].includes(state) && <p className="empty small">Nothing for the nurse to do from this state.</p>}
    </>
  );
}
