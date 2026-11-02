import { Route, Routes } from "react-router-dom";
import { CareHome, CareRoutes } from "./care/CareShell";
import AiDashboard from "./care/AiDashboard.jsx";
import Help from "./care/Help.jsx";
import Chart from "./care/Chart";
import Ask from "./care/Ask";
import MyCare from "./care/MyCare";
import { PatientsRoute, QueueRoute } from "./care/MyPatients";
import Today from "./care/Today.jsx";

// The Lightday mark: a half sun resting above a horizon.
export function Mark() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path className="sun" d="M6 19a10 10 0 0 1 20 0z" />
      <rect className="horizon" x="3" y="22" width="26" height="3.5" rx="1.75" />
    </svg>
  );
}

export function PageLead({ kicker, title, body }) {
  return (
    <header className="page-head">
      <p className="label">{kicker}</p>
      <h1>{title}</h1>
      <p>{body}</p>
    </header>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<CareRoutes />}>
        <Route path="/" element={<CareHome />} />
        <Route path="/queue" element={<QueueRoute />} />
        <Route path="/patients" element={<PatientsRoute />} />
        <Route path="/chart/:episodeId" element={<Chart />} />
        <Route path="/today" element={<Today />} />
        <Route path="/my-care" element={<MyCare />} />
        <Route path="/ask" element={<Ask />} />
        <Route path="/ai" element={<AiDashboard />} />
        <Route path="/help" element={<Help />} />
        <Route path="/guide" element={<Help />} />
      </Route>
      {/* A screen kept past the freeze (U11) is routed here and listed in KEPT (care/menu.js), never in MENU. None is kept. */}
    </Routes>
  );
}
