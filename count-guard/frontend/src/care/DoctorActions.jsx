import { useState } from "react";
import { parseStrips } from "../journey";
import { RxImport, RxTable } from "../screens/ClinicPanel";
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

function Clinic({ view, busy, act }) {
  const [reason, setReason] = useState("");
  return (
    <>
      <section className="card">
        <p className="label">Prescription</p>
        <RxImport busy={busy} act={act} />
        <RxTable rx={view.rx} />
      </section>
      <StripCheck busy={busy} act={act} />
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

function Ward({ view, busy, act }) {
  const [procedure, setProcedure] = useState("");
  const [summary, setSummary] = useState("");
  const [template, setTemplate] = useState("hernia-repair");
  const procedures = Object.entries(view.procedures || {});
  const templates = Object.entries(view.templates || {});
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
      <section className="card">
        <p className="label">Discharge</p>
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
        <button type="button" className="primary" disabled={busy || !summary.trim()} onClick={() => act("/discharge/sign", { summary: summary.trim(), template, by: DOCTOR })}>Sign discharge</button>
      </section>
    </>
  );
}

const sign = (act) => (items) => act("/orders/sign", { items, by: DOCTOR });

// The doctor's actions for the patient's current state.
export default function DoctorActions({ state, view, act, busy }) {
  const signOrders = sign(act);
  if (state === "clinic") {
    return <Clinic view={view} busy={busy} act={act} />;
  }
  if (state === "admitting") {
    return (
      <>
        <p className="note" role="status">Waiting for the nurse to complete admission.</p>
        <OrderForm busy={busy} onSign={signOrders} />
      </>
    );
  }
  if (state === "ward") {
    return (
      <>
        <OrderForm busy={busy} onSign={signOrders} />
        <Ward view={view} busy={busy} act={act} />
      </>
    );
  }
  if (state === "theatre") {
    const { began, ended } = surgeryNow(view.timeline);
    return (
      <section className="card">
        <p className="label">In theatre</p>
        <p className="small">Surgery began: {began ? "yes" : "not yet"}</p>
        <p className="small">Surgery ended: {ended ? "yes" : "not yet"}</p>
      </section>
    );
  }
  return <p className="empty small">Nothing to do from this state. The chart below is the record.</p>;
}
