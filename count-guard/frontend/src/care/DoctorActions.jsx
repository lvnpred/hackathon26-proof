import { useState } from "react";
import { parseStrips } from "../journey";
import { RxImport, RxTable } from "../screens/ClinicPanel";
import Dictate from "./Dictate";
import { draftChanged, sectionsToSummary, sourceLabel } from "./drafts";
import OrderForm from "./OrderForm";
import { surgeryNow } from "./tasklist";

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

const dictate = (upload, path) => ({ file, text }) => upload(path, file, { text, by: DOCTOR });

function ReferencePhoto({ busy, upload }) {
  async function pick(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) await upload("/photos", file, { purpose: "reference", by: DOCTOR });
  }
  return (
    <label className="field">
      Add reference photo
      <input type="file" accept="image/*" capture="environment" disabled={busy} onChange={pick} />
    </label>
  );
}

// Dictation, the order form that loads its draft, and the reference photo input.
function OrdersDictation({ view, busy, upload, signOrders }) {
  return (
    <>
      <Dictate label="Dictate orders" busy={busy} onSend={dictate(upload, "/dictate/orders")} />
      <OrderForm busy={busy} onSign={signOrders} draft={view.drafts?.order} />
    </>
  );
}

function Clinic({ view, busy, act, upload, signOrders }) {
  const [reason, setReason] = useState("");
  const [reasonDraftId, setReasonDraftId] = useState(null);
  const draft = view.drafts?.order;
  if (draftChanged(reasonDraftId, draft)) {
    setReasonDraftId(draft.id);
    if (draft.reason) setReason(draft.reason);
  }
  return (
    <>
      <section className="card">
        <p className="label">Prescription</p>
        <RxImport busy={busy} act={act} />
        <RxTable rx={view.rx} />
      </section>
      <ReferencePhoto busy={busy} upload={upload} />
      <StripCheck busy={busy} act={act} />
      <OrdersDictation view={view} busy={busy} upload={upload} signOrders={signOrders} />
      <section className="card">
        <p className="label">Visit</p>
        <label className="field">
          Reason for admission
          <input value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <div className="row">
          <button type="button" className="primary" disabled={busy || !reason.trim()} onClick={() => act("/state", { to: "admitting", by: DOCTOR, reason: reason.trim() })}>Admit</button>
          <button type="button" disabled={busy} onClick={() => act("/state", { to: "clinic_done", by: DOCTOR })}>Close visit</button>
        </div>
      </section>
    </>
  );
}

function Ward({ view, busy, act, upload }) {
  const [procedure, setProcedure] = useState("");
  const [summary, setSummary] = useState("");
  const [summaryDraftId, setSummaryDraftId] = useState(null);
  const draft = view.drafts?.discharge;
  if (draftChanged(summaryDraftId, draft)) {
    setSummaryDraftId(draft.id);
    setSummary(sectionsToSummary(draft.sections || []));
  }
  const [template, setTemplate] = useState("hernia-repair");
  const procedures = Object.entries(view.procedures || {});
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
      <section className="card">
        <p className="label">Theatre</p>
        <label className="field">
          Procedure
          <select value={procedure} onChange={(e) => setProcedure(e.target.value)}>
            <option value="">Choose a procedure</option>
            {procedures.map(([key, title]) => <option key={key} value={key}>{title}</option>)}
          </select>
        </label>
        <button type="button" className="primary" disabled={busy || !procedure} onClick={() => act("/state", { to: "theatre", by: DOCTOR, procedure })}>Send to theatre</button>
      </section>
      <Dictate label="Dictate discharge" busy={busy} onSend={dictate(upload, "/dictate/discharge")} />
      <section className="card">
        <p className="label">Discharge</p>
        {summaryDraftId && (
          <p className="note small" role="status">
            Draft from dictation · {sourceLabel(draft?.source)}. Check the summary, then sign.
            {draft?.transcript && <> Heard: “{draft.transcript}”</>}
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
      </section>
    </>
  );
}

function Theatre({ view, busy, act }) {
  const [reason, setReason] = useState("");
  const { began, ended } = surgeryNow(view.timeline);
  const move = (view.allowed || []).find((m) => m.to === "ward" && m.role === "doctor");
  return (
    <section className="card">
      <p className="label">In theatre</p>
      <p className="small">Surgery began: {began || "not yet"}</p>
      <p className="small">Surgery ended: {ended || "not yet"}</p>
      {move && (
        <>
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
        </>
      )}
    </section>
  );
}

const sign = (act) => (items, draftId) => act("/orders/sign", { items, by: DOCTOR, draft_id: draftId || undefined });

// The doctor's actions for the patient's current state.
export default function DoctorActions({ state, view, act, upload, busy }) {
  const signOrders = sign(act);
  if (state === "clinic") {
    return <Clinic view={view} busy={busy} act={act} upload={upload} signOrders={signOrders} />;
  }
  if (state === "admitting") {
    return (
      <>
        <p className="note" role="status">Waiting for the nurse to complete admission.</p>
        <OrdersDictation view={view} busy={busy} upload={upload} signOrders={signOrders} />
      </>
    );
  }
  if (state === "ward") {
    return (
      <>
        <OrdersDictation view={view} busy={busy} upload={upload} signOrders={signOrders} />
        <ReferencePhoto busy={busy} upload={upload} />
        <Ward view={view} busy={busy} act={act} upload={upload} />
      </>
    );
  }
  if (state === "theatre") {
    return <Theatre view={view} busy={busy} act={act} />;
  }
  return <p className="empty small">Nothing to do from this state. The chart below is the record.</p>;
}
