import { Link } from "react-router-dom";
import { PageLead, Pill, Shell } from "../App";
import { startPatient } from "../episode";
import { getJourney, postJourney, subtitle, useJourney } from "../journey";

const PLACE = { "/doctor": "Doctor screen", "/nurse": "Nurse screen", "/patient": "Patient screen", "/ot": "In the room", "/opd": "Before the operation", "/ward": "After the room" };
const MARK = { done: ["✓ done", "tag ready"], now: ["now", "tag sun"], next: ["next", "tag"] };

function Story({ story }) {
  return (
    <section className="card">
      <div className="row between">
        <p className="label">{story.who}</p>
        <Pill tone={story.done === story.total ? "ready" : "sun"}>{story.done} of {story.total}</Pill>
      </div>
      <h2>{story.title}</h2>
      <div className="rows">
        {story.steps.map((step) => {
          const state = step.done ? "done" : step.current ? "now" : "next";
          const [word, tone] = MARK[state];
          return (
            <Link key={step.id} to={step.href} className={`list-row${step.current ? " on" : ""}`}>
              <span>
                <b>{step.title}</b>
                <small>{PLACE[step.href] || step.href}</small>
              </span>
              <span className={tone}>{word}</span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function NudgeGroup({ title, nudges }) {
  return (
    <div className="stack">
      <p className="label">{title}</p>
      {nudges.length === 0 && <p className="empty small">No open nudges.</p>}
      <div className="rows">
        {nudges.map((nudge) => (
          <div className="list-row" key={nudge.id}>
            <span>
              <b>{nudge.says}</b>
              <small>{nudge.when} · {nudge.kind}</small>
            </span>
            <span className="tag sun">open</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Journey() {
  const { view, setView, error, setError, busy, setBusy } = useJourney();

  async function fresh(play) {
    setError("");
    setBusy(true);
    try {
      const morning = await startPatient("Synthetic demo, R. Kumar");
      const id = morning.episode.id;
      setView(play ? await postJourney(id, "/play") : await getJourney(id));
    } catch (exc) {
      setError(exc.message);
    } finally {
      setBusy(false);
    }
  }

  const stories = view?.stories || [];
  const nudges = view?.nudges || [];
  const done = stories.reduce((sum, story) => sum + story.done, 0);
  const total = stories.reduce((sum, story) => sum + story.total, 0);

  return (
    <Shell subtitle={subtitle(view)} status={view ? { tone: done === total ? "ready" : "sun", label: `${done} of ${total} recorded` } : null}>
      <PageLead
        kicker="Care journey"
        title="Doctor, nurse and patient on one timeline."
        body="One patient, three people. Each nudge sets a recorded fact beside what a person ordered."
      />
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button className="primary" onClick={() => fresh(true)} disabled={busy}>
          {busy ? "Working…" : "Play the three-act demo"}
        </button>
        <button onClick={() => fresh(false)} disabled={busy}>New patient</button>
        <span className="small muted">The demo starts a fresh synthetic patient, so nothing is written twice.</span>
      </div>

      {!view && !error && <p className="empty">Loading the journey…</p>}
      <div className="grid-3">
        {stories.map((story) => <Story key={story.id} story={story} />)}
      </div>

      <section className="card">
        <div className="row between">
          <p className="label">Open nudges</p>
          <Link to="/audit">Read the audit trail</Link>
        </div>
        <div className="grid-2">
          <NudgeGroup title="To the patient" nudges={nudges.filter((nudge) => nudge.to === "patient")} />
          <NudgeGroup title="To the nurse" nudges={nudges.filter((nudge) => nudge.to === "nurse")} />
        </div>
      </section>
    </Shell>
  );
}
