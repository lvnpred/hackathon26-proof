import { sentenceText } from "./orders.js";
import Checklist from "./Checklist";
import DoseGiven from "./DoseGiven.jsx";
import Handover from "./Handover.jsx";
import NowCard from "./NowCard";
import NurseTasks from "./NurseTasks";
import ProofItem from "./ProofItem.jsx";
import TheatreChecklist from "./TheatreChecklist";
import { own } from "./stepOutcome.js";
import { checkFor } from "./verdict.js";
import Opens from "./Opens.jsx";
import { gate } from "./visibility.js";

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

// The photo check under one checklist item: take or retake the photo, or override an open one with a reason.
export function proofFor({ view, step, by, busy, act, upload }) {
  return function proof(key, label) {
    const item = `${step}:${key}`;
    return (
      <ProofItem view={view} check={checkFor(view, item)} label={label} busy={busy} acts={view.acts}
        onPhoto={(file, o) => upload(`/checks/${item}/photo`, file, { by }, undefined, own(o))}
        onOverride={(reason) => act(`/checks/${item}/override`, { reason, by })} />
    );
  };
}

// A checklist that is not on the Now card stays as a card and says when it opens (clarity §4.4).
const STEPS = [["admission", "admission", "Admission checklist"], ["theatre", "theatreChecklist", "Theatre checklist"], ["discharge", "dischargeChecklist", "Discharge checklist"]];
function Waiting({ title, reason }) {
  return <section className="card" aria-label={title}><p className="label">{title}</p><Opens reason={reason} /></section>;
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
        <Checklist items={ADMISSION} busy={busy} button="Complete admission" primary={nowStep} onDone={(c) => move("ward", c)}
          proof={proofFor({ view, step: "admission", by, busy, act, upload })} />
      </div>
    ),
    theatre: <TheatreChecklist key="theatre" role="nurse" episodeId={episodeId} view={view} busy={busy} act={act} upload={upload} ask={ask} replaced={replaced} nowMs={nowMs} primary={nowStep} />,
    discharge: (
      <div key="discharge">
        <p className="label">Discharge checklist</p>
        <Checklist items={DISCHARGE} busy={busy} button="Complete discharge" primary={nowStep} onDone={(c) => move("home", c)}
          proof={proofFor({ view, step: "discharge", by, busy, act, upload })} />
      </div>
    ),
  };
  return (
    <>
      <NowCard pick={pick} card={card} control={control}>{card.actions.map((key) => primary[key])}</NowCard>
      {afterNow}
      <NurseTasks view={view} nowMs={nowMs} state={state} by={by} busy={busy} act={act} upload={upload} ask={ask} reason={gate("tasks", state).reason} />
      <DoseGiven by={by} busy={busy} act={act} reason={gate("dose", state).reason} />
      <Handover view={view} busy={busy} act={act} reason={gate("handover", state).reason} />
      {STEPS.filter(([key]) => !card.actions.includes(key)).filter(([, gateKey]) => gate(gateKey, state).reason).map(([key, gateKey, title]) => <Waiting key={key} title={title} reason={gate(gateKey, state).reason} />)}
    </>
  );
}
