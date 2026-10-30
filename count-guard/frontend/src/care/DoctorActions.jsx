import { useState } from "react";
import { parseStrips } from "../journey";
import { RxImport, RxTable } from "../screens/ClinicPanel";
import { answerHow, doctorOpenItems, doctorWaiting } from "./askText";
import ActionBar from "./ActionBar";
import { panelOpen, toggled } from "./actions";
import { doctorBlocks, quietActions } from "./journey";
import NextCard from "./NextCard";
import Dictate from "./Dictate";
import { draftChanged, heardLine, sectionsToSummary, sourceLabel } from "./drafts";
import OrderForm from "./OrderForm";
import TheatreChecklist from "./TheatreChecklist";
import { theatreSteps } from "./theatre";
import { TrayPreview } from "./VideoCheck";

export const DOCTOR = "Dr. A. Rao (synthetic)";

function StripCheck({ busy, act }) {
  const [lines, setLines] = useState("");
  return (
    <section className="card">
      <p className="label">Check strips</p>
      <label className="field">
        One strip per line: name then strength
        <textarea rows={3} value={lines} onChange={(e) => setLines(e.target.value)} />
      </label>
      <button type="button" disabled={busy || !lines.trim()} onClick={() => act("/strips", { strips: parseStrips(lines) })}>
        Check these strips
      </button>
    </section>
  );
}

// Hear a recording as text to check, then draft from that text. heard_by keeps who heard it.
const hearing = (ask, path) => (file) => ask("/ask/hear", file, { by: DOCTOR }, path);
const drafting = (upload, path) => ({ text, heard }) =>
  upload(path, undefined, { text, by: DOCTOR, heard_by: answerHow(heard?.text, text, heard?.by).heard_by });

function PhotoCard({ title, busy, upload }) {
  async function pick(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) await upload("/photos", file, { purpose: "reference", by: DOCTOR });
  }
  return (
    <section className="card" aria-label={title}>
      <p className="label">{title}</p>
      <label className="field">
        Add reference photo
        <input type="file" accept="image/*" capture="environment" disabled={busy} onChange={pick} />
      </label>
    </section>
  );
}

// Dictation, the order form that loads its draft, and the reference photo input.
function OrdersDictation({ view, busy, upload, ask, signOrders }) {
  return (
    <>
      <Dictate label="Dictate orders" verb="Draft orders" busy={busy} onHear={hearing(ask, "/dictate/orders")} onSend={drafting(upload, "/dictate/orders")} />
      <OrderForm busy={busy} onSign={signOrders} draft={view.drafts?.order} />
    </>
  );
}

// Primary action for the clinic card: admit the patient or close the visit.
function Admit({ view, busy, act }) {
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
        <button type="button" className="primary" disabled={busy || !reason.trim()} onClick={() => act("/state", { to: "admitting", by: DOCTOR, reason: reason.trim() })}>Admit</button>
        <button type="button" disabled={busy} onClick={() => act("/state", { to: "clinic_done", by: DOCTOR })}>Close visit</button>
      </div>
    </>
  );
}

// The clinic cards that sit below the quiet row (R25).
function Clinic({ view, busy, act }) {
  return (
    <>
      <section className="card">
        <p className="label">Prescription</p>
        <RxImport busy={busy} act={act} />
        <RxTable rx={view.rx} />
      </section>
      <StripCheck busy={busy} act={act} />
    </>
  );
}

// Primary action for the ward card: dictate the discharge, then sign it. The form keeps its text while closed.
function Discharge({ view, busy, act, upload, ask, open, onToggle }) {
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
      <button type="button" aria-expanded={open} onClick={onToggle}>Dictate discharge</button>
      {open && (
        <>
          <Dictate label="Dictate discharge" verb="Draft discharge" busy={busy} onHear={hearing(ask, "/dictate/discharge")} onSend={drafting(upload, "/dictate/discharge")} />
          <div>
            <p className="label">Discharge</p>
            {summaryDraftId && (
              <p className="note small" role="status">
                Draft from dictation · {sourceLabel(draft?.source)}. Check the summary, then sign.
                {draft?.transcript && <> {heardLine(draft)}</>}
              </p>
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
            <button type="button" className="primary" disabled={busy || !summary.trim()} onClick={signDischarge}>Sign discharge</button>
          </div>
        </>
      )}
    </>
  );
}

// Primary action for the ward card: pick the procedure and send the patient to theatre.
function SendToTheatre({ view, busy, act }) {
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
      <button type="button" className="primary" disabled={busy || !procedure} onClick={() => act("/state", { to: "theatre", by: DOCTOR, procedure })}>Send to theatre</button>
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
            className="primary"
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
export default function DoctorActions({ state, card, view, act, upload, ask, busy }) {
  const [chosen, setChosen] = useState(() => new Set());
  const signOrders = sign(act);
  const open = (id) => panelOpen(chosen, id, view);
  const toggle = (id) => setChosen((current) => toggled(current, id));
  const primary = {
    admit: <Admit key="admit" view={view} busy={busy} act={act} />,
    theatre: <SendToTheatre key="theatre" view={view} busy={busy} act={act} />,
    discharge: <Discharge key="discharge" view={view} busy={busy} act={act} upload={upload} ask={ask} open={open("discharge")} onToggle={() => toggle("discharge")} />,
  };
  const { inside, below } = doctorBlocks(state, card);
  return (
    <>
      <NextCard card={card}>{inside.map((key) => primary[key])}</NextCard>
      <ActionBar actions={quietActions(state, "doctor")} isOpen={open} onToggle={toggle} />
      {open("orders") && <OrdersDictation view={view} busy={busy} upload={upload} ask={ask} signOrders={signOrders} />}
      {open("photo") && <PhotoCard title={state === "ward" ? "Wound photo" : "Reference photo"} busy={busy} upload={upload} />}
      {below.map((key) => primary[key])}
      {state === "clinic" && <Clinic view={view} busy={busy} act={act} />}
      {state === "theatre" && <Theatre view={view} busy={busy} act={act} upload={upload} />}
      {!["clinic", "admitting", "ward", "theatre"].includes(state) && (
        <p className={doctorOpenItems(view) > 0 ? "note" : "empty small"} role="status">{doctorWaiting(view)}</p>
      )}
    </>
  );
}
