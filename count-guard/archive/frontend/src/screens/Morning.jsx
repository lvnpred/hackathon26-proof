import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PageLead, Shell } from "../App";

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

function eventLine(event) {
  const type = event.event_type.replace(/[._]/g, " ");
  if (event.event_type === "druglog.given") return `${type} · ${event.payload.generic || event.payload.name_as_heard}`;
  if (event.event_type === "brownbag.med_found") return `${type} · ${event.payload.generic || event.payload.name_as_read} ${event.payload.strength}`;
  if (event.event_type === "count.closing") return `${type} · unaccounted ${event.payload.unaccounted}`;
  if (event.event_type === "vitals.reading") return `${type} · ${event.payload.systolic}/${event.payload.diastolic}`;
  return type;
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
    <Shell subtitle="One synthetic morning, played from the script" status={{ tone: "info", label: "Scripted demo" }}>
      <PageLead
        kicker="Whole morning"
        title="Play one synthetic morning."
        body="The script fills the timeline from strips to the closing count. The camera count is a separate screen."
      />
      <div className="row">
        <button className="primary" onClick={play}>Play the morning</button>
        <Link to="/count">Camera count</Link>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split">
        <section className="main">
          <div className="card">
            <p className="label">Timeline</p>
            {!view && <p className="empty">Play the morning to fill the timeline from the hackathon script.</p>}
            <div className="timeline">
              {(view?.events || []).map((event, index) => (
                <div key={event.id}>
                  <span className="when">{event.tier === "decision" ? "Decision" : `#${index + 1}`}</span>
                  <span className="what">{eventLine(event)}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
        <aside className="side">
          <div className="card">
            <label className="switch">
              Fact card
              <input type="checkbox" checked={tier === 1} onChange={toggleTier} />
            </label>
            <p className="small muted">
              {tier === 1
                ? "The card only repeats recorded facts."
                : "Decision-tier card is off. Recorded readings still show."}
            </p>
            {card && (
              <div className="card sunk">
                <p className="label">Fact card</p>
                <p className="num"><b>{card}</b></p>
              </div>
            )}
          </div>
          <div className="card">
            <p className="label">Fold</p>
            {!sheet && <p className="empty">The fold appears after the morning plays.</p>}
            {sheet && (
              <>
                <p>OPD: {sheet.opd.map((item) => `${item.generic || item.name_as_read} ${item.strength}`).join(", ") || "none"}</p>
                <p>Confirmed drugs: {sheet.drugs.map((item) => item.generic || item.name_as_heard).join(", ") || "none"}</p>
                <p>
                  Count: {sheet.count ? `opened ${sheet.count.opened}, returned ${sheet.count.returned}, unaccounted ${sheet.count.unaccounted}` : "none"}
                </p>
              </>
            )}
            <label className="field">
              Spoken drug line
              <input value={phrase} onChange={(event) => setPhrase(event.target.value)} />
            </label>
            <div className="row">
              <button onClick={hear} disabled={!view}>Hear line</button>
              <button onClick={confirm} disabled={!draft}>Confirm</button>
            </div>
            {draft && (
              <p className="small">
                <span className={draft.payload.grounded ? "tag ready" : "tag"}>
                  {draft.payload.grounded ? "Grounded" : "As heard, not in the demo list"}
                </span>{" "}
                {draft.payload.generic || draft.payload.name_as_heard} {draft.payload.amount} {draft.payload.unit}
              </p>
            )}
            <button onClick={discharge} disabled={!view}>Draft discharge</button>
            {links && (
              <p>
                <a href={links.pdf_url}>PDF</a> · <a href={links.ics_url}>Follow-up calendar</a>
              </p>
            )}
          </div>
        </aside>
      </div>
    </Shell>
  );
}
