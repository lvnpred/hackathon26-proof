import { Fragment, useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useMatch, useNavigate, useOutletContext } from "react-router-dom";
import { Mark } from "../App";
import { stripPills } from "./alerts";
import { alertsLabel } from "./dock";
import DemoDock from "./DemoDock";
import { waitingPills } from "./derive";
import { chipClass } from "./status";
import "./care.css";
import { useWard } from "./ward";

const STAFF_TABS = {
  doctor: [["/patients", "My patients"]],
  nurse: [["/queue", "My queue"], ["/patients", "Patients"]],
};
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
  return <Navigate to={role === "patient" ? "/today" : role === "doctor" ? "/patients" : "/queue"} replace />;
}

function Strip({ mine, others }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState({});
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

// The doctor's status, on every screen. Nothing until the server has answered.
export function DoctorChip({ status }) {
  if (!status) return null;
  return <span className={`pill ${chipClass(status.status)}`}>{status.text}</span>;
}

export default function CareShell({ ward, children }) {
  const navigate = useNavigate();
  const tabs = ward.role === "patient" ? PATIENT_TABS : STAFF_TABS[ward.role];
  const { pathname } = useLocation();
  const { clearFault } = ward;
  const chartId = useMatch("/chart/:episodeId")?.params.episodeId;
  const [alertsOpen, setAlertsOpen] = useState(false);
  const { mine, others } = stripPills(waitingPills(ward.patients, ward.nowMs), chartId, ward.role);
  const alerts = ward.role === "patient" ? 0 : mine.length + others.reduce((n, g) => n + g.pills.length, 0);

  // A fault belongs to the screen it happened on.
  useEffect(() => { clearFault(); }, [pathname, ward.role, ward.patientBed]);

  function pick(role) {
    ward.setRole(role);
    if (role === "patient") navigate("/today");
    else if (ward.role === "patient" || pathname === "/queue" || pathname === "/patients") navigate(role === "doctor" ? "/patients" : "/queue");
  }

  return (
    <div className="app">
      <DemoDock ward={ward} showClock={DEMO} pick={pick} />
      <header className="app-bar">
        <Link to="/" className="brand">
          <span className="brand-logo"><Mark /></span>
          <span className="brand-names">
            <span className="brand-name"><b>lightday</b> <span>· Count Guard</span></span>
            <span className="brand-sub">Ward care. Records only, no medical advice.</span>
          </span>
        </Link>
        <nav className="nav" aria-label="Main">
          {tabs.map(([to, name]) => <NavLink key={to} to={to}>{name}</NavLink>)}
        </nav>
        {alerts > 0 && (
          <button type="button" className="pill wait" aria-expanded={alertsOpen} onClick={() => setAlertsOpen((v) => !v)}>
            {alertsLabel(alerts)}
          </button>
        )}
        <DoctorChip status={ward.doctorStatus} />
      </header>
      {alerts > 0 && alertsOpen && <Strip mine={mine} others={others} />}
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
