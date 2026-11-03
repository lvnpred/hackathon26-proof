import { useEffect, useState } from "react";
import TheatreDrugs from "./TheatreDrugs.jsx";
import VitalsStrip from "./VitalsStrip.jsx";
import ContextCard from "./ContextCard.jsx";
import { call } from "../journey.js";
import { own } from "./stepOutcome.js";

export const NO_PANEL = "No theatre record for this patient yet.";
const base = (id) => `/journey/episodes/${id}/theatre`;
const getTheatre = (id) => call(base(id));
const setTier = (id, on, opts) => call(`${base(id)}/tier`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on }) }, opts);
// The card, or null while the tier is off or before a drop (the server says 404). The reply is {banner, card}.
async function getCard(id, opts) {
  try {
    return (await call(`${base(id)}/card`, undefined, opts)).card ?? null;
  } catch (exc) {
    if (exc.status === 404) return null;
    throw exc;
  }
}

// The theatre chart's three panels (spec §6.4). They read their own record (GET …/theatre) and reload whenever
// the chart's timeline grows; writes go through the chart's act/upload, so the clock and the view move as usual.
export default function TheatrePanels({ episodeId, view, role, by, busy, act, upload, ask }) {
  const [panel, setPanel] = useState(null);
  const [card, setCard] = useState(null);
  const [problem, setProblem] = useState("");
  const [seq, setSeq] = useState(0);
  const [read, setRead] = useState(false); // the first read answered: a missing panel then says so, never "Reading…"
  const version = view.timeline?.length || 0;

  useEffect(() => {
    if (!episodeId) return undefined;
    let live = true;
    (async () => {
      try {
        const next = await getTheatre(episodeId);
        const shown = next.tier ? await getCard(episodeId) : null;
        if (!live) return;
        setPanel(next || null);
        setCard(shown);
        setProblem("");
      } catch (exc) {
        if (live && exc.status !== 404) setProblem(exc.message);
        if (live && exc.status === 404) setPanel(null);
      } finally {
        if (live) setRead(true);
      }
    })();
    return () => { live = false; };
  }, [episodeId, version, seq]);

  // Turning the tier on reads the card (Spark words it); ContextCard runs this as its step, so a failure shows there.
  // The panels reload once the tier is set, even when reading the card then fails.
  async function toggleTier(on, opts) {
    await setTier(episodeId, on, opts);
    try {
      const shown = on ? await getCard(episodeId, opts) : null;
      setCard(shown);
      return { card: shown };
    } finally {
      setSeq((n) => n + 1);
    }
  }

  // The next reading. With `opts` (the strip's step, run only when the panel says the card is due) the card it wrote
  // is read back, so the step says how it was worded. Without, a failure is the chart's fault.
  async function nextReading(opts) {
    const view = await act("/theatre/vitals/step", {}, undefined, opts ? own(opts) : undefined);
    if (!view || !opts) return { view, card: null };
    const shown = await getCard(episodeId, opts);
    return { view, card: shown && shown.id !== card?.id ? shown : null };
  }

  if (problem && !panel) return <p className="note small" role="alert">{problem}</p>;
  if (!panel) return <p className="empty small">{read || !episodeId ? NO_PANEL : "Reading the theatre record…"}</p>;
  return (
    <>
      <TheatreDrugs episodeId={episodeId} panel={panel} role={role} by={by} busy={busy} act={act} upload={upload} ask={ask} acts={view?.acts} />
      <VitalsStrip panel={panel} busy={busy} onNext={nextReading} />
      <ContextCard tier={panel.tier} card={card} due={panel.card_on_tier} busy={busy} onTier={toggleTier} />
      {problem && <p className="note small" role="alert">{problem}</p>}
    </>
  );
}
