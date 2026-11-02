import { useEffect, useState } from "react";
import TheatreDrugs from "./TheatreDrugs.jsx";
import VitalsStrip from "./VitalsStrip.jsx";
import ContextCard from "./ContextCard.jsx";
import { call } from "../journey.js";

const base = (id) => `/journey/episodes/${id}/theatre`;
const getTheatre = (id) => call(base(id));
const setTier = (id, on) => call(`${base(id)}/tier`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ on }) });
// The card, or null while the tier is off or before a drop (the server says 404).
async function getCard(id) {
  try {
    return await call(`${base(id)}/card`);
  } catch (exc) {
    if (exc.status === 404) return null;
    throw exc;
  }
}

// The theatre chart's three panels (spec §6.4). They read their own record (GET …/theatre) and reload whenever
// the chart's timeline grows; writes go through the chart's act/upload, so the clock and the view move as usual.
export default function TheatrePanels({ episodeId, view, role, by, busy, act, upload }) {
  const [panel, setPanel] = useState(null);
  const [card, setCard] = useState(null);
  const [problem, setProblem] = useState("");
  const [seq, setSeq] = useState(0);
  const version = view.timeline?.length || 0;

  useEffect(() => {
    if (!episodeId) return undefined;
    let live = true;
    (async () => {
      try {
        const next = await getTheatre(episodeId);
        const shown = next.tier ? await getCard(episodeId) : null;
        if (!live) return;
        setPanel(next);
        setCard(shown);
        setProblem("");
      } catch (exc) {
        if (live) setProblem(exc.message);
      }
    })();
    return () => { live = false; };
  }, [episodeId, version, seq]);

  async function toggleTier(on) {
    try {
      await setTier(episodeId, on);
      setSeq((n) => n + 1);
    } catch (exc) {
      setProblem(exc.message);
    }
  }

  if (!panel) return problem ? <p className="note small" role="alert">{problem}</p> : null;
  return (
    <>
      <TheatreDrugs episodeId={episodeId} panel={panel} role={role} by={by} busy={busy} act={act} upload={upload} />
      <VitalsStrip panel={panel} busy={busy} act={act} />
      <ContextCard tier={panel.tier} card={card} busy={busy} onTier={toggleTier} />
      {problem && <p className="note small" role="alert">{problem}</p>}
    </>
  );
}
