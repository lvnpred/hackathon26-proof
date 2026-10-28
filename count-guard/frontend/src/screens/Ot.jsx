import { useEffect, useState } from "react";
import { loadEpisode, send } from "../episode";
import { PageLead, Shell } from "../App";

const BANNER = "Research demo. Not for clinical use.";

function Sparkline({ readings }) {
  if (readings.length < 2) return <p className="empty small">No readings yet. Start the log to fill it.</p>;
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
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Systolic readings" style={{ width: "100%", height: "auto" }}>
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// One timeline row per run of same-type events, so a 19-swab replay reads as one line.
function group(events) {
  const rows = [];
  for (const event of events) {
    const last = rows[rows.length - 1];
    if (last && last.type === event.event_type) last.events.push(event);
    else rows.push({ type: event.event_type, events: [event] });
  }
  return rows;
}

function tagFor(event) {
  const type = event.event_type;
  if (type === "count.closing") {
    return event.payload.unaccounted > 0 ? ["record", "Not back"] : ["ready", "All back"];
  }
  if (type.startsWith("druglog")) return type.endsWith("given") ? ["ready", "Confirmed"] : ["sun", "Heard"];
  if (type.startsWith("vitals")) return ["info", "Reading"];
  if (type.startsWith("count")) return ["ready", "Count"];
  return ["", "Recorded"];
}

export default function Ot() {
  const [view, setView] = useState(null);
  const [line, setLine] = useState("opening twenty swabs");
  const [heard, setHeard] = useState(null);
  const [cursor, setCursor] = useState(0);
  const [error, setError] = useState("");
  const [tier, setTier] = useState(0);
  const [card, setCard] = useState(null);
  const [open, setOpen] = useState({});
  const [playing, setPlaying] = useState(false);

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

  async function run(action) {
    setError("");
    try {
      await action();
    } catch (exc) {
      setError(exc.message);
    }
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
    setPlaying(Boolean(next.sim.playing));
    if (tier === 1) await refreshCard(id);
  }

  const events = view?.events || [];
  const readings = events.filter((event) => event.event_type === "vitals.reading").map((event) => event.payload);
  const latest = readings[readings.length - 1];
  const closing = [...events].reverse().find((event) => event.event_type === "count.closing");
  const missing = closing?.payload.unaccounted || 0;
  const rows = group(events).slice(-10);
  const drug = heard?.kind === "drug" ? heard.event.payload : null;

  return (
    <Shell
      guide={view?.guide}
      status={closing ? (missing > 0 ? { tone: "record", label: `${missing} not back` } : { tone: "ready", label: "All back" }) : null}
    >
      <PageLead
        kicker="In the room"
        title="Record what was opened, what came back, and what was given."
        body="Hear a line first. “Opening twenty swabs” sets the pack. A drug line stays unconfirmed until you tap Confirm. Replay 20 swabs to see one left in the field. Step the blood-pressure log when you want the numbers on the timeline."
      />
      {error && <p className="error" role="alert">{error}</p>}

      <div className="split">
        <section className="narrow">
          <div className="card">
            <p className="label">Hear a line</p>
            <div className="stack" style={{ alignItems: "center" }}>
              <button className="mic" onClick={() => run(say)} disabled={!id} aria-label="Hear the line below">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="9" y="3" width="6" height="11" rx="3" />
                  <path d="M6 11a6 6 0 0 0 12 0" />
                  <path d="M12 17v4" />
                </svg>
                <span>Hear</span>
              </button>
              <span className="muted small">Sends the line below as if it was spoken.</span>
            </div>
            <label className="field">
              Spoken line
              <input value={line} onChange={(event) => setLine(event.target.value)} />
            </label>
            <p className="label" style={{ marginTop: 4 }}>What to say</p>
            <ol className="stack" style={{ margin: 0, paddingLeft: 20 }}>
              <li><b>Opening twenty swabs</b> <span className="muted small">Sets the pack. Once per pack.</span></li>
              <li><b>Ondansetron four milligrams</b> <span className="muted small">A drug line. It waits for Confirm.</span></li>
            </ol>
          </div>
        </section>

        <section className="main">
          <div className="card">
            <div className="row between">
              <p className="label">Swab count{closing ? ` · pack of ${closing.payload.opened}` : ""}</p>
              {closing && <span className={`pill ${missing > 0 ? "record" : "ready"}`}>{missing > 0 ? `${missing} not back` : "All back"}</span>}
            </div>
            {heard?.kind === "pack" && (
              <p>Pack opened: {heard.event.payload.quantity} {heard.event.payload.item_type}.</p>
            )}
            {closing ? (
              <>
                <div className="stats">
                  <div className="stat"><p className="label">Opened</p><b>{closing.payload.opened}</b></div>
                  <div className="stat"><p className="label">Back</p><b>{closing.payload.returned}</b></div>
                  <div className={`stat ${missing > 0 ? "alert" : "clear"}`}><p className="label">Not back</p><b>{missing}</b></div>
                </div>
                {missing > 0 && (
                  <p><b>{closing.payload.track_id}</b> was last seen in the field, frame {closing.payload.frame_id}.</p>
                )}
              </>
            ) : (
              <p className="empty">No closing count yet. Hear the pack, then replay the swabs.</p>
            )}
            <div className="row">
              <button className="primary" onClick={() => run(replay)} disabled={!id}>Replay 20 swabs</button>
              <button onClick={() => run(manual)} disabled={!id}>Add one counted back</button>
            </div>
          </div>

          <div className="card">
            <p className="label">Timeline</p>
            {rows.length === 0 && <p className="empty">Nothing recorded in the room yet. Each line you hear appears here.</p>}
            <div className="timeline">
              {rows.map((row) => {
                const first = row.events[0];
                const [tone, word] = tagFor(row.events[row.events.length - 1]);
                const many = row.events.length > 2;
                const expanded = open[first.id];
                return (
                  <div key={first.id}>
                    <span className="when">{many ? `${row.events.length} lines` : "1 line"}</span>
                    <span className="what">
                      {many && !expanded ? (
                        <>
                          {first.plain || first.event_type} … {row.events[row.events.length - 1].plain}
                          {" "}
                          <button className="quiet" onClick={() => setOpen({ ...open, [first.id]: true })}>
                            Show all {row.events.length}
                          </button>
                        </>
                      ) : (
                        row.events.map((event) => <span key={event.id} style={{ display: "block" }}>{event.plain || event.event_type}</span>)
                      )}
                    </span>
                    <span className={`tag ${tone}`}>{word}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        <section className="narrow">
          <div className="card">
            <p className="label">Drugs given</p>
            {drug ? (
              <div className="say row between">
                <span><b>{drug.generic || drug.name_as_heard}</b> {drug.amount} {drug.unit}</span>
                <span className="tag sun">{heard.grounded ? "Grounded" : "As heard"}</span>
              </div>
            ) : (
              <p className="empty small">Hear a drug line to confirm it here.</p>
            )}
            <button className="block" onClick={() => run(confirm)} disabled={!drug}>
              {drug ? `Confirm ${drug.generic || drug.name_as_heard}` : "Confirm drug"}
            </button>
            <p className="muted small">A drug stays off the sheet until a person confirms it.</p>
          </div>

          <div className="card">
            <p className="label">Blood pressure</p>
            {latest && (
              <p>
                <b className="num" style={{ fontSize: 26, lineHeight: "32px" }}>{latest.systolic}/{latest.diastolic}</b>
                {latest.hr != null && <span className="muted small num"> HR {latest.hr}</span>}
              </p>
            )}
            <Sparkline readings={readings} />
            <div className="row">
              <button onClick={() => run(() => sim("start"))} disabled={!id || playing}>Start</button>
              <button onClick={() => run(() => sim("pause"))} disabled={!id || !playing}>Pause</button>
              <button onClick={() => run(() => sim("tick"))} disabled={!id || !playing}>Next reading</button>
            </div>
            {!playing && <p className="muted small">Start the log, then take the next reading.</p>}
            <label className="field">
              Seek · {Math.round(cursor / 60000)} min of 4
              <input
                type="range"
                min="0"
                max="240000"
                step="60000"
                value={cursor}
                onChange={(event) => run(() => sim("seek", Number(event.target.value)))}
              />
            </label>
            <div className="stack" style={{ borderTop: "1px solid var(--line)", paddingTop: 12 }}>
              <label className="switch">
                Fact card
                <input type="checkbox" checked={tier === 1} onChange={() => run(toggleTier)} />
              </label>
              <p className="muted small">
                {tier === 1
                  ? "The card only repeats recorded facts."
                  : "Decision-tier card is off. Recorded readings still show."}
              </p>
              {tier === 1 && card && (
                <div className="say stack" style={{ gap: 4 }}>
                  <span className="muted small"><b>{BANNER}</b></span>
                  <span className="num"><b>{card.payload.text}</b></span>
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </Shell>
  );
}
