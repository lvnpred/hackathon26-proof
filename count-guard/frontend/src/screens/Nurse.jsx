import { useState } from "react";
import { PageLead, Pill, Shell } from "../App";
import { num, subtitle, useJourney } from "../journey";
import { OrdersSummary } from "./DoctorOrders";
import NurseHandover from "./NurseHandover";

const NURSE = "Nurse Meena (synthetic)";
const OBS = [
  ["sbp", "SBP"],
  ["dbp", "DBP"],
  ["hr", "HR"],
  ["spo2", "SpO2"],
  ["temp", "Temp °C"],
];

function Nudge({ nudge, busy, act }) {
  const [note, setNote] = useState("");
  const [by, setBy] = useState(NURSE);
  return (
    <div className="card sunk">
      <div className="row between">
        <span className="tag sun">{nudge.when}</span>
        <span className="small muted">{nudge.kind}</span>
      </div>
      <p><b>{nudge.says}</b></p>
      <div className="row">
        <label className="field" style={{ flex: "2 1 200px" }}>
          What you did or saw
          <input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Called the patient back" />
        </label>
        <label className="field" style={{ flex: "1 1 160px" }}>
          By
          <input value={by} onChange={(event) => setBy(event.target.value)} />
        </label>
        <button
          className="primary"
          disabled={busy || !by.trim()}
          onClick={() => act(`/nudges/${nudge.id}/seen`, { by: by.trim(), note: note.trim() })}
        >
          Answer
        </button>
      </div>
    </div>
  );
}

export default function Nurse() {
  const { view, error, busy, act } = useJourney();
  const [dose, setDose] = useState("");
  const [doseBy, setDoseBy] = useState(NURSE);
  const [obs, setObs] = useState({ sbp: "", dbp: "", hr: "", spo2: "", temp: "" });
  const [obsBy, setObsBy] = useState(NURSE);

  const inbox = (view?.nudges || []).filter((nudge) => nudge.to === "nurse");
  const recent = (view?.timeline || []).slice(-10).reverse();
  const ready = view && !busy;

  async function logDose() {
    if (await act("/dose", { text: dose.trim(), by: doseBy.trim() })) setDose("");
  }

  async function logObs() {
    const body = { by: obsBy.trim() };
    for (const [key] of OBS) body[key] = num(obs[key]);
    if (await act("/obs", body)) setObs({ sbp: "", dbp: "", hr: "", spo2: "", temp: "" });
  }

  return (
    <Shell subtitle={subtitle(view)} status={view ? { tone: inbox.length ? "sun" : "ready", label: `${inbox.length} open for the nurse` } : null}>
      <PageLead
        kicker="Nurse"
        title="Give, log, and answer the nudges."
        body="A nudge sets a logged dose or reading beside the doctor's order. It does not tell you what to give. Answer it with what you did or saw."
      />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split">
        <section className="main">
          <section className="card">
            <div className="row between">
              <p className="label">Nudge inbox</p>
              <button onClick={() => act("/tick", {})} disabled={!ready}>Check due times now</button>
            </div>
            {view && inbox.length === 0 && <p className="empty">No open nudges for the nurse.</p>}
            {inbox.map((nudge) => <Nudge key={nudge.id} nudge={nudge} busy={!ready} act={act} />)}
          </section>
          <NurseHandover handover={view?.handover} busy={!ready} act={act} />
          <section className="card">
            <p className="label">Last entries</p>
            {recent.length === 0 && <p className="empty small">Nothing recorded yet.</p>}
            <div className="timeline">
              {recent.map((line) => (
                <div key={line.id}>
                  <span className="when" style={{ width: 96 }}>{line.when}</span>
                  <span className="what small">{line.plain}</span>
                </div>
              ))}
            </div>
          </section>
        </section>
        <aside className="side">
          <section className="card">
            <p className="label">Log a dose</p>
            <label className="field">
              What was given
              <input value={dose} onChange={(event) => setDose(event.target.value)} placeholder="ondansetron 4 mg iv" />
            </label>
            <label className="field">
              By
              <input value={doseBy} onChange={(event) => setDoseBy(event.target.value)} />
            </label>
            <button className="primary" onClick={logDose} disabled={!ready || !dose.trim() || !doseBy.trim()}>Log dose</button>
          </section>
          <section className="card">
            <p className="label">Log observations</p>
            <div className="row">
              {OBS.map(([key, label]) => (
                <label className="field" key={key} style={{ flex: "1 1 70px" }}>
                  {label}
                  <input inputMode="decimal" value={obs[key]} onChange={(event) => setObs({ ...obs, [key]: event.target.value })} />
                </label>
              ))}
            </div>
            <label className="field">
              By
              <input value={obsBy} onChange={(event) => setObsBy(event.target.value)} />
            </label>
            <button
              className="primary"
              onClick={logObs}
              disabled={!ready || !obsBy.trim() || num(obs.sbp) === null || num(obs.dbp) === null || num(obs.hr) === null}
            >
              Log observations
            </button>
            <p className="small muted">SBP, DBP and HR are needed; SpO2 and temperature can stay blank.</p>
          </section>
          <section className="card">
            <div className="row between">
              <p className="label">Ward orders</p>
              <Pill>read only</Pill>
            </div>
            <OrdersSummary orders={view?.orders} />
          </section>
        </aside>
      </div>
    </Shell>
  );
}
