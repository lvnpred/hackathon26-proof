import { Fragment, useEffect, useState } from "react";
import { Navigate, Outlet, useLocation, useMatch, useNavigate, useOutletContext } from "react-router-dom";
import { stripPills } from "./alerts";
import { alertCount } from "./dock";
import DemoDock from "./DemoDock";
import ProductHeader, { PausedBanner } from "./ProductHeader.jsx";
import ProductStrip from "./ProductStrip.jsx";
import { useOpsPaused } from "./useOpsPaused.js";
import Inspector from "./Inspector.jsx";
import { waitingPills } from "./derive";
import { chipClass } from "./status";
import "./care.css";
import { readOpened, unreadCount } from "./thread.js";
import { findPatient } from "./Patients";
import { useWard } from "./ward";

const STAFF_TABS = {
  doctor: [["/patients", "My patients"], ["/ai", "AI activity"]],
  nurse: [["/queue", "My queue"], ["/patients", "Patients"], ["/ai", "AI activity"]],
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
  const { mine, others } = stripPills(waitingPills(ward.patients, ward.nowMs, ward.role), chartId, ward.role);
  const me = ward.role === "patient" ? findPatient(ward.patients, ward.patientBed) : null;
  const unread = me ? unreadCount(me.view, readOpened(me.id)) : 0;
  const alerts = alertCount({ mine, others }, ward.role);
  useEffect(() => { if (alerts === 0) setAlertsOpen(false); }, [alerts]);

  // A fault belongs to the screen it happened on.
  useEffect(() => { clearFault(); }, [pathname, ward.role, ward.patientBed]);

  function pick(role) {
    ward.setRole(role);
    if (role === "patient") navigate("/today");
    else if (ward.role === "patient" || pathname === "/queue" || pathname === "/patients") navigate(role === "doctor" ? "/patients" : "/queue");
  }

  const ops = useOpsPaused(ward.role, ward.nowMs);
  const clinicChart = ward.role === "doctor" && ward.patients.find((p) => p.id === chartId)?.view.state === "clinic";

  return (
    <div className="app">
      <ProductStrip />
      <ProductHeader
        role={ward.role}
        tabs={tabs}
        unread={unread}
        alerts={alerts}
        alertsOpen={alertsOpen}
        onAlerts={() => setAlertsOpen((v) => !v)}
        ops={ops}
      />
      {alerts > 0 && alertsOpen && <Strip mine={mine} others={others} />}
      {ward.role !== "patient" && <PausedBanner ops={ops} nowMs={ward.nowMs} />}
      <main className="page">
        {children}
        <Inspector ward={ward} />
      </main>
      <DemoDock ward={ward} showClock={DEMO} pick={pick} ops={ops} demoRx={clinicChart ? () => ward.act(chartId, "/rx/demo", {}) : null} />
    </div>
  );
}
