import { Fragment, useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useMatch, useNavigate, useOutletContext } from "react-router-dom";
import { Banner, Mark } from "../App";
import { call } from "../journey";
import { stripPills } from "./alerts";
import { label, skipTargets } from "./clock";
import { foldsOnPhone } from "./fold";
import { waitingPills } from "./derive";
import Fault from "./Fault";
import { CLOCK } from "./faults";
import { findPatient } from "./Patients";
import { chipClass } from "./status";
import "./care.css";
import { useWard } from "./ward";

const ROLES = [
  ["doctor", "Doctor"],
  ["nurse", "Nurse"],
  ["patient", "Patient"],
];

const STAFF_TABS = [["/queue", "My queue"], ["/patients", "Patients"]];
const PATIENT_TABS = [["/today", "Today"], ["/my-care", "My care"], ["/ask", "Ask"]];

export const DEMO = import.meta.env.VITE_DEMO !== "0";

// The one place useWard() is called. Care screens read it with useCareWard() (react-router outlet context).
export function CareRoutes() {
  const ward = useWard();
  return (
    <CareShell ward={ward}>
      <Outlet context={ward} />
    </CareShell>
  );
}

export function useCareWard() {
  return useOutletContext();
}

// "/" lands on each role's first tab.
export function CareHome() {
  const { role } = useCareWard();
  return <Navigate to={role === "patient" ? "/today" : "/queue"} replace />;
}

function Strip({ ward }) {
  const navigate = useNavigate();
  const chartId = useMatch("/chart/:episodeId")?.params.episodeId;
  const [open, setOpen] = useState({});
  const { mine, others } = stripPills(waitingPills(ward.patients, ward.nowMs), chartId, ward.role);
  if (!mine.length && !others.length) return null;
  const pillButton = (pill) => (
    <li key={pill.key}>
      <button
        type="button"
        className={`pill wait ${pill.late ? "sun" : ""}`}
        onClick={() => navigate(`/chart/${pill.episodeId}${pill.lineId ? `?line=${pill.lineId}` : ""}`)}
      >
        {pill.text}{pill.waited ? ` · ${pill.waited}` : ""}
      </button>
    </li>
  );
  return (
    <ul className="wait-strip" aria-label="Waiting">
      {mine.map(pillButton)}
      {others.map((group) => (
        <Fragment key={group.role}>
          <li>
            <button
              type="button"
              className="pill wait"
              aria-expanded={Boolean(open[group.role])}
              onClick={() => setOpen((o) => ({ ...o, [group.role]: !o[group.role] }))}
            >
              {group.text}
            </button>
          </li>
          {open[group.role] && group.pills.map(pillButton)}
        </Fragment>
      ))}
    </ul>
  );
}

function ClockBar({ ward, fold }) {
  return (
    <div className={`clock-bar ${fold}`} role="group" aria-label="Demo clock">
      <span className="num clock-now">{label(ward.nowMs)}</span>
      {skipTargets(ward.nowMs, ward.patients).map((target) => (
        <button key={target.id} type="button" disabled={ward.busy} onClick={() => ward.jump(target.atMs)}>
          {target.label}
        </button>
      ))}
      <button type="button" disabled={ward.busy} onClick={ward.reset}>Reset</button>
      <Fault fault={ward.fault} episodeId={null} only={[CLOCK]} />
    </div>
  );
}

// "Models: live" when a key is set; otherwise prepared results. Unknown until the server answers.
function ModelsChip() {
  const [live, setLive] = useState(null);
  useEffect(() => {
    call("/journey/models").then((m) => setLive(Boolean(m.live))).catch(() => setLive(null));
  }, []);
  if (live === null) return null;
  return <span className={`pill ${live ? "ready" : "info"}`}>{live ? "Models: live" : "Models: offline (prepared results)"}</span>;
}

// The doctor's status, on every screen. Nothing until the server has answered.
function DoctorChip({ status }) {
  if (!status) return null;
  return <span className={`pill ${chipClass(status.status)}`}>{status.text}</span>;
}

export default function CareShell({ ward, children }) {
  const navigate = useNavigate();
  const tabs = ward.role === "patient" ? PATIENT_TABS : STAFF_TABS;
  const { pathname } = useLocation();
  const { clearFault } = ward;
  const [demoOpen, setDemoOpen] = useState(false);
  // Phone chrome: controls that fold behind "Demo controls" carry demo-fold (care.css hides them at <= 640 px).
  const fold = (control) => (foldsOnPhone(control, ward.role) ? "demo-fold" : "");

  // A fault belongs to the screen it happened on.
  useEffect(() => { clearFault(); }, [pathname, ward.role, ward.patientBed]);

  function pick(role) {
    ward.setRole(role);
    if (role === "patient") navigate("/today");
    else if (ward.role === "patient") navigate("/queue");
  }

  return (
    <div className={`app${demoOpen ? " demo-open" : ""}`}>
      <header className="app-bar">
        <Link to="/" className="brand">
          <span className="brand-logo"><Mark /></span>
          <span className="brand-names">
            <span className="brand-name"><b>lightday</b> <span>· Count Guard</span></span>
            <span className="brand-sub">Ward care. Records only, no medical advice.</span>
          </span>
        </Link>
        <div className="header-controls">
          <button type="button" className="demo-toggle" aria-expanded={demoOpen} onClick={() => setDemoOpen((v) => !v)}>Demo controls</button>
          <div className={`picker-slot ${fold("picker")}`}>
            {ward.role === "patient" && ward.patients.length > 0 && (
              <select aria-label="Patient" value={findPatient(ward.patients, ward.patientBed).bed} onChange={(e) => ward.setPatientBed(e.target.value)}>
                {ward.patients.map((p) => <option key={p.id} value={p.bed}>{p.name}</option>)}
              </select>
            )}
          </div>
          <div className={`role-switch ${fold("role")}`} role="group" aria-label="Role">
            {ROLES.map(([id, name]) => (
              <button key={id} type="button" aria-pressed={ward.role === id} onClick={() => pick(id)}>{name}</button>
            ))}
          </div>
        </div>
      </header>
      <div className="nav-bar">
        <nav className="nav" aria-label="Main">
          {tabs.map(([to, name]) => <NavLink key={to} to={to}>{name}</NavLink>)}
        </nav>
        <span className={`fold-wrap ${fold("doctor")}`}><DoctorChip status={ward.doctorStatus} /></span>
        <span className={`fold-wrap ${fold("models")}`}><ModelsChip /></span>
        <span className={`fold-wrap ${fold("banner")}`}><Banner /></span>
      </div>
      {ward.role !== "patient" && <Strip ward={ward} />}
      {DEMO && <ClockBar ward={ward} fold={fold("clock")} />}
      <main className="page">
        {children}
      </main>
      <footer className="care-foot">
        <Link to="/guide">Guide</Link>
        <Link to="/older">Older screens</Link>
      </footer>
    </div>
  );
}
