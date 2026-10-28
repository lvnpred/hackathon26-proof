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
      {error && <p className="error" role="alert">{error}</p>}
      <div className="split">
        <section className="main">
          <article className="paper">
            <header className="paper-head">
              <p className="paper-letter">Count Guard · research demo</p>
              <h2 className="paper-title">Discharge sheet</h2>
            </header>
            <section>
              <p>{sheet?.narrative || "Play the theatre count, then draft this sheet."}</p>
            </section>
            <section>
              <h3>OPD medicines</h3>
              {(sheet?.opd || []).length === 0 && <p className="blank">None recorded.</p>}
              {(sheet?.opd || []).map((item, index) => (
                <p key={index}>{item.generic || item.name_as_read} {item.strength}</p>
              ))}
            </section>
            <section>
              <h3>Drugs recorded in the room</h3>
              {(sheet?.drugs || []).length === 0 && <p className="blank">None confirmed.</p>}
              {(sheet?.drugs || []).map((item, index) => (
                <p key={index}>{item.generic || item.name_as_heard} {item.amount} {item.unit} {item.route}</p>
              ))}
            </section>
            <section>
              <h3>Count</h3>
              {sheet?.count ? (
                <p className="num">
                  Opened {sheet.count.opened}. Returned {sheet.count.returned}. Unaccounted {sheet.count.unaccounted}. {sheet.count.detail}
                </p>
              ) : (
                <p className="blank">No closing count yet.</p>
              )}
            </section>
          </article>
          <div className="row">
            <button className="primary" onClick={draft} disabled={!view}>Draft discharge</button>
            {links && (
              <p>
                <a href={links.pdf_url}>PDF</a> · <a href={links.ics_url}>Follow-up calendar</a>
              </p>
            )}
          </div>
        </section>
      </div>
    </Shell>
  );
}
