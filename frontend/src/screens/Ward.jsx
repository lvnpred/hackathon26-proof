import { useEffect, useState } from "react";
import { loadEpisode, send } from "../episode";
import { PageLead, Shell } from "../App";

export default function Ward() {
  const [view, setView] = useState(null);
  const [links, setLinks] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    loadEpisode().then(setView).catch((exc) => setError(exc.message));
  }, []);

  async function draft() {
    setError("");
    try {
      const body = await send(`/morning/episodes/${view.episode.id}/discharge`, { method: "POST" });
      setLinks(body);
      setView(await send(`/morning/episodes/${view.episode.id}`));
    } catch (exc) {
      setError(exc.message);
    }
  }

  const sheet = links?.sheet || view?.sheet;

  return (
    <Shell guide={view?.guide}>
      <PageLead
        kicker="After the room"
        title="The sheet is only what was recorded."
        body="Medicines from the strips, drugs you confirmed, and the closing count. The fact card is left off this sheet. Draft it when the theatre steps are done."
      />
      {error && <p className="error">{error}</p>}
      <section className="sheet">
        <h2>Sheet</h2>
        <p>{sheet?.narrative || "Play the theatre count, then draft this sheet."}</p>
        <h2>OPD medicines</h2>
        {(sheet?.opd || []).length === 0 && <p>None recorded.</p>}
        {(sheet?.opd || []).map((item, index) => (
          <p key={index}>{item.generic || item.name_as_read} {item.strength}</p>
        ))}
        <h2>Drugs recorded in the room</h2>
        {(sheet?.drugs || []).length === 0 && <p>None confirmed.</p>}
        {(sheet?.drugs || []).map((item, index) => (
          <p key={index}>{item.generic || item.name_as_heard} {item.amount} {item.unit} {item.route}</p>
        ))}
        <h2>Count</h2>
        {sheet?.count ? (
          <p>
            Opened {sheet.count.opened}. Returned {sheet.count.returned}. Unaccounted {sheet.count.unaccounted}. {sheet.count.detail}
          </p>
        ) : (
          <p>No closing count yet.</p>
        )}
        <button onClick={draft} disabled={!view}>Draft discharge</button>
        {links && (
          <p>
            <a href={links.pdf_url}>PDF</a> · <a href={links.ics_url}>Follow-up calendar</a>
          </p>
        )}
      </section>
    </Shell>
  );
}
