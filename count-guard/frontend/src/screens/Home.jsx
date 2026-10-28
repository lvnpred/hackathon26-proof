import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Shell } from "../App";
import { listPatients, loadEpisode, remember, startPatient } from "../episode";

const SHOWN = 3;
const OPEN = { "/opd": "Open the strips screen", "/ot": "Open the room screen", "/ward": "Open the discharge sheet" };

// "27 Oct 2026, 10:20 am": the only thing that tells two demo labels apart.
function started(iso) {
  if (!iso) return "Start time unknown";
  const at = new Date(iso);
  const day = at.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const time = at.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase();
  return `Started ${day}, ${time}`;
}

export default function Home() {
  const [view, setView] = useState(null);
  const [others, setOthers] = useState([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState(false);

  function refresh(next) {
    setView(next);
    listPatients().then((body) => setOthers(body.episodes)).catch(() => setOthers([]));
  }

  useEffect(() => {
    loadEpisode().then(refresh).catch((exc) => setError(exc.message));
  }, []);

  const guide = view?.guide;
  const steps = guide?.steps || [];
  const nowIndex = steps.findIndex((step) => step.current);
  const next = steps[nowIndex] || steps[steps.length - 1];
  const currentId = view?.episode?.id;
  const shown = showAll ? others : others.slice(0, SHOWN);

  return (
    <Shell guide={guide} status={guide ? { tone: guide.done === guide.total ? "ready" : "sun", label: `${guide.done} of ${guide.total} recorded` } : null}>
      <header className="page-head">
        <p className="label">One patient, one morning</p>
        <h1>{view?.episode?.label || "Loading this patient"}</h1>
        <p>
          {guide?.rule || "These six steps are for this patient only. The next patient starts a new morning."}
          {" "}The name is a demo label, not a real record.
        </p>
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      <div className="split">
        <div className="main">
          {guide && next && (
            <section className="card hero">
              <div className="row between">
                <p className="label sun">
                  {next.done ? "All steps recorded" : `Do this now · step ${nowIndex + 1} of ${guide.total}`}
                </p>
                {!next.done && <span className="pill sun">{next.place}</span>}
              </div>
              <h2 style={{ fontSize: 26, lineHeight: "32px" }}>{next.done ? "Read the discharge sheet" : next.title}</h2>
              <p style={{ maxWidth: "60ch" }}>{guide.summary}</p>
              <div className="row">
                <Link className="button primary" to={next.href}>
                  {next.done ? "Open the sheet" : OPEN[next.href] || next.title}
                </Link>
                <span className="num muted small">{guide.done} of {guide.total} steps recorded</span>
              </div>
            </section>
          )}

          <section className="card">
            <p className="label">What each place is for</p>
            <dl className="grid-2" style={{ margin: 0 }}>
              <div><dt><b>Before the operation</b></dt><dd className="muted small" style={{ margin: 0 }}>The medicine strips the person brought.</dd></div>
              <div><dt><b>In the room</b></dt><dd className="muted small" style={{ margin: 0 }}>The swab count, the drugs that were confirmed, and the blood-pressure log.</dd></div>
              <div><dt><b>After the room</b></dt><dd className="muted small" style={{ margin: 0 }}>A discharge sheet made only from those records.</dd></div>
              <div><dt><b>Camera count</b></dt><dd className="muted small" style={{ margin: 0 }}>A separate screen that tracks swabs in a video. The theatre replay does not use the camera.</dd></div>
            </dl>
          </section>
        </div>

        <aside className="side">
          <section className="card">
            <p className="label">Mornings on this computer</p>
            {others.length === 0 && <p className="empty small">Only this morning so far.</p>}
            <div className="rows">
              {shown.map((episode) => {
                const on = episode.id === currentId;
                return (
                  <button
                    key={episode.id}
                    className={`list-row${on ? " on" : ""}`}
                    aria-current={on ? "true" : undefined}
                    onClick={() => {
                      remember(episode.id);
                      loadEpisode().then(refresh);
                    }}
                  >
                    <span>
                      <b>{episode.label}</b>
                      <small>{started(episode.created_at)}</small>
                    </span>
                    <span className="tag">{on ? "Open" : "Switch"}</span>
                  </button>
                );
              })}
            </div>
            {others.length > SHOWN && (
              <button className="quiet" onClick={() => setShowAll(!showAll)}>
                {showAll ? "Show fewer" : `Show ${others.length - SHOWN} older mornings`}
              </button>
            )}
            <div className="stack" style={{ borderTop: "1px solid var(--line)", paddingTop: 14 }}>
              <label className="field">
                Name for the next patient
                <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Synthetic demo, second patient" />
                <span className="hint">A demo label, not a real record.</span>
              </label>
              <button className="block" onClick={() => startPatient(name.trim() || "Synthetic demo, next patient").then(refresh)}>
                Start the next patient
              </button>
            </div>
          </section>
        </aside>
      </div>
    </Shell>
  );
}
