import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Banner } from "../App";
import { call } from "../journey";
import { label, skipTargets } from "./clock";
import { ROLE_NAME, dockSummary, modelsText } from "./dock";
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

// Every demo control in one dark strip: role, patient, clock, the synthetic-data and research notices.
export default function DemoDock({ ward, showClock, pick }) {
  const [open, setOpen] = useState(false);
  const live = useModelsLive();
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
        <Link to="/ai">AI at work</Link>
        <span>{modelsText(live)}</span>
      </div>
      <Banner />
    </section>
  );
}
