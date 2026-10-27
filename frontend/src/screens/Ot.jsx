import { useEffect, useState } from "react";
import { loadEpisode, send } from "../episode";
import { PageLead, Shell } from "../App";

const BANNER = "Research demo. Not for clinical use.";

function Sparkline({ readings }) {
  if (readings.length < 2) return <p className="clock">No readings yet.</p>;
  const width = 280;
  const height = 72;
  const max = Math.max(...readings.map((row) => row.systolic), 140);
  const points = readings
    .map((row, index) => {
      const x = (index / (readings.length - 1)) * width;
      const y = height - (row.systolic / max) * (height - 10) - 4;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Systolic readings">
      <polyline points={points} fill="none" stroke="#7f1d1d" strokeWidth="2" />
    </svg>
  );
}

export default function Ot() {
  const [view, setView] = useState(null);
  const [line, setLine] = useState("opening twenty swabs");
  const [heard, setHeard] = useState(null);
  const [cursor, setCursor] = useState(0);
  const [error, setError] = useState("");
  const [tier, setTier] = useState(0);
  const [card, setCard] = useState(null);

  useEffect(() => {
    loadEpisode().then(setView).catch((exc) => setError(exc.message));
    send("/morning/tier").then((body) => setTier(body.decision_tier)).catch(() => setTier(0));
  }, []);

  const id = view?.episode?.id;

  useEffect(() => {
    if (id && tier === 1) refreshCard(id);
  }, [id, tier]);

  // The card route is 404 while the tier is off or before the drop, so a miss just hides the panel.
  async function refreshCard(episodeId) {
    try {
      const found = await send(`/morning/episodes/${episodeId}/card`);
      setCard(found.card);
    } catch {
      setCard(null);
    }
  }

  async function toggleTier() {
    const next = await send("/morning/tier", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: tier !== 1 }),
    });
    setTier(next.decision_tier);
    setCard(null);
  }

  async function say() {
    const result = await send(`/morning/episodes/${id}/hear`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: line }),
    });
    setHeard(result);
    setView(await send(`/morning/episodes/${id}`));
  }

  async function confirm() {
    if (heard?.kind !== "drug") return;
    setView(
      await send(`/morning/episodes/${id}/druglog/${heard.event.id}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ by: "demo user" }),
      }),
    );
    setHeard(null);
  }

  async function replay() {
    setView(await send(`/morning/episodes/${id}/count/replay`, { method: "POST" }));
  }

  async function manual() {
    setView(
      await send(`/morning/episodes/${id}/count/manual`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_id: "manual-1" }),
      }),
    );
  }

  async function sim(action, t_ms) {
    const next = await send(`/morning/episodes/${id}/vitals/sim`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, t_ms, step_ms: 60_000 }),
    });
    setView(next);
    setCursor(next.sim.cursor_ms);
    if (tier === 1) await refreshCard(id);
  }

  const events = view?.events || [];
  const readings = events.filter((event) => event.event_type === "vitals.reading").map((event) => event.payload);
  const closing = [...events].reverse().find((event) => event.event_type === "count.closing");

  return (
    <Shell guide={view?.guide}>
      <PageLead
        kicker="In the room"
        title="Record what was opened, what came back, and what was given."
        body="Hear a line first. “Opening twenty swabs” sets the pack. A drug line stays unconfirmed until you tap Confirm. Replay 20 swabs to see one left in the field. Step the blood-pressure log when you want the numbers on the timeline."
      />
      {error && <p className="error">{error}</p>}
      <div className="layout">
        <section className="sheet">
          <h2>Timeline</h2>
          {events.slice(-12).map((event) => (
            <p key={event.id}>{event.plain || event.event_type}</p>
          ))}
        </section>
        <section className="panel">
          <h2>Count and drugs</h2>
          <label>
            Spoken line
            <input value={line} onChange={(event) => setLine(event.target.value)} />
          </label>
          <div className="row">
            <button onClick={say} disabled={!id}>Hear</button>
            <button className="secondary" onClick={confirm} disabled={heard?.kind !== "drug"}>
              Confirm drug
            </button>
          </div>
          {heard?.kind === "pack" && <p>Pack opened: {heard.event.payload.quantity} {heard.event.payload.item_type}.</p>}
          {heard?.kind === "drug" && (
            <p className="clock">
              {heard.grounded ? "Grounded" : "As heard"} {heard.event.payload.generic || heard.event.payload.name_as_heard}
            </p>
          )}
          <div className="row">
            <button onClick={replay} disabled={!id}>Replay 20 swabs</button>
            <button className="secondary" onClick={manual} disabled={!id}>+1 out</button>
          </div>
          {closing && (
            <p>
              Opened {closing.payload.opened}. Returned {closing.payload.returned}. Unaccounted {closing.payload.unaccounted}.{" "}
              {closing.payload.track_id} last frame {closing.payload.frame_id}.
            </p>
          )}
          <h2>Vitals</h2>
          <Sparkline readings={readings} />
          <div className="row">
            <button className="secondary" onClick={toggleTier}>
              Fact card {tier === 1 ? "on" : "off"}
            </button>
            <span className="clock">
              {tier === 1
                ? "The card only repeats recorded facts."
                : "Decision-tier card is off. Recorded readings still show."}
            </span>
          </div>
          <div className="row">
            <button className="secondary" onClick={() => sim("start")} disabled={!id}>Start</button>
            <button className="secondary" onClick={() => sim("pause")} disabled={!id}>Pause</button>
            <button className="secondary" onClick={() => sim("tick")} disabled={!id}>Step</button>
          </div>
          <label className="clock">
            Seek {Math.round(cursor / 1000)} sec
            <input
              type="range"
              min="0"
              max="240000"
              step="60000"
              value={cursor}
              onChange={(event) => sim("seek", Number(event.target.value))}
            />
          </label>
          {tier === 1 && card && (
            <section className="sheet">
              <h2>Fact card</h2>
              <p className="clock">{BANNER}</p>
              <p>{card.payload.text}</p>
            </section>
          )}
        </section>
      </div>
    </Shell>
  );
}
