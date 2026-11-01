import { useState } from "react";
import { RxImport, RxTable } from "../screens/ClinicPanel";
import { answerHow } from "./askText";
import ActionBar from "./ActionBar";
import { IconMic } from "./icons.jsx";
import { panelOpen, toggled } from "./actions";
import { doctorBlocks, quietActions } from "./journey";
import NowCard from "./NowCard";
import Dictate from "./Dictate";
import AiMoment from "./AiMoment.jsx";
import { draftChanged, sectionsToSummary } from "./drafts";
import { lastSigned, momentFor } from "./moments";
import OrderForm from "./OrderForm";
import TheatreChecklist from "./TheatreChecklist";
import { theatreSteps } from "./theatre";
import PhotoInput from "./PhotoInput.jsx";
import StripPhoto from "./StripPhoto.jsx";
import { TrayPreview } from "./VideoCheck";

export const DOCTOR = "Dr. A. Rao (synthetic)";

// Hear a recording as text to check, then draft from that text. heard_by keeps who heard it.
const hearing = (ask, path) => (file) => ask("/ask/hear", file, { by: DOCTOR }, path);
const drafting = (upload, path) => ({ text, heard }) =>
  upload(path, undefined, { text, by: DOCTOR, heard_by: answerHow(heard?.text, text, heard?.by).heard_by });

function PhotoCard({ title, busy, upload }) {
  return (
    <section className="card" aria-label={title}>
      <p className="label">{title}</p>
      <PhotoInput disabled={busy} onFiles={([file]) => upload("/photos", file, { purpose: "reference", by: DOCTOR })} />
    </section>
  );
}

// Dictation, the order form that loads its draft, and the reference photo input. While a draft waits to be signed the
// order form sits under the Next card (OrderDraft) and the finished dictation box folds away (spec P3).
function OrderDraft({ view, busy, signOrders }) {
  const draft = view.drafts?.order;
  return <OrderForm busy={busy} onSign={signOrders} draft={draft} moment={momentFor(view, draft?.id)} episodeId={view.episode?.id} />;
}

function OrdersDictation({ view, busy, upload, ask, signOrders }) {
  const draft = view.drafts?.order;
  const signed = draft ? null : lastSigned(view.ai_moments, "orders");
  const dictate = <Dictate label="Dictate orders" capability="orders" verb="Draft orders" busy={busy} onHear={hearing(ask, "/dictate/orders")} onSend={drafting(upload, "/dictate/orders")} />;
  if (draft) return <details className="fold"><summary>Dictate again</summary>{dictate}</details>;
  return (
    <>
      {dictate}
      {signed && <AiMoment moment={signed} role="doctor" episodeId={view.episode?.id} />}
      <OrderDraft view={view} busy={busy} signOrders={signOrders} />
    </>
  );
}

// Action for the clinic card: admit the patient (primary while it is Now) or close the visit.
function Admit({ view, busy, act, primary }) {
  const [reason, setReason] = useState("");
  const [reasonDraftId, setReasonDraftId] = useState(null);
  const draft = view.drafts?.order;
  if (draftChanged(reasonDraftId, draft)) {
    setReasonDraftId(draft.id);
    if (draft.reason) setReason(draft.reason);
  }
  return (
    <>
      <label className="field">
        Reason for admission
        <input value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      <div className="row">
        <button type="button" className={primary ? "primary" : undefined} disabled={busy || !reason.trim()} onClick={() => act("/state", { to: "admitting", by: DOCTOR, reason: reason.trim() })}>Admit</button>
        <button type="button" disabled={busy} onClick={() => act("/state", { to: "clinic_done", by: DOCTOR })}>Close visit</button>
      </div>
    </>
  );
}

// The clinic cards that sit below the quiet row (R25).
function Clinic({ view, busy, act, upload }) {
  return (
    <>
      <section className="card">
        <p className="label">Prescription</p>
        <RxImport busy={busy} act={act} />
        <RxTable rx={view.rx} />
      </section>
      <StripPhoto view={view} busy={busy} upload={upload} act={act} />
    </>
  );
}

// Primary action for the ward card: dictate the discharge, then sign it. The form keeps its text while closed.
function Discharge({ view, busy, act, upload, ask, open, onToggle, primary }) {
  const [summary, setSummary] = useState("");
  const [summaryDraftId, setSummaryDraftId] = useState(null);
  const [template, setTemplate] = useState("hernia-repair");
  const draft = view.drafts?.discharge;
  if (draftChanged(summaryDraftId, draft)) {
    setSummaryDraftId(draft.id);
    setSummary(sectionsToSummary(draft.sections || []));
  }
  const templates = Object.entries(view.templates || {});
  async function signDischarge() {
    const done = await act("/discharge/sign", { summary: summary.trim(), template, by: DOCTOR, draft_id: summaryDraftId || undefined });
    if (done) {
      setSummary("");
      setSummaryDraftId(null);
    }
  }
  return (
    <>
      <button type="button" aria-expanded={open} onClick={onToggle}><IconMic />Dictate discharge</button>
      {open && (
        <>
          <Dictate label="Dictate discharge" capability="discharge" verb="Draft discharge" busy={busy} onHear={hearing(ask, "/dictate/discharge")} onSend={drafting(upload, "/dictate/discharge")} />
          <div>
            <p className="label">Discharge</p>
            {summaryDraftId && (
              <>
                {momentFor(view, draft?.id) && <AiMoment moment={momentFor(view, draft.id)} role="doctor" episodeId={view.episode?.id} />}
                <p className="note small" role="status">Draft from dictation. Check the summary, then sign.</p>
              </>
            )}
            <label className="field">
              Summary
              <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
            </label>
            <label className="field">
              Template
              <select value={template} onChange={(e) => setTemplate(e.target.value)}>
                {templates.length === 0 && <option value="hernia-repair">hernia-repair</option>}
                {templates.map(([key, title]) => <option key={key} value={key}>{title}</option>)}
              </select>
            </label>
            <button type="button" className={primary ? "primary" : undefined} disabled={busy || !summary.trim()} onClick={signDischarge}>Sign discharge</button>
          </div>
        </>
      )}
    </>
  );
}

// Primary action for the ward card: pick the procedure and send the patient to theatre.
function SendToTheatre({ view, busy, act, primary }) {
  const [procedure, setProcedure] = useState("");
  const procedures = Object.entries(view.procedures || {});
  return (
    <div>
      <label className="field">
        Procedure
        <select value={procedure} onChange={(e) => setProcedure(e.target.value)}>
          <option value="">Choose a procedure</option>
          {procedures.map(([key, title]) => <option key={key} value={key}>{title}</option>)}
        </select>
      </label>
      <TrayPreview plan={view.tray_templates?.[procedure]} />
      <button type="button" className={primary ? "primary" : undefined} disabled={busy || !procedure} onClick={() => act("/state", { to: "theatre", by: DOCTOR, procedure })}>Send to theatre</button>
    </div>
  );
}

function Theatre({ view, busy, act, upload }) {
  const [reason, setReason] = useState("");
  const ended = theatreSteps(view)[3].done;
  const move = (view.allowed || []).find((m) => m.to === "ward" && m.role === "doctor");
  return (
    <>
      <TheatreChecklist role="doctor" view={view} busy={busy} act={act} upload={upload} />
      {move && (
        <section className="card">
          <label className="field">
            Reason for leaving the count open
            <input value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          {move.needs.filter((need) => !need.startsWith("reason")).length > 0 && (
            <p className="small muted">Needs: {move.needs.filter((need) => !need.startsWith("reason")).join(", ")}</p>
          )}
          <button
            type="button"
            disabled={busy || !ended || !reason.trim()}
            onClick={() => act("/state", { to: "ward", by: DOCTOR, reason: reason.trim(), checklist: {} })}
          >
            Back to ward
          </button>
        </section>
      )}
    </>
  );
}

const sign = (act) => (items, draftId) => act("/orders/sign", { items, by: DOCTOR, draft_id: draftId || undefined });

// The doctor's actions for the patient's current state: the card, the quiet row, the open panels, the rest.
export default function DoctorActions({ state, card, pick, control, view, act, upload, ask, busy, afterNow = null }) {
  const [chosen, setChosen] = useState(() => new Set());
  const signOrders = sign(act);
  const open = (id) => panelOpen(chosen, id, view);
  const toggle = (id) => setChosen((current) => toggled(current, id));
  // A block is primary only inside the Now card while the step is Now; otherwise it is a secondary button.
  const blocks = (primary) => ({
    admit: <Admit key="admit" view={view} busy={busy} act={act} primary={primary} />,
    theatre: <SendToTheatre key="theatre" view={view} busy={busy} act={act} primary={primary} />,
    discharge: <Discharge key="discharge" view={view} busy={busy} act={act} upload={upload} ask={ask} open={open("discharge")} onToggle={() => toggle("discharge")} primary={primary} />,
  });
  const { inside, below } = doctorBlocks(state, card);
  return (
    <>
      <NowCard pick={pick} card={card} control={control} lead={open("orders") && view.drafts?.order ? <OrderDraft view={view} busy={busy} signOrders={signOrders} /> : null}>
        {inside.map((key) => blocks(pick.now.action?.kind === "step")[key])}
        <ActionBar actions={quietActions(state, "doctor")} isOpen={open} onToggle={toggle} />
      </NowCard>
      {afterNow}
      {open("orders") && <OrdersDictation view={view} busy={busy} upload={upload} ask={ask} signOrders={signOrders} />}
      {open("photo") && <PhotoCard title={state === "ward" ? "Wound photo" : "Reference photo"} busy={busy} upload={upload} />}
      {below.map((key) => blocks(false)[key])}
      {state === "clinic" && <Clinic view={view} busy={busy} act={act} upload={upload} />}
      {state === "theatre" && <Theatre view={view} busy={busy} act={act} upload={upload} />}
    </>
  );
}
