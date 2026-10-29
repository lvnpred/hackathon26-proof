import { useState } from "react";
import { num } from "../journey";
import NurseHandover from "./NurseHandover";

const NURSE = "Nurse Meena (synthetic)";
const OBS = [
  ["sbp", "SBP"],
  ["dbp", "DBP"],
  ["hr", "HR"],
  ["spo2", "SpO2"],
  ["temp", "Temp °C"],
];

export function Nudge({ nudge, busy, act }) {
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

// The nurse's cards: nudge inbox, handover, log a dose, log observations.
export default function WardPanel({ view, busy, act }) {
  const [dose, setDose] = useState("");
  const [doseBy, setDoseBy] = useState(NURSE);
  const [obs, setObs] = useState({ sbp: "", dbp: "", hr: "", spo2: "", temp: "" });
  const [obsBy, setObsBy] = useState(NURSE);

  const inbox = (view?.nudges || []).filter((nudge) => nudge.to === "nurse");
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
    <>
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
    </>
  );
}
