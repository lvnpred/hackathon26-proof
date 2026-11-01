import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { call } from "../journey";
import { label, skipTargets } from "./clock";
import { ROLE_NAME, aiChip, dockPauseLabel, modelsText } from "./dock";
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

// The page keeps room for the fixed dock: --dock-h is the dock's height, so it never covers the last controls.
// On a phone the open sheet floats over the page, so --dock-h keeps the closed height and the page does not jump.
function useDockSpace(ref, open) {
  const openRef = useRef(open);
  openRef.current = open;
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const set = () => !openRef.current && document.documentElement.style.setProperty("--dock-h", `${el.offsetHeight}px`);
    set();
    const watch = new ResizeObserver(set);
    watch.observe(el);
    return () => { watch.disconnect(); document.documentElement.style.removeProperty("--dock-h"); };
  }, []);
}

// Demo tools, set apart from the product: role, patient, clock, AI shortcut and the demo prescription.
// demoRx is a function while the doctor has a clinic patient open, else null.
export default function DemoDock({ ward, showClock, pick, ops, demoRx }) {
  const [open, setOpen] = useState(false);
  const live = useModelsLive();
  const ref = useRef(null);
  useDockSpace(ref, open);
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  return (
    <>
      {open && <div className="dock-backdrop" aria-hidden="true" onClick={() => setOpen(false)} />}
      <section ref={ref} className={`demo-dock${open ? " open" : ""}`} aria-label="Demo">
        <button type="button" className="dock-summary" aria-expanded={open} onClick={() => setOpen((v) => !v)}>Demo</button>
        <div className="dock-body">
          <span className="dock-label t-caption">Demo</span>
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
          {demoRx && <button type="button" disabled={ward.busy} onClick={demoRx}>Use the demo prescription</button>}
          {ops.paused != null && (
            <>
              <span className="pill">{aiChip(ops.paused)}</span>
              <button type="button" disabled={ops.busy} onClick={ops.toggle}>{dockPauseLabel(ops.paused)}</button>
            </>
          )}
          <span>{modelsText(live)}</span>
          <Link to="/guide">Guide</Link>
          <Link to="/older">Older screens</Link>
        </div>
      </section>
    </>
  );
}
