import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Shell } from "../App";
import { listPatients, loadEpisode, remember, startPatient } from "../episode";

export default function Home() {
  const [view, setView] = useState(null);
  const [others, setOthers] = useState([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  function refresh(next) {
    setView(next);
    listPatients().then((body) => setOthers(body.episodes)).catch(() => setOthers([]));
  }

  useEffect(() => {
    loadEpisode().then(refresh).catch((exc) => setError(exc.message));
  }, []);

  const guide = view?.guide;
  const next = guide?.steps?.find((step) => step.current) || guide?.steps?.[guide.steps.length - 1];

  return (
    <Shell guide={guide}>
      <section className="sheet lead">
        <p className="kicker">One patient, one morning</p>
        <h2>Do these steps for this patient, then start the next one.</h2>
        <p>
          {guide?.rule || "These six steps are for this patient only. The next patient starts a new morning."}
          {" "}The name below is a label for the demo. It is not a real record.
        </p>
        {error && <p className="error">{error}</p>}
        {guide && (
          <>
            <p className="now">{guide.summary}</p>
            <p className="clock">{guide.done} of {guide.total} steps recorded.</p>
            {next && (
              <Link className="go" to={next.href}>
                {next.done ? "Read the sheet" : next.title}
              </Link>
            )}
          </>
        )}
      </section>
      <section className="panel" style={{ marginTop: 16 }}>
        <h2>What each place is for</h2>
        <p><b>Medicines.</b> Before the operation, the strips the person brought.</p>
        <p><b>Theatre.</b> In the room, the swab count, the drugs that were confirmed, and the blood-pressure log.</p>
        <p><b>Discharge.</b> After the room, a sheet made only from those records.</p>
        <p><b>Camera count.</b> A separate screen that tracks swabs in a video. The theatre replay does not use the camera.</p>
        <p><Link to="/guide">Open the guide</Link> · <Link to="/count">Open the camera count</Link></p>
        <h2>This patient</h2>
        <p className="now">{view?.episode?.label}</p>
        <label>
          Name for the next patient
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Synthetic demo, second patient" />
        </label>
        <button
          onClick={() => startPatient(name.trim() || "Synthetic demo, next patient").then(refresh)}
        >
          Start the next patient
        </button>
        {others.length > 1 && (
          <ul className="patients">
            {others.map((episode) => (
              <li key={episode.id}>
                <button
                  className="secondary"
                  onClick={() => {
                    remember(episode.id);
                    loadEpisode().then(refresh);
                  }}
                >
                  {episode.label}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Shell>
  );
}
