import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Shell } from "../App";

async function send(path, options) {
  const response = await fetch(path, options);
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const error = new Error(body?.detail || response.statusText);
    error.status = response.status;
    throw error;
  }
  return body;
}

export default function Morning() {
  const [tier, setTier] = useState(0);
  const [view, setView] = useState(null);
  const [phrase, setPhrase] = useState("lignocaine two percent, five ml, local infiltration");
  const [draft, setDraft] = useState(null);
  const [card, setCard] = useState("");
  const [error, setError] = useState("");
  const [links, setLinks] = useState(null);

  useEffect(() => {
    send("/morning/tier").then((body) => setTier(body.decision_tier)).catch(() => setTier(0));
  }, []);

  async function play() {
    setError("");
    setCard("");
    setLinks(null);
    const episode = await send("/morning/episodes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: "Synthetic demo, R. Kumar" }),
    });
    const played = await send(`/morning/episodes/${episode.id}/play`, { method: "POST" });
    setView(played);
    if (tier === 1) {
      try {
        const found = await send(`/morning/episodes/${episode.id}/card`);
        setCard(found.card.payload.text);
      } catch {
        setCard("");
      }
    }
  }

  async function toggleTier() {
    const next = await send("/morning/tier", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: tier !== 1 }),
    });
    setTier(next.decision_tier);
    setCard("");
  }

  async function hear() {
    if (!view) return;
    setError("");
    const heard = await send(`/morning/episodes/${view.episode.id}/druglog`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: phrase }),
    });
    setDraft(heard.draft);
  }

  async function confirm() {
    if (!view || !draft) return;
    const next = await send(`/morning/episodes/${view.episode.id}/druglog/${draft.id}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ by: "demo user" }),
    });
    setView(next);
    setDraft(null);
  }

  async function discharge() {
    if (!view) return;
    setError("");
    try {
      setLinks(await send(`/morning/episodes/${view.episode.id}/discharge`, { method: "POST" }));
    } catch (exc) {
      setError(exc.message);
    }
  }

  const sheet = view?.sheet;

  return (
    <Shell>
      <p className="clock">
        One synthetic morning. <Link to="/count">Camera count</Link>
      </p>
      <div className="row" style={{ marginBottom: 12 }}>
        <button onClick={play}>Play the morning</button>
        <button className="secondary" onClick={toggleTier}>
          Fact card {tier === 1 ? "on" : "off"}
        </button>
        <span className="clock">
          {tier === 1
            ? "The card only repeats recorded facts."
            : "Decision-tier card is off. Recorded readings still show."}
        </span>
      </div>
      {error && <p className="error">{error}</p>}
      {card && (
        <section className="sheet">
          <h2>Fact card</h2>
          <p>{card}</p>
        </section>
      )}
      <div className="layout">
        <section className="sheet">
          <h2>Timeline</h2>
          {!view && <p>Play the morning to fill the timeline from the hackathon script.</p>}
          {(view?.events || []).map((event) => (
            <p key={event.id} className="clock">
              {event.tier === "decision" ? "decision · " : ""}
              {event.event_type}
              {event.event_type === "druglog.given" ? ` · ${event.payload.generic || event.payload.name_as_heard}` : ""}
              {event.event_type === "brownbag.med_found" ? ` · ${event.payload.generic || event.payload.name_as_read} ${event.payload.strength}` : ""}
              {event.event_type === "count.closing" ? ` · unaccounted ${event.payload.unaccounted}` : ""}
              {event.event_type === "vitals.reading" ? ` · ${event.payload.systolic}/${event.payload.diastolic}` : ""}
            </p>
          ))}
        </section>
        <section className="panel">
          <h2>Fold</h2>
          {sheet && (
            <>
              <p>OPD: {sheet.opd.map((item) => `${item.generic || item.name_as_read} ${item.strength}`).join(", ") || "none"}</p>
              <p>Confirmed drugs: {sheet.drugs.map((item) => item.generic || item.name_as_heard).join(", ") || "none"}</p>
              <p>
                Count: {sheet.count ? `opened ${sheet.count.opened}, returned ${sheet.count.returned}, unaccounted ${sheet.count.unaccounted}` : "none"}
              </p>
            </>
          )}
          <label>
            Spoken drug line
            <input value={phrase} onChange={(event) => setPhrase(event.target.value)} />
          </label>
          <div className="row">
            <button className="secondary" onClick={hear} disabled={!view}>Hear line</button>
            <button onClick={confirm} disabled={!draft}>Confirm</button>
          </div>
          {draft && (
            <p className="clock">
              {draft.payload.grounded ? "Grounded" : "As heard, not in the demo list"}:{" "}
              {draft.payload.generic || draft.payload.name_as_heard} {draft.payload.amount} {draft.payload.unit}
            </p>
          )}
          <button onClick={discharge} disabled={!view}>Draft discharge</button>
          {links && (
            <p>
              <a href={links.pdf_url}>PDF</a> · <a href={links.ics_url}>Follow-up calendar</a>
            </p>
          )}
        </section>
      </div>
    </Shell>
  );
}
