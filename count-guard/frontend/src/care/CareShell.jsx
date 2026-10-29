import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, useNavigate, useOutletContext } from "react-router-dom";
import { Banner, Mark } from "../App";
import { call } from "../journey";
import { label, skipTargets } from "./clock";
import { waitingPills } from "./derive";
import { useWard } from "./ward";

const ROLES = [
  ["doctor", "Doctor"],
  ["nurse", "Nurse"],
  ["patient", "Patient"],
];

const STAFF_TABS = [["/queue", "My queue"], ["/patients", "Patients"]];
const PATIENT_TABS = [["/today", "Today"], ["/my-care", "My care"]];

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
  const pills = waitingPills(ward.patients, ward.nowMs);
  if (!pills.length) return null;
  return (
    <ul className="wait-strip" aria-label="Waiting">
      {pills.map((pill) => (
        <li key={pill.key}>
          <button
            type="button"
            className={`pill wait ${pill.late ? "sun" : ""}`}
            onClick={() => navigate(`/chart/${pill.episodeId}${pill.lineId ? `?line=${pill.lineId}` : ""}`)}
          >
            {pill.who} → {pill.what}{pill.waited ? ` · ${pill.waited}` : ""}
          </button>
        </li>
      ))}
    </ul>
  );
}

function ClockBar({ ward }) {
  return (
    <div className="clock-bar" role="group" aria-label="Demo clock">
      <span className="num clock-now">{label(ward.nowMs)}</span>
      {skipTargets(ward.nowMs, ward.patients).map((target) => (
        <button key={target.id} type="button" disabled={ward.busy} onClick={() => ward.jump(target.atMs)}>
          {target.label}
        </button>
      ))}
      <button type="button" disabled={ward.busy} onClick={ward.reset}>Reset</button>
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

export default function CareShell({ ward, children }) {
  const navigate = useNavigate();
  const tabs = ward.role === "patient" ? PATIENT_TABS : STAFF_TABS;

  function pick(role) {
    ward.setRole(role);
    if (role === "patient") navigate("/today");
    else if (ward.role === "patient") navigate("/queue");
  }

  return (
    <div className="app">
      <header className="app-bar">
        <Link to="/" className="brand">
          <span className="brand-logo"><Mark /></span>
          <span className="brand-names">
            <span className="brand-name"><b>lightday</b> <span>· Count Guard</span></span>
            <span className="brand-sub">Ward care. Records only, no medical advice.</span>
          </span>
        </Link>
        <div className="role-switch" role="group" aria-label="Role">
          {ROLES.map(([id, name]) => (
            <button key={id} type="button" aria-pressed={ward.role === id} onClick={() => pick(id)}>{name}</button>
          ))}
        </div>
      </header>
      <div className="nav-bar">
        <nav className="nav" aria-label="Main">
          {tabs.map(([to, name]) => <NavLink key={to} to={to}>{name}</NavLink>)}
        </nav>
        <ModelsChip />
        <Banner />
      </div>
      {ward.role !== "patient" && <Strip ward={ward} />}
      {DEMO && <ClockBar ward={ward} />}
      <main className="page">
        {ward.error && <p className="note" role="alert">{ward.error}</p>}
        {children}
      </main>
      <footer className="care-foot">
        <Link to="/guide">Guide</Link>
        <Link to="/older">Older screens</Link>
      </footer>
    </div>
  );
}
