import { Link, NavLink, Route, Routes } from "react-router-dom";
import Close from "./screens/Close";
import Guide from "./screens/Guide";
import Home from "./screens/Home";
import Live from "./screens/Live";
import Morning from "./screens/Morning";
import Opd from "./screens/Opd";
import Ot from "./screens/Ot";
import Setup from "./screens/Setup";
import Ward from "./screens/Ward";

export const BANNER = "Research demo. Not for clinical use.";

export function Banner() {
  return (
    <div className="banner" role="note">
      {BANNER}
    </div>
  );
}

export function Models({ health }) {
  const adapters = health?.adapters || {};
  const cards = [
    ["SAM 3.1", adapters["sam-3.1"], "Detect and track. One id each."],
    ["Muse Voice Transcribe", adapters["muse-voice-transcribe"], "Spoken counts, turn times."],
    ["Muse Spark Open", adapters["muse-spark-open"], "Explains the rules. Does not decide."],
    ["Muse Spark 1.3", adapters["muse-spark-1.3"], "Second look only when R5 fires."],
  ];
  return (
    <div className="models">
      {cards.map(([name, adapter, job]) => (
        <div className="model" key={name}>
          <b>{name}</b>
          <span>{adapter ? (adapter.configured ? "Key present" : "Key not set") : job}</span>
          <span>{adapter?.model || job}</span>
        </div>
      ))}
    </div>
  );
}

export function PageLead({ kicker, title, body }) {
  return (
    <header className="lead-inline">
      <p className="kicker">{kicker}</p>
      <h2>{title}</h2>
      <p>{body}</p>
    </header>
  );
}

export function Shell({ children, guide }) {
  return (
    <div className="app">
      <Banner />
      <div className="top">
        <div>
          <h1><Link to="/">Count Guard</Link></h1>
          <div className="clock">One morning per patient. Records only. No medical advice.</div>
        </div>
        <nav className="nav">
          <NavLink to="/">Morning</NavLink>
          <NavLink to="/guide">Guide</NavLink>
          <NavLink to="/count">Camera</NavLink>
        </nav>
      </div>
      {guide && (
        <p className="patient-rule" role="note">
          <b>Patient: {guide.patient}.</b> {guide.rule}
        </p>
      )}
      {guide && (
        <ol className="rail">
          {guide.steps.map((step, index) => (
            <li key={step.id} className={step.done ? "done" : step.current ? "now" : ""}>
              <Link to={step.href}>
                <span>{index + 1}</span>
                {step.title}
              </Link>
              <small>{step.done ? "Recorded" : step.current ? "Do this now" : step.place}</small>
            </li>
          ))}
        </ol>
      )}
      {children}
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/guide" element={<Guide />} />
      <Route path="/count" element={<Setup />} />
      <Route path="/morning" element={<Morning />} />
      <Route path="/opd" element={<Opd />} />
      <Route path="/ot" element={<Ot />} />
      <Route path="/ward" element={<Ward />} />
      <Route path="/case/:caseId" element={<Live />} />
      <Route path="/case/:caseId/close" element={<Close />} />
    </Routes>
  );
}
