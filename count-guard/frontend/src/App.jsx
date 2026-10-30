import { Link, NavLink, Route, Routes } from "react-router-dom";
import { CareHome, CareRoutes } from "./care/CareShell";
import AiDashboard from "./care/AiDashboard.jsx";
import Chart from "./care/Chart";
import Ask from "./care/Ask";
import MyCare from "./care/MyCare";
import { PatientsRoute, QueueRoute } from "./care/MyPatients";
import Today from "./care/Today.jsx";
import Audit from "./screens/Audit";
import Close from "./screens/Close";
import Doctor from "./screens/Doctor";
import Guide from "./screens/Guide";
import Home from "./screens/Home";
import Journey from "./screens/Journey";
import Live from "./screens/Live";
import Morning from "./screens/Morning";
import Nurse from "./screens/Nurse";
import Opd from "./screens/Opd";
import Ot from "./screens/Ot";
import Patient from "./screens/Patient";
import Setup from "./screens/Setup";
import Ward from "./screens/Ward";
import { OLD_NAV, OLDER_SCREENS } from "./care/older";

export const BANNER = "Research demo. Not for clinical use.";

export function Banner() {
  return (
    <p className="note" role="note">
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 16v-4" />
        <path d="M12 8h.01" />
      </svg>
      {BANNER}
    </p>
  );
}

// The Lightday mark: a half sun resting above a horizon.
export function Mark() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
      <path className="sun" d="M6 19a10 10 0 0 1 20 0z" />
      <rect className="horizon" x="3" y="22" width="26" height="3.5" rx="1.75" />
    </svg>
  );
}

export function Pill({ tone, children }) {
  return <span className={`pill ${tone || ""}`}>{children}</span>;
}

// The four model names, folded into one line so they never sit above the work.
export function Models({ health }) {
  const adapters = health?.adapters || {};
  const cards = [
    ["SAM 3.1", adapters["sam-3.1"], "detect and track, one id each"],
    ["Muse Voice Transcribe", adapters["muse-voice-transcribe"], "spoken counts and turn times"],
    ["Muse Spark Open", adapters["muse-spark-open"], "explains the rules, does not decide"],
    ["Muse Spark 1.3", adapters["muse-spark-1.3"], "second look only when R5 fires"],
  ];
  const keyed = cards.filter(([, adapter]) => adapter?.configured).length;
  return (
    <details>
      <summary>
        Models: {cards.length} named, {keyed === 0 ? "no key set" : `${keyed} with a key`}
      </summary>
      <ul>
        {cards.map(([name, adapter, job]) => (
          <li key={name}>
            {name} — {job}. {adapter ? (adapter.configured ? "Key present" : "Key not set") : "Status unknown"}
            {adapter?.model ? ` · ${adapter.model}` : ""}
          </li>
        ))}
      </ul>
    </details>
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

function Steps({ guide }) {
  const steps = guide.steps;
  const nowIndex = steps.findIndex((step) => step.current);
  const now = steps[nowIndex];
  return (
    <>
      <ol className="steps" aria-label="Steps for this patient">
        {steps.map((step, index) => {
          const state = step.done ? "done" : step.current ? "now" : "next";
          return (
            <li key={step.id} className={state}>
              <Link to={step.href} aria-current={step.current ? "step" : undefined}>
                <span className="dot" aria-hidden="true">{step.done ? "✓" : index + 1}</span>
                <span>
                  {step.title}
                  <small>{step.done ? "Recorded" : step.current ? "Do this now" : step.place}</small>
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
      <div className="steps-bar">
        <div className="row between">
          <p className="label sun">
            {now ? `Step ${nowIndex + 1} of ${steps.length} · ${now.title}` : `All ${steps.length} steps recorded`}
          </p>
          <Link to="/steps">All steps</Link>
        </div>
        <div className="segments" aria-hidden="true">
          {steps.map((step) => (
            <span key={step.id} className={step.done ? "done" : step.current ? "now" : ""} />
          ))}
        </div>
      </div>
    </>
  );
}

export function Shell({ children, guide, subtitle, status }) {
  const sub = subtitle || (guide ? `${guide.patient} · this morning only` : "One morning per patient. Records only, no medical advice.");
  return (
    <div className="app">
      <header className="app-bar">
        <Link to="/steps" className="brand">
          <span className="brand-logo"><Mark /></span>
          <span className="brand-names">
            <span className="brand-name"><b>lightday</b> <span>· Count Guard</span></span>
            <span className="brand-sub">{sub}</span>
          </span>
        </Link>
        {status && <Pill tone={status.tone}>{status.label}</Pill>}
      </header>
      <div className="nav-bar">
        <nav className="nav" aria-label="Main">
          {OLD_NAV.map(([to, name]) => <NavLink key={to} to={to}>{name}</NavLink>)}
        </nav>
        <Banner />
      </div>
      <main className="page">
        {guide && <Steps guide={guide} />}
        {children}
      </main>
    </div>
  );
}

function Older() {
  return (
    <Shell>
      <PageLead kicker="Archive" title="Older screens" body="These still work. The ward care screens are the main route now." />
      <ul>{OLDER_SCREENS.map(([to, name]) => <li key={to}><Link to={to}>{name}</Link></li>)}</ul>
    </Shell>
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
      </Route>
      <Route path="/steps" element={<Home />} />
      <Route path="/older" element={<Older />} />
      <Route path="/guide" element={<Guide />} />
      <Route path="/count" element={<Setup />} />
      <Route path="/morning" element={<Morning />} />
      <Route path="/opd" element={<Opd />} />
      <Route path="/ot" element={<Ot />} />
      <Route path="/ward" element={<Ward />} />
      <Route path="/case/:caseId" element={<Live />} />
      <Route path="/case/:caseId/close" element={<Close />} />
      <Route path="/journey" element={<Journey />} />
      <Route path="/doctor" element={<Doctor />} />
      <Route path="/nurse" element={<Nurse />} />
      <Route path="/patient" element={<Patient />} />
      <Route path="/audit" element={<Audit />} />
    </Routes>
  );
}
