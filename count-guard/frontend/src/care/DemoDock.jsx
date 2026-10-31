import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Banner } from "../App";
import { call } from "../journey";
import { label, skipTargets } from "./clock";
import { canSeeAi } from "./ai.js";
import { ROLE_NAME, aiChip, dockSummary, modelsText, pauseLabel } from "./dock";
import Fault from "./Fault";
import { CLOCK } from "./faults";
import { findPatient } from "./Patients";

// "Models: live" when a key is set; otherwise prepared results. Unknown until the server answers.
function useModelsLive() {
  const [live, setLive] = useState(null);
  useEffect(() => {
    call("/journey/models").then((m) => setLive(Boolean(m.live))).catch(() => setLive(null));
  }, []);
  return live;
}

// Whether the ops agent is paused. Null until the server answers; staff only.
function useOpsPaused(staff) {
  const [paused, setPaused] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!staff) return;
    call("/journey/ops").then((o) => setPaused(Boolean(o.paused))).catch(() => setPaused(null));
  }, [staff]);
  const toggle = (role) => {
    const verb = paused ? "resume" : "pause";
    setBusy(true);
    setError("");
    return call(`/journey/ops/${verb}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ by: `Demo dock (${ROLE_NAME[role]})` }) })
      .then((o) => setPaused(Boolean(o.paused)))
      .catch(() => setError(`Could not ${verb} the AI.`))
      .finally(() => setBusy(false));
  };
  return { paused, toggle, busy, error };
}

// Every demo control in one dark strip: role, patient, clock, the synthetic-data and research notices.
export default function DemoDock({ ward, showClock, pick }) {
  const [open, setOpen] = useState(false);
  const live = useModelsLive();
  const staff = canSeeAi(ward.role);
  const { paused, toggle: togglePause, busy: pauseBusy, error: pauseError } = useOpsPaused(staff);
  return (
    <section className={`demo-dock${open ? " open" : ""}`} aria-label="Demo">
      <button type="button" className="dock-summary" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {dockSummary(ward.role, ward.nowMs)} ▾
      </button>
      <div className="dock-body">
        <div className="role-switch" role="group" aria-label="Role">
          {Object.entries(ROLE_NAME).map(([id, name]) => (
            <button key={id} type="button" aria-pressed={ward.role === id} onClick={() => pick(id)}>{name}</button>
          ))}
        </div>
        {ward.role === "patient" && ward.patients.length > 0 && (
          <select aria-label="Patient" value={findPatient(ward.patients, ward.patientBed).bed} onChange={(e) => ward.setPatientBed(e.target.value)}>
            {ward.patients.map((p) => <option key={p.id} value={p.bed}>{p.name}</option>)}
          </select>
        )}
        {showClock && (
          <div className="clock-bar" role="group" aria-label="Demo clock">
            <span className="num clock-now">{label(ward.nowMs)}</span>
            {skipTargets(ward.nowMs, ward.patients).map((target) => (
              <button key={target.id} type="button" disabled={ward.busy} onClick={() => ward.jump(target.atMs)}>
                {target.label}
              </button>
            ))}
            <button type="button" disabled={ward.busy} onClick={ward.reset}>Reset</button>
            <Fault fault={ward.fault} episodeId={null} only={[CLOCK]} />
          </div>
        )}
        {staff && paused != null && (
          <>
            <span className="pill">{aiChip(paused)}</span>
            <button type="button" disabled={pauseBusy} onClick={() => togglePause(ward.role)}>{pauseLabel(paused)}</button>
            {pauseError && <span className="error small" role="alert">{pauseError}</span>}
          </>
        )}
        <span>{modelsText(live)}</span>
      </div>
      <Banner />
    </section>
  );
}
